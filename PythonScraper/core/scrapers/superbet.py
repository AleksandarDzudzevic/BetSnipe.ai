"""
SuperBet scraper for BetSnipe.ai v2.0

Scrapes odds from SuperBet Serbia API.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Tuple

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)

# Sport ID mapping (SuperBet to internal)
SUPERBET_SPORTS = {
    5: 1,    # Football
    4: 2,    # Basketball
    2: 3,    # Tennis
    3: 4,    # Hockey
    24: 5,   # Table Tennis
}

# ── Football market dispatch ────────────────────────────────────────
# marketName → (bet_type_id, parser_type)
# Parser types: '3way', '2way', 'ou', 'hc', 'dc', 'yn', 'oe', 'sel'
FOOTBALL_MARKETS = {
    "Konačan ishod":                     (2,  '3way'),
    "1. poluvreme - 1X2":                (3,  '3way'),
    "2. poluvreme - 1X2":                (4,  '3way'),
    "Ukupno golova":                     (5,  'ou'),
    "1. poluvreme - ukupno golova":      (6,  'ou'),
    "2. poluvreme - ukupno golova":      (7,  'ou'),
    "Oba tima daju gol (GG)":           (8,  'yn'),
    "Hendikep":                          (9,  'hc'),
    "Dupla šansa":                       (13, 'dc'),
    "Winner DNB":                        (14, '2way'),
    "Par/nepar":                         (15, 'oe'),
    "1. gol":                            (18, '3way'),
    "Poluvreme sa više golova":          (19, '3way'),
    "1. poluvreme - dupla šansa":        (20, 'dc'),
    "1. poluvreme - Winner DNB":         (21, '2way'),
    "Tačan rezultat":                    (23, 'sel_score'),
    "Poluvreme/kraj":                    (24, 'sel'),
    "Tačno golova":                      (26, 'sel'),
    "1. poluvreme - tačan rezultat":     (79, 'sel_score'),  # H1 correct score
    "1. poluvreme - par/nepar":          (77, 'oe'),         # H1 odd/even
    "1. poluvreme - hendikep":           (50, 'hc'),         # H1 handicap
    "2. poluvreme - dupla šansa":        (75, 'dc'),         # H2 double chance
    "2. poluvreme - Winner DNB":         (76, '2way'),       # H2 draw no bet
    # Corner and card markets
    "Ukupno kornera":                    (84, 'ou'),         # Total corners O/U
    "1. poluvreme - ukupno kornera":     (94, 'ou'),         # H1 total corners O/U
    "Ukupno kartona":                    (88, 'ou'),         # Total cards O/U
}

# Dynamic football patterns: suffix → (bet_type_id_team1, bet_type_id_team2, parser_type)
FOOTBALL_TEAM_PATTERNS = [
    (" ukupno golova", 48, 49, 'ou'),        # Team total O/U
    (" tačno golova",  27, 28, 'sel'),        # Team exact goals
]

# ── Basketball market dispatch ──────────────────────────────────────
BASKETBALL_MARKETS = {
    "Pobednik (uklj. produžetke)":           (1,  '2way'),
    "Pobednik meča":                         (1,  '2way'),
    "Konačan ishod":                         (2,  '3way'),   # Regulation 1X2 (draw possible)
    "1. poluvreme - 1X2":                    (3,  '3way'),
    "Hendikep poena (uklj. produžetke)":     (9,  'hc'),
    "Ukupno poena (uklj. produžetke)":       (10, 'ou'),
    "1. poluvreme - hendikep poena":         (50, 'hc'),
    "1. poluvreme - ukupno poena":           (6,  'ou'),
    "Par/nepar poeni (uklj. produžetke)":    (15, 'oe'),
    "1. poluvreme - par/nepar poeni":        (77, 'oe'),    # H1 odd/even
    "Dupla šansa":                           (13, 'dc'),
    "1. poluvreme - Winner DNB":             (21, '2way'),
    "1. poluvreme - dupla šansa":            (20, 'dc'),
}

BASKETBALL_TEAM_PATTERNS = [
    (" - ukupno poena (uklj. produžetke)", 48, 49, 'ou'),  # Team total points
    ("1. poluvreme - {} ukupno poena",     51, 52, 'ou'),   # Team total H1
]

# ── Tennis market dispatch ──────────────────────────────────────────
TENNIS_MARKETS = {
    "Konačan ishod":                     (1,  '2way'),
    "Hendikep setova":                   (56, 'hc'),
    "Hendikep gemova":                   (9,  'hc'),
    "Ukupno gemova":                     (5,  'ou'),
    "Gemovi - Par/Nepar":                (15, 'oe'),
    "Tačan rezultat":                    (65, 'sel'),
    "Tačno setova":                      (65, 'sel'),
    "1. Set / Meč":                      (64, 'sel'),
    # "Ukupno setova" removed: total sets is not total games (bt5)
    "1. set - Ukupno gemova":            (6,  'ou'),          # S1 total (literal name)
    "1. set - Ukupno gemova - par/nepar": (59, 'oe'),         # S1 games odd/even (literal name)
    "1. Set - Tačni rezultati":          (66, 'sel'),         # S1 exact score (literal name)
}

TENNIS_TEAM_PATTERNS = [
    (" - Ukupno gemova", 48, 49, 'ou'),   # Player total games
]

# X. set markets use sbv prefix for set number
TENNIS_SET_MARKETS = {
    "X. set - Pobednik":                 (57, '2way'),
    "X. set - Hendikep gemova":          (58, 'hc'),
    "X. set - Ukupno gemova":            (6,  'ou'),   # S1 total (for set 1)
    "X. set - Ukupno gemova - par/nepar": (59, 'oe'),
    "X. set – Tačan rezultat":           (66, 'sel'),  # S1 exact score
}

# ── Hockey market dispatch ──────────────────────────────────────────
HOCKEY_MARKETS = {
    "Konačan ishod":                            (2,  '3way'),
    "Pobednik (uklj. produžetke i penale)":     (1,  '2way'),
    "Ukupno golova":                            (5,  'ou'),
    "Hendikep":                                 (9,  'hc'),
    "Oba tima daju gol":                        (8,  'yn'),
    "Dupla šansa":                              (13, 'dc'),
    "Par/nepar":                                (15, 'oe'),
    "Tačan rezultat":                           (23, 'sel_score'),
    "1. gol":                                   (18, '3way'),   # First goal
    "1. trećina - ukupno golova":               (6,  'ou'),
    "1. trećina - par/nepar":                   (77, 'oe'),     # P1 odd/even
    "X. trećina - 1X2":                         (3,  '3way'),
    "1 trećina - Dupla šansa":                  (20, 'dc'),
    "X. trećina - winner DNB":                  (21, '2way'),
    "X. trećina - oba tima daju gol":           (8,  'yn'),
}

HOCKEY_TEAM_PATTERNS = [
    (" ukupno golova", 48, 49, 'ou'),   # Team total O/U
]

# ── Table Tennis market dispatch ────────────────────────────────────
TABLE_TENNIS_MARKETS = {
    "Pobednik":                          (1,  '2way'),
    "Pobednik meča":                     (1,  '2way'),
    "Konačan ishod":                     (1,  '2way'),
    "Ukupno poena":                      (5,  'ou'),
    "Hendikep poena":                    (9,  'hc'),
}

TABLE_TENNIS_SET_MARKETS = {
    "Set X - pobednik":                  (57, '2way'),
    "Ukupno poena u setu":              (6,  'ou'),
    "Set X - par/nepar poeni":           (59, 'oe'),
    "1. set - hendikep poena":           (58, 'hc'),
}

SPORT_DISPATCH = {
    1: (FOOTBALL_MARKETS,    FOOTBALL_TEAM_PATTERNS),
    2: (BASKETBALL_MARKETS,  BASKETBALL_TEAM_PATTERNS),
    3: (TENNIS_MARKETS,      TENNIS_TEAM_PATTERNS),
    4: (HOCKEY_MARKETS,      HOCKEY_TEAM_PATTERNS),
    5: (TABLE_TENNIS_MARKETS, []),
}


class SuperbetScraper(BaseScraper):
    """Scraper for SuperBet Serbia."""

    def __init__(self):
        super().__init__(bookmaker_id=6, bookmaker_name="Superbet")

    def get_base_url(self) -> str:
        return "https://production-superbet-offer-rs.freetls.fastly.net/sb-rs/api/v2/sr-Latn-RS"

    def get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    def get_supported_sports(self) -> List[int]:
        return [1, 2, 3, 4, 5]

    async def fetch_event_ids(self, sport_id: int) -> List[int]:
        """Fetch event IDs for a sport."""
        superbet_sport_id = None
        for sb_id, internal_id in SUPERBET_SPORTS.items():
            if internal_id == sport_id:
                superbet_sport_id = sb_id
                break

        if superbet_sport_id is None:
            return []

        url = f"{self.get_base_url()}/events/by-date"
        params = {
            "currentStatus": "active",
            "offerState": "prematch",
            "startDate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sportId": str(superbet_sport_id),
        }

        data = await self.fetch_json(url, params=params)

        if not data or "data" not in data:
            return []

        event_ids = []
        for match in data["data"]:
            if match.get("sportId") == superbet_sport_id and "eventId" in match:
                event_ids.append(match["eventId"])

        return event_ids

    async def fetch_event_details(self, event_id: int) -> Optional[Dict]:
        """Fetch event details with odds."""
        url = f"{self.get_base_url()}/events/{event_id}"
        return await self.fetch_json(url)

    # ── Generic parsers ─────────────────────────────────────────────

    @staticmethod
    def _is_under(name: str) -> bool:
        """Check if an odd name represents 'under'."""
        low = name.lower()
        return "manje" in low

    @staticmethod
    def _is_over(name: str) -> bool:
        """Check if an odd name represents 'over'."""
        low = name.lower()
        return "više" in low or "vi\u0161e" in low or "vise" in low

    @staticmethod
    def _parse_sbv_margin(sbv: str) -> Optional[float]:
        """Extract numeric margin from specialBetValue.
        Handles: '2.5', '-1.5', '1-2.5' (set-margin format for tennis)."""
        if not sbv:
            return None
        # Tennis set markets use format like "1-2.5" (set_number-margin)
        if '-' in sbv and not sbv.startswith('-'):
            parts = sbv.rsplit('-', 1)
            try:
                return float(parts[-1])
            except (ValueError, IndexError):
                return None
        try:
            return float(sbv)
        except ValueError:
            return None

    def _parse_3way(self, bt_id: int, odds_entries: List[Dict]) -> Optional[ScrapedOdds]:
        """Parse 3-way market (1X2). Returns single ScrapedOdds or None."""
        home = draw = away = None
        for o in odds_entries:
            code = str(o.get("code", ""))
            if code == "1":
                home = o.get("price")
            elif code in ("0", "X"):
                draw = o.get("price")
            elif code == "2":
                away = o.get("price")
        if home and draw and away:
            return ScrapedOdds(bet_type_id=bt_id, odd1=float(home), odd2=float(draw), odd3=float(away))
        return None

    def _parse_2way(self, bt_id: int, odds_entries: List[Dict]) -> Optional[ScrapedOdds]:
        """Parse 2-way market (Winner/DNB). Returns single ScrapedOdds or None."""
        o1 = o2 = None
        for o in odds_entries:
            code = str(o.get("code", ""))
            if code == "1":
                o1 = o.get("price")
            elif code == "2":
                o2 = o.get("price")
        if o1 and o2:
            return ScrapedOdds(bet_type_id=bt_id, odd1=float(o1), odd2=float(o2))
        return None

    def _parse_yn(self, bt_id: int, odds_entries: List[Dict]) -> Optional[ScrapedOdds]:
        """Parse Yes/No market (BTTS). Code 1=Yes, 2=No."""
        yes = no = None
        for o in odds_entries:
            code = str(o.get("code", ""))
            if code == "1":
                yes = o.get("price")
            elif code == "2":
                no = o.get("price")
        if yes and no:
            return ScrapedOdds(bet_type_id=bt_id, odd1=float(yes), odd2=float(no))
        return None

    def _parse_oe(self, bt_id: int, odds_entries: List[Dict]) -> Optional[ScrapedOdds]:
        """Parse Odd/Even market. Detect by name: Par=Even(odd1), Nepar=Odd(odd2)."""
        even = odd = None
        for o in odds_entries:
            name = o.get("name", "").lower()
            if "par" in name and "nepar" not in name:
                even = o.get("price")
            elif "nepar" in name:
                odd = o.get("price")
        if odd and even:
            return ScrapedOdds(bet_type_id=bt_id, odd1=float(odd), odd2=float(even))
        return None

    def _parse_dc(self, bt_id: int, odds_entries: List[Dict]) -> Optional[ScrapedOdds]:
        """Parse double chance (1X, X2, 12). Codes: 10=1X, 02=X2, 12=12."""
        o1x = ox2 = o12 = None
        for o in odds_entries:
            code = str(o.get("code", ""))
            name = o.get("name", "")
            if code == "10" or name == "1X":
                o1x = o.get("price")
            elif code == "02" or name == "X2":
                ox2 = o.get("price")
            elif code == "12" or name == "12":
                o12 = o.get("price")
        if o1x and ox2 and o12:
            return ScrapedOdds(bet_type_id=bt_id, odd1=float(o1x), odd2=float(ox2), odd3=float(o12))
        return None

    def _parse_over_under(self, bt_id: int, odds_entries: List[Dict]) -> List[ScrapedOdds]:
        """Parse O/U market with multiple margins. Groups by sbv."""
        by_margin: Dict[str, Dict] = {}
        for o in odds_entries:
            sbv = o.get("specialBetValue", "")
            if not sbv:
                continue
            margin = self._parse_sbv_margin(str(sbv))
            if margin is None:
                continue
            key = str(margin)
            if key not in by_margin:
                by_margin[key] = {"under": None, "over": None, "margin": margin}
            name = o.get("name", "")
            price = o.get("price")
            if self._is_under(name):
                by_margin[key]["under"] = price
            elif self._is_over(name):
                by_margin[key]["over"] = price

        results = []
        for data in by_margin.values():
            if data["under"] and data["over"]:
                results.append(ScrapedOdds(
                    bet_type_id=bt_id,
                    odd1=float(data["under"]),
                    odd2=float(data["over"]),
                    margin=data["margin"],
                ))
        return results

    def _parse_handicap(self, bt_id: int, odds_entries: List[Dict]) -> List[ScrapedOdds]:
        """Parse handicap market with multiple margins. Groups by sbv."""
        by_margin: Dict[str, Dict] = {}
        for o in odds_entries:
            sbv = o.get("specialBetValue", "")
            if not sbv:
                continue
            margin = self._parse_sbv_margin(str(sbv))
            if margin is None:
                continue
            key = str(margin)
            if key not in by_margin:
                by_margin[key] = {"1": None, "2": None, "margin": margin}
            code = str(o.get("code", ""))
            if code == "1":
                by_margin[key]["1"] = o.get("price")
            elif code == "2":
                by_margin[key]["2"] = o.get("price")

        results = []
        for data in by_margin.values():
            if data["1"] and data["2"]:
                results.append(ScrapedOdds(
                    bet_type_id=bt_id,
                    odd1=float(data["1"]),
                    odd2=float(data["2"]),
                    margin=data["margin"],
                ))
        return results

    def _parse_selection(self, bt_id: int, odds_entries: List[Dict], normalize_score: bool = False) -> List[ScrapedOdds]:
        """Parse selection-based market. Each odd becomes a separate entry."""
        results = []
        for o in odds_entries:
            price = o.get("price")
            if not price:
                continue
            code = str(o.get("code", ""))
            name = o.get("name", "")

            if normalize_score:
                # Convert score codes like "10" → "1/0", "21" → "2/1"
                sel = self._normalize_score(code, name)
            else:
                sel = name.strip() if name else code

            if sel:
                results.append(ScrapedOdds(
                    bet_type_id=bt_id,
                    odd1=float(price),
                    selection=sel,
                ))
        return results

    @staticmethod
    def _normalize_score(code: str, name: str) -> str:
        """Normalize score representation: '10' → '1:0', '0:1' stays, name fallback."""
        # If name already looks like a score, use it
        if re.match(r'^\d+:\d+$', name.strip()):
            return name.strip()
        # Try to parse code as score (e.g., "10" → "1:0", "00" → "0:0")
        if re.match(r'^\d{2}$', code):
            return f"{code[0]}:{code[1]}"
        # "99" or special codes → use name
        if name:
            return name.strip()
        return code

    # ── Combo market parsers (football) ────────────────────────────

    @staticmethod
    def _combo_by_code(entries: List[Dict], bt_id: int,
                       code_map: Dict[str, str]) -> List[ScrapedOdds]:
        """Map entries to selections by outcome code."""
        results = []
        for o in entries:
            code = str(o.get('code', ''))
            price = o.get('price')
            if price and code in code_map:
                results.append(ScrapedOdds(
                    bet_type_id=bt_id, odd1=float(price), selection=code_map[code],
                ))
        return results

    @staticmethod
    def _yn_to_sel(entries: List[Dict], bt_yes: int, sel_yes: str,
                   bt_no: Optional[int] = None,
                   sel_no: Optional[str] = None) -> List[ScrapedOdds]:
        """Map yes/no market to selection-based odds."""
        results = []
        for o in entries:
            code = str(o.get('code', ''))
            price = o.get('price')
            if not price:
                continue
            if code == '1':
                results.append(ScrapedOdds(
                    bet_type_id=bt_yes, odd1=float(price), selection=sel_yes,
                ))
            elif code == '2' and bt_no is not None and sel_no:
                results.append(ScrapedOdds(
                    bet_type_id=bt_no, odd1=float(price), selection=sel_no,
                ))
        return results

    def _parse_result_ou_combo(self, entries: List[Dict], bt_id: int,
                               threshold: float) -> List[ScrapedOdds]:
        """Parse result + O/U combo. Names like '1 & Više 2.5'."""
        over_label = f'{int(threshold + 0.5)}+'
        under_label = f'0-{int(threshold - 0.5)}'
        results = []
        for o in entries:
            name = o.get('name', '')
            price = o.get('price')
            if not price or not name:
                continue
            parts = name.split(' & ', 1)
            if len(parts) != 2:
                continue
            result = parts[0].strip()
            ou_part = parts[1].strip()
            if result not in ('1', 'X', '2'):
                continue
            if self._is_over(ou_part):
                sel = f'{result}&{over_label}'
            elif self._is_under(ou_part):
                sel = f'{result}&{under_label}'
            else:
                continue
            results.append(ScrapedOdds(
                bet_type_id=bt_id, odd1=float(price), selection=sel,
            ))
        return results

    def _parse_dc_ou_combo(self, entries: List[Dict], bt_id: int,
                           threshold: float) -> List[ScrapedOdds]:
        """Parse DC + O/U combo. Codes like '10-', '10+', '02-', '02+'."""
        over_label = f'{int(threshold + 0.5)}+'
        under_label = f'0-{int(threshold - 0.5)}'
        DC_CODES = {'10': '1X', '02': 'X2', '12': '12'}
        results = []
        for o in entries:
            code = str(o.get('code', ''))
            price = o.get('price')
            if not price or len(code) < 3:
                continue
            dc_part = code[:2]
            direction = code[2:]
            dc = DC_CODES.get(dc_part)
            if not dc:
                continue
            if direction == '+':
                sel = f'{dc}&{over_label}'
            elif direction == '-':
                sel = f'{dc}&{under_label}'
            else:
                continue
            results.append(ScrapedOdds(
                bet_type_id=bt_id, odd1=float(price), selection=sel,
            ))
        return results

    def _parse_htft_ou_combo(self, entries: List[Dict], bt_id: int,
                             threshold: float) -> List[ScrapedOdds]:
        """Parse HT/FT + O/U combo. Names like '1/1 & Više 2.5'."""
        over_label = f'{int(threshold + 0.5)}+'
        under_label = f'0-{int(threshold - 0.5)}'
        results = []
        for o in entries:
            name = o.get('name', '')
            price = o.get('price')
            if not price or not name:
                continue
            parts = name.split(' & ', 1)
            if len(parts) != 2:
                continue
            htft_raw = parts[0].strip()
            ou_part = parts[1].strip()
            # Normalize HT/FT: "1/1", "X/2", etc.
            htft = htft_raw.replace(' ', '')
            if '/' not in htft or len(htft) < 3:
                continue
            if self._is_over(ou_part):
                sel = f'{htft}&{over_label}'
            elif self._is_under(ou_part):
                sel = f'{htft}&{under_label}'
            else:
                continue
            results.append(ScrapedOdds(
                bet_type_id=bt_id, odd1=float(price), selection=sel,
            ))
        return results

    def _parse_htft_btts_combo(self, entries: List[Dict],
                               bt_id: int) -> List[ScrapedOdds]:
        """Parse HT/FT + BTTS combo. Names like '1/1 & Da'."""
        results = []
        for o in entries:
            name = o.get('name', '')
            price = o.get('price')
            if not price or not name:
                continue
            parts = name.split(' & ', 1)
            if len(parts) != 2:
                continue
            htft_raw = parts[0].strip().replace(' ', '')
            yn = parts[1].strip()
            if '/' not in htft_raw or len(htft_raw) < 3:
                continue
            if yn == 'Da':
                sel = f'{htft_raw}&GG'
            elif yn == 'Ne':
                sel = f'{htft_raw}&NG'
            else:
                continue
            results.append(ScrapedOdds(
                bet_type_id=bt_id, odd1=float(price), selection=sel,
            ))
        return results

    def _parse_btts_ou_combo(self, entries: List[Dict]) -> List[ScrapedOdds]:
        """Parse BTTS + O/U combo. Codes: +1/-1 (GG+ou), +2/-2 (NG+ou)."""
        results = []
        by_sbv: Dict[str, List[Dict]] = {}
        for o in entries:
            sbv = str(o.get('specialBetValue', ''))
            if sbv:
                if sbv not in by_sbv:
                    by_sbv[sbv] = []
                by_sbv[sbv].append(o)

        for sbv_str, odds in by_sbv.items():
            try:
                threshold = float(sbv_str)
            except ValueError:
                continue
            over_label = f'{int(threshold + 0.5)}+'
            under_label = f'0-{int(threshold - 0.5)}'
            for o in odds:
                code = str(o.get('code', ''))
                price = o.get('price')
                if not price:
                    continue
                if code == '+1':
                    sel = f'GG&{over_label}'
                elif code == '-1':
                    sel = f'GG&{under_label}'
                elif code == '+2':
                    sel = f'NG&{over_label}'
                elif code == '-2':
                    sel = f'NG&{under_label}'
                else:
                    continue
                results.append(ScrapedOdds(
                    bet_type_id=46, odd1=float(price), selection=sel,
                ))
        return results

    def _try_football_combo(self, market_name: str,
                            entries: List[Dict]) -> List[ScrapedOdds]:
        """Handle football combo markets. Returns odds or empty list."""

        # === Code-based combo markets ===
        if market_name == "1X2 & oba tima daju gol":
            return self._combo_by_code(entries, 46, {
                '11': '1&GG', '12': '1&NG',
                '01': 'X&GG', '02': 'X&NG',
                '21': '2&GG', '22': '2&NG',
            })

        if market_name == "Dupla šansa & oba tima daju gol":
            return self._combo_by_code(entries, 41, {
                '101': '1X&GG', '102': '1X&NG',
                '121': '12&GG', '122': '12&NG',
                '021': 'X2&GG', '022': 'X2&NG',
            })

        if market_name == "1X2 & poluvreme sa više golova":
            return self._combo_by_code(entries, 40, {
                '11': '1&H1>H2', '10': '1&H1=H2', '12': '1&H1<H2',
                '01': 'X&H1>H2', '00': 'X&H1=H2', '02': 'X&H1<H2',
                '21': '2&H1>H2', '20': '2&H1=H2', '22': '2&H1<H2',
            })

        if market_name == "1X2 & gol u oba poluvremena":
            return self._combo_by_code(entries, 38, {
                '1': '1&H1:1+&H2:1+',
                '0': 'X&H1:1+&H2:1+',
                '2': '2&H1:1+&H2:1+',
            })

        if market_name == "Oba tima daju gol 1.poluvreme/2.poluvreme":
            return self._combo_by_code(entries, 46, {
                '11': 'GG_H1&GG_H2',
                '10': 'GG_H1&NG_H2',
                '01': 'NG_H1&GG_H2',
                '00': 'NG_H1&NG_H2',
            })

        if market_name == "1. poluvreme - 1X2 & oba tima daju gol":
            results = []
            for o in entries:
                code = str(o.get('code', ''))
                price = o.get('price')
                if not price:
                    continue
                # Da (yes) → bt46, Ne (no) → bt123
                sel_map = {
                    '11': (46, '1_H1&GG_H1'), '12': (123, '1_H1&NG_H1'),
                    '01': (46, 'X_H1&GG_H1'), '02': (123, 'X_H1&NG_H1'),
                    '21': (46, '2_H1&GG_H1'), '22': (123, '2_H1&NG_H1'),
                }
                if code in sel_map:
                    bt, sel = sel_map[code]
                    results.append(ScrapedOdds(
                        bet_type_id=bt, odd1=float(price), selection=sel,
                    ))
            return results

        if market_name == "2. poluvreme - 1X2 & oba tima daju gol":
            results = []
            for o in entries:
                code = str(o.get('code', ''))
                price = o.get('price')
                if not price:
                    continue
                sel_map = {
                    '11': (46, '1_H2&GG_H2'), '12': (123, '1_H2&NG_H2'),
                    '01': (46, 'X_H2&GG_H2'), '02': (123, 'X_H2&NG_H2'),
                    '21': (46, '2_H2&GG_H2'), '22': (123, '2_H2&NG_H2'),
                }
                if code in sel_map:
                    bt, sel = sel_map[code]
                    results.append(ScrapedOdds(
                        bet_type_id=bt, odd1=float(price), selection=sel,
                    ))
            return results

        # === Goal range markets (code-based) ===
        if market_name == "Raspon golova":
            code_map = {}
            for a in range(0, 7):
                for b in range(a + 1, 8):
                    code_map[f'{a}{b}'] = f'{a}-{b}'
            return self._combo_by_code(entries, 25, code_map)

        if market_name == "1. poluvreme - raspon golova":
            # Names like "1-2", "1-3", "2-3"
            return self._parse_name_range(entries, 29)

        if market_name == "2. poluvreme - raspon golova":
            return self._parse_name_range(entries, 30)

        if market_name == "1. poluvreme - tačno golova":
            # code 0→T0, 1→T1, 2→T2 (skip 3+ as not exact)
            return self._combo_by_code(entries, 29, {
                '0': 'T0', '1': 'T1', '2': 'T2',
            })

        # === 1X2 & goal range (code like '123' = result 1, range 2-3) ===
        if market_name == "1X2 & raspon golova":
            results = []
            RESULT_MAP = {'1': '1', '0': 'X', '2': '2'}
            for o in entries:
                code = str(o.get('code', ''))
                price = o.get('price')
                if not price or len(code) != 3:
                    continue
                result = RESULT_MAP.get(code[0])
                if not result:
                    continue
                rng = f'{code[1]}-{code[2]}'
                results.append(ScrapedOdds(
                    bet_type_id=38, odd1=float(price),
                    selection=f'{result}&{rng}',
                ))
            return results

        # === Yes/No → selection markets ===
        if market_name == "2. poluvreme - oba tima daju gol":
            return self._yn_to_sel(entries, 46, 'GG_H2', 46, 'NG_H2')

        if market_name == "1. poluvreme - oba tima daju gol":
            return self._yn_to_sel(entries, 46, 'GG_H1', 46, 'NG_H1')

        if market_name == "Gol u oba poluvremena":
            return self._yn_to_sel(entries, 35, 'H1:1+&H2:1+')

        if market_name == "Oba tima daju gol & 3+":
            return self._yn_to_sel(entries, 46, 'GG&3+')

        if market_name == "Oba tima daju gol & 4+":
            return self._yn_to_sel(entries, 46, 'GG&4+')

        if market_name == "Oba tima daju gol ili 3+":
            return self._yn_to_sel(entries, 46, 'GG|3+')

        if market_name == "Oba tima daju gol ili 4+":
            return self._yn_to_sel(entries, 46, 'GG|4+')

        if market_name == "Oba tima daju po dva ili više golova":
            return self._yn_to_sel(entries, 46, 'GG2+')

        # === Threshold-based combo markets (regex matching) ===

        # 1X2 & total (X.5) → bt38
        if market_name.startswith("1X2 & ukupno golova ("):
            try:
                threshold = float(market_name.split('(')[1].rstrip(')'))
                return self._parse_result_ou_combo(entries, 38, threshold)
            except (ValueError, IndexError):
                pass

        # DC & total (X.5) → bt41
        if market_name.startswith("Dupla šansa & ukupno golova ("):
            try:
                threshold = float(market_name.split('(')[1].rstrip(')'))
                return self._parse_dc_ou_combo(entries, 41, threshold)
            except (ValueError, IndexError):
                pass

        # HT/FT & total (X.5) → bt44
        if market_name.startswith("Poluvreme/kraj & ukupno golova ("):
            try:
                threshold = float(market_name.split('(')[1].rstrip(')'))
                return self._parse_htft_ou_combo(entries, 44, threshold)
            except (ValueError, IndexError):
                pass

        # HT/FT & BTTS → bt44
        if market_name == "Poluvreme/kraj & oba tima daju gol (GG)":
            return self._parse_htft_btts_combo(entries, 44)

        # BTTS & total (multi-sbv) → bt46
        if market_name == "Ukupno golova & oba tima daju gol":
            return self._parse_btts_ou_combo(entries)

        # === OR combo markets (bt114) ===
        # "1X2 ili ukupno golova (X.5)" → bt114
        if market_name.startswith("1X2 ili ukupno golova ("):
            try:
                threshold = float(market_name.split('(')[1].rstrip(')'))
                return self._parse_result_or_total(entries, 114, threshold)
            except (ValueError, IndexError):
                pass

        # "1X2 ili 1. poluvreme ukupno golova (X.5)" → bt114
        if market_name.startswith("1X2 ili 1. poluvreme ukupno golova ("):
            try:
                threshold = float(market_name.split('(')[1].rstrip(')'))
                return self._parse_result_or_total(entries, 114, threshold, half='H1')
            except (ValueError, IndexError):
                pass

        # === HT/FT OR combos (bt124) ===
        if market_name == "Poluvreme/kraj multi \u0161ansa":
            return self._parse_htft_or(entries)

        # === HT/FT DC (bt37) ===
        if market_name == "1. poluvreme dupla \u0161ansa & kraj utakmice dupla \u0161ansa":
            return self._parse_htft_dc(entries)

        # === HT/FT + goal range (bt44) ===
        if market_name == "Poluvreme/kraj & raspon golova":
            return self._parse_htft_range(entries, 44)

        # === First goal + result (bt36) ===
        if market_name == "1. gol & 1X2":
            return self._combo_by_code(entries, 36, {
                '10': 'X&H_first', '11': '1&H_first', '12': '2&H_first',
                '20': 'X&A_first', '21': '1&A_first', '22': '2&A_first',
            })

        # === DC + goal range (bt41) ===
        if market_name == "Dupla \u0161ansa & raspon golova":
            return self._parse_dc_range(entries, 41)

        # === DC + half with more goals (bt42) ===
        if market_name == "Dupla \u0161ansa & poluvreme sa vi\u0161e golova":
            return self._parse_dc_half_goals(entries, 42)

        return []

    @staticmethod
    def _parse_name_range(entries: List[Dict],
                          bt_id: int) -> List[ScrapedOdds]:
        """Parse goal range from outcome name (e.g., '1-2', '2-3')."""
        results = []
        for o in entries:
            name = o.get('name', '').strip()
            price = o.get('price')
            if not price or not name:
                continue
            # Extract range pattern like "1-2" from names like "1-2" or "1-2 golova"
            parts = name.split()
            sel = parts[0] if parts else name
            if '-' in sel and sel.replace('-', '').isdigit():
                results.append(ScrapedOdds(
                    bet_type_id=bt_id, odd1=float(price), selection=sel,
                ))
        return results

    def _parse_result_or_total(self, entries: List[Dict], bt_id: int,
                               threshold: float,
                               half: Optional[str] = None) -> List[ScrapedOdds]:
        """Parse 'Result OR Total' combo → bt114.

        Names like '1 ili Više 2.5' → '1|3+', 'X ili Manje 2.5' → 'X|0-2'.
        With half='H1': '1 ili Više 1.5' → '1|H1:2+'.
        """
        over_label = f'{int(threshold + 0.5)}+'
        under_label = f'0-{int(threshold - 0.5)}'
        if half:
            over_label = f'{half}:{over_label}'
            under_label = f'{half}:{under_label}'
        results = []
        for o in entries:
            name = o.get('name', '')
            price = o.get('price')
            if not price or not name:
                continue
            parts = name.split(' ili ', 1)
            if len(parts) != 2:
                continue
            result = parts[0].strip()
            ou_part = parts[1].strip()
            if result not in ('1', 'X', '2'):
                continue
            if self._is_over(ou_part):
                sel = f'{result}|{over_label}'
            elif self._is_under(ou_part):
                sel = f'{result}|{under_label}'
            else:
                continue
            results.append(ScrapedOdds(
                bet_type_id=bt_id, odd1=float(price), selection=sel,
            ))
        return results

    @staticmethod
    def _parse_htft_or(entries: List[Dict]) -> List[ScrapedOdds]:
        """Parse HT/FT OR combos → bt124.

        Names like '1/1 ili 1/2' → '1/1|1/2'.
        """
        results = []
        for o in entries:
            name = o.get('name', '').strip()
            price = o.get('price')
            if not price or not name or ' ili ' not in name:
                continue
            parts = name.split(' ili ')
            # Validate each part looks like HT/FT (contains /)
            valid = all('/' in p.strip() for p in parts)
            if not valid:
                continue
            sel = '|'.join(p.strip() for p in parts)
            results.append(ScrapedOdds(
                bet_type_id=124, odd1=float(price), selection=sel,
            ))
        return results

    @staticmethod
    def _parse_htft_dc(entries: List[Dict]) -> List[ScrapedOdds]:
        """Parse HT/FT DC → bt37.

        Names like '12/12', '1X/X2', 'X2/1X'. Only use entries with '/' in name.
        """
        results = []
        for o in entries:
            name = o.get('name', '').strip()
            price = o.get('price')
            if not price or not name:
                continue
            # Only parse entries in DC/DC format (contain /)
            if '/' not in name or ' ' in name:
                continue
            results.append(ScrapedOdds(
                bet_type_id=37, odd1=float(price), selection=name,
            ))
        return results

    @staticmethod
    def _parse_htft_range(entries: List[Dict],
                          bt_id: int) -> List[ScrapedOdds]:
        """Parse HT/FT + goal range → bt44.

        Names like '1/1 & 2-3' → '1/1&2-3'.
        """
        results = []
        for o in entries:
            name = o.get('name', '').strip()
            price = o.get('price')
            if not price or not name:
                continue
            parts = name.split(' & ', 1)
            if len(parts) != 2:
                continue
            htft = parts[0].strip().replace(' ', '')
            goal_range = parts[1].strip()
            if '/' not in htft:
                continue
            sel = f'{htft}&{goal_range}'
            results.append(ScrapedOdds(
                bet_type_id=bt_id, odd1=float(price), selection=sel,
            ))
        return results

    @staticmethod
    def _parse_dc_range(entries: List[Dict],
                        bt_id: int) -> List[ScrapedOdds]:
        """Parse DC + goal range → bt41.

        Codes like '0223' → 'X2&2-3', '1025' → '1X&2-5'.
        First 2 digits: DC code (10=1X, 02=X2, 12=12).
        Next 2 digits: range start-end.
        """
        DC_CODES = {'10': '1X', '02': 'X2', '12': '12'}
        results = []
        for o in entries:
            code = str(o.get('code', ''))
            price = o.get('price')
            if not price or len(code) != 4:
                continue
            dc_part = code[:2]
            dc = DC_CODES.get(dc_part)
            if not dc:
                continue
            rng = f'{code[2]}-{code[3]}'
            results.append(ScrapedOdds(
                bet_type_id=bt_id, odd1=float(price),
                selection=f'{dc}&{rng}',
            ))
        return results

    @staticmethod
    def _parse_dc_half_goals(entries: List[Dict],
                             bt_id: int) -> List[ScrapedOdds]:
        """Parse DC + half with more goals → bt42.

        Names like '1X & 1. poluvreme' → '1X&H1>H2',
        '1X & 2. poluvreme' → '1X&H1<H2',
        '1X & Nijedno poluvreme' → '1X&H1=H2'.
        """
        results = []
        for o in entries:
            name = o.get('name', '').strip()
            price = o.get('price')
            if not price or not name:
                continue
            parts = name.split(' & ', 1)
            if len(parts) != 2:
                continue
            dc = parts[0].strip()
            half_part = parts[1].strip().lower()
            if dc not in ('1X', 'X2', '12'):
                continue
            if '1.' in half_part and 'poluvreme' in half_part:
                sel = f'{dc}&H1>H2'
            elif '2.' in half_part and 'poluvreme' in half_part:
                sel = f'{dc}&H1<H2'
            elif 'nijedno' in half_part:
                sel = f'{dc}&H1=H2'
            else:
                continue
            results.append(ScrapedOdds(
                bet_type_id=bt_id, odd1=float(price), selection=sel,
            ))
        return results

    def _try_tennis_combo(self, market_name: str, entries: List[Dict],
                          team1: str, team2: str) -> List[ScrapedOdds]:
        """Handle tennis combo and per-set player markets."""
        # Winner & total games → bt38 (codes: 1-/1+/2-/2+, grouped by sbv)
        if market_name in ("Pobednik & ukupno gemova",):
            return self._parse_winner_total_combo(entries, 38)

        # S1 winner & total games → bt38 with set context (codes same)
        if market_name == "1. Set pobednik & ukupno gemova":
            # Filter to set 1 entries only (sbv starts with "1-")
            s1 = []
            for o in entries:
                sbv = str(o.get('specialBetValue', ''))
                if sbv.startswith('1-'):
                    o_copy = dict(o)
                    o_copy['specialBetValue'] = sbv[2:]  # strip "1-" prefix
                    s1.append(o_copy)
            if s1:
                return self._parse_winner_total_combo(s1, 38)
            return []

        # Per-set player total games (literal "1./2. set - {player} ukupno gemova")
        if team1 and team2:
            mn_lower = market_name.lower()
            for prefix, bt_t1, bt_t2 in [("1. set - ", 51, 52), ("2. set - ", 51, 52)]:
                if mn_lower.startswith(prefix) and mn_lower.endswith(" ukupno gemova"):
                    # Only S1 → bt51/52
                    if prefix == "2. set - ":
                        break  # skip S2 (no separate bt for S2 player total)
                    if team1.lower() in mn_lower:
                        return self._dispatch_parser(bt_t1, 'ou', entries)
                    elif team2.lower() in mn_lower:
                        return self._dispatch_parser(bt_t2, 'ou', entries)

        return []

    def _parse_winner_total_combo(self, entries: List[Dict],
                                  bt_id: int) -> List[ScrapedOdds]:
        """Parse winner + total combo. Codes: 1-/1+/2-/2+ grouped by sbv."""
        by_sbv: Dict[str, List[Dict]] = {}
        for o in entries:
            sbv = str(o.get('specialBetValue', ''))
            if sbv:
                if sbv not in by_sbv:
                    by_sbv[sbv] = []
                by_sbv[sbv].append(o)

        results = []
        for sbv_str, odds in by_sbv.items():
            try:
                threshold = float(sbv_str)
            except ValueError:
                continue
            over_label = f'{int(threshold + 0.5)}+'
            under_label = f'0-{int(threshold - 0.5)}'
            for o in odds:
                code = str(o.get('code', ''))
                price = o.get('price')
                if not price:
                    continue
                if code == '1+':
                    sel = f'1&{over_label}'
                elif code == '1-':
                    sel = f'1&{under_label}'
                elif code == '2+':
                    sel = f'2&{over_label}'
                elif code == '2-':
                    sel = f'2&{under_label}'
                else:
                    continue
                results.append(ScrapedOdds(
                    bet_type_id=bt_id, odd1=float(price), selection=sel,
                ))
        return results

    def _try_basketball_combo(self, market_name: str,
                              entries: List[Dict]) -> List[ScrapedOdds]:
        """Handle basketball combo markets (winner + total)."""
        if market_name in ("Pobednik & ukupno poena (uklj. produžetke)",
                           "Pobednik & ukupno poena"):
            return self._parse_winner_total_combo(entries, 38)
        return []

    # ── Main odds parser ────────────────────────────────────────────

    def parse_odds(self, match_data: Dict, sport_id: int) -> List[ScrapedOdds]:
        """Parse all odds from match data for given sport."""
        odds_list: List[ScrapedOdds] = []
        all_odds = match_data.get("odds", [])
        if not all_odds:
            return odds_list

        dispatch = SPORT_DISPATCH.get(sport_id)
        if not dispatch:
            return odds_list

        market_map, team_patterns = dispatch

        # Extract team names for team-specific market detection
        match_name = match_data.get("matchName", "")
        team1, team2 = self._extract_teams(match_name)

        # Group odds by marketName
        by_market: Dict[str, List[Dict]] = {}
        for o in all_odds:
            mn = o.get("marketName", "")
            if mn not in by_market:
                by_market[mn] = []
            by_market[mn].append(o)

        # Process fixed market names
        for market_name, entries in by_market.items():
            mapping = market_map.get(market_name)
            if mapping:
                bt_id, parser_type = mapping
                parsed = self._dispatch_parser(bt_id, parser_type, entries)
                odds_list.extend(parsed)
                continue

            # Football combo markets (result+total, BTTS combos, goal ranges, etc.)
            if sport_id == 1:
                parsed = self._try_football_combo(market_name, entries)
                if parsed:
                    odds_list.extend(parsed)
                    continue

            # Tennis "X. set" markets (only parse set 1)
            if sport_id == 3:
                parsed = self._try_tennis_set_market(market_name, entries)
                if parsed:
                    odds_list.extend(parsed)
                    continue
                # Tennis combo: Winner & total games → bt38
                parsed = self._try_tennis_combo(market_name, entries, team1, team2)
                if parsed:
                    odds_list.extend(parsed)
                    continue

            # Table Tennis set markets
            if sport_id == 5:
                parsed = self._try_tt_set_market(market_name, entries)
                if parsed:
                    odds_list.extend(parsed)
                    continue

            # Hockey "X. trećina" markets (only parse period 1)
            if sport_id == 4:
                parsed = self._try_hockey_period_market(market_name, entries)
                if parsed:
                    odds_list.extend(parsed)
                    continue
                # Hockey combo: 1X2 & total (X.5) → bt38
                if market_name.startswith("1X2 & ukupno golova ("):
                    try:
                        threshold = float(market_name.split('(')[1].rstrip(')'))
                        parsed = self._parse_result_ou_combo(entries, 38, threshold)
                        if parsed:
                            odds_list.extend(parsed)
                            continue
                    except (ValueError, IndexError):
                        pass

            # Basketball combo: Winner & total → bt38
            if sport_id == 2:
                parsed = self._try_basketball_combo(market_name, entries)
                if parsed:
                    odds_list.extend(parsed)
                    continue

            # Team-specific markets
            if team1 and team2:
                parsed = self._try_team_market(
                    market_name, entries, team1, team2, team_patterns, sport_id
                )
                if parsed:
                    odds_list.extend(parsed)
                    continue

            logger.debug(f"[SuperBet] Unmapped market '{market_name}' sport={sport_id}")

        return odds_list

    def _dispatch_parser(self, bt_id: int, parser_type: str,
                         entries: List[Dict]) -> List[ScrapedOdds]:
        """Dispatch to appropriate parser and tag results with bet_type_id."""
        results: List[ScrapedOdds] = []

        if parser_type == '3way':
            parsed = self._parse_3way(bt_id, entries)
            if parsed:
                results.append(parsed)

        elif parser_type == '2way':
            parsed = self._parse_2way(bt_id, entries)
            if parsed:
                results.append(parsed)

        elif parser_type == 'yn':
            parsed = self._parse_yn(bt_id, entries)
            if parsed:
                results.append(parsed)

        elif parser_type == 'oe':
            parsed = self._parse_oe(bt_id, entries)
            if parsed:
                results.append(parsed)

        elif parser_type == 'dc':
            parsed = self._parse_dc(bt_id, entries)
            if parsed:
                results.append(parsed)

        elif parser_type == 'ou':
            results.extend(self._parse_over_under(bt_id, entries))

        elif parser_type == 'hc':
            results.extend(self._parse_handicap(bt_id, entries))

        elif parser_type == 'sel':
            results.extend(self._parse_selection(bt_id, entries))

        elif parser_type == 'sel_score':
            results.extend(self._parse_selection(bt_id, entries, normalize_score=True))

        return results

    def _try_tennis_set_market(self, market_name: str,
                               entries: List[Dict]) -> List[ScrapedOdds]:
        """Handle tennis 'X. set' markets. Only parse set 1."""
        for pattern, (bt_id, parser_type) in TENNIS_SET_MARKETS.items():
            if market_name == pattern:
                # Filter to set 1 and normalize sbv
                # O/U format: "1-10.5" (set-margin) → starts with "1-"
                # HC format: "-1.5-1" or "1.5-1" (margin-set) → ends with "-1"
                # Simple format: "1" → exact match
                set1_entries = []
                for o in entries:
                    sbv = str(o.get("specialBetValue", ""))
                    if sbv == "1" or sbv.startswith("1-"):
                        # O/U/simple format: strip "1-" prefix → keep margin
                        new_sbv = sbv[2:] if sbv.startswith("1-") else sbv
                        o_copy = dict(o)
                        o_copy["specialBetValue"] = new_sbv
                        set1_entries.append(o_copy)
                    elif sbv.endswith("-1") and len(sbv) > 2:
                        # HC format: strip "-1" suffix → keep margin
                        new_sbv = sbv[:-2]
                        o_copy = dict(o)
                        o_copy["specialBetValue"] = new_sbv
                        set1_entries.append(o_copy)
                if set1_entries:
                    return self._dispatch_parser(bt_id, parser_type, set1_entries)
        return []

    def _try_tt_set_market(self, market_name: str,
                           entries: List[Dict]) -> List[ScrapedOdds]:
        """Handle table tennis set-specific markets. Only parse set 1."""
        mapping = TABLE_TENNIS_SET_MARKETS.get(market_name)
        if not mapping:
            return []

        bt_id, parser_type = mapping
        set1_entries = []
        for o in entries:
            sbv = str(o.get("specialBetValue", ""))
            # sbv formats: "1" (simple), "1-18.5" (set-margin), "1--2.5" (set-neg_margin)
            if sbv == "1" or sbv.startswith("1-"):
                o_copy = dict(o)
                if sbv.startswith("1-"):
                    # Strip "1-" prefix, keep margin (handles "1-18.5" → "18.5" and "1--2.5" → "-2.5")
                    o_copy["specialBetValue"] = sbv[2:]
                set1_entries.append(o_copy)

        if set1_entries:
            return self._dispatch_parser(bt_id, parser_type, set1_entries)
        return []

    def _try_hockey_period_market(self, market_name: str,
                                  entries: List[Dict]) -> List[ScrapedOdds]:
        """Handle hockey period markets. Map period 1 to H1 bet types."""
        # Filter to period 1 only (sbv = "1")
        p1 = [o for o in entries if str(o.get("specialBetValue", "")) == "1"]
        if not p1:
            return []

        if market_name == "X. trećina - 1X2":
            return self._dispatch_parser(3, '3way', p1)
        if market_name == "X. trećina - oba tima daju gol":
            return self._dispatch_parser(8, 'yn', p1)
        if market_name == "X. trećina - winner DNB":
            return self._dispatch_parser(21, '2way', p1)

        return []

    def _try_team_market(self, market_name: str, entries: List[Dict],
                         team1: str, team2: str,
                         patterns: List, sport_id: int) -> List[ScrapedOdds]:
        """Try to match team-specific market names."""
        mn_lower = market_name.lower()

        for pattern_info in patterns:
            suffix, bt_t1, bt_t2, parser_type = pattern_info[0], pattern_info[1], pattern_info[2], pattern_info[3]

            # Check if market ends with suffix (case-insensitive)
            if not mn_lower.endswith(suffix.lower()):
                # Also check format like "1. poluvreme - {team} ukupno poena"
                if "{}" in suffix:
                    continue
                continue

            # Determine which team this market is for
            bt_id = None
            if team1.lower() in mn_lower:
                bt_id = bt_t1
            elif team2.lower() in mn_lower:
                bt_id = bt_t2

            if bt_id is None:
                continue

            # Don't match half-specific team markets against full-match patterns
            if "poluvreme" in mn_lower or "trećina" in mn_lower or "četvrtina" in mn_lower:
                # Only match if the pattern is meant for halves
                if "poluvreme" not in suffix.lower() and "trećina" not in suffix.lower():
                    continue

            return self._dispatch_parser(bt_id, parser_type, entries)

        # Basketball half-specific team markets
        if sport_id == 2:
            return self._try_basketball_team_half(
                market_name, entries, team1, team2
            )

        return []

    def _try_basketball_team_half(self, market_name: str, entries: List[Dict],
                                  team1: str, team2: str) -> List[ScrapedOdds]:
        """Handle basketball half-specific team totals like '1. poluvreme - Team ukupno poena'."""
        mn_lower = market_name.lower()
        if "1. poluvreme" not in mn_lower or "ukupno poena" not in mn_lower:
            return []

        bt_id = None
        if team1.lower() in mn_lower:
            bt_id = 51  # team1_total_h1
        elif team2.lower() in mn_lower:
            bt_id = 52  # team2_total_h1

        if bt_id:
            return self._dispatch_parser(bt_id, 'ou', entries)
        return []

    @staticmethod
    def _extract_teams(match_name: str) -> Tuple[str, str]:
        """Extract team1/team2 from SuperBet match name (separated by ·)."""
        if "·" in match_name:
            parts = match_name.split("·")
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
        return "", ""

    # ── Scrape orchestration ────────────────────────────────────────

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Scrape all matches for a sport."""
        matches: List[ScrapedMatch] = []

        event_ids = await self.fetch_event_ids(sport_id)
        if not event_ids:
            return matches

        logger.debug(f"[Superbet] Found {len(event_ids)} events for sport {sport_id}")

        # Fetch event details concurrently
        tasks = [self.fetch_event_details(eid) for eid in event_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception) or not result:
                continue

            try:
                data = result.get("data", [{}])[0] if result.get("data") else {}
                match_name = data.get("matchName", "")
                match_date = data.get("matchDate", "")

                # Parse team names (separated by ·)
                teams = match_name.split("·")
                if len(teams) != 2:
                    continue

                team1, team2 = [t.strip() for t in teams]

                start_time = self.parse_timestamp(match_date)
                if not start_time:
                    continue

                scraped = ScrapedMatch(
                    team1=team1,
                    team2=team2,
                    sport_id=sport_id,
                    start_time=start_time,
                    external_id=str(data.get("eventId")),
                )

                scraped.odds = self.parse_odds(data, sport_id)

                if scraped.odds:
                    matches.append(scraped)

            except Exception as e:
                logger.warning(f"[Superbet] Error processing event: {e}")

        return matches
