"""
Mozzart Bet scraper v3.0 — Mobile API Edition

Uses the undocumented mobile API at api-gateway.mozzartbet.com
with tls_client for Cloudflare TLS fingerprint bypass.

No Playwright, no browser, no headless Chrome needed.

Endpoints:
  POST /mobile-content-service/mobile/sports       → list sports/competitions
  POST /mobile-content-service/mobile/matches       → matches for a competition
  POST /mobile-content-service/mobile/match-by-id   → match details + odds

Auth: Basic YW5kcm9pZDpkanVzYW1lbnRvbA== (android:djusamentol)
TLS:  tls_client with chrome_120 profile
"""

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional, List, Dict

import tls_client

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)


# Sport ID mapping (Mozzart → internal)
MOZZART_SPORTS = {
    1: 1,   # Fudbal (Football)
    2: 2,   # Kosarka (Basketball)
    5: 3,   # Tenis (Tennis)
    4: 4,   # Hokej (Hockey)
    9: 5,   # Stoni tenis (Table Tennis)
}
INTERNAL_TO_MOZZART = {v: k for k, v in MOZZART_SPORTS.items()}


# ============================================================
# API Client
# ============================================================

class MozzartMobileAPI:
    """Lightweight HTTP client for Mozzart's mobile API."""

    BASE = "https://api-gateway.mozzartbet.com/mobile-content-service/mobile"

    def __init__(self):
        self.session = tls_client.Session(client_identifier="chrome_120")
        self._request_count = 0
        self._error_count = 0

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": "Basic YW5kcm9pZDpkanVzYW1lbnRvbA==",
            "Content-Type": "application/json",
            "User-Agent": "AndroidClientApp/bosna",
            "moz-origin": "ANDROID",
            "origin-app-name": "mozzart-betting-and-app-v3",
            "correlationId": str(uuid.uuid4()),
        }

    def _post(self, path: str, payload: Dict) -> Optional[Dict]:
        """Make a POST request. Returns parsed JSON or None."""
        self._request_count += 1
        url = f"{self.BASE}{path}"
        try:
            r = self.session.post(url, headers=self._headers, json=payload)
            if r.status_code == 200:
                return r.json()
            logger.warning(f"[Mozzart] {r.status_code} for {path}")
            self._error_count += 1
            return None
        except Exception as e:
            logger.warning(f"[Mozzart] Error {path}: {e}")
            self._error_count += 1
            return None

    def get_sports(self, mozzart_sport_id: int) -> Optional[Dict]:
        """Get sports overview (competition list with match counts)."""
        return self._post("/sports", {
            "groupationId": 1,
            "sportIds": [mozzart_sport_id],
            "orderType": "BY_COMPETITION",
            "uberOffer": True,
            "packGroupsInMatch": True,
        })

    def get_matches(self, filter_payload: Dict) -> Optional[Dict]:
        """Fetch matches using a filter object returned by /sports."""
        filter_payload["groupationId"] = 1
        return self._post("/matches", filter_payload)

    def get_match_details(self, match_id: int) -> Optional[Dict]:
        """Get full match details including all odds groups."""
        return self._post("/match-by-id", {
            "groupationId": 1,
            "matchId": match_id,
            "pageSize": 100,
            "currentPage": 0,
            "matchTypeId": 0,
            "orderType": "BY_COMPETITION",
            "offerType": "PRE_MATCH",
            "loadPriorityTemplateGamesOnly": False,
            "loadAllTemplateGames": True,
            "packGamesGroupBySport": False,
            "medium": "ANDROID",
            "loadExtendedOffer": True,
            "packGroupsInMatch": True,
            "uberOffer": True,
            "sportsLoad": True,
            "tspMatchLoad": True,
        })


# ============================================================
# Odds parsers (ported from v2.0 — same Mozzart data format)
# ============================================================

