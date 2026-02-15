"""
TopBet scraper for BetSnipe.ai v2.0

Scrapes odds from TopBet Serbia API (NSoft platform).
Uses two API formats:
- WEB_OVERVIEW (compressed, shortProps=1): event list with basic markets (~16/event)
- WEB_SINGLE_MATCH (full format): individual event with all markets (~52/event)

Compressed format fields: b=marketId, d=variant, n=margin, h=outcomes, e=code, g=price
Full format fields: marketId, name, specialValues, outcomes[{shortcut, name, odd}]
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)

# Sport ID mapping (TopBet/NSoft to internal)
TOPBET_SPORTS = {
    3: 1,   # Football
    1: 2,   # Basketball
    4: 3,   # Tennis
    5: 4,   # Hockey
    27: 5,  # Table Tennis
}

INTERNAL_TO_TOPBET = {v: k for k, v in TOPBET_SPORTS.items()}

# ============================================================================
# BET TYPE DISPATCH MAPS — Overview (compressed) format
# Format: b_code -> (internal_bet_type_id, parser_type)
# Parser types: '3way', '2way', 'btts', 'ou', 'hc_eu', 'sel', 'hvg', 'oe'
# ============================================================================

FOOTBALL_OVERVIEW_MAP = {
    6:    (2,  '3way'),       # KONAČAN ISHOD (1X2)
    345:  (8,  'btts'),       # OBA TIMA DAJU GOL (parse GG/NG only)
    54:   (24, 'sel'),        # POLUVREME - KRAJ (HT/FT)
    36:   (25, 'sel'),        # UKUPNO GOLOVA (total goals range)
    39:   (29, 'sel'),        # I POLUVREME UKUPNO GOLOVA
    45:   (30, 'sel'),        # II POLUVREME UKUPNO GOLOVA
    66:   (27, 'sel'),        # DOMAĆIN UKUPNO GOLOVA (team1 goals)
    69:   (28, 'sel'),        # GOST UKUPNO GOLOVA (team2 goals)
    156:  (35, 'sel'),        # GOLOVI U OBA POLUVREMENA
    168:  (38, 'sel'),        # KONAČAN ISHOD & UKUPNO GOLOVA
    90:   (46, 'sel'),        # OBA TIMA DAJU GOL & UKUPNO GOLOVA
    93:   (44, 'sel'),        # POLUVREME-KRAJ & UKUPNO GOLOVA
    477:  (39, 'sel'),        # KONAČAN ISHOD & OBA TIMA DAJU GOL
    633:  (43, 'sel'),        # DUPLA ŠANSA & OBA TIMA DAJU GOL
    639:  (41, 'sel'),        # DUPLA ŠANSA & UKUPNO GOLOVA
    111:  (47, 'sel'),        # ŠANSA
}

# Full-format only markets (available via WEB_SINGLE_MATCH individual event fetch)
FOOTBALL_FULL_MAP = {
    6:    (2,  '3way'),       # KONAČAN ISHOD (1X2)
    9:    (13, 'dc'),          # DUPLA ŠANSA (DC: 1X/12/X2)
    48:   (3,  '3way'),       # I POLUVREME (H1 1X2)
    51:   (4,  '3way'),       # II POLUVREME (H2 1X2)
    63:   (14, '2way'),       # X VRAĆA ULOG (DNB)
    138:  (16, '2way'),       # DUPLA POBEDA (both halves winner)
    150:  (19, 'hvg'),        # PADA VIŠE GOLOVA (half with more goals)
    1180: (15, 'oe'),         # GOLOVI NEPAR - PAR (odd/even)
    345:  (8,  'btts'),       # OBA TIMA DAJU GOL
    105:  (23, 'sel'),        # TAČAN REZULTAT (correct score)
    54:   (24, 'sel'),        # POLUVREME - KRAJ (HT/FT)
    57:   (37, 'sel'),        # POLUVREME - KRAJ DUPLA ŠANSA
    36:   (25, 'sel'),        # UKUPNO GOLOVA (total goals range)
    39:   (29, 'sel'),        # I POLUVREME UKUPNO GOLOVA
    45:   (30, 'sel'),        # II POLUVREME UKUPNO GOLOVA
    66:   (27, 'sel'),        # DOMAĆIN UKUPNO GOLOVA
    69:   (28, 'sel'),        # GOST UKUPNO GOLOVA
    72:   (31, 'sel'),        # I POLUVREME DOMAĆIN UKUPNO GOLOVA
    75:   (32, 'sel'),        # I POLUVREME GOST UKUPNO GOLOVA
    78:   (33, 'sel'),        # II POLUVREME DOMAĆIN UKUPNO GOLOVA
    81:   (34, 'sel'),        # II POLUVREME GOST UKUPNO GOLOVA
    156:  (35, 'sel'),        # GOLOVI U OBA POLUVREMENA
    168:  (38, 'sel'),        # KONAČAN ISHOD & UKUPNO GOLOVA
    171:  (36, 'sel'),        # KONAČAN ISHOD & PRVI DAJE GOL
    90:   (46, 'sel'),        # OBA TIMA DAJU GOL & UKUPNO GOLOVA
    93:   (44, 'sel'),        # POLUVREME-KRAJ & UKUPNO GOLOVA
    348:  (45, 'sel'),        # POLUVREME - KRAJ & OBA TIMA DAJU GOL
    477:  (39, 'sel'),        # KONAČAN ISHOD & OBA TIMA DAJU GOL
    486:  (40, 'sel'),        # KONAČAN ISHOD & PADA VIŠE GOLOVA
    633:  (43, 'sel'),        # DUPLA ŠANSA & OBA TIMA DAJU GOL
    639:  (41, 'sel'),        # DUPLA ŠANSA & UKUPNO GOLOVA
    111:  (47, 'sel'),        # ŠANSA
    825:  (9,  'hc_eu'),      # EVROPSKI HENDIKEP (European handicap 1X2)
}


# ============================================================================
# NON-FOOTBALL OVERVIEW DISPATCH MAPS
# NSoft uses same market IDs across sports (b=6 is always "KONAČAN ISHOD")
# ============================================================================

BASKETBALL_OVERVIEW_MAP = {
    6:    (1,  '2way'),       # POBEDNIK (winner incl. OT → 2-way)
    345:  (8,  'btts'),       # OBA TIMA DAJU GOL (BTTS)
    54:   (24, 'sel'),        # POLUVREME - KRAJ (HT/FT)
    36:   (25, 'sel'),        # UKUPNO POENA (total points range)
    66:   (27, 'sel'),        # DOMAĆIN UKUPNO (team1 total)
    69:   (28, 'sel'),        # GOST UKUPNO (team2 total)
}

HOCKEY_OVERVIEW_MAP = {
    6:    (2,  '3way'),       # KONAČAN ISHOD (1X2)
    345:  (8,  'btts'),       # OBA TIMA DAJU GOL (BTTS)
}

TENNIS_OVERVIEW_MAP = {
    6:    (1,  '2way'),       # POBEDNIK (match winner → 2-way)
}

TABLE_TENNIS_OVERVIEW_MAP = {
    6:    (1,  '2way'),       # POBEDNIK (match winner → 2-way)
}

# Map sport_id → (overview_map, default_ou_bet_type)
# default_ou_bet_type: which bet type to use for generic O/U fallback
SPORT_DISPATCH = {
    1: (FOOTBALL_OVERVIEW_MAP, 5),       # Football: bt5 (total_over_under)
    2: (BASKETBALL_OVERVIEW_MAP, 10),    # Basketball: bt10 (total_points)
    3: (TENNIS_OVERVIEW_MAP, 5),         # Tennis: bt5 (total_games)
    4: (HOCKEY_OVERVIEW_MAP, 5),         # Hockey: bt5 (total_over_under)
    5: (TABLE_TENNIS_OVERVIEW_MAP, 5),   # Table Tennis: bt5 (total)
}


class TopbetScraper(BaseScraper):
    """
    Scraper for TopBet Serbia (NSoft platform).

    Uses WEB_OVERVIEW for the event list (one API call per sport, ~16 markets
    in compressed format) and optionally WEB_SINGLE_MATCH for individual event
    details (~52 markets in full format).
    """

    def __init__(self):
        super().__init__(bookmaker_id=10, bookmaker_name="Topbet")

    def get_base_url(self) -> str:
        return "https://sports-sm-distribution-api.de-2.nsoftcdn.com/api/v1"

    def get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://topbet.rs",
            "Referer": "https://topbet.rs/"
        }

    def get_supported_sports(self) -> List[int]:
        return [1, 2, 3, 4, 5]

    def _common_params(self) -> Dict[str, str]:
        return {
            "deliveryPlatformId": "3",
            "timezone": "Europe/Budapest",
            "company": "{}",
            "companyUuid": "4dd61a16-9691-4277-9027-8cd05a647844",
        }

    async def fetch_events(self, sport_id: int) -> Optional[Dict]:
        """Fetch event list for a sport using WEB_OVERVIEW (compressed format)."""
        topbet_sport_id = INTERNAL_TO_TOPBET.get(sport_id)
        if topbet_sport_id is None:
            return None

        url = f"{self.get_base_url()}/events"
        params = {
            **self._common_params(),
            "dataFormat": '{"default":"object","events":"array","outcomes":"array"}',
            "language": '{"default":"sr-Latn","events":"sr-Latn","sport":"sr-Latn","category":"sr-Latn","tournament":"sr-Latn","team":"sr-Latn","market":"sr-Latn"}',
            "filter[sportId]": str(topbet_sport_id),
            "filter[from]": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "sort": "categoryPosition,categoryName,tournamentPosition,tournamentName,startsAt",
            "offerTemplate": "WEB_OVERVIEW",
            "shortProps": "1"
        }
        return await self.fetch_json(url, params=params)

    async def fetch_event_detail(self, event_id: str) -> Optional[Dict]:
        """Fetch full event details using WEB_SINGLE_MATCH (full format)."""
        url = f"{self.get_base_url()}/events/{event_id}"
        params = {
            **self._common_params(),
            "language": '{"default":"sr-Latn","events":"sr-Latn","sport":"sr-Latn","category":"sr-Latn","tournament":"sr-Latn","team":"sr-Latn","market":"sr-Latn"}',
            "offerTemplate": "WEB_SINGLE_MATCH",
        }
        return await self.fetch_json(url, params=params)

    # ========================================================================
    # COMPRESSED FORMAT PARSERS (WEB_OVERVIEW)
    # Fields: b=marketId, d=variant, n=margin, h=outcomes, e=code, g=price
    # ========================================================================

    @staticmethod
    def _get_outcome(outcomes: list, code: str) -> Optional[float]:
        """Get outcome price by code from compressed format."""
        for o in outcomes:
            if o.get("e") == code:
                val = o.get("g")
                if val is not None and float(val) > 1.0:
                    return float(val)
        return None

    def _parse_3way_compressed(self, bt_id: int, outcomes: list,
                                margin: float = 0.0) -> List[ScrapedOdds]:
        """Parse 3-way market from compressed format (codes: 1/X/2)."""
        odd1 = self._get_outcome(outcomes, "1")
        oddX = self._get_outcome(outcomes, "X")
        odd2 = self._get_outcome(outcomes, "2")
        if odd1 and oddX and odd2:
            return [ScrapedOdds(bet_type_id=bt_id, odd1=odd1, odd2=oddX,
                                odd3=odd2, margin=margin)]
        return []

    def _parse_2way_compressed(self, bt_id: int, outcomes: list,
                                margin: float = 0.0) -> List[ScrapedOdds]:
        """Parse 2-way market from compressed format (codes: 1/2)."""
        odd1 = self._get_outcome(outcomes, "1")
        odd2 = self._get_outcome(outcomes, "2")
        if odd1 and odd2:
            return [ScrapedOdds(bet_type_id=bt_id, odd1=odd1, odd2=odd2,
                                margin=margin)]
        return []

    def _parse_dc_compressed(self, bt_id: int,
                              outcomes: list) -> List[ScrapedOdds]:
        """Parse double chance from compressed format (codes: 1X/12/X2)."""
        o1X = self._get_outcome(outcomes, "1X")
        o12 = self._get_outcome(outcomes, "12")
        oX2 = self._get_outcome(outcomes, "X2")
        if o1X and o12 and oX2:
            return [ScrapedOdds(bet_type_id=bt_id, odd1=o1X, odd2=o12,
                                odd3=oX2)]
        return []

    def _parse_btts_compressed(self, outcomes: list) -> List[ScrapedOdds]:
        """Parse BTTS from compressed format (codes: GG/NG)."""
        gg = self._get_outcome(outcomes, "GG")
        ng = self._get_outcome(outcomes, "NG")
        if gg and ng:
            return [ScrapedOdds(bet_type_id=8, odd1=gg, odd2=ng)]
        return []

    def _parse_hvg_compressed(self, outcomes: list) -> List[ScrapedOdds]:
        """Parse half-with-more-goals from compressed (codes: I>II/I=II/I<II)."""
        o1 = self._get_outcome(outcomes, "I>II")
        oX = self._get_outcome(outcomes, "I=II")
        o2 = self._get_outcome(outcomes, "I<II")
        if o1 and oX and o2:
            return [ScrapedOdds(bet_type_id=19, odd1=o1, odd2=oX, odd3=o2)]
        return []

    def _parse_oe_compressed(self, outcomes: list) -> List[ScrapedOdds]:
        """Parse odd/even from compressed (codes: Nepar/Par)."""
        odd = self._get_outcome(outcomes, "Nepar")
        even = self._get_outcome(outcomes, "Par")
        if odd and even:
            return [ScrapedOdds(bet_type_id=15, odd1=odd, odd2=even)]
        return []

    def _parse_ou_compressed(self, bt_id: int, outcomes: list,
                              margin: float) -> List[ScrapedOdds]:
        """Parse over/under from compressed (codes: Više/Manje or +/-)."""
        over = self._get_outcome(outcomes, "Više") or self._get_outcome(outcomes, "+")
        under = self._get_outcome(outcomes, "Manje") or self._get_outcome(outcomes, "-")
        if over and under:
            return [ScrapedOdds(bet_type_id=bt_id, odd1=under, odd2=over,
                                margin=margin)]
        return []

    def _parse_hc_eu_compressed(self, outcomes: list,
                                 margin_str: str) -> List[ScrapedOdds]:
        """Parse European handicap from compressed (3-way 1/X/2 with score margin)."""
        # margin_str like "0:1" (away +1), "1:0" (home +1)
        try:
            parts = margin_str.split(":")
            home_hc = int(parts[0])
            away_hc = int(parts[1])
            margin_val = float(home_hc - away_hc)
        except (ValueError, IndexError):
            return []
        return self._parse_3way_compressed(9, outcomes, margin=margin_val)

    # HT/FT-related bet types that need dash-to-slash conversion in selections
    _HTFT_BET_TYPES = {24, 37, 44, 45, 113, 124}

    def _parse_selection_compressed(self, bt_id: int,
                                     outcomes: list) -> List[ScrapedOdds]:
        """Parse selection-based market from compressed format."""
        convert_htft = bt_id in self._HTFT_BET_TYPES
        result = []
        for o in outcomes:
            code = o.get("e", "")
            price = o.get("g")
            if code and price is not None and float(price) > 1.0:
                sel = code.replace("-", "/") if convert_htft else code
                result.append(ScrapedOdds(
                    bet_type_id=bt_id, odd1=float(price), selection=sel
                ))
        return result

    def _dispatch_compressed(self, bt_id: int, parser_type: str,
                              market_data: dict) -> List[ScrapedOdds]:
        """Route compressed market data to the correct parser."""
        outcomes = market_data.get("h", [])
        if not outcomes:
            return []

        margin_raw = market_data.get("n")

        if parser_type == '3way':
            return self._parse_3way_compressed(bt_id, outcomes)
        elif parser_type == '2way':
            return self._parse_2way_compressed(bt_id, outcomes)
        elif parser_type == 'dc':
            return self._parse_dc_compressed(bt_id, outcomes)
        elif parser_type == 'btts':
            return self._parse_btts_compressed(outcomes)
        elif parser_type == 'hvg':
            return self._parse_hvg_compressed(outcomes)
        elif parser_type == 'oe':
            return self._parse_oe_compressed(outcomes)
        elif parser_type == 'ou':
            if margin_raw is not None:
                try:
                    margin = float(margin_raw)
                except (ValueError, TypeError):
                    return []
                return self._parse_ou_compressed(bt_id, outcomes, margin)
            return []
        elif parser_type == 'hc_eu':
            if margin_raw is not None:
                return self._parse_hc_eu_compressed(outcomes, str(margin_raw))
            return []
        elif parser_type == 'sel':
            return self._parse_selection_compressed(bt_id, outcomes)
        return []

    # ========================================================================
    # FULL FORMAT PARSERS (WEB_SINGLE_MATCH)
    # Fields: marketId, name, specialValues, outcomes[{shortcut, name, odd}]
    # ========================================================================

    @staticmethod
    def _get_outcome_full(outcomes: list, code: str) -> Optional[float]:
        """Get outcome price by shortcut code from full format."""
        for o in outcomes:
            if o.get("shortcut") == code:
                val = o.get("odd")
                if val is not None and float(val) > 1.0:
                    return float(val)
        return None

    def _parse_3way_full(self, bt_id: int, outcomes: list,
                          margin: float = 0.0) -> List[ScrapedOdds]:
        odd1 = self._get_outcome_full(outcomes, "1")
        oddX = self._get_outcome_full(outcomes, "X")
        odd2 = self._get_outcome_full(outcomes, "2")
        if odd1 and oddX and odd2:
            return [ScrapedOdds(bet_type_id=bt_id, odd1=odd1, odd2=oddX,
                                odd3=odd2, margin=margin)]
        return []

    def _parse_2way_full(self, bt_id: int,
                          outcomes: list) -> List[ScrapedOdds]:
        odd1 = self._get_outcome_full(outcomes, "1")
        odd2 = self._get_outcome_full(outcomes, "2")
        if odd1 and odd2:
            return [ScrapedOdds(bet_type_id=bt_id, odd1=odd1, odd2=odd2)]
        return []

    def _parse_dc_full(self, bt_id: int,
                        outcomes: list) -> List[ScrapedOdds]:
        o1X = self._get_outcome_full(outcomes, "1X")
        o12 = self._get_outcome_full(outcomes, "12")
        oX2 = self._get_outcome_full(outcomes, "X2")
        if o1X and o12 and oX2:
            return [ScrapedOdds(bet_type_id=bt_id, odd1=o1X, odd2=o12,
                                odd3=oX2)]
        return []

    def _parse_btts_full(self, outcomes: list) -> List[ScrapedOdds]:
        gg = self._get_outcome_full(outcomes, "GG")
        ng = self._get_outcome_full(outcomes, "NG")
        if gg and ng:
            return [ScrapedOdds(bet_type_id=8, odd1=gg, odd2=ng)]
        return []

    def _parse_hvg_full(self, outcomes: list) -> List[ScrapedOdds]:
        o1 = self._get_outcome_full(outcomes, "I>II")
        oX = self._get_outcome_full(outcomes, "I=II")
        o2 = self._get_outcome_full(outcomes, "I<II")
        if o1 and oX and o2:
            return [ScrapedOdds(bet_type_id=19, odd1=o1, odd2=oX, odd3=o2)]
        return []

    def _parse_oe_full(self, outcomes: list) -> List[ScrapedOdds]:
        odd = self._get_outcome_full(outcomes, "Nepar")
        even = self._get_outcome_full(outcomes, "Par")
        if odd and even:
            return [ScrapedOdds(bet_type_id=15, odd1=odd, odd2=even)]
        return []

    def _parse_selection_full(self, bt_id: int,
                               outcomes: list) -> List[ScrapedOdds]:
        convert_htft = bt_id in self._HTFT_BET_TYPES
        result = []
        for o in outcomes:
            code = o.get("shortcut", "")
            price = o.get("odd")
            if code and price is not None and float(price) > 1.0:
                sel = code.replace("-", "/") if convert_htft else code
                result.append(ScrapedOdds(
                    bet_type_id=bt_id, odd1=float(price), selection=sel
                ))
        return result

    def _dispatch_full(self, bt_id: int, parser_type: str,
                        market_data: dict) -> List[ScrapedOdds]:
        """Route full-format market data to the correct parser."""
        outcomes = market_data.get("outcomes", [])
        if not outcomes:
            return []

        svs = market_data.get("specialValues", [])

        if parser_type == '3way':
            return self._parse_3way_full(bt_id, outcomes)
        elif parser_type == '2way':
            return self._parse_2way_full(bt_id, outcomes)
        elif parser_type == 'dc':
            return self._parse_dc_full(bt_id, outcomes)
        elif parser_type == 'btts':
            return self._parse_btts_full(outcomes)
        elif parser_type == 'hvg':
            return self._parse_hvg_full(outcomes)
        elif parser_type == 'oe':
            return self._parse_oe_full(outcomes)
        elif parser_type == 'hc_eu':
            # European handicap: specialValues like ['0:1']
            if svs:
                try:
                    parts = str(svs[0]).split(":")
                    margin = float(int(parts[0]) - int(parts[1]))
                except (ValueError, IndexError):
                    return []
                return self._parse_3way_full(9, outcomes, margin=margin)
            return []
        elif parser_type == 'sel':
            return self._parse_selection_full(bt_id, outcomes)
        return []

    # ========================================================================
    # OVERVIEW ODDS PARSING (compressed format from event list)
    # ========================================================================

    def parse_overview_odds(self, event: Dict, sport_id: int) -> List[ScrapedOdds]:
        """Parse odds from WEB_OVERVIEW compressed format."""
        markets = event.get("o", {})
        if not markets:
            return []

        result = []

        # Get sport-specific dispatch map and O/U bet type
        sport_config = SPORT_DISPATCH.get(sport_id)
        if sport_config:
            dispatch_map, ou_bt = sport_config
        else:
            dispatch_map, ou_bt = {}, 5

        for _mid, mdata in markets.items():
            b = mdata.get("b")
            outcomes = mdata.get("h", [])
            margin_raw = mdata.get("n")

            # Check dispatch map first
            if b in dispatch_map:
                bt_id, parser_type = dispatch_map[b]
                result.extend(self._dispatch_compressed(
                    bt_id, parser_type, mdata))
                continue

            # Generic O/U handler for any market with margin + Više/Manje
            if margin_raw is not None and outcomes:
                try:
                    margin_val = float(margin_raw)
                except (ValueError, TypeError):
                    continue
                over = self._get_outcome(outcomes, "Više") or \
                       self._get_outcome(outcomes, "+")
                under = self._get_outcome(outcomes, "Manje") or \
                        self._get_outcome(outcomes, "-")
                if over and under:
                    result.append(ScrapedOdds(
                        bet_type_id=ou_bt, odd1=under, odd2=over,
                        margin=margin_val))
                    continue

            logger.debug(f"[TopBet] Unmapped market b={b} sport={sport_id}")

        return result

    # ========================================================================
    # FULL DETAIL ODDS PARSING (full format from individual event fetch)
    # ========================================================================

    def parse_full_odds(self, event_data: Dict,
                        sport_id: int) -> List[ScrapedOdds]:
        """Parse odds from WEB_SINGLE_MATCH full format."""
        markets = event_data.get("markets", [])
        if not markets:
            return []

        result = []

        if sport_id == 1:
            dispatch_map = FOOTBALL_FULL_MAP
        else:
            dispatch_map = {}

        for mdata in (markets if isinstance(markets, list)
                      else markets.values()):
            mid = mdata.get("marketId")

            if mid in dispatch_map:
                bt_id, parser_type = dispatch_map[mid]
                result.extend(self._dispatch_full(
                    bt_id, parser_type, mdata))

        # For non-football, parse basic winner/1X2
        if sport_id != 1:
            for mdata in (markets if isinstance(markets, list)
                          else markets.values()):
                if mdata.get("marketId") != 6:
                    continue
                outcomes = mdata.get("outcomes", [])
                if sport_id in (2, 3, 5):
                    parsed = self._parse_2way_full(1, outcomes)
                elif sport_id == 4:
                    parsed = self._parse_3way_full(2, outcomes)
                else:
                    continue
                result.extend(parsed)
                break

        return result

    # ========================================================================
    # MAIN SCRAPE LOGIC
    # ========================================================================

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Scrape all matches for a sport.

        Uses WEB_OVERVIEW (single API call) for all events. The overview
        provides ~16 markets per event in compressed format, covering the
        main bet types (1X2, BTTS, HT/FT, goal ranges, team totals, combos).

        The full-format parsers (parse_full_odds, fetch_event_detail) are
        available for targeted use but not called here due to the high event
        count (~500+ football events would require too many individual calls).
        """
        matches: List[ScrapedMatch] = []

        data = await self.fetch_events(sport_id)
        if not data or "data" not in data or "events" not in data["data"]:
            return matches

        events = data["data"]["events"]
        logger.debug(f"[Topbet] Found {len(events)} events for sport {sport_id}")

        for event in events:
            try:
                match_name = event.get("j", "")
                teams = match_name.split(" - ")
                if len(teams) != 2:
                    continue

                team1, team2 = teams

                start_time_str = event.get("n")
                if not start_time_str:
                    continue
                try:
                    start_time = datetime.strptime(
                        start_time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                except ValueError:
                    start_time = self.parse_timestamp(start_time_str)
                    if not start_time:
                        continue

                scraped = ScrapedMatch(
                    team1=team1,
                    team2=team2,
                    sport_id=sport_id,
                    start_time=start_time,
                    external_id=str(event.get("a")),
                )

                scraped.odds = self.parse_overview_odds(event, sport_id)

                if scraped.odds:
                    matches.append(scraped)

            except Exception as e:
                logger.warning(f"[Topbet] Error processing event: {e}")

        return matches
