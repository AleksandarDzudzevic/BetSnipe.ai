"""
Admiral Bet scraper for BetSnipe.ai v2.0

Scrapes odds from Admiral Bet Serbia API.
Uses structured bets[] array with betTypeId, betTypeName, and betOutcomes[].
Each outcome has: name, odd, sBV (special bet value = margin), orderNo.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)

# ============================================================================
# SELECTION NORMALIZATION CONSTANTS
# ============================================================================

# Bet types where standalone single digits (0-5) → T-prefix (exact goal count)
_GOAL_EXACT_BTS = frozenset({25, 27, 28, 29, 30, 31, 32, 33, 34})

# Combo BTs needing I/II/Tim/GG/NG normalization
_COMBO_BTS = frozenset({
    35, 36, 38, 39, 40, 41, 44, 45, 46,
    114, 115, 116, 119, 120, 121, 122, 123, 124,
})

# BTs where Tim1/Tim2 standalone = first scorer
_FIRST_GOAL_BTS = frozenset({36, 122})

# BTs where plain goal values need FT: prefix when H1:/H2: parts exist
_FT_PREFIX_BTS = frozenset({35, 119, 120})

# Regex for goal value with half suffix: digits/ranges followed by I or II
_GOAL_II_RE = re.compile(r'^([\d][\d+\-]*)II$')
_GOAL_I_RE = re.compile(r'^([\d][\d+\-]*)I$')
_TEAM_SUFFIX_RE = re.compile(r'^(.+?)(?:Tim([12])|T([12]))$')
_PLAIN_GOAL_RE = re.compile(r'^[\d][\d+\-]*$')


def _normalize_part(part: str, bt: int) -> str:
    """Normalize a single token of a combo selection.

    Converts Admiral's naming convention to cross-bookmaker standard:
      - I/II suffix on goal values → H1:/H2: prefix
      - Tim1/T1 → H (home), Tim2/T2 → A (away)
      - GGI/GGII/NGI/NGII → GG_H1/GG_H2/NG_H1/NG_H2
      - I1/IX/I2 → 1_H1/X_H1/2_H1 (half result prefix)
      - II1/IIX/II2 → 1_H2/X_H2/2_H2
      - "I pol"/"II pol"/"I=II" → H1>H2/H1<H2/H1=H2
    """
    p = part.strip()
    if not p:
        return p

    # --- Half comparison phrases ---
    if p == 'I pol':
        return 'H1>H2'
    if p == 'II pol':
        return 'H1<H2'
    if p == 'I=II':
        return 'H1=H2'

    # --- Half result prefix (check II before I) ---
    m = re.match(r'^II([1X2])$', p)
    if m:
        return m.group(1) + '_H2'
    m = re.match(r'^I([1X2])$', p)
    if m:
        return m.group(1) + '_H1'

    # --- BTTS/NG with half suffix ---
    if p == 'GGII':
        return 'GG_H2'
    if p == 'GGI':
        return 'GG_H1'
    if p == 'NGII':
        return 'NG_H2'
    if p == 'NGI':
        return 'NG_H1'

    # --- Standalone team references ---
    if p in ('Tim1', 'Tim2'):
        if bt in _FIRST_GOAL_BTS:
            return 'H_first' if p == 'Tim1' else 'A_first'
        return 'H' if p == 'Tim1' else 'A'

    # --- Team suffix: xxxTim1/xxxT1 → Hxxx ---
    m = _TEAM_SUFFIX_RE.match(p)
    if m:
        val = m.group(1)
        team_num = m.group(2) or m.group(3)
        return ('H' if team_num == '1' else 'A') + val

    # --- Goal value with half suffix: 0-1II → H2:0-1, 1+I → H1:1+ ---
    m = _GOAL_II_RE.match(p)
    if m:
        return 'H2:' + m.group(1)
    m = _GOAL_I_RE.match(p)
    if m:
        return 'H1:' + m.group(1)

    return p


def _normalize_selection(name: str, bt: int) -> str:
    """Normalize Admiral's raw selection name to cross-bookmaker standard format.

    Handles all bet type-specific conversions:
      - Goal range BTs: standalone digit → T-prefix (e.g. "1" → "T1")
      - HT/FT simple: dash → slash (e.g. "1-1" → "1/1")
      - HT/FT combos: smart dash→slash in HT/FT part + normalize goal part
      - OR combos (bt114): v → | separator
      - General combos: I/II/Tim/GG/NG normalization via _normalize_part
      - bt36: swap parts to match result-first convention
    """
    name = name.strip()
    if not name:
        return name

    # --- Simple HT/FT (bt24, bt37, bt113): dash→slash everywhere ---
    if bt in (24, 37, 113):
        return name.replace('-', '/')

    # --- Goal range BTs: standalone digit → T-prefix ---
    if bt in _GOAL_EXACT_BTS:
        m = re.match(r'^(\d)$', name)
        if m:
            return 'T' + m.group(1)
        return name

    # --- bt124 (HT/FT OR combos): "1-1vX-X" → "1/1|X/X" ---
    if bt == 124:
        parts = re.split(r'[vV]', name)
        return '|'.join(p.strip().replace('-', '/') for p in parts)

    # --- bt44, bt45 (HT/FT + goals combo): smart dash→slash + normalize ---
    if bt in (44, 45):
        if '&' in name:
            idx = name.index('&')
            htft = name[:idx].strip().replace('-', '/')
            goal = _normalize_part(name[idx + 1:].strip(), bt)
            return htft + '&' + goal
        return name.replace('-', '/')

    # --- bt114 (OR combos): v → | + normalize parts ---
    if bt == 114:
        parts = re.split(r'v', name)
        return '|'.join(_normalize_part(p, bt) for p in parts)

    # --- bt36 (first goal + result): normalize + swap to result-first ---
    if bt == 36:
        parts = re.split(r'\s*&\s*', name)
        if len(parts) == 2:
            norm = [_normalize_part(p, bt) for p in parts]
            # Admiral puts scorer first, standard puts result first
            if norm[0] in ('H_first', 'A_first') and norm[1] in ('1', 'X', '2'):
                norm.reverse()
            return '&'.join(norm)
        return _normalize_part(name, bt)

    # --- General combo BTs ---
    if bt in _COMBO_BTS:
        # " v " (with spaces) = distinct separator (e.g. bt46 XOR-like)
        if ' v ' in name:
            parts = name.split(' v ')
            return ' v '.join(_normalize_part(p, bt) for p in parts)
        # | separator
        if '|' in name:
            parts = name.split('|')
            return '|'.join(_normalize_part(p, bt) for p in parts)
        # & separator
        if '&' in name:
            parts = name.split('&')
            normalized = [_normalize_part(p, bt) for p in parts]
            # For bt35/119/120: add FT: prefix to plain goal values
            # when other parts have H1:/H2: prefix (e.g. "H1:1+&2+" → "H1:1+&FT:2+")
            if bt in _FT_PREFIX_BTS:
                has_half = any(p.startswith(('H1:', 'H2:')) for p in normalized)
                if has_half:
                    normalized = [
                        'FT:' + p if _PLAIN_GOAL_RE.match(p) else p
                        for p in normalized
                    ]
            return '&'.join(normalized)
        # Single part (no separator)
        return _normalize_part(name, bt)

    # --- No normalization needed (bt23, bt79, bt117, bt118, corners, cards) ---
    return name

# Admiral sport ID to internal sport ID mapping
SPORT_MAPPING = {
    1: 1,    # Football
    2: 2,    # Basketball
    3: 3,    # Tennis
    4: 4,    # Hockey
    17: 5,   # Table Tennis
}

INTERNAL_TO_ADMIRAL = {v: k for k, v in SPORT_MAPPING.items()}

# ============================================================================
# BET TYPE DISPATCH MAPS
# Format: admiral_betTypeId -> (internal_bet_type_id, parser_type)
# Parser types: '3way', '2way', 'ou', 'hc2', 'hc3', 'sel', 'sel_htft'
#   sel      = raw selection names (no conversion)
#   sel_htft = converts "-" to "/" for HT/FT-style markets
# ============================================================================

FOOTBALL_MAP = {
    # === Core result markets ===
    135: (2, '3way'),       # Konacan ishod (1X2)
    148: (3, '3way'),       # 1.pol - 1X2
    149: (4, '3way'),       # 2.pol - 1X2
    152: (13, '3way'),      # Dupla sansa (Double Chance)
    147: (20, '3way'),      # 1.pol - Dupla sansa (H1 DC)
    150: (75, '3way'),      # 2.pol - Dupla sansa (H2 DC)
    154: (14, '2way'),      # Draw No Bet
    724: (21, '2way'),      # 1.pol - Draw no bet (H1 DNB)
    725: (76, '2way'),      # 2.pol - Draw no bet (H2 DNB)
    151: (8, '2way'),       # Oba tima daju gol (BTTS)
    165: (15, '2way'),      # Par/nepar (Odd/Even)
    232: (77, '2way'),      # 1.pol - Par/nepar (H1 Odd/Even)
    726: (78, '2way'),      # 2.pol - Par/nepar (H2 Odd/Even)
    55:  (19, '3way'),      # Poluvreme sa vise golova
    153: (17, '2way'),      # Pobeda sa nulom (Win to nil)
    174: (16, '2way'),      # Dupla pobeda (Double win)
    182: (99, '2way'),      # Dupla pobeda sa nulom (Double win to nil)
    166: (18, '3way'),      # Prvi daje gol (First goal)
    760: (89, '2way'),      # Poslednji daje gol (Last goal)
    1009: (100, '3way'),    # 1.pol - Prvi daje gol (H1 first goal)
    1011: (101, '3way'),    # 2.pol - Prvi daje gol (H2 first goal)
    1099: (102, '2way'),    # Pobeda iz preokreta (Win from behind)
    955: (103, '2way'),     # Domacin pobedjuje bar u jednom pol (Team1 wins half)
    956: (104, '2way'),     # Gost pobedjuje bar u jednom pol (Team2 wins half)
    # === Total O/U markets ===
    137: (5, 'ou'),         # Ukupno golova (Total)
    143: (6, 'ou'),         # 1.pol - Ukupno golova (Total H1)
    144: (7, 'ou'),         # 2.pol - Ukupno golova (Total H2)
    161: (48, 'ou'),        # Domacin ukupno gol (Team 1 total)
    162: (49, 'ou'),        # Gost ukupno gol (Team 2 total)
    141: (51, 'ou'),        # 1.p - Domacin ukupno (Team 1 H1 total)
    142: (52, 'ou'),        # 1.p - Gost ukupno (Team 2 H1 total)
    126: (81, 'ou'),        # 2.pol - Domacin ukupno gol (Team 1 H2 total)
    129: (82, 'ou'),        # 2.pol - Gost ukupno gol (Team 2 H2 total)
    # === Handicap markets ===
    160: (9, 'hc3'),        # Hendikep 1X2 (3-way handicap)
    212: (80, 'hc3'),       # 1.pol - Hendikep 1X2 (H1 3-way handicap)
    # === Correct score / HT-FT selection markets ===
    170: (23, 'sel'),       # Tacan rezultat (Correct score)
    184: (79, 'sel'),       # 1.pol - Tacan rezultat (H1 correct score)
    1179: (117, 'sel'),     # Tacan rezultat bilo kada (Correct score anytime)
    1180: (118, 'sel'),     # Tacan rezultat kombinacije (Correct score combos)
    140: (24, 'sel_htft'),  # Poluvreme - kraj (HT/FT)
    171: (113, 'sel_htft'), # Poluvreme - kraj NE (HT/FT NOT)
    183: (37, 'sel_htft'),  # Poluvreme - kraj dupla sansa (HT/FT DC)
    167: (36, 'sel'),       # Prvi daje gol i kon ishod (First goal + result)
    1170: (40, 'sel'),      # Kon ishod i pol sa vise golova (Result + half goals)
    1223: (116, 'sel'),     # Dupla sansa i pol sa vise golova (DC + half combo)
    1552: (115, 'sel'),     # Oba tima daju gol i pol sa vise golova (BTTS+half)
    # === Goal range selection markets ===
    138: (25, 'sel'),       # Broj golova (Total goals range)
    1146: (29, 'sel'),      # 1.pol - Broj golova (H1 goals range)
    1147: (30, 'sel'),      # 2.pol - Broj golova (H2 goals range)
    1148: (27, 'sel'),      # Domacin broj golova (Team 1 goals)
    1151: (28, 'sel'),      # Gost broj golova (Team 2 goals)
    307: (31, 'sel'),       # 1.pol - Domacin broj golova (Team 1 goals H1)
    308: (32, 'sel'),       # 1.pol - Gost broj golova (Team 2 goals H1)
    1149: (33, 'sel'),      # 2.pol - Domacin broj golova (Team 1 goals H2)
    1152: (34, 'sel'),      # 2.pol - Gost broj golova (Team 2 goals H2)
    1173: (121, 'sel'),     # Pobedjuje sa razlikom (Win by margin)
    1174: (122, 'sel'),     # Prvi daje gol i uk golova (First goal + total)
    # === Combo selection markets (result + goals) ===
    1154: (38, 'sel'),      # Domacin kombinacije (Team1 win + goals combos)
    1155: (38, 'sel'),      # Gost kombinacije (Team2 win + goals combos)
    1161: (35, 'sel'),      # Ukupno golova kombinacije (Goals H1&H2 combo)
    1150: (119, 'sel'),     # Domacin ukupno gol kombinacije (Team1 H1&H2)
    1153: (120, 'sel'),     # Gost ukupno gol kombinacije (Team2 H1&H2)
    # === DC / draw combo markets ===
    1162: (41, 'sel'),      # 1X kombinacije (DC 1X combos)
    1163: (41, 'sel'),      # X2 kombinacije (DC X2 combos)
    1164: (41, 'sel'),      # 12 kombinacije (DC 12 combos)
    1165: (39, 'sel'),      # X kombinacije (Draw combos)
    # === HT/FT combo markets ===
    1156: (44, 'sel_htft'),  # 1-1 kombinacije (HT/FT 1-1 + goals)
    1157: (44, 'sel_htft'),  # X-1 kombinacije (HT/FT X-1 + goals)
    1158: (44, 'sel_htft'),  # 2-2 kombinacije (HT/FT 2-2 + goals)
    1159: (44, 'sel_htft'),  # X-2 kombinacije (HT/FT X-2 + goals)
    1160: (44, 'sel_htft'),  # 1-2, 2-1 kombinacije (HT/FT 1-2/2-1 + goals)
    309: (45, 'sel_htft'),   # X-X kombinacije (HT/FT X-X combos)
    1171: (124, 'sel_htft'), # Poluvreme - kraj kombinacije (HT/FT OR combos)
    # === BTTS combo markets ===
    1166: (46, 'sel'),      # Oba tima daju gol i golovi (BTTS + goals)
    1167: (46, 'sel'),      # Oba tima daju gol kombinacije (BTTS combos)
    1172: (123, 'sel'),     # Poluvreme i oba tima daju gol (HT result + BTTS)
    # === OR / misc combo markets ===
    1168: (114, 'sel'),     # Ili kombinacije (OR combinations)
    # === Corner markets ===
    244: (83, '3way'),      # Korneri - 1X2
    250: (93, '3way'),      # 1.p - Korneri 1X2
    272: (84, 'ou'),        # Ukupno kornera (Total corners)
    273: (94, 'ou'),        # 1.p - Ukupno kornera (H1 total corners)
    274: (105, '3way'),     # Prvi korner (First corner)
    275: (86, '2way'),      # Korneri par/nepar (Corners odd/even)
    276: (96, '2way'),      # 1.p - Korneri par/nepar (H1 corners odd/even)
    277: (85, 'hc2'),       # Hendikep kornera (Corner handicap)
    278: (95, 'hc2'),       # 1.p - Hendikep kornera (H1 corner handicap)
    279: (109, 'sel'),      # Domacin - broj kornera (Team1 corner range)
    280: (110, 'sel'),      # Gost - broj kornera (Team2 corner range)
    1028: (107, 'sel'),     # Broj kornera (Corner count range)
    # === Card markets ===
    281: (87, '3way'),      # Kartoni - 1X2
    282: (97, '3way'),      # 1.p - Kartoni 1X2
    283: (88, 'ou'),        # Ukupno kartona (Total cards)
    284: (98, 'ou'),        # 1.p - Ukupno kartona (H1 total cards)
    285: (111, 'sel'),      # Domacin - broj kartona (Team1 card range)
    286: (112, 'sel'),      # Gost - broj kartona (Team2 card range)
    287: (90, '2way'),      # Crveni karton na mecu (Red card)
    290: (106, '3way'),     # Prvi karton (First card)
    # === Penalty markets ===
    1181: (91, '2way'),     # Dosudjen penal (Penalty awarded)
    1182: (92, '2way'),     # Realizovan penal (Penalty scored)
}

BASKETBALL_MAP = {
    186: (1, '2way'),      # Pobednik (Winner incl. OT)
    189: (2, '3way'),      # Konacan ishod (Regulation 1X2)
    148: (3, '3way'),      # 1.pol - 1X2
    149: (4, '3way'),      # 2.pol - 1X2
    302: (15, '2way'),     # Par/Nepar (Odd/Even +OT)
    154: (14, '2way'),     # Draw No Bet
    213: (10, 'ou'),       # Ukupno (+OT) (Total)
    197: (6, 'ou'),        # 1.p - Ukupno (H1 Total)
    191: (9, 'hc2'),       # Hendikep (+OT)
    196: (50, 'hc2'),      # 1.p - Hendikep
    728: (48, 'ou'),       # Domacin ukupno (+OT)
    729: (49, 'ou'),       # Gost ukupno (+OT)
    141: (51, 'ou'),       # 1.p - Domacin ukupno
    142: (52, 'ou'),       # 1.p - Gost ukupno
    140: (24, 'sel_htft'),  # Poluvreme - kraj (HT/FT)
}

TENNIS_MAP = {
    454: (1, '2way'),      # Pobednik (Winner)
    214: (57, '2way'),     # 1.set - Pobednik
    221: (56, 'hc2'),      # Hendikep setova (Set Handicap)
    210: (58, 'hc2'),      # 1.set - Hendikep gemova
    187: (5, 'ou'),        # Ukupno gemova (Total Games)
    223: (65, 'sel'),      # Tacan rezultat (Exact Sets)
    188: (64, 'sel'),      # 1.set - Kraj (S1 + Match)
    663: (15, '2way'),     # Par/Nepar gemova
}

HOCKEY_MAP = {
    135: (2, '3way'),      # Konacan ishod (1X2)
    237: (3, '3way'),      # 1.per - 1X2
    238: (4, '3way'),      # 2.per - 1X2
    151: (8, '2way'),      # Oba tima daju gol (BTTS)
    152: (13, '3way'),     # Dupla sansa
    154: (14, '2way'),     # Draw No Bet
    137: (5, 'ou'),        # Ukupno golova (Total)
    240: (6, 'ou'),        # 1.per - Ukupno golova
    161: (48, 'ou'),       # Domacin ukupno gol
    162: (49, 'ou'),       # Gost ukupno gol
    788: (9, 'hc2'),       # Hendikep
    763: (23, 'sel'),      # Tacan rezultat (Correct Score)
    165: (15, '2way'),     # Par/nepar
}

TABLE_TENNIS_MAP = {
    454: (1, '2way'),      # Pobednik (Winner)
    243: (5, 'ou'),        # Ukupno poena (Total Points)
}

SPORT_MAPS = {
    1: FOOTBALL_MAP,
    2: BASKETBALL_MAP,
    3: TENNIS_MAP,
    4: HOCKEY_MAP,
    5: TABLE_TENNIS_MAP,
}


class AdmiralScraper(BaseScraper):
    """
    Scraper for Admiral Bet Serbia.

    API endpoints:
    - webTree: Get list of sports/regions/competitions
    - getWebEventsSelections: Get matches for a competition
    - betsAndGroups: Get odds for a specific match
    """

    def __init__(self):
        super().__init__(bookmaker_id=4, bookmaker_name="Admiral")
        self._competitions_cache: Dict[int, List[Dict]] = {}

    def get_base_url(self) -> str:
        return "https://srboffer.admiralbet.rs/api/offer"

    def get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/utf8+json, application/json;q=0.9, text/plain;q=0.8, */*;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Host": "srboffer.admiralbet.rs",
            "Language": "sr-Latn",
            "Officeid": "138",
            "Origin": "https://admiralbet.rs",
            "Referer": "https://admiralbet.rs/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }

    def get_supported_sports(self) -> List[int]:
        return [1, 2, 3, 4, 5]

    # ========================================================================
    # Generic parsers for different market types
    # ========================================================================

    @staticmethod
    def _parse_3way(outcomes: List[Dict], bt: int) -> List[ScrapedOdds]:
        """Parse a 3-way market (1, X, 2) with no margin."""
        if len(outcomes) < 3:
            return []
        try:
            sorted_oc = sorted(outcomes, key=lambda x: x.get("orderNo", 0))
            return [ScrapedOdds(
                bet_type_id=bt,
                odd1=float(sorted_oc[0].get("odd", 0)),
                odd2=float(sorted_oc[1].get("odd", 0)),
                odd3=float(sorted_oc[2].get("odd", 0)),
            )]
        except (ValueError, TypeError, IndexError):
            return []

    @staticmethod
    def _parse_2way(outcomes: List[Dict], bt: int) -> List[ScrapedOdds]:
        """Parse a 2-way market (1, 2) with no margin."""
        if len(outcomes) < 2:
            return []
        try:
            sorted_oc = sorted(outcomes, key=lambda x: x.get("orderNo", 0))
            return [ScrapedOdds(
                bet_type_id=bt,
                odd1=float(sorted_oc[0].get("odd", 0)),
                odd2=float(sorted_oc[1].get("odd", 0)),
            )]
        except (ValueError, TypeError, IndexError):
            return []

    @staticmethod
    def _parse_over_under(outcomes: List[Dict], bt: int) -> List[ScrapedOdds]:
        """Parse O/U market: group by sBV, identify under/over by name."""
        by_margin: Dict[float, Dict[str, float]] = {}
        for oc in outcomes:
            try:
                margin = float(oc.get("sBV", 0))
                name = oc.get("name", "").lower().strip()
                odd = float(oc.get("odd", 0))
                if margin not in by_margin:
                    by_margin[margin] = {}
                if "manj" in name or "under" in name:
                    by_margin[margin]["under"] = odd
                elif "vi" in name or "over" in name:
                    by_margin[margin]["over"] = odd
            except (ValueError, TypeError):
                continue

        result = []
        for margin, odds in sorted(by_margin.items()):
            if "under" in odds and "over" in odds:
                result.append(ScrapedOdds(
                    bet_type_id=bt,
                    odd1=odds["under"],
                    odd2=odds["over"],
                    margin=margin,
                ))
        return result

    @staticmethod
    def _parse_handicap_2way(outcomes: List[Dict], bt: int) -> List[ScrapedOdds]:
        """Parse 2-way handicap: group by sBV, identify team1/team2.

        NOTE: Uses raw sBV sign from API.  MaxBet/Merkur negate the sign
        for 2-way HC (positive = home advantage).  If Admiral's API uses
        the opposite convention, this may cause cross-bookmaker sign
        inconsistency for basketball/hockey handicaps.
        """
        by_margin: Dict[float, Dict[str, float]] = {}
        for oc in outcomes:
            try:
                margin = float(oc.get("sBV", 0))
                name = oc.get("name", "").strip()
                odd = float(oc.get("odd", 0))
                if margin not in by_margin:
                    by_margin[margin] = {}
                if name == "1":
                    by_margin[margin]["t1"] = odd
                elif name == "2":
                    by_margin[margin]["t2"] = odd
            except (ValueError, TypeError):
                continue

        result = []
        for margin, odds in sorted(by_margin.items()):
            if "t1" in odds and "t2" in odds:
                result.append(ScrapedOdds(
                    bet_type_id=bt,
                    odd1=odds["t1"],
                    odd2=odds["t2"],
                    margin=margin,
                ))
        return result

    @staticmethod
    def _parse_handicap_3way(outcomes: List[Dict], bt: int) -> List[ScrapedOdds]:
        """Parse 3-way handicap: group by sBV, identify 1/X/2.

        Football (European HC): raw sBV sign, consistent with MaxBet/Merkur.
        """
        by_margin: Dict[float, Dict[str, float]] = {}
        for oc in outcomes:
            try:
                margin = float(oc.get("sBV", 0))
                name = oc.get("name", "").strip()
                odd = float(oc.get("odd", 0))
                if margin not in by_margin:
                    by_margin[margin] = {}
                if name == "1":
                    by_margin[margin]["t1"] = odd
                elif name == "X":
                    by_margin[margin]["x"] = odd
                elif name == "2":
                    by_margin[margin]["t2"] = odd
            except (ValueError, TypeError):
                continue

        result = []
        for margin, odds in sorted(by_margin.items()):
            if "t1" in odds and "x" in odds and "t2" in odds:
                result.append(ScrapedOdds(
                    bet_type_id=bt,
                    odd1=odds["t1"],
                    odd2=odds["x"],
                    odd3=odds["t2"],
                    margin=margin,
                ))
        return result

    @staticmethod
    def _parse_selection(outcomes: List[Dict], bt: int) -> List[ScrapedOdds]:
        """Parse selection market with normalization.

        For bt25 (total goals range): standalone digits (exact counts) are
        remapped to bt26 (exact_goals) with T-prefix.
        """
        result = []
        for oc in outcomes:
            try:
                name = oc.get("name", "").strip()
                odd = float(oc.get("odd", 0))
                if not name or odd <= 0:
                    continue
                out_bt = bt
                # bt25 exact counts → bt26
                if bt == 25 and re.match(r'^\d$', name):
                    out_bt = 26
                sel = _normalize_selection(name, bt)
                result.append(ScrapedOdds(
                    bet_type_id=out_bt, odd1=odd, odd2=0, selection=sel,
                ))
            except (ValueError, TypeError):
                continue
        return result

    @staticmethod
    def _parse_selection_htft(outcomes: List[Dict], bt: int) -> List[ScrapedOdds]:
        """Parse HT/FT selection market with normalization."""
        result = []
        for oc in outcomes:
            try:
                name = oc.get("name", "").strip()
                odd = float(oc.get("odd", 0))
                if not name or odd <= 0:
                    continue
                sel = _normalize_selection(name, bt)
                result.append(ScrapedOdds(
                    bet_type_id=bt, odd1=odd, odd2=0, selection=sel,
                ))
            except (ValueError, TypeError):
                continue
        return result

    # ========================================================================
    # Main parse method
    # ========================================================================

    def parse_odds_from_bets(self, bets: List[Dict], sport_id: int) -> List[ScrapedOdds]:
        """Parse all odds from structured bets array."""
        sport_map = SPORT_MAPS.get(sport_id, {})
        if not sport_map:
            return []

        odds_list: List[ScrapedOdds] = []

        for bet in bets:
            bt_id = bet.get("betTypeId")
            if bt_id not in sport_map:
                bt_name = bet.get("betTypeName", "?")
                logger.debug(f"[Admiral] Unmapped betTypeId={bt_id} ({bt_name}) sport={sport_id}")
                continue

            internal_bt, parser_type = sport_map[bt_id]
            outcomes = bet.get("betOutcomes", [])

            if parser_type == '3way':
                odds_list.extend(self._parse_3way(outcomes, internal_bt))
            elif parser_type == '2way':
                odds_list.extend(self._parse_2way(outcomes, internal_bt))
            elif parser_type == 'ou':
                odds_list.extend(self._parse_over_under(outcomes, internal_bt))
            elif parser_type == 'hc2':
                odds_list.extend(self._parse_handicap_2way(outcomes, internal_bt))
            elif parser_type == 'hc3':
                odds_list.extend(self._parse_handicap_3way(outcomes, internal_bt))
            elif parser_type == 'sel':
                odds_list.extend(self._parse_selection(outcomes, internal_bt))
            elif parser_type == 'sel_htft':
                odds_list.extend(self._parse_selection_htft(outcomes, internal_bt))

        return odds_list

    # ========================================================================
    # Network methods (unchanged)
    # ========================================================================

    async def fetch_competitions(self, sport_id: int) -> List[Dict[str, Any]]:
        """Fetch all competitions for a sport."""
        admiral_sport_id = INTERNAL_TO_ADMIRAL.get(sport_id)
        if admiral_sport_id is None:
            return []

        if sport_id in self._competitions_cache:
            return self._competitions_cache[sport_id]

        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000")
        far = "2030-12-31T23:59:59.000"
        url = f"{self.get_base_url()}/webTree/null/true/true/true/{now}/{far}/false"
        params = {"eventMappingTypes": ["1", "2", "3", "4", "5"]}

        data = await self.fetch_json(url, params=params)

        if not data:
            return []

        competitions = []
        for sport in data:
            if sport.get("id") == admiral_sport_id:
                for region in sport.get("regions", []):
                    for comp in region.get("competitions", []):
                        competitions.append({
                            "regionId": comp.get("regionId"),
                            "competitionId": comp.get("competitionId"),
                            "name": comp.get("competitionName", ""),
                            "regionName": region.get("regionName", ""),
                        })

        self._competitions_cache[sport_id] = competitions
        return competitions

    async def fetch_matches_for_competition(
        self,
        sport_id: int,
        competition: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Fetch all matches for a competition."""
        admiral_sport_id = INTERNAL_TO_ADMIRAL.get(sport_id)
        if admiral_sport_id is None:
            return []

        url = f"{self.get_base_url()}/getWebEventsSelections"
        params = {
            "pageId": "35",
            "sportId": str(admiral_sport_id),
            "regionId": competition["regionId"],
            "competitionId": competition["competitionId"],
            "isLive": "false",
            "dateFrom": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000"),
            "dateTo": "2030-12-31T23:59:59.000",
            "eventMappingTypes": ["1", "2", "3", "4", "5"],
        }

        matches = await self.fetch_json(url, params=params)
        return matches if matches else []

    async def fetch_match_odds(
        self,
        sport_id: int,
        competition: Dict[str, Any],
        match_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch odds for a specific match."""
        admiral_sport_id = INTERNAL_TO_ADMIRAL.get(sport_id)
        if admiral_sport_id is None:
            return None

        url = (
            f"{self.get_base_url()}/betsAndGroups/"
            f"{admiral_sport_id}/{competition['regionId']}/"
            f"{competition['competitionId']}/{match_id}"
        )

        return await self.fetch_json(url)

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Scrape all matches for a sport."""
        matches: List[ScrapedMatch] = []

        competitions = await self.fetch_competitions(sport_id)

        if not competitions:
            logger.debug(f"[Admiral] No competitions for sport {sport_id}")
            return matches

        logger.debug(f"[Admiral] Found {len(competitions)} competitions for sport {sport_id}")

        match_tasks = [
            self.fetch_matches_for_competition(sport_id, comp)
            for comp in competitions
        ]
        competition_matches = await asyncio.gather(*match_tasks, return_exceptions=True)

        match_info_list = []
        for comp_idx, comp_matches in enumerate(competition_matches):
            if isinstance(comp_matches, Exception):
                logger.warning(f"[Admiral] Error fetching competition: {comp_matches}")
                continue

            if not comp_matches:
                continue

            competition = competitions[comp_idx]

            for match_data in comp_matches:
                name = match_data.get("name", "")
                if name.count(" - ") != 1:
                    continue

                match_info_list.append({
                    'match_data': match_data,
                    'competition': competition,
                })

        odds_tasks = [
            self.fetch_match_odds(
                sport_id,
                info['competition'],
                str(info['match_data'].get('id'))
            )
            for info in match_info_list
        ]
        odds_results = await asyncio.gather(*odds_tasks, return_exceptions=True)

        for idx, info in enumerate(match_info_list):
            try:
                match_data = info['match_data']
                competition = info['competition']

                team1, team2 = self.parse_teams(match_data.get("name", ""))
                if not team1 or not team2:
                    continue

                start_time = self.parse_timestamp(match_data.get("dateTime"))
                if not start_time:
                    continue

                scraped_match = ScrapedMatch(
                    team1=team1,
                    team2=team2,
                    sport_id=sport_id,
                    start_time=start_time,
                    league_name=competition.get("name"),
                    external_id=str(match_data.get("id")),
                    metadata={
                        'region': competition.get("regionName"),
                    }
                )

                odds_result = odds_results[idx]
                if isinstance(odds_result, dict) and "bets" in odds_result:
                    scraped_match.odds = self.parse_odds_from_bets(
                        odds_result["bets"],
                        sport_id
                    )

                if scraped_match.odds:
                    matches.append(scraped_match)

            except Exception as e:
                logger.warning(f"[Admiral] Error processing match: {e}")
                continue

        return matches

    async def scrape_all(self) -> List[ScrapedMatch]:
        """Override to clear competition cache before scraping."""
        self._competitions_cache.clear()
        return await super().scrape_all()