class OddsParser:
    """Static parsing methods for Mozzart odds groups."""

    # ---- Football group map ----
    FOOTBALL_GROUP_MAP = {
        "Konačan ishod":                ("_parse_1x2", 2),
        "Dupla šansa":                  ("_parse_three_way", 13),
        "Ukupno golova - Par/Nepar":    ("_parse_odd_even", 15),
        "Winner":                       ("_parse_two_way", 14),
        "Dupla pobeda":                 ("_parse_two_way", 16),
        "Sigurna pobeda":               ("_parse_two_way", 17),
        "Daje prvi gol":                ("_parse_1x2", 18),
        "Poluvreme sa više golova":     ("_parse_1x2", 19),
        "Prvo poluvreme":               ("_parse_1x2", 3),
        "Dupla šansa prvo poluvreme":   ("_parse_three_way", 20),
        "Winner prvo poluvreme":        ("_parse_two_way", 21),
        "Drugo poluvreme":              ("_parse_1x2", 4),
        "Prolazi dalje":                ("_parse_two_way", 22),
        "Dupla šansa drugo poluvreme":  ("_parse_three_way", 75),
        "Winner drugo poluvreme":       ("_parse_two_way", 76),
        "Ukupno golova - Par/Nepar prvo poluvreme":  ("_parse_odd_even", 77),
        "Ukupno golova prvo poluvreme - Par/Nepar":  ("_parse_odd_even", 77),
        "Ukupno golova - Par/Nepar drugo poluvreme": ("_parse_odd_even", 78),
        "Ukupno golova drugo poluvreme - Par/Nepar": ("_parse_odd_even", 78),
        "Tačan rezultat":               ("_parse_selection", 23),
        "Tačan rezultat prvog poluvremena":  ("_parse_selection", 79),
        "Tačan rezultat I poluvreme":        ("_parse_selection", 79),
        "Poluvreme - Kraj":             ("_parse_selection", 24),
        "Ukupno golova na meču":        ("_parse_selection", 25),
        "Tačan broj golova na meču":    ("_parse_selection", 26),
        "Tim 1 daje gol":               ("_parse_selection", 27),
        "Tim 2 daje gol":               ("_parse_selection", 28),
        "Ukupno golova prvo poluvreme":             ("_parse_selection", 29),
        "Ukupno golova drugo poluvreme":            ("_parse_selection", 30),
        "Tim 1 golovi prvo poluvreme":              ("_parse_selection", 31),
        "Tim 2 golovi prvo poluvreme":              ("_parse_selection", 32),
        "Tim 1 golovi drugo poluvreme":             ("_parse_selection", 33),
        "Tim 2 golovi drugo poluvreme":             ("_parse_selection", 34),
        "Broj golova u prvom i drugom poluvremenu": ("_parse_selection", 35),
        "Daje prvi gol - Kraj":                     ("_parse_selection", 36),
        "Poluvreme- Kraj / Dupla šansa":            ("_parse_selection", 37),
        "Konačan ishod + Golovi":                   ("_parse_selection", 38),
        "Konačan ishod kombinazzije":               ("_parse_selection", 39),
        "Konačan ishod + Više golova prvo ili drugo poluvreme": ("_parse_selection", 40),
        "Dupla šansa + Golovi":                     ("_parse_selection", 41),
        "Dupla šansa + Više golova prvo ili drugo poluvreme":   ("_parse_selection", 42),
        "Dupla šansa kombinazzije":                 ("_parse_selection", 43),
        "Poluvreme - Kraj + Golovi":                ("_parse_selection", 44),
        "Poluvreme - Kraj kombinazzije":            ("_parse_selection", 45),
        "Mozzart šansa":                            ("_parse_selection", 47),
    }

    # ---- Basketball group map ----
    BASKETBALL_GROUP_MAP = {
        "Konačan ishod":                          ("_parse_1x2", 2),
        "Pobednik meča sa ev. produžecima":       ("_parse_two_way", 1),
        "Dupla šansa":                            ("_parse_two_way", 13),
        "Prvo poluvreme":                         ("_parse_1x2", 3),
        "Dupla pobeda":                           ("_parse_two_way", 16),
        "Dupla šansa prvo poluvreme":             ("_parse_two_way", 20),
        "Poluvreme sa više poena":                ("_parse_three_way", 19),
        "Poluvreme - kraj":                       ("_parse_selection", 24),
        "Četvrtina sa najviše poena":             ("_parse_selection", 54),
    }
    BASKETBALL_MARGIN_MAP = {
        "Ukupno poena na meču":                   10,
        "Ukupno poena Tim 1":                     48,
        "Ukupno poena Tim 2":                     49,
        "Ukupno poena prvo poluvreme":            6,
        "Ukupno poena prvo poluvreme Tim 1":      51,
        "Ukupno poena prvo poluvreme Tim 2":      52,
        "Ukupno poena drugo poluvreme":           7,
        "Ukupno poena najefikasnija četvrtina":   53,
    }
    BASKETBALL_COMBO_MARGIN_MAP = {
        "Konačan ishod + Ukupno poena":                       38,
        "Prvo poluvreme + Ukupno poena prvo poluvreme":       55,
    }

    # ---- Tennis group map ----
    TENNIS_GROUP_MAP = {
        "Konačan ishod":                                           ("_parse_two_way", 1),
        "Prvi set":                                                ("_parse_two_way", 57),
        "Prvi set - Kraj":                                         ("_parse_selection", 64),
        "Tačan broj setova":                                       ("_parse_selection", 65),
        "Ukupno gemova - Par/Nepar":                               ("_parse_odd_even", 15),
        "Rangovi gemova prvi set":                                 ("_parse_selection", 66),
        "Ukupno gemova prvi set - Par/Nepar":                      ("_parse_odd_even", 59),
        "Tajbrejk u prvom setu - Da/Ne":                           ("_parse_two_way", 60),
        "Rangovi gemova drugi set":                                ("_parse_selection", 67),
        "Ukupno gemova drugi set - Par/Nepar":                     ("_parse_odd_even", 61),
        "Tajbrejk u drugom setu - Da/Ne":                          ("_parse_two_way", 62),
        "Pobeda igrača 1 + Gemovi prvi set":                       ("_parse_selection", 69),
        "Pobeda igrača 1 + Gemovi prvi set - Par/Nepar":           ("_parse_two_way", 70),
        "Pobeda igrača 2 + Gemovi prvi set":                       ("_parse_selection", 71),
        "Pobeda igrača 2 + Gemovi prvi set - Par/Nepar":           ("_parse_two_way", 72),
        "Konačan ishod + Više gemova - Prvi ili drugi set":        ("_parse_selection", 73),
        "Više gemova - Prvi ili drugi set":                        ("_parse_three_way", 63),
    }
    TENNIS_MARGIN_MAP = {
        "Ukupno gemova":            5,
        "Ukupno gemova u 1. setu":  6,
        "Ukupno gemova u 2. setu":  7,
    }
    TENNIS_COMBO_MARGIN_MAP = {
        "Mozzart kombinazzije":          68,
        "Konačan ishod + Ukupno gemova": 68,
    }
    TENNIS_HANDICAP_MAP = {
        "Hendikep setova":           56,
        "Hendikep gemova":           9,
        "Hendikep gemova u 1. setu": 58,
    }

    # ---- Hockey group map ----
    HOCKEY_GROUP_MAP = {
        "Konačan ishod":                ("_parse_1x2", 2),
        "Dupla šansa":                  ("_parse_three_way", 13),
        "Winner":                       ("_parse_two_way", 14),
        "Prva trećina":                 ("_parse_1x2", 3),
        "Ukupno golova":                ("_parse_selection", 25),
        "Konačan ishod + Golovi":       ("_parse_selection", 38),
        "Prva trećina + Golovi":        ("_parse_selection", 74),
        "Prva trećina - Kraj":          ("_parse_selection", 24),
        "Ukupno golova prva trećina":   ("_parse_selection", 29),
        "Ukupno golova druga trećina":  ("_parse_selection", 30),
    }
    HOCKEY_MARGIN_MAP = {
        "Ukupno golova":                5,
        "Ukupno golova prva trećina":   6,
    }

    # ========== primitive parsers ==========

    @staticmethod
    def _parse_1x2(odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        collected = {}
        for odd in odds_group.get("odds", []):
            subgame_name = odd.get("subgame", {}).get("name", "")
            try:
                value = float(odd.get("value", 0))
            except (ValueError, TypeError):
                continue
            if value > 0 and subgame_name in ("1", "X", "2"):
                collected[subgame_name] = value
        if "1" in collected and "X" in collected and "2" in collected:
            return [ScrapedOdds(bet_type_id=bet_type_id, odd1=collected["1"], odd2=collected["X"], odd3=collected["2"])]
        return []

    @staticmethod
    def _parse_three_way(odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        values = []
        for odd in sorted(odds_group.get("odds", []), key=lambda o: o.get("subgame", {}).get("rank", 0)):
            try:
                value = float(odd.get("value", 0))
            except (ValueError, TypeError):
                continue
            if value > 0:
                values.append(value)
        if len(values) == 3:
            return [ScrapedOdds(bet_type_id=bet_type_id, odd1=values[0], odd2=values[1], odd3=values[2])]
        return []

    @staticmethod
    def _parse_two_way(odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        values = []
        for odd in sorted(odds_group.get("odds", []), key=lambda o: o.get("subgame", {}).get("rank", 0)):
            try:
                value = float(odd.get("value", 0))
            except (ValueError, TypeError):
                continue
            if value > 0:
                values.append(value)
        if len(values) == 2:
            return [ScrapedOdds(bet_type_id=bet_type_id, odd1=values[0], odd2=values[1])]
        return []

    @staticmethod
    def _parse_selection(odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        result = []
        for odd in odds_group.get("odds", []):
            subgame_name = odd.get("subgame", {}).get("name", "")
            if not subgame_name:
                continue
            try:
                value = float(odd.get("value", 0))
            except (ValueError, TypeError):
                continue
            if value > 0:
                result.append(ScrapedOdds(bet_type_id=bet_type_id, odd1=value, selection=subgame_name))
        return result

    @staticmethod
    def _parse_odd_even(odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        odd_val = even_val = None
        for odd in odds_group.get("odds", []):
            name = odd.get("subgame", {}).get("name", "").upper()
            try:
                value = float(odd.get("value", 0))
            except (ValueError, TypeError):
                continue
            if value <= 0:
                continue
            if name == "NEPAR":
                odd_val = value
            elif name == "PAR":
                even_val = value
        if odd_val and even_val:
            return [ScrapedOdds(bet_type_id=bet_type_id, odd1=odd_val, odd2=even_val)]
        return []

    @staticmethod
    def _parse_btts_group(odds_group: Dict) -> List[ScrapedOdds]:
        simple = {}
        combos = []
        for odd in odds_group.get("odds", []):
            subgame_name = odd.get("subgame", {}).get("name", "")
            try:
                value = float(odd.get("value", 0))
            except (ValueError, TypeError):
                continue
            if value <= 0:
                continue
            name_lower = subgame_name.lower()
            if name_lower == "da":
                simple["gg"] = value
            elif name_lower == "ne":
                simple["ng"] = value
            else:
                combos.append(ScrapedOdds(bet_type_id=46, odd1=value, selection=subgame_name))
        result = []
        if simple.get("gg") and simple.get("ng"):
            result.append(ScrapedOdds(bet_type_id=8, odd1=simple["gg"], odd2=simple["ng"]))
        result.extend(combos)
        return result

    @staticmethod
    def _parse_handicap_group(odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        collected = {}
        margin = None
        for odd in odds_group.get("odds", []):
            sv = odd.get("specialOddValue", "")
            subgame = odd.get("subgame", {}).get("name", "")
            try:
                value = float(odd.get("value", 0))
                if sv:
                    margin = float(sv)
            except (ValueError, TypeError):
                continue
            if value > 0 and subgame in ("1", "2", "H1", "H2"):
                key = subgame[-1]
                collected[key] = value
        if "1" in collected and "2" in collected and margin is not None:
            return [ScrapedOdds(bet_type_id=bet_type_id, odd1=collected["1"], odd2=collected["2"], margin=margin)]
        return []

    @staticmethod
    def _parse_ou_group(odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        collected = {}
        margin = None
        for odd in odds_group.get("odds", []):
            sv = odd.get("specialOddValue", "")
            subgame = odd.get("subgame", {}).get("name", "")
            try:
                value = float(odd.get("value", 0))
                if sv:
                    margin = float(sv)
            except (ValueError, TypeError):
                continue
            if value > 0:
                if subgame == "manje":
                    collected["under"] = value
                elif subgame == "više":
                    collected["over"] = value
        if "under" in collected and "over" in collected and margin is not None:
            return [ScrapedOdds(bet_type_id=bet_type_id, odd1=collected["over"], odd2=collected["under"], margin=margin)]
        return []

    @staticmethod
    def _parse_selection_margin_group(odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        result = []
        for odd in odds_group.get("odds", []):
            subgame = odd.get("subgame", {}).get("name", "")
            sv = odd.get("specialOddValue", "")
            if not subgame:
                continue
            try:
                value = float(odd.get("value", 0))
                margin = float(sv) if sv else 0.0
            except (ValueError, TypeError):
                continue
            if value > 0:
                result.append(ScrapedOdds(bet_type_id=bet_type_id, odd1=value, selection=subgame, margin=margin))
        return result

    # ========== O/U across all groups (football) ==========

    @staticmethod
    def _parse_ou_markets(match: Dict) -> List[ScrapedOdds]:
        total_goals = {}
        total_goals_h1 = {}
        total_goals_h2 = {}

        for odds_group in match.get("oddsGroup", []):
            group_name = odds_group.get("groupName", "").lower()
            for odd in odds_group.get("odds", []):
                if odd.get("oddStatus") == "DEACTIVATED":
                    continue
                special_value = odd.get("specialOddValue", "")
                value_type = odd.get("game", {}).get("specialOddValueType", "")
                subgame_name = odd.get("subgame", {}).get("name", "")
                if value_type != "MARGIN" or not special_value:
                    continue
                try:
                    value = float(odd.get("value", 0))
                    total = float(special_value)
                except (ValueError, TypeError):
                    continue
                if value <= 0:
                    continue
                if "1. poluvreme" in group_name or "pp" in group_name:
                    total_goals_h1.setdefault(total, {})
                    if subgame_name == "manje":
                        total_goals_h1[total]["under"] = value
                    elif subgame_name == "više":
                        total_goals_h1[total]["over"] = value
                elif "2. poluvreme" in group_name or "dp" in group_name:
                    total_goals_h2.setdefault(total, {})
                    if subgame_name == "manje":
                        total_goals_h2[total]["under"] = value
                    elif subgame_name == "više":
                        total_goals_h2[total]["over"] = value
                else:
                    total_goals.setdefault(total, {})
                    if subgame_name == "manje":
                        total_goals[total]["under"] = value
                    elif subgame_name == "više":
                        total_goals[total]["over"] = value

        odds_list = []
        for total, t in total_goals.items():
            if "under" in t and "over" in t:
                odds_list.append(ScrapedOdds(bet_type_id=5, odd1=t["over"], odd2=t["under"], margin=total))
        for total, t in total_goals_h1.items():
            if "under" in t and "over" in t:
                odds_list.append(ScrapedOdds(bet_type_id=6, odd1=t["over"], odd2=t["under"], margin=total))
        for total, t in total_goals_h2.items():
            if "under" in t and "over" in t:
                odds_list.append(ScrapedOdds(bet_type_id=7, odd1=t["over"], odd2=t["under"], margin=total))
        return odds_list

    # ========== sport-level dispatchers ==========

    @classmethod
    def _dispatch_groups(cls, match: Dict, group_map: Dict,
                         margin_map: Dict = None, combo_margin_map: Dict = None,
                         handicap_map: Dict = None) -> List[ScrapedOdds]:
        """Generic dispatcher for any sport's odds groups."""
        odds_list = []

        for odds_group in match.get("oddsGroup", []):
            active_odds = [o for o in odds_group.get("odds", []) if o.get("oddStatus") != "DEACTIVATED"]
            if not active_odds:
                continue
            filtered_group = {**odds_group, "odds": active_odds}
            group_name = odds_group.get("groupName", "")

            # Detect specialOddValueType
            first_type = ""
            for odd in active_odds:
                vt = odd.get("game", {}).get("specialOddValueType", "")
                if vt and vt != "NONE":
                    first_type = vt
                    break

            if first_type == "HANDICAP":
                if handicap_map:
                    hc_bt = handicap_map.get(group_name)
                    if hc_bt is not None:
                        odds_list.extend(cls._parse_handicap_group(filtered_group, hc_bt))
                else:
                    bt = 50 if "poluvreme" in group_name.lower() else 9
                    odds_list.extend(cls._parse_handicap_group(filtered_group, bt))

            elif first_type == "MARGIN":
                if combo_margin_map:
                    combo_bt = combo_margin_map.get(group_name)
                    if combo_bt is not None:
                        odds_list.extend(cls._parse_selection_margin_group(filtered_group, combo_bt))
                        continue
                if margin_map:
                    ou_bt = margin_map.get(group_name)
                    if ou_bt is not None:
                        odds_list.extend(cls._parse_ou_group(filtered_group, ou_bt))

            else:
                # Special handling for BTTS
                if group_name == "Oba tima daju gol":
                    odds_list.extend(cls._parse_btts_group(filtered_group))
                    continue

                mapping = group_map.get(group_name)
                if mapping:
                    handler_name, bet_type_id = mapping
                    handler = getattr(cls, handler_name)
                    odds_list.extend(handler(filtered_group, bet_type_id))

        return odds_list

    @classmethod
    def parse_football(cls, match: Dict) -> List[ScrapedOdds]:
        odds = cls._parse_ou_markets(match)
        odds.extend(cls._dispatch_groups(match, cls.FOOTBALL_GROUP_MAP))
        return odds

    @classmethod
    def parse_basketball(cls, match: Dict) -> List[ScrapedOdds]:
        return cls._dispatch_groups(
            match, cls.BASKETBALL_GROUP_MAP,
            margin_map=cls.BASKETBALL_MARGIN_MAP,
            combo_margin_map=cls.BASKETBALL_COMBO_MARGIN_MAP,
        )

    @classmethod
    def parse_tennis(cls, match: Dict) -> List[ScrapedOdds]:
        return cls._dispatch_groups(
            match, cls.TENNIS_GROUP_MAP,
            margin_map=cls.TENNIS_MARGIN_MAP,
            combo_margin_map=cls.TENNIS_COMBO_MARGIN_MAP,
            handicap_map=cls.TENNIS_HANDICAP_MAP,
        )

    @classmethod
    def parse_hockey(cls, match: Dict) -> List[ScrapedOdds]:
        return cls._dispatch_groups(
            match, cls.HOCKEY_GROUP_MAP,
            margin_map=cls.HOCKEY_MARGIN_MAP,
        )

    @classmethod
    def parse_table_tennis(cls, match: Dict) -> List[ScrapedOdds]:
        winner_odds = {"1": 0.0, "2": 0.0}
        for odds_group in match.get("oddsGroup", []):
            for odd in odds_group.get("odds", []):
                game_name = odd.get("game", {}).get("name", "")
                subgame_name = odd.get("subgame", {}).get("name", "")
                try:
                    value = float(odd.get("value", 0))
                except (ValueError, TypeError):
                    continue
                if game_name == "Pobednik meča":
                    if subgame_name == "1":
                        winner_odds["1"] = value
                    elif subgame_name == "2":
                        winner_odds["2"] = value
        if winner_odds["1"] and winner_odds["2"]:
            return [ScrapedOdds(bet_type_id=1, odd1=winner_odds["1"], odd2=winner_odds["2"])]
        return []

    @classmethod
    def parse(cls, match: Dict, sport_id: int) -> List[ScrapedOdds]:
        parsers = {1: cls.parse_football, 2: cls.parse_basketball,
                   3: cls.parse_tennis, 4: cls.parse_hockey, 5: cls.parse_table_tennis}
        parser = parsers.get(sport_id)
        return parser(match) if parser else []


# ============================================================
# Main scraper (inherits from BaseScraper)
# ============================================================

class MozzartScraper(BaseScraper):
    """
    Mozzart Bet scraper v3.0 — Mobile API edition.

    Uses tls_client to hit the mobile API directly.
    No Playwright, no browser needed.

    Flow:  /sports → iterate competitions → /matches (paginated)
           → /match-by-id (parallel via ThreadPool) → parse odds
    """

    MAX_WORKERS = 5

    def __init__(self):
        super().__init__(bookmaker_id=1, bookmaker_name="Mozzart")
        self._api = MozzartMobileAPI()
        self._executor = ThreadPoolExecutor(max_workers=self.MAX_WORKERS)

    def get_base_url(self) -> str:
        return MozzartMobileAPI.BASE

    def get_supported_sports(self) -> List[int]:
        return [1, 2, 3, 4, 5]

    @staticmethod
    def _parse_timestamp(ts) -> Optional[datetime]:
        """Parse Mozzart timestamp (epoch millis or ISO string)."""
        if not ts:
            return None
        try:
            if isinstance(ts, (int, float)):
                return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _restructure_odds(match_item: Dict) -> Dict:
        """Transform mobile API flat odds[] into oddsGroup[] for parsers.

        Mobile API returns: match.odds[] with game.name per odd
        Parsers expect:     match.oddsGroup[] with groupName and nested odds[]
        """
        flat_odds = match_item.get("odds", [])
        if not flat_odds:
            return match_item

        groups = {}
        for odd in flat_odds:
            game_name = odd.get("game", {}).get("name", "Unknown")
            if game_name not in groups:
                groups[game_name] = []
            groups[game_name].append(odd)

        odds_groups = []
        for group_name, odds in groups.items():
            odds_groups.append({
                "groupName": group_name,
                "odds": odds,
            })

        match_item["oddsGroup"] = odds_groups
        return match_item

    def _scrape_sport_sync(self, sport_id: int) -> List[ScrapedMatch]:
        """Synchronous implementation of sport scraping."""
        mozzart_sport_id = INTERNAL_TO_MOZZART.get(sport_id)
        if mozzart_sport_id is None:
            return []

        matches: List[ScrapedMatch] = []
        seen = set()
        debug_logged = False

        # Step 1: get competitions for this sport
        sports_data = self._api.get_sports(mozzart_sport_id)
        if not sports_data or not sports_data.get("items"):
            logger.warning(f"[Mozzart] No data from /sports for sport {sport_id}")
            return []

        competitions = sports_data["items"]
        logger.info(f"[Mozzart] Sport {sport_id}: found {len(competitions)} competitions")

        # Step 2: for each competition, fetch matches (with pagination)
        for comp in competitions:
            comp_name = comp.get("name", "Unknown")
            comp_filter = comp.get("filter")
            if not comp_filter:
                continue

            comp_filter["groupationId"] = 1
            comp_filter["uberOffer"] = True
            comp_filter["packGroupsInMatch"] = True

            all_match_items = []
            page = 0
            while True:
                comp_filter["currentPage"] = page
                matches_data = self._api.get_matches(comp_filter)
                if not matches_data or not matches_data.get("items"):
                    break
                items = matches_data["items"]
                all_match_items.extend(items)
                if len(items) < comp_filter.get("pageSize", 100):
                    break
                page += 1

            if not all_match_items:
                continue

            logger.info(f"[Mozzart]   {comp_name}: {len(all_match_items)} match items")

            # Step 3: fetch match details in parallel
            match_ids_to_fetch = []
            for match_item in all_match_items:
                mid = match_item.get("id")
                if mid and mid not in seen:
                    seen.add(mid)
                    match_ids_to_fetch.append(mid)

            def fetch_detail(mid):
                return mid, self._api.get_match_details(mid)

            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
                futures = {executor.submit(fetch_detail, mid): mid for mid in match_ids_to_fetch}
                for future in as_completed(futures):
                    try:
                        match_id, detail_data = future.result()
                    except Exception as e:
                        logger.warning(f"[Mozzart] Thread error: {e}")
                        continue

                    if not detail_data or not detail_data.get("items"):
                        continue

                    for item in detail_data["items"]:
                        match_obj = item if "home" in item else item.get("match", item)

                        if "specialMatchGroupId" in match_obj:
                            continue

                        home = match_obj.get("home", {}).get("name") if isinstance(match_obj.get("home"), dict) else None
                        away = match_obj.get("visitor", {}).get("name") if isinstance(match_obj.get("visitor"), dict) else None

                        if not home or not away:
                            home = match_obj.get("homeName", home)
                            away = match_obj.get("visitorName", away)
                            if not home or not away:
                                continue

                        start_time = self._parse_timestamp(match_obj.get("startTime"))
                        if not start_time:
                            continue

                        match_obj = self._restructure_odds(match_obj)

                        scraped = ScrapedMatch(
                            team1=home,
                            team2=away,
                            sport_id=sport_id,
                            start_time=start_time,
                            league_name=comp_name,
                            external_id=str(match_id),
                        )

                        scraped.odds = OddsParser.parse(match_obj, sport_id)

                        if scraped.odds:
                            matches.append(scraped)
                        elif match_obj.get("oddsGroup"):
                            if not debug_logged:
                                debug_logged = True
                                group_names = [g.get("groupName") for g in match_obj.get("oddsGroup", [])]
                                logger.warning(
                                    f"[Mozzart] DEBUG: {home} vs {away} has "
                                    f"{len(match_obj.get('odds', []))} raw odds, "
                                    f"{len(match_obj.get('oddsGroup', []))} groups: "
                                    f"{group_names[:10]}"
                                )

        # Update stats
        self._request_count = self._api._request_count
        self._error_count = self._api._error_count

        return matches

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Async wrapper around sync scraper (tls_client is synchronous)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._scrape_sport_sync, sport_id)

    async def close(self) -> None:
        """Cleanup resources."""
        self._executor.shutdown(wait=False)
        await super().close()
