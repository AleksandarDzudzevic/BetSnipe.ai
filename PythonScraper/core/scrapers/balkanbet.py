"""
BalkanBet scraper for BetSnipe.ai v2.0

Scrapes odds from BalkanBet Serbia via NSoft distribution API.
Two-step approach:
  1. Overview API: fetch all match IDs for a sport (with basic inline odds)
  2. Detail API: fetch full odds per match (all markets)

Football only for now (sportId=18 in BalkanBet).
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

BASE_URL = "https://sports-sm-distribution-api.de-2.nsoftcdn.com/api/v1"
COMPANY_UUID = "4f54c6aa-82a9-475d-bf0e-dc02ded89225"

# BalkanBet sportId → internal sport ID
SPORT_MAPPING = {
    18: 1,   # Football
}
INTERNAL_TO_BB = {v: k for k, v in SPORT_MAPPING.items()}

# Concurrency limit for detail requests
MAX_CONCURRENT_DETAIL = 15

# ============================================================================
# MARKET MAPPING: BalkanBet marketId → (internal_bet_type_id, parser_type)
#
# Parser types:
#   '3way'      - 3-outcome market (1X2, DC, etc.) by position order
#   '2way'      - 2-outcome market (BTTS yes/no, O/E, DNB) by position order
#   '2way_lg'   - 2-outcome last goal (name W1/W2, no draw)
#   '3way_fg'   - 3-outcome first goal (name PDG 1/Niko/2)
#   'ah'        - Asian handicap (2-way with specialValues margin)
#   'eh'        - European handicap (3-way with specialValues margin)
#   'sel'       - Selection-based (each outcome → selection key)
#   'sel_score' - Correct score (outcome name "X:Y")
#   'sel_htft'  - HT/FT market (dash → slash in selection)
#   'sel_btts'  - BTTS combo (special normalization)
#   'sel_or'    - OR combinations
# ============================================================================

FOOTBALL_MAP = {
    # === Core result markets ===
    6:    (2, '3way'),        # KONAČAN ISHOD (1X2)
    368:  (13, '3way'),       # DUPLA ŠANSA (Double Chance)
    371:  (3, '3way'),        # PRVO POLUVREME (H1 1X2)
    380:  (20, '3way'),       # DUPLA ŠANSA PRVO POLUVREME (H1 DC)
    383:  (4, '3way'),        # DRUGO POLUVREME (H2 1X2)
    # No H2 DC market in BB
    389:  (14, '2way'),       # X VRAĆA ULOG (DNB)
    392:  (16, '2way'),       # DUPLA POBEDA (Double win)
    395:  (17, '2way'),       # SIGURNA POBEDA (Win to nil)
    437:  (19, '3way'),       # PADA VIŠE GOLOVA (Half with more goals)
    665:  (15, '2way'),       # NEPAR/PAR (Odd/Even)
    674:  (77, '2way'),       # 1.POLUVREME NEPAR/PAR (H1 Odd/Even)
    695:  (78, '2way'),       # 2.POLUVREME NEPAR/PAR (H2 Odd/Even)
    1658: (18, '3way_fg'),    # PRVI DAJE GOL (First goal)
    1655: (100, '3way_fg'),   # PRVI DAJE GOL PRVO POLUVREME (H1 first goal)
    662:  (89, '3way_fg'),    # POSLEDNJI GOL (Last goal) - has 3 outcomes: 1/Niko/2

    # === Handicap markets ===
    722:  (9, 'ah'),          # AZIJSKI HENDIKEP (Asian HC, specialValues = margin)
    728:  (80, 'eh'),         # EVROPSKI HENDIKEP (European HC 3-way, specialValues = "X:Y")

    # === Correct score ===
    686:  (23, 'sel_score'),  # TAČAN REZULTAT (Correct score)
    677:  (79, 'sel_score'),  # PRVO POLUVREME TAČAN REZULTAT (H1 correct score)
    698:  (None, 'skip'),     # DRUGO POLUVREME TAČAN REZULTAT (no internal bt)
    707:  (118, 'sel'),       # MULTI TAČAN REZULTAT (Multi correct score groups)

    # === HT/FT ===
    398:  (24, 'sel_htft'),   # POLUVREME - KRAJ (HT/FT)
    401:  (114, 'sel_or'),    # PRVO POLUVREME ILI KRAJ (H1 or FT result)

    # === Selection-based goal markets ===
    443:  (25, 'sel'),        # UKUPNO GOLOVA (Total goals range/exact)
    419:  (27, 'sel'),        # DOMAĆIN UKUPNO GOLOVA (Team1 total goals)
    422:  (28, 'sel'),        # GOST UKUPNO GOLOVA (Team2 total goals)
    428:  (29, 'sel'),        # GOLOVI PRVO POLUVREME (H1 goals range)
    431:  (30, 'sel'),        # GOLOVI DRUGO POLUVREME (H2 goals range)
    407:  (31, 'sel'),        # DOMAĆIN GOLOVI PRVO POLUVREME (Team1 goals H1)
    410:  (33, 'sel'),        # DOMAĆIN GOLOVI DRUGO POLUVREME (Team1 goals H2)
    413:  (32, 'sel'),        # GOST GOLOVI PRVO POLUVREME (Team2 goals H1)
    416:  (34, 'sel'),        # GOST GOLOVI DRUGO POLUVREME (Team2 goals H2)

    # === Combo selection markets ===
    434:  (35, 'sel'),        # GOLOVI U OBA POLUVREMENA (Goals H1&H2 combo)
    425:  (46, 'sel_btts'),   # OBA TIMA DAJU GOL (BTTS combos)
    455:  (38, 'sel'),        # KONAČAN ISHOD I UKUPNO GOLOVA (Result + total goals)
    479:  (41, 'sel'),        # DUPLA ŠANSA I UKUPNO GOLOVA (DC + total goals)
    488:  (44, 'sel_htft'),   # POLUVREME-KRAJ I UKUPNO GOLOVA (HT/FT + total)
    458:  (114, 'sel_or'),    # KONAČAN ISHOD ILI UKUPNO GOLOVA (Result OR total)
    491:  (40, 'sel'),        # KONAČAN ISHOD I PADA VIŠE GOLOVA (Result + half more)

    # === H1 result combo markets ===
    449:  (38, 'sel'),        # KONAČAN ISHOD I GOLOVI PRVO POLUVREME
    452:  (38, 'sel'),        # KONAČAN ISHOD I GOLOVI DRUGO POLUVREME

    # === DC combo markets ===
    470:  (43, 'sel'),        # DUPLA ŠANSA I GOLOVI U PRVOM POLUVREMENU
    473:  (43, 'sel'),        # DUPLA ŠANSA I GOLOVI U DRUGOM POLUVREMENU
    476:  (42, 'sel'),        # DUPLA ŠANSA I PADA VIŠE GOLOVA

    # === H1 result + DC combos ===
    461:  (39, 'sel'),        # PRVO POLUVREME I DUPLA ŠANSA
    464:  (39, 'sel'),        # DUPLA ŠANSA PRVO POLUVREME I KONAČAN ISHOD
    467:  (43, 'sel'),        # DUPLA ŠANSA PRVO POLUVREME I DUPLA ŠANSA

    # === HT/FT combo markets ===
    482:  (44, 'sel_htft'),   # POLUVREME-KRAJ I GOLOVA PRVO POLUVREME
    485:  (44, 'sel_htft'),   # POLUVREME-KRAJ I GOLOVA DRUGO POLUVREME

    # === First goal combos ===
    1661: (36, 'sel'),        # PRVI DAJE GOL I KONAČAN ISHOD

    # === Result + BTTS combos ===
    2237: (46, 'sel_btts'),   # KONAČAN ISHOD I OBA TIMA DAJU GOL
    2240: (46, 'sel_btts'),   # PRVO POLUVREME I OBA TIMA DAJU GOL
    2243: (46, 'sel_btts'),   # DUPLA ŠANSA I OBA TIMA DAJU GOL
    2246: (45, 'sel_htft'),   # POLUVREME-KRAJ I OBA TIMA DAJU GOL

    # === HT/FT OR combos ===
    2252: (124, 'sel_or'),    # POLUVREME-KRAJ ILI UKUPNO GOLOVA
}

# ============================================================================
# SELECTION NORMALIZATION
# ============================================================================

# Bet types where standalone single digits → T-prefix (exact goal count)
_GOAL_EXACT_BTS = frozenset({25, 26, 27, 28, 29, 30, 31, 32, 33, 34})


def _normalize_selection(name: str, bt: int, market_id: int) -> str:
    """Normalize BalkanBet outcome name to cross-bookmaker standard selection format.

    Conventions:
      - HT/FT: slash separator (1/1, X/2), NEVER dash
      - Goal ranges: "0-2", "3+", "2-3" etc. (as-is)
      - Exact goals: standalone digit → T-prefix ("T0", "T1", etc.)
      - Halves: I/II → H1:/H2: prefix
      - Teams: D → H (home), G → A (away)
      - BTTS: GG/NG standard, I GG → GG_H1, II GG → GG_H2
      - Combo separator: & (AND), | (OR)
      - v (OR) → |
    """
    name = name.strip()
    if not name:
        return name

    # === Correct score: already in "X:Y" format from sel_score parser ===

    # === HT/FT markets (bt24, bt37, bt113): dash → slash ===
    if bt in (24, 37, 113):
        return name.replace('-', '/')

    # === Exact goal markets: standalone digit → T-prefix ===
    if bt in _GOAL_EXACT_BTS:
        m = re.match(r'^(\d)$', name)
        if m:
            return 'T' + m.group(1)

    return name


def _normalize_btts_outcome(name: str) -> str:
    """Normalize BTTS market outcome names.

    BalkanBet uses:
      "GG" → "GG", "NG" → "NG"
      "I GG" → "GG_H1", "II GG" → "GG_H2"
      "IGG&II GG" → "GG_H1&GG_H2"
      "IGG&II NG" → "GG_H1&NG_H2"
      "I NG&II GG" → "NG_H1&GG_H2"
      "IGGvII GG" → "GG_H1|GG_H2"
      "NE I GG" → "!GG_H1", "NE II GG" → "!GG_H2"
      "GG&D2+" → "GG&H2+"
      "GG&G2+" → "GG&A2+"
      etc.
    """
    n = name.strip()

    # Simple BTTS
    if n == 'GG':
        return 'GG'
    if n == 'NG':
        return 'NG'

    # Half BTTS
    if n == 'I GG':
        return 'GG_H1'
    if n == 'II GG':
        return 'GG_H2'
    if n == 'I NG':
        return 'NG_H1'
    if n == 'II NG':
        return 'NG_H2'

    # Negation
    if n == 'NE I GG':
        return '!GG_H1'
    if n == 'NE II GG':
        return '!GG_H2'

    # Combo with & separator
    if '&' in n:
        parts = n.split('&')
        normalized_parts = []
        for p in parts:
            p = p.strip()
            np = _normalize_btts_part(p)
            normalized_parts.append(np)
        return '&'.join(normalized_parts)

    # OR separator: "v" (without surrounding spaces sometimes)
    if 'v' in n.lower():
        # "IGGvII GG" or "GG v3+"
        parts = re.split(r'\s*v\s*', n, flags=re.IGNORECASE)
        normalized_parts = []
        for p in parts:
            p = p.strip()
            np = _normalize_btts_part(p)
            normalized_parts.append(np)
        return '|'.join(normalized_parts)

    return _normalize_btts_part(n)


def _normalize_btts_part(p: str) -> str:
    """Normalize a single part of a BTTS combo outcome."""
    p = p.strip()

    # Half BTTS
    if p in ('IGG', 'I GG'):
        return 'GG_H1'
    if p in ('IIGG', 'II GG'):
        return 'GG_H2'
    if p in ('I NG', 'ING'):
        return 'NG_H1'
    if p in ('II NG', 'IING'):
        return 'NG_H2'
    if p == 'GG':
        return 'GG'
    if p == 'NG':
        return 'NG'
    if p == 'NE I GG':
        return '!GG_H1'
    if p == 'NE II GG':
        return '!GG_H2'

    # Team references: D → H (home), G → A (away)
    p = re.sub(r'^D(\d)', r'H\1', p)
    p = re.sub(r'^G(\d)', r'A\1', p)

    # Half goal references: I → H1:, II → H2:
    p = re.sub(r'^I(\d)', r'H1:\1', p)
    p = re.sub(r'^II(\d)', r'H2:\1', p)

    # "D3+ vG3+" → "H3+|A3+"
    if p.startswith('D') and '+' in p:
        p = 'H' + p[1:]
    if p.startswith('G') and '+' in p:
        p = 'A' + p[1:]

    return p


def _normalize_goal_selection(name: str, bt: int) -> str:
    """Normalize goal range/count outcome names.

    BalkanBet format examples:
      "D1+", "D2+", "D0", "D0-1" → "H1+", "H2+", "T0", "0-1" (for bt27=team1)
      "G1+", "G2+", "G0" → "A1+", "A2+", "T0" (for bt28=team2)
      "I 1+", "I 2+" → "1+", "2+" (for bt29=H1 goals)
      "II 1+", "II 2+" → "1+", "2+" (for bt30=H2 goals)
      "DI 1+", "DI 2+" → "1+", "2+" (for bt31=team1 goals H1)
      "GI 1+", "GI 2+" → "1+", "2+" (for bt32=team2 goals H1)
      "DII 1+", "DII 2+" → "1+", "2+" (for bt33=team1 goals H2)
      "GII 1+", "GII 2+" → "1+", "2+" (for bt34=team2 goals H2)
      "1 gol" / "1 gol." → "T1" (exact count)
      "2 gol." → "T2"
      "0-2", "3+", "2-3" → as-is (range)
    """
    n = name.strip()

    # Exact goal count: "N gol" / "N gol." / "Ng." / "D1g." / "G2g." (abbreviated)
    m = re.match(r'^(?:DII\s+|DI\s+|GII\s+|GI\s+|II\s+|I\s+|D|G)?(\d)\s*(?:gol|g)\.?$', n)
    if m:
        return 'T' + m.group(1)

    # Strip prefix for team/half-specific markets
    # For bt27 (team1_goals): "D1+" → strip D
    # For bt28 (team2_goals): "G1+" → strip G
    # For bt29 (h1_total_goals_range): "I 1+" → strip "I "
    # For bt30 (h2_total_goals_range): "II 1+" → strip "II "
    # For bt31-34 (team goals per half): "DI 1+", "GII 2+" → strip prefix

    # Remove leading prefix: DII, DI, GII, GI, D, G, II, I (order matters: longest first)
    for prefix in ['DII ', 'DI ', 'GII ', 'GI ', 'II ', 'I ']:
        if n.startswith(prefix):
            n = n[len(prefix):]
            break
    else:
        # Check single-char prefixes without space: D0, G0
        if bt == 27 and n.startswith('D'):
            n = n[1:]
        elif bt == 28 and n.startswith('G'):
            n = n[1:]

    # Standalone digit → T-prefix for exact-count BTs
    if bt in _GOAL_EXACT_BTS:
        m = re.match(r'^(\d)$', n)
        if m:
            return 'T' + m.group(1)

    # "NE X-Y" → skip (negation markets, not standard)
    if n.startswith('NE '):
        return '!' + n[3:]

    return n


def _normalize_combo_selection(name: str, bt: int, market_id: int) -> str:
    """Normalize combo market selections (result+goals, DC+goals, etc.).

    Handles BalkanBet's naming for markets like:
      bt38 (result+total): "1&2+", "1&3+", "2&2-3", "1&0-2"
      bt41 (DC+total): "1X&2+", "1X&3+", "12&2+", "X2&2-3"
      bt35 (goals H1&H2): "I1+&II1+", "I2+&II2+", "NE(I1+&II1+)"
      bt39 (result combos): "I 1 &1X", "I X &12"
      bt44 (HT/FT+total): "1-1&2+" → "1/1&2+"
      bt40 (result+half more): "1& I >", "1& II >"
      bt42 (DC+half more): "1X& I >", "X2& II >"
      bt43 (DC+H1 goals): "1X&I1+", "12&I2+"
      bt36 (first goal+result): "PDG1 & 1" → "1&H_first"
    """
    n = name.strip()

    # HT/FT combo: convert dash→slash in HT/FT portion
    if bt in (44, 45, 124):
        # "1-1&2+" → "1/1&2+", "X-1&II2+" → "X/1&II2+"
        if '&' in n:
            parts = n.split('&', 1)
            htft = parts[0].strip().replace('-', '/')
            rest = _normalize_combo_part(parts[1].strip(), bt)
            return htft + '&' + rest
        return n.replace('-', '/')

    # NE(...) negation for H1&H2 combos
    ne_match = re.match(r'^NE\((.+)\)$', n)
    if ne_match:
        inner = ne_match.group(1)
        inner_norm = _normalize_combo_inner(inner, bt)
        return '!' + inner_norm

    # Strip remaining parentheses (grouping only, NE() already handled above)
    n = n.replace('(', '').replace(')', '')

    # OR separator: v → |
    if ' v ' in n.lower() or re.search(r'(?<!\w)v(?!\w)', n):
        parts = re.split(r'\s*v\s*', n, flags=re.IGNORECASE)
        return '|'.join(_normalize_combo_part(p.strip(), bt) for p in parts)

    # Regular & combo
    if '&' in n:
        parts = n.split('&')
        normalized = [_normalize_combo_part(p.strip(), bt) for p in parts]
        result = '&'.join(normalized)

        # For bt119/bt120: add FT: prefix to plain number parts when mixed with H1:/H2:
        if bt in (119, 120):
            result = _apply_ft_prefix(result)

        return result

    return _normalize_combo_part(n, bt)


def _apply_ft_prefix(selection: str) -> str:
    """Add FT: prefix to plain number parts in bt119/bt120 selections.

    When a selection mixes H1:/H2: parts with plain numbers (total goals),
    the plain parts get FT: prefix for consistency with other scrapers.
    Example: "H1:1+&2+" → "H1:1+&FT:2+"
    """
    parts = selection.split('&')
    has_half = any(p.startswith('H1:') or p.startswith('H2:') for p in parts)
    if not has_half:
        return selection

    result = []
    for p in parts:
        if p.startswith('H1:') or p.startswith('H2:') or p.startswith('FT:'):
            result.append(p)
        elif re.match(r'^\d', p):
            # Plain number part like "2+", "0-1" → add FT: prefix
            result.append('FT:' + p)
        else:
            result.append(p)
    return '&'.join(result)


def _normalize_combo_inner(inner: str, bt: int) -> str:
    """Normalize the inner part of a NE(...) expression."""
    if '&' in inner:
        parts = inner.split('&')
        return '&'.join(_normalize_combo_part(p.strip(), bt) for p in parts)
    return _normalize_combo_part(inner, bt)


def _normalize_combo_part(p: str, bt: int) -> str:
    """Normalize a single part of a combo selection."""
    p = p.strip()
    if not p:
        return p

    # Half comparison
    if p in ('I >', 'I>'):
        return 'H1>H2'
    if p in ('II >', 'II>'):
        return 'H1<H2'
    if p in ('I = II', 'I=II'):
        return 'H1=H2'

    # Half result references: "I 1" → "1_H1", "II X" → "X_H2"
    m = re.match(r'^I\s+([1X2])$', p)
    if m:
        return m.group(1) + '_H1'
    m = re.match(r'^II\s+([1X2])$', p)
    if m:
        return m.group(1) + '_H2'

    # DC values: "I 1X" → "1X_H1", "I X2" → "X2_H1"
    m = re.match(r'^I\s+(1X|X2|12)$', p)
    if m:
        return m.group(1) + '_H1'

    # First goal references: "PDG1" → "H_first", "PDG2" → "A_first", "PDG Niko" → "none"
    if p.startswith('PDG'):
        if '1' in p:
            return 'H_first'
        elif '2' in p:
            return 'A_first'
        elif 'Niko' in p:
            return 'none'

    # Team+half goals: "DI1+" → "H1:1+", "DII2+" → "H2:2+", "GI1+" → "H1:1+", "GII2+" → "H2:2+"
    # (team is already encoded in bt119 vs bt120, so strip team prefix)
    m = re.match(r'^[DG]II(\d[\d\-+]*)$', p)
    if m:
        return 'H2:' + m.group(1)
    m = re.match(r'^[DG]I(\d[\d\-+]*)$', p)
    if m:
        return 'H1:' + m.group(1)

    # Half goals: "I1+" → "H1:1+", "II2+" → "H2:2+"
    m = re.match(r'^II(\d[\d\-+]*)$', p)
    if m:
        return 'H2:' + m.group(1)
    m = re.match(r'^I(\d[\d\-+]*)$', p)
    if m:
        return 'H1:' + m.group(1)

    # Half under: "I0-1" → "H1:0-1", "II0-2" → "H2:0-2"
    m = re.match(r'^II(\d+-\d+)$', p)
    if m:
        return 'H2:' + m.group(1)
    m = re.match(r'^I(\d+-\d+)$', p)
    if m:
        return 'H1:' + m.group(1)

    # Team totals in combo:
    # For bt119/bt120: team prefix is redundant (already in bt), strip it
    # For other bts: "D2+" → "H2+", "G2+" → "A2+"
    m = re.match(r'^D(\d[\d\-+]*)$', p)
    if m:
        if bt in (119, 120):
            return m.group(1)  # Strip team prefix: "D2+" → "2+"
        return 'H' + m.group(1)
    m = re.match(r'^G(\d[\d\-+]*)$', p)
    if m:
        if bt in (119, 120):
            return m.group(1)  # Strip team prefix: "G2+" → "2+"
        return 'A' + m.group(1)

    return p


def _normalize_htft_selection(name: str) -> str:
    """Normalize HT/FT selection: dash → slash.

    "1-1" → "1/1", "X-2" → "X/2", "2-X" → "2/X"
    Also handles NE variants: "NE 1-1" → "!1/1"
    """
    n = name.strip()

    if n.startswith('NE '):
        inner = n[3:].strip().replace('-', '/')
        return '!' + inner

    return n.replace('-', '/')


def _normalize_or_part(p: str, bt: int) -> str:
    """Normalize a single part of an OR selection."""
    p = p.strip()
    if not p:
        return p

    # For bt124: convert HT/FT dashes to slashes (e.g. "1-1" → "1/1")
    if bt == 124:
        p = re.sub(r'([12X])-([12X])', r'\1/\2', p)

    # Half BTTS: "IGG" → "GG_H1", "IIGG" → "GG_H2", "ING" → "NG_H1", "IING" → "NG_H2"
    if p in ('IGG', 'I GG'):
        return 'GG_H1'
    if p in ('IIGG', 'II GG'):
        return 'GG_H2'
    if p in ('ING', 'I NG'):
        return 'NG_H1'
    if p in ('IING', 'II NG'):
        return 'NG_H2'

    # Half goals: "I2+" → "H1:2+", "II2+" → "H2:2+"
    m = re.match(r'^II(\d[\d\-+]*)$', p)
    if m:
        return 'H2:' + m.group(1)
    m = re.match(r'^I(\d[\d\-+]*)$', p)
    if m:
        return 'H1:' + m.group(1)

    # GG/NG with goal count: "GG4+" → "GG&4+" or leave as-is
    # These are already in acceptable format

    return p


def _normalize_or_selection(name: str, bt: int = 0) -> str:
    """Normalize OR combination selections.

    "I 1v1" → "1_H1|1", "I XvX" → "X_H1|X"
    "1v3+" → "1|3+", "2v4+" → "2|4+"
    "Xv3+" → "X|3+"
    For bt124: "1-1vIGG" → "1/1|GG_H1"
    """
    n = name.strip()

    # Remove leading "I " for H1-specific markets (bt114 half-result OR)
    if n.startswith('I '):
        n = n[2:]

    # v → |
    parts = re.split(r'\s*v\s*', n, flags=re.IGNORECASE)
    normalized = [_normalize_or_part(p.strip(), bt) for p in parts]

    if len(normalized) >= 2:
        return '|'.join(normalized)

    return normalized[0] if normalized else n


# ============================================================================
# SCRAPER
# ============================================================================


class BalkanBetScraper(BaseScraper):
    """Scraper for BalkanBet (Serbia) via NSoft distribution API."""

    def __init__(self):
        super().__init__(bookmaker_id=12, bookmaker_name="balkanbet")

    def get_base_url(self) -> str:
        return BASE_URL

    def get_supported_sports(self) -> List[int]:
        return [1]  # Football only for now

    def get_headers(self) -> Dict[str, str]:
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'sr-Latn,sr;q=0.9,en;q=0.8',
        }

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Scrape all football matches from BalkanBet."""
        bb_sport_id = INTERNAL_TO_BB.get(sport_id)
        if bb_sport_id is None:
            logger.warning(f"[balkanbet] Unsupported sport_id: {sport_id}")
            return []

        # Step 1: Get all match IDs from overview API
        match_ids = await self._fetch_match_ids(bb_sport_id)
        if not match_ids:
            logger.warning(f"[balkanbet] No matches found for sport {sport_id}")
            return []

        logger.info(f"[balkanbet] Found {len(match_ids)} matches for sport {sport_id}")

        # Step 2: Fetch detail for each match concurrently
        sem = asyncio.Semaphore(MAX_CONCURRENT_DETAIL)
        tasks = [self._fetch_match_detail(mid, sem) for mid in match_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        matches = []
        errors = 0
        for result in results:
            if isinstance(result, Exception):
                errors += 1
                continue
            if result is not None:
                matches.append(result)

        if errors:
            logger.warning(f"[balkanbet] {errors} detail fetch errors")

        total_odds = sum(len(m.odds) for m in matches)
        logger.info(
            f"[balkanbet] Sport {sport_id}: {len(matches)} matches, "
            f"{total_odds} odds ({total_odds / len(matches):.0f} avg/match)"
            if matches else f"[balkanbet] Sport {sport_id}: 0 matches"
        )

        return matches

    async def _fetch_match_ids(self, bb_sport_id: int) -> List[int]:
        """Fetch all match IDs from the overview API."""
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        url = f"{BASE_URL}/events"
        params = {
            'deliveryPlatformId': '3',
            'dataFormat': '{"default":"object","events":"array","outcomes":"array"}',
            'language': '{"default":"sr-Latn","events":"sr-Latn","sport":"sr-Latn","category":"sr-Latn","tournament":"sr-Latn","team":"sr-Latn","market":"sr-Latn"}',
            'timezone': 'Europe/Budapest',
            'company': '{}',
            'companyUuid': COMPANY_UUID,
            'filter[sportId]': str(bb_sport_id),
            'filter[from]': now,
            'sort': 'categoryPosition,categoryName,tournamentPosition,tournamentName,startsAt',
            'offerTemplate': 'WEB_OVERVIEW',
            'shortProps': '1',
        }

        data = await self.fetch_json(url, params=params)
        if not data or 'data' not in data:
            return []

        events = data['data'].get('events', [])
        # 'a' is the event ID in shorthand format
        return [ev['a'] for ev in events if 'a' in ev]

    async def _fetch_match_detail(
        self, match_id: int, sem: asyncio.Semaphore
    ) -> Optional[ScrapedMatch]:
        """Fetch and parse full odds for a single match."""
        async with sem:
            url = f"{BASE_URL}/events/{match_id}"
            params = {
                'companyUuid': COMPANY_UUID,
                'id': str(match_id),
                'language': '{"default":"sr-Latn","events":"sr-Latn","sport":"sr-Latn","category":"sr-Latn","tournament":"sr-Latn","team":"sr-Latn","market":"sr-Latn"}',
                'timezone': 'Europe/Budapest',
                'dataFormat': '{"default":"array","markets":"array","events":"array"}',
            }

            data = await self.fetch_json(url, params=params)
            if not data or 'data' not in data:
                return None

            return self._parse_match_detail(data['data'])

    def _parse_match_detail(self, data: Dict) -> Optional[ScrapedMatch]:
        """Parse match detail API response into ScrapedMatch."""
        try:
            name = data.get('name', '')
            team1, team2 = self.parse_teams(name)
            if not team1 or not team2:
                return None

            start_time = self.parse_timestamp(data.get('startsAt'))
            if not start_time:
                return None

            sport_id = SPORT_MAPPING.get(data.get('sportId', 0))
            if not sport_id:
                return None

            match = ScrapedMatch(
                team1=team1,
                team2=team2,
                sport_id=sport_id,
                start_time=start_time,
                external_id=str(data.get('id', '')),
                league_name=None,
            )

            # Parse all markets
            markets = data.get('markets', [])
            for market in markets:
                if not market.get('active'):
                    continue
                self._parse_market(market, match)

            return match if match.odds else None

        except Exception as e:
            logger.error(f"[balkanbet] Error parsing match detail: {e}")
            return None

    def _parse_3way(
        self, outcomes: List[Dict], bt: int, match: ScrapedMatch
    ) -> None:
        """Parse 3-way market (1X2, DC, H1 1X2, etc.) by position."""
        sorted_oc = sorted(outcomes, key=lambda x: x.get('position') or 0)
        if len(sorted_oc) < 3:
            return

        odd1 = sorted_oc[0].get('odd', 0)
        odd2 = sorted_oc[1].get('odd', 0)
        odd3 = sorted_oc[2].get('odd', 0)

        if odd1 > 0 and odd2 > 0 and odd3 > 0:
            match.add_odds(bet_type_id=bt, odd1=odd1, odd2=odd2, odd3=odd3)

    def _parse_2way(
        self, outcomes: List[Dict], bt: int, match: ScrapedMatch
    ) -> None:
        """Parse 2-way market (BTTS, O/E, DNB, etc.) by position."""
        sorted_oc = sorted(outcomes, key=lambda x: x.get('position') or 0)
        if len(sorted_oc) < 2:
            return

        odd1 = sorted_oc[0].get('odd', 0)
        odd2 = sorted_oc[1].get('odd', 0)

        if odd1 > 0 and odd2 > 0:
            match.add_odds(bet_type_id=bt, odd1=odd1, odd2=odd2)

    def _parse_3way_fg(
        self, outcomes: List[Dict], bt: int, match: ScrapedMatch
    ) -> None:
        """Parse 3-way first/last goal market.

        BalkanBet order: PDG 1 (home), PDG Niko (none), PDG 2 (away)
        Internal order: home=odd1, draw/none=odd2, away=odd3
        But for bt18 (first_goal) and bt89 (last_goal), outcomes=3 means 1/X/2.
        For last_goal bt89 which is outcomes=2 in config but actually has 3:
          odd1=home, odd2=away (skip Niko/none)
        """
        # Sort by position to get consistent ordering
        sorted_oc = sorted(outcomes, key=lambda x: x.get('position') or 0)

        if bt == 89:
            # Last goal is 2-way in our system (skip "Niko"/none)
            home_odd = None
            away_odd = None
            for o in sorted_oc:
                name = o.get('name', '').strip()
                odd = o.get('odd', 0)
                if odd <= 0:
                    continue
                if 'Niko' in name or name.endswith('0'):
                    continue  # Skip "no goal" outcome
                if '1' in o.get('shortcut', '') or name.endswith('1'):
                    home_odd = odd
                elif '2' in o.get('shortcut', '') or name.endswith('2'):
                    away_odd = odd
            if home_odd and away_odd:
                match.add_odds(bet_type_id=bt, odd1=home_odd, odd2=away_odd)
        else:
            # 3-way: home / none / away
            if len(sorted_oc) >= 3:
                odd1 = sorted_oc[0].get('odd', 0)
                odd2 = sorted_oc[1].get('odd', 0)
                odd3 = sorted_oc[2].get('odd', 0)
                if odd1 > 0 and odd2 > 0 and odd3 > 0:
                    match.add_odds(bet_type_id=bt, odd1=odd1, odd2=odd2, odd3=odd3)

    def _parse_asian_handicap(
        self, outcomes: List[Dict], special_values: List,
        match: ScrapedMatch
    ) -> None:
        """Parse Asian handicap market.

        specialValues contains the margin (e.g. "-0.5", "0", "-1").
        BalkanBet convention: negative = home gives handicap (standard convention).
        Outcome "AH 1 -0.5" = home with -0.5, "AH 2 0.5" = away with +0.5.
        Our standard: positive margin = home advantage.
        BB special value "-0.5" means away is favored by 0.5, so margin = -0.5
        Wait - let's think about this more carefully:
          specialValues=["-0.5"] means the line is -0.5 for home.
          If home gets -0.5, that means home is favored.
          Our convention: positive = home advantage.
          So margin = -(-0.5) = 0.5? No...
          Actually looking at the outcome names: "AH 1 -0.5" and "AH 2 0.5"
          This means home team has -0.5 handicap applied.
          Home needs to win by more than 0.5 goals (i.e., win).
          This is equivalent to "home gives 0.5" = home advantage.
          In our system positive margin = home advantage.
          So special value -0.5 → our margin = 0.5 (negate BB sign).

        Wait, let me reconsider. In standard Asian HC:
          - If home is favorite, they give goals (negative handicap for home)
          - Special value "-1" means home gives 1 goal
          - Our convention: positive margin = home advantage
          - So our margin = -specialValue = 1

        But MaxBet also negates. Let me check what other scrapers do.
        MaxBet: raw param is negative for home advantage, code negates it.
        Admiral: raw sBV appears to be positive for home advantage already.

        For BB: specialValue "-1" + outcomes "AH 1 -1" and "AH 2 1"
        The -1 means home gives 1 goal. This IS home advantage.
        So our margin = abs(specialValue) = 1? No, we need the sign.
        Convention: positive = home advantage.
        BB "-1" = home gives 1 goal = home advantage of 1.
        So we negate: margin = -(-1) = 1. ✓

        But what if BB has positive specialValue like "+1"?
        That would mean away gives 1 goal to home.
        Convention: margin = -(+1) = -1 (away advantage). ✓

        So: margin = -float(specialValue)
        """
        if not special_values:
            return

        margin_raw = special_values[0]
        try:
            margin = -float(margin_raw)  # Negate: BB negative = home advantage → our positive
        except (ValueError, TypeError):
            return

        sorted_oc = sorted(outcomes, key=lambda x: x.get('position') or 0)
        if len(sorted_oc) < 2:
            return

        odd1 = sorted_oc[0].get('odd', 0)  # Home
        odd2 = sorted_oc[1].get('odd', 0)  # Away

        if odd1 > 0 and odd2 > 0:
            match.add_odds(bet_type_id=9, odd1=odd1, odd2=odd2, margin=margin)

    def _parse_european_handicap(
        self, outcomes: List[Dict], special_values: List,
        match: ScrapedMatch
    ) -> None:
        """Parse European (3-way) handicap.

        specialValues format: "X:Y" where X=home handicap, Y=away handicap.
        e.g. "0:1" means away gets +1, i.e. home is favored by 1.
        e.g. "1:0" means home gets +1, i.e. away is favored by 1.

        Our convention: positive margin = home advantage.
        "0:1" → home advantage = 1 (away gives 1) → margin = 1
        "1:0" → home advantage = -1 (home gets 1) → margin = -1
        "0:2" → margin = 2
        "2:0" → margin = -2

        So: margin = away_hc - home_hc
        """
        if not special_values:
            return

        sv = special_values[0]
        try:
            parts = sv.split(':')
            home_hc = int(parts[0])
            away_hc = int(parts[1])
            margin = float(away_hc - home_hc)
        except (ValueError, IndexError):
            return

        sorted_oc = sorted(outcomes, key=lambda x: x.get('position') or 0)
        if len(sorted_oc) < 3:
            return

        odd1 = sorted_oc[0].get('odd', 0)  # Home
        odd2 = sorted_oc[1].get('odd', 0)  # Draw
        odd3 = sorted_oc[2].get('odd', 0)  # Away

        if odd1 > 0 and odd2 > 0 and odd3 > 0:
            match.add_odds(
                bet_type_id=80, odd1=odd1, odd2=odd2, odd3=odd3,
                margin=margin
            )

    def _parse_correct_score(
        self, outcomes: List[Dict], bt: int, match: ScrapedMatch
    ) -> None:
        """Parse correct score market.

        Outcome names are like "0:0", "1:0", "2:1" etc.
        BalkanBet uses shortcut "00", "10", "21" but name has the colon format.
        We parse from shortcut: "XY" → "X:Y"
        """
        for o in outcomes:
            odd = o.get('odd', 0)
            if odd <= 0:
                continue

            # Use shortcut to build selection: "10" → "1:0"
            shortcut = o.get('shortcut', '')
            if len(shortcut) == 2 and shortcut.isdigit():
                selection = f"{shortcut[0]}:{shortcut[1]}"
            else:
                # Fallback: try to extract from name
                name = o.get('name', '')
                m = re.match(r'(\d+):(\d+)', name)
                if m:
                    selection = f"{m.group(1)}:{m.group(2)}"
                else:
                    continue

            match.add_odds(bet_type_id=bt, odd1=odd, selection=selection)

    def _parse_htft_selection(
        self, outcomes: List[Dict], bt: int, market_id: int,
        match: ScrapedMatch
    ) -> None:
        """Parse HT/FT selection markets.

        For bt24 (simple HT/FT): "1-1" → "1/1", "X-2" → "X/2"
        For bt44 (HT/FT + total): "1-1&2+" → "1/1&2+"
        For bt45 (HT/FT + BTTS): "1-1&GG" → "1/1&GG"
        """
        for o in outcomes:
            odd = o.get('odd', 0)
            if odd <= 0:
                continue

            name = o.get('name', '').strip()
            if not name:
                continue

            if bt == 24:
                # Simple HT/FT
                selection = _normalize_htft_selection(name)
            elif bt in (44, 45, 124):
                # Combo with HT/FT part
                selection = _normalize_combo_selection(name, bt, market_id)
            else:
                selection = name.replace('-', '/')

            if selection:
                match.add_odds(bet_type_id=bt, odd1=odd, selection=selection)

    def _parse_btts_selection(
        self, outcomes: List[Dict], bt: int, market_id: int,
        match: ScrapedMatch
    ) -> None:
        """Parse BTTS combo selection markets (2237, 2240, 2243 etc.).
        Note: market 425 is handled separately by _handle_btts_market."""
        for o in outcomes:
            odd = o.get('odd', 0)
            if odd <= 0:
                continue

            name = o.get('name', '').strip()
            if not name:
                continue

            selection = _normalize_btts_outcome(name)
            if selection:
                match.add_odds(bet_type_id=bt, odd1=odd, selection=selection)

    def _parse_or_selection(
        self, outcomes: List[Dict], bt: int, market_id: int,
        match: ScrapedMatch
    ) -> None:
        """Parse OR combination selection markets."""
        for o in outcomes:
            odd = o.get('odd', 0)
            if odd <= 0:
                continue

            name = o.get('name', '').strip()
            if not name:
                continue

            selection = _normalize_or_selection(name, bt)
            if selection:
                match.add_odds(bet_type_id=bt, odd1=odd, selection=selection)

    def _parse_selection(
        self, outcomes: List[Dict], bt: int, market_id: int,
        match: ScrapedMatch
    ) -> None:
        """Parse generic selection-based markets."""
        for o in outcomes:
            odd = o.get('odd', 0)
            if odd <= 0:
                continue

            name = o.get('name', '').strip()
            if not name:
                continue

            # Use appropriate normalizer based on bet type
            actual_bt = bt

            # Route combo outcomes from bt27/bt28 to bt119/bt120
            if bt in (27, 28) and '&' in name:
                actual_bt = 119 if bt == 27 else 120
                selection = _normalize_combo_selection(name, actual_bt, market_id)
            elif bt in (25, 26, 27, 28, 29, 30, 31, 32, 33, 34):
                selection = _normalize_goal_selection(name, bt)
            elif bt in (35, 38, 39, 40, 41, 42, 43, 44, 45, 119, 120):
                selection = _normalize_combo_selection(name, bt, market_id)
            elif bt == 36:
                selection = _normalize_combo_selection(name, bt, market_id)
            elif bt == 118:
                # Multi correct score: use name as-is (group labels)
                selection = name
            else:
                selection = _normalize_selection(name, bt, market_id)

            if selection:
                match.add_odds(bet_type_id=actual_bt, odd1=odd, selection=selection)

    def _handle_btts_market(
        self, outcomes: List[Dict], match: ScrapedMatch
    ) -> None:
        """Handle market 425 specially: extract bt8 (2-way BTTS) from GG/NG,
        and all other outcomes as bt46 selections."""
        gg_odd = None
        ng_odd = None

        for o in outcomes:
            odd = o.get('odd', 0)
            if odd <= 0:
                continue
            name = o.get('name', '').strip()
            if name == 'GG':
                gg_odd = odd
            elif name == 'NG':
                ng_odd = odd

        # Add bt8 (BTTS yes/no) as 2-way
        if gg_odd and ng_odd:
            match.add_odds(bet_type_id=8, odd1=gg_odd, odd2=ng_odd)

        # Add all other outcomes as bt46 selections
        for o in outcomes:
            odd = o.get('odd', 0)
            if odd <= 0:
                continue
            name = o.get('name', '').strip()
            if name in ('GG', 'NG'):
                continue  # Already handled as bt8

            selection = _normalize_btts_outcome(name)
            if selection:
                match.add_odds(bet_type_id=46, odd1=odd, selection=selection)

    def _parse_market(self, market: Dict, match: ScrapedMatch) -> None:
        """Parse a single market and add odds to match.
        Override to handle BTTS market 425 specially."""
        market_id = market.get('marketId')

        # Special handling for BTTS market 425
        if market_id == 425:
            outcomes = market.get('outcomes', [])
            active_outcomes = [o for o in outcomes if o.get('active')]
            if active_outcomes:
                self._handle_btts_market(active_outcomes, match)
            return

        mapping = FOOTBALL_MAP.get(market_id)
        if not mapping:
            return

        bt, parser_type = mapping
        if bt is None or parser_type == 'skip':
            return

        outcomes = market.get('outcomes', [])
        active_outcomes = [o for o in outcomes if o.get('active')]
        if not active_outcomes:
            return

        special_values = market.get('specialValues', [])

        if parser_type == '3way':
            self._parse_3way(active_outcomes, bt, match)
        elif parser_type == '2way':
            self._parse_2way(active_outcomes, bt, match)
        elif parser_type == '3way_fg':
            self._parse_3way_fg(active_outcomes, bt, match)
        elif parser_type == 'ah':
            self._parse_asian_handicap(active_outcomes, special_values, match)
        elif parser_type == 'eh':
            self._parse_european_handicap(active_outcomes, special_values, match)
        elif parser_type == 'sel_score':
            self._parse_correct_score(active_outcomes, bt, match)
        elif parser_type == 'sel_htft':
            self._parse_htft_selection(active_outcomes, bt, market_id, match)
        elif parser_type == 'sel_btts':
            self._parse_btts_selection(active_outcomes, bt, market_id, match)
        elif parser_type == 'sel_or':
            self._parse_or_selection(active_outcomes, bt, market_id, match)
        elif parser_type == 'sel':
            self._parse_selection(active_outcomes, bt, market_id, match)
