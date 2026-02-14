"""
Mozzart Bet scraper for BetSnipe.ai v2.0

Scrapes odds from Mozzart Bet Serbia API.
Supports: Football, Basketball, Tennis, Hockey, Table Tennis

Uses Playwright to bypass Cloudflare protection with a real browser context.
"""

import asyncio
import logging
import random
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None
    Browser = None
    BrowserContext = None
    Page = None

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)


def generate_unique_id() -> str:
    """Generate unique ID in format used by Mozzart: timestamp-randomhex"""
    timestamp = int(time.time() * 1000)
    random_hex = ''.join(random.choices('0123456789abcdef', k=8))
    return f"{timestamp}-{random_hex}"

# Sport ID mapping (Mozzart to internal)
# Updated based on actual API response from 2026-01-19
MOZZART_SPORTS = {
    1: 1,   # Fudbal (Football)
    2: 2,   # Kosarka (Basketball)
    5: 3,   # Tenis (Tennis)
    4: 4,   # Hokej (Hockey)
    9: 5,   # Stoni tenis (Table Tennis) - Changed from 28 to 9
}

# Reverse mapping
INTERNAL_TO_MOZZART = {v: k for k, v in MOZZART_SPORTS.items()}


class MozzartScraper(BaseScraper):
    """
    Scraper for Mozzart Bet Serbia.

    Uses Playwright to bypass Cloudflare protection with a real browser.

    API endpoints:
    - POST /betting/get-competitions: Get leagues for a sport
    - POST /betting/matches: Get matches for a league
    - POST /betting/match/{id}: Get match details with odds
    """

    def __init__(self):
        super().__init__(bookmaker_id=1, bookmaker_name="Mozzart")
        self._semaphore = asyncio.Semaphore(8)  # Limit concurrent requests
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._initialized = False
        self._init_lock = asyncio.Lock()  # Prevent race condition during initialization

    async def _ensure_initialized(self):
        """Initialize Playwright browser if not already done."""
        if self._initialized:
            return

        # Use lock to prevent race condition when multiple sports scrape concurrently
        async with self._init_lock:
            # Double-check after acquiring lock (another task may have initialized)
            if self._initialized:
                return

            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled']
                )
                self._context = await self._browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
                )

                # Create a persistent page for making API requests
                self._page = await self._context.new_page()

                # Warm up session by visiting the betting page
                try:
                    await self._page.goto('https://www.mozzartbet.com/sr/kladjenje/sport/1?date=today', timeout=45000)
                    await asyncio.sleep(3)
                    logger.info("[Mozzart] Playwright browser initialized and warmed up")
                except Exception as e:
                    logger.warning(f"[Mozzart] Warmup navigation issue: {e}")

                self._initialized = True

            except Exception as e:
                logger.error(f"[Mozzart] Failed to initialize Playwright: {e}")
                raise

    async def reset_session(self) -> None:
        """No-op: Mozzart browser persists across cycles for performance."""
        pass

    async def close(self):
        """Clean up Playwright resources."""
        if hasattr(self, '_page') and self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._initialized = False
        logger.debug("[Mozzart] Playwright browser closed")

    def get_base_url(self) -> str:
        return "https://www.mozzartbet.com"

    def get_headers(self) -> Dict[str, str]:
        return {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.7',
            'Content-Type': 'application/json',
            'Origin': 'https://www.mozzartbet.com',
            'Referer': 'https://www.mozzartbet.com/sr/kladjenje',
            'Medium': 'WEB'
        }

    def get_supported_sports(self) -> List[int]:
        return [1, 2, 3, 4, 5]

    async def _post_request(self, url: str, payload: Dict) -> Optional[Dict]:
        """Make a POST request using fetch() from within the browser page."""
        await self._ensure_initialized()

        unique_id = generate_unique_id()

        try:
            # Use page.evaluate to make fetch request with browser's full context
            result = await self._page.evaluate('''async ({url, payload, uniqueId}) => {
                try {
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Accept': 'application/json, text/plain, */*',
                            'Content-Type': 'application/json',
                            'medium': 'PREMATCH_WEB',
                            'x-unique-id': uniqueId
                        },
                        body: JSON.stringify(payload)
                    });

                    if (response.ok) {
                        return {success: true, data: await response.json()};
                    } else {
                        return {success: false, status: response.status};
                    }
                } catch (e) {
                    return {success: false, error: e.message};
                }
            }''', {'url': url, 'payload': payload, 'uniqueId': unique_id})

            if result.get('success'):
                return result.get('data')
            else:
                logger.warning(f"[Mozzart] Request failed for {url}: {result}")
                return None

        except Exception as e:
            logger.warning(f"[Mozzart] Error fetching {url}: {e}")
            return None

    async def fetch_leagues(self, sport_id: int) -> List[Tuple[int, str]]:
        """Fetch leagues for a sport."""
        mozzart_sport_id = INTERNAL_TO_MOZZART.get(sport_id)
        if mozzart_sport_id is None:
            return []

        url = f"{self.get_base_url()}/betting/get-competitions"
        # Updated payload format based on actual API
        payload = {
            "date": "all_days",
            "sportId": mozzart_sport_id
        }

        data = await self._post_request(url, payload)

        if not data:
            return []

        leagues = []
        for comp in data.get("competitions", []):
            league_id = comp.get("id")
            league_name = comp.get("name")
            if league_id and league_name:
                leagues.append((league_id, league_name))

        return leagues

    async def fetch_match_ids(self, sport_id: int, league_id: int) -> List[int]:
        """Fetch match IDs for a league."""
        mozzart_sport_id = INTERNAL_TO_MOZZART.get(sport_id)
        if mozzart_sport_id is None:
            return []

        url = f"{self.get_base_url()}/betting/matches"
        # Updated payload format based on actual API
        payload = {
            "date": "all_days",
            "sort": "bycompetition",
            "currentPage": 0,
            "pageSize": 100,
            "sportId": mozzart_sport_id,
            "competitionIds": [league_id],
            "search": "",
            "matchTypeId": 0
        }

        data = await self._post_request(url, payload)

        if not data or not data.get("items"):
            return []

        return [match["id"] for match in data["items"]]

    async def fetch_match_details(self, match_id: int, sport_id: int, league_id: int) -> Optional[Dict]:
        """Fetch detailed match data with odds."""
        async with self._semaphore:
            # Match endpoint - simple POST with empty body or minimal payload
            url = f"{self.get_base_url()}/betting/match/{match_id}"
            payload = {}  # Match endpoint typically needs minimal payload

            for attempt in range(3):
                data = await self._post_request(url, payload)
                if data and not data.get("error"):
                    return data
                await asyncio.sleep(0.5)

            return None

    # ==========================================
    # Football group-based parsing
    # ==========================================

    # Mapping of Mozzart group names to parsing handlers
    # Each handler returns a list of ScrapedOdds
    FOOTBALL_GROUP_MAP = {
        # === Grouped markets (2-3 outcomes, use odd1/odd2/odd3) ===
        "Konačan ishod":                ("_parse_1x2", 2),
        "Dupla šansa":                  ("_parse_three_way", 13),   # 1X, 12, X2
        "Ukupno golova - Par/Nepar":    ("_parse_two_way", 15),     # Par, Nepar -> odd/even
        "Winner":                       ("_parse_two_way", 14),     # draw no bet
        "Dupla pobeda":                 ("_parse_two_way", 16),     # both halves winner
        "Sigurna pobeda":               ("_parse_two_way", 17),     # win to nil
        "Daje prvi gol":                ("_parse_three_way", 18),   # first goal team
        "Poluvreme sa više golova":     ("_parse_three_way", 19),   # half with more goals
        "Prvo poluvreme":               ("_parse_1x2", 3),          # 1X2 first half
        "Dupla šansa prvo poluvreme":   ("_parse_three_way", 20),   # double chance H1
        "Winner prvo poluvreme":        ("_parse_two_way", 21),     # draw no bet H1
        "Drugo poluvreme":              ("_parse_1x2", 4),          # 1X2 second half
        "Prolazi dalje":                ("_parse_two_way", 22),     # to qualify
        # === Selection markets (multi-outcome, 1 row per selection) ===
        "Tačan rezultat":               ("_parse_selection", 23),
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

    def _parse_1x2(self, odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        """Parse a 1X2 (three-way) group into a single grouped ScrapedOdds."""
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
            return [ScrapedOdds(
                bet_type_id=bet_type_id,
                odd1=collected["1"], odd2=collected["X"], odd3=collected["2"]
            )]
        return []

    def _parse_three_way(self, odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        """Parse a three-way group (e.g. double chance: 1X, 12, X2) into grouped odds."""
        values = []
        for odd in sorted(odds_group.get("odds", []), key=lambda o: o.get("subgame", {}).get("rank", 0)):
            try:
                value = float(odd.get("value", 0))
            except (ValueError, TypeError):
                continue
            if value > 0:
                values.append(value)

        if len(values) == 3:
            return [ScrapedOdds(
                bet_type_id=bet_type_id,
                odd1=values[0], odd2=values[1], odd3=values[2]
            )]
        return []

    def _parse_two_way(self, odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        """Parse a two-way group into grouped odds."""
        values = []
        for odd in sorted(odds_group.get("odds", []), key=lambda o: o.get("subgame", {}).get("rank", 0)):
            try:
                value = float(odd.get("value", 0))
            except (ValueError, TypeError):
                continue
            if value > 0:
                values.append(value)

        if len(values) == 2:
            return [ScrapedOdds(
                bet_type_id=bet_type_id,
                odd1=values[0], odd2=values[1]
            )]
        return []

    def _parse_selection(self, odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        """Parse a multi-outcome group into selection-based ScrapedOdds (1 row per outcome)."""
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
                result.append(ScrapedOdds(
                    bet_type_id=bet_type_id,
                    odd1=value,
                    selection=subgame_name
                ))
        return result

    def _parse_btts_group(self, odds_group: Dict) -> List[ScrapedOdds]:
        """Parse BTTS group — simple GG/NG goes to bet_type 8, combos to 46."""
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
                # Combo subgames like "1GG", "2NG", "GG3+", etc.
                combos.append(ScrapedOdds(
                    bet_type_id=46, odd1=value, selection=subgame_name
                ))

        result = []
        if simple.get("gg") and simple.get("ng"):
            result.append(ScrapedOdds(
                bet_type_id=8, odd1=simple["gg"], odd2=simple["ng"]
            ))
        result.extend(combos)
        return result

    def _parse_ou_markets(self, match: Dict) -> List[ScrapedOdds]:
        """Parse all O/U markets (specialOddValueType=MARGIN) across all groups."""
        total_goals = {}
        total_goals_h1 = {}
        total_goals_h2 = {}

        for odds_group in match.get("oddsGroup", []):
            group_name = odds_group.get("groupName", "").lower()

            for odd in odds_group.get("odds", []):
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
                    if total not in total_goals_h1:
                        total_goals_h1[total] = {}
                    if subgame_name == "manje":
                        total_goals_h1[total]["under"] = value
                    elif subgame_name == "više":
                        total_goals_h1[total]["over"] = value
                elif "2. poluvreme" in group_name or "dp" in group_name:
                    if total not in total_goals_h2:
                        total_goals_h2[total] = {}
                    if subgame_name == "manje":
                        total_goals_h2[total]["under"] = value
                    elif subgame_name == "više":
                        total_goals_h2[total]["over"] = value
                else:
                    if total not in total_goals:
                        total_goals[total] = {}
                    if subgame_name == "manje":
                        total_goals[total]["under"] = value
                    elif subgame_name == "više":
                        total_goals[total]["over"] = value

        odds_list = []
        for total, t_odds in total_goals.items():
            if "under" in t_odds and "over" in t_odds:
                odds_list.append(ScrapedOdds(
                    bet_type_id=5, odd1=t_odds["under"], odd2=t_odds["over"], margin=total
                ))
        for total, t_odds in total_goals_h1.items():
            if "under" in t_odds and "over" in t_odds:
                odds_list.append(ScrapedOdds(
                    bet_type_id=6, odd1=t_odds["under"], odd2=t_odds["over"], margin=total
                ))
        for total, t_odds in total_goals_h2.items():
            if "under" in t_odds and "over" in t_odds:
                odds_list.append(ScrapedOdds(
                    bet_type_id=7, odd1=t_odds["under"], odd2=t_odds["over"], margin=total
                ))
        return odds_list

    # ==========================================
    # Generic helpers for handicap / O/U / combo groups
    # ==========================================

    def _parse_handicap_group(self, odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        """Parse a single handicap group — line read dynamically from specialOddValue.
        Accepts both '1'/'2' and 'H1'/'H2' subgame naming conventions."""
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
                key = subgame[-1]  # "H1" -> "1", "H2" -> "2"
                collected[key] = value

        if "1" in collected and "2" in collected and margin is not None:
            return [ScrapedOdds(
                bet_type_id=bet_type_id,
                odd1=collected["1"], odd2=collected["2"],
                margin=margin
            )]
        return []

    def _parse_ou_group(self, odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        """Parse a single O/U group — line read dynamically from specialOddValue."""
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
            return [ScrapedOdds(
                bet_type_id=bet_type_id,
                odd1=collected["under"], odd2=collected["over"],
                margin=margin
            )]
        return []

    def _parse_selection_margin_group(self, odds_group: Dict, bet_type_id: int) -> List[ScrapedOdds]:
        """Parse a combo group with both selections AND a margin from specialOddValue."""
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
                result.append(ScrapedOdds(
                    bet_type_id=bet_type_id,
                    odd1=value,
                    selection=subgame,
                    margin=margin
                ))
        return result

    def parse_football_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse all football odds from Mozzart match data using group-based dispatch."""
        odds_list = []
        match = match_data.get("match", {})

        if "specialMatchGroupId" in match:
            return odds_list

        # 1) Parse O/U markets (MARGIN-based) across all groups first
        odds_list.extend(self._parse_ou_markets(match))

        # 2) Parse each group via the dispatch map
        for odds_group in match.get("oddsGroup", []):
            group_name = odds_group.get("groupName", "")

            # Special handling for BTTS (can have both simple and combo subgames)
            if group_name == "Oba tima daju gol":
                odds_list.extend(self._parse_btts_group(odds_group))
                continue

            mapping = self.FOOTBALL_GROUP_MAP.get(group_name)
            if not mapping:
                continue

            handler_name, bet_type_id = mapping
            handler = getattr(self, handler_name)
            odds_list.extend(handler(odds_group, bet_type_id))

        return odds_list

    # ==========================================
    # Basketball group-based parsing
    # ==========================================

    # Simple groups (no HANDICAP/MARGIN specialOddValueType)
    BASKETBALL_GROUP_MAP = {
        "Konačan ishod":                          ("_parse_1x2", 2),
        "Pobednik meča sa ev. produžecima":       ("_parse_two_way", 1),   # winner incl. OT
        "Dupla šansa":                            ("_parse_two_way", 13),  # only 2 outcomes in basketball
        "Prvo poluvreme":                         ("_parse_1x2", 3),
        "Dupla pobeda":                           ("_parse_two_way", 16),
        "Dupla šansa prvo poluvreme":             ("_parse_two_way", 20),  # only 2 outcomes
        "Poluvreme sa više poena":                ("_parse_three_way", 19),  # prvo, drugo, jednako
        "Poluvreme - kraj":                       ("_parse_selection", 24),  # HT/FT
        "Četvrtina sa najviše poena":             ("_parse_selection", 54),  # quarter most points
    }

    # MARGIN-type groups → bet_type_id mapping (line from specialOddValue)
    BASKETBALL_MARGIN_MAP = {
        "Ukupno poena na meču":                   10,   # total_points
        "Ukupno poena Tim 1":                     48,   # team1_total_points
        "Ukupno poena Tim 2":                     49,   # team2_total_points
        "Ukupno poena prvo poluvreme":            6,    # total_h1
        "Ukupno poena prvo poluvreme Tim 1":      51,   # team1_total_h1
        "Ukupno poena prvo poluvreme Tim 2":      52,   # team2_total_h1
        "Ukupno poena drugo poluvreme":           7,    # total_h2
        "Ukupno poena najefikasnija četvrtina":   53,   # most_efficient_quarter_total
    }

    # Combo groups that have MARGIN + selections
    BASKETBALL_COMBO_MARGIN_MAP = {
        "Konačan ishod + Ukupno poena":                       38,  # result_total_goals
        "Prvo poluvreme + Ukupno poena prvo poluvreme":       55,  # h1_result_total
    }

    def parse_basketball_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse all basketball odds from Mozzart match data using group-based dispatch."""
        odds_list = []
        match = match_data.get("match", {})

        if "specialMatchGroupId" in match:
            return odds_list

        for odds_group in match.get("oddsGroup", []):
            group_name = odds_group.get("groupName", "")

            # Detect if this group uses HANDICAP or MARGIN specialOddValueType
            first_type = ""
            for odd in odds_group.get("odds", []):
                vt = odd.get("game", {}).get("specialOddValueType", "")
                if vt and vt != "NONE":
                    first_type = vt
                    break

            if first_type == "HANDICAP":
                # Handicap — determine full-time vs half based on group name
                if "poluvreme" in group_name.lower():
                    odds_list.extend(self._parse_handicap_group(odds_group, 50))
                else:
                    odds_list.extend(self._parse_handicap_group(odds_group, 9))

            elif first_type == "MARGIN":
                # Check combo markets first (they also have MARGIN)
                combo_bt = self.BASKETBALL_COMBO_MARGIN_MAP.get(group_name)
                if combo_bt is not None:
                    odds_list.extend(self._parse_selection_margin_group(odds_group, combo_bt))
                else:
                    # Regular O/U market
                    ou_bt = self.BASKETBALL_MARGIN_MAP.get(group_name)
                    if ou_bt is not None:
                        odds_list.extend(self._parse_ou_group(odds_group, ou_bt))

            else:
                # Simple group — use dispatch map
                mapping = self.BASKETBALL_GROUP_MAP.get(group_name)
                if mapping:
                    handler_name, bet_type_id = mapping
                    handler = getattr(self, handler_name)
                    odds_list.extend(handler(odds_group, bet_type_id))

        return odds_list

    # ==========================================
    # Tennis group-based parsing
    # ==========================================

    # Simple groups (no HANDICAP/MARGIN specialOddValueType)
    TENNIS_GROUP_MAP = {
        "Konačan ishod":                                           ("_parse_two_way", 1),    # winner
        "Prvi set":                                                ("_parse_two_way", 57),   # first_set_winner
        "Prvi set - Kraj":                                         ("_parse_selection", 64),  # first_set_match_combo
        "Tačan broj setova":                                       ("_parse_selection", 65),  # exact_sets
        "Ukupno gemova - Par/Nepar":                               ("_parse_two_way", 15),   # odd_even
        "Rangovi gemova prvi set":                                 ("_parse_selection", 66),  # games_range_s1
        "Ukupno gemova prvi set - Par/Nepar":                      ("_parse_two_way", 59),   # odd_even_s1
        "Tajbrejk u prvom setu - Da/Ne":                           ("_parse_two_way", 60),   # tiebreak_s1
        "Rangovi gemova drugi set":                                ("_parse_selection", 67),  # games_range_s2
        "Ukupno gemova drugi set - Par/Nepar":                     ("_parse_two_way", 61),   # odd_even_s2
        "Tajbrejk u drugom setu - Da/Ne":                          ("_parse_two_way", 62),   # tiebreak_s2
        "Pobeda igrača 1 + Gemovi prvi set":                       ("_parse_selection", 69),  # p1_win_games_s1
        "Pobeda igrača 1 + Gemovi prvi set - Par/Nepar":           ("_parse_two_way", 70),   # p1_win_odd_even_s1
        "Pobeda igrača 2 + Gemovi prvi set":                       ("_parse_selection", 71),  # p2_win_games_s1
        "Pobeda igrača 2 + Gemovi prvi set - Par/Nepar":           ("_parse_two_way", 72),   # p2_win_odd_even_s1
        "Konačan ishod + Više gemova - Prvi ili drugi set":        ("_parse_selection", 73),  # winner_set_more_games
        "Više gemova - Prvi ili drugi set":                        ("_parse_three_way", 63),  # set_with_more_games
    }

    # MARGIN-type groups → bet_type_id (O/U markets)
    TENNIS_MARGIN_MAP = {
        "Ukupno gemova":            5,    # total_over_under
        "Ukupno gemova u 1. setu":  6,    # total_h1
        "Ukupno gemova u 2. setu":  7,    # total_h2
    }

    # Combo groups with MARGIN + selections
    TENNIS_COMBO_MARGIN_MAP = {
        "Mozzart kombinazzije":          68,   # winner_total_games
        "Konačan ishod + Ukupno gemova": 68,   # winner_total_games (alternate name)
    }

    # HANDICAP groups → bet_type_id
    TENNIS_HANDICAP_MAP = {
        "Hendikep setova":           56,   # handicap_sets
        "Hendikep gemova":           9,    # handicap (main tennis handicap)
        "Hendikep gemova u 1. setu": 58,   # handicap_games_s1
    }

    def parse_tennis_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse all tennis odds from Mozzart match data using group-based dispatch."""
        odds_list = []
        match = match_data.get("match", {})

        if "specialMatchGroupId" in match:
            return odds_list

        for odds_group in match.get("oddsGroup", []):
            # Filter out DEACTIVATED odds (template placeholders with value=1)
            active_odds = [o for o in odds_group.get("odds", [])
                           if o.get("oddStatus") != "DEACTIVATED"]
            if not active_odds:
                continue
            filtered_group = {**odds_group, "odds": active_odds}

            group_name = odds_group.get("groupName", "")

            # Detect specialOddValueType from first active odd
            first_type = ""
            for odd in active_odds:
                vt = odd.get("game", {}).get("specialOddValueType", "")
                if vt and vt != "NONE":
                    first_type = vt
                    break

            if first_type == "HANDICAP":
                hc_bt = self.TENNIS_HANDICAP_MAP.get(group_name)
                if hc_bt is not None:
                    odds_list.extend(self._parse_handicap_group(filtered_group, hc_bt))

            elif first_type == "MARGIN":
                # Check combo markets first (they also have MARGIN)
                combo_bt = self.TENNIS_COMBO_MARGIN_MAP.get(group_name)
                if combo_bt is not None:
                    odds_list.extend(self._parse_selection_margin_group(filtered_group, combo_bt))
                else:
                    ou_bt = self.TENNIS_MARGIN_MAP.get(group_name)
                    if ou_bt is not None:
                        odds_list.extend(self._parse_ou_group(filtered_group, ou_bt))

            else:
                # Simple group — use dispatch map
                mapping = self.TENNIS_GROUP_MAP.get(group_name)
                if mapping:
                    handler_name, bet_type_id = mapping
                    handler = getattr(self, handler_name)
                    odds_list.extend(handler(filtered_group, bet_type_id))

        return odds_list

    # ==========================================
    # Hockey group-based parsing
    # ==========================================

    # All hockey groups are simple (no HANDICAP/MARGIN specialOddValueType)
    HOCKEY_GROUP_MAP = {
        "Konačan ishod":                ("_parse_1x2", 2),          # 1X2
        "Dupla šansa":                  ("_parse_three_way", 13),   # double chance
        "Winner":                       ("_parse_two_way", 14),     # draw no bet
        "Prva trećina":                 ("_parse_1x2", 3),          # first period 1X2
        "Ukupno golova":                ("_parse_selection", 25),   # total goals range
        "Konačan ishod + Golovi":       ("_parse_selection", 38),   # result + total goals
        "Prva trećina + Golovi":        ("_parse_selection", 74),   # first period result + total goals
        "Prva trećina - Kraj":          ("_parse_selection", 24),   # first period + match result (HT/FT)
        "Ukupno golova prva trećina":   ("_parse_selection", 29),   # first period goals range
        "Ukupno golova druga trećina":  ("_parse_selection", 30),   # second period goals range
    }

    def parse_hockey_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse all hockey odds from Mozzart match data using group-based dispatch."""
        odds_list = []
        match = match_data.get("match", {})

        if "specialMatchGroupId" in match:
            return odds_list

        for odds_group in match.get("oddsGroup", []):
            # Filter out DEACTIVATED odds
            active_odds = [o for o in odds_group.get("odds", [])
                           if o.get("oddStatus") != "DEACTIVATED"]
            if not active_odds:
                continue
            filtered_group = {**odds_group, "odds": active_odds}

            group_name = odds_group.get("groupName", "")

            mapping = self.HOCKEY_GROUP_MAP.get(group_name)
            if mapping:
                handler_name, bet_type_id = mapping
                handler = getattr(self, handler_name)
                odds_list.extend(handler(filtered_group, bet_type_id))

        return odds_list

    def parse_table_tennis_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse table tennis odds from Mozzart match data."""
        odds_list = []
        match = match_data.get("match", {})

        winner_odds = {"1": 0, "2": 0}

        for odds_group in match.get("oddsGroup", []):
            for odd in odds_group.get("odds", []):
                game_name = odd.get("game", {}).get("name", "")
                subgame_name = odd.get("subgame", {}).get("name", "")

                try:
                    value = float(odd.get("value", 0))
                except (ValueError, TypeError):
                    continue

                # Winner
                if game_name == "Pobednik meča":
                    if subgame_name == "1":
                        winner_odds["1"] = value
                    elif subgame_name == "2":
                        winner_odds["2"] = value

        if winner_odds["1"] and winner_odds["2"]:
            odds_list.append(ScrapedOdds(
                bet_type_id=1,
                odd1=winner_odds["1"],
                odd2=winner_odds["2"]
            ))

        return odds_list

    def parse_odds(self, match_data: Dict, sport_id: int) -> List[ScrapedOdds]:
        """Parse odds based on sport type."""
        if sport_id == 1:
            return self.parse_football_odds(match_data)
        elif sport_id == 2:
            return self.parse_basketball_odds(match_data)
        elif sport_id == 3:
            return self.parse_tennis_odds(match_data)
        elif sport_id == 4:
            return self.parse_hockey_odds(match_data)
        elif sport_id == 5:
            return self.parse_table_tennis_odds(match_data)
        return []

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Scrape all matches for a sport."""
        matches: List[ScrapedMatch] = []
        processed_matches = set()

        try:
            leagues = await self.fetch_leagues(sport_id)
            if not leagues:
                logger.warning(f"[Mozzart] No leagues found for sport {sport_id}")
                return matches

            logger.debug(f"[Mozzart] Found {len(leagues)} leagues for sport {sport_id}")

            # Phase 1: Fetch all league match IDs in parallel
            league_tasks = [self.fetch_match_ids(sport_id, lid) for lid, _ in leagues]
            league_results = await asyncio.gather(*league_tasks, return_exceptions=True)

            # Collect all (match_id, league_name) pairs
            all_match_info = []  # list of (match_id, league_name)
            for (league_id, league_name), result in zip(leagues, league_results):
                if isinstance(result, Exception):
                    logger.warning(f"[Mozzart] Error fetching league {league_name}: {result}")
                    continue
                for mid in (result or []):
                    all_match_info.append((mid, league_name))

            if not all_match_info:
                return matches

            logger.debug(f"[Mozzart] Fetching {len(all_match_info)} match details for sport {sport_id}")

            # Phase 2: Fetch all match details in one big parallel batch
            detail_tasks = [self.fetch_match_details(mid, sport_id, 0) for mid, _ in all_match_info]
            detail_results = await asyncio.gather(*detail_tasks, return_exceptions=True)

            # Phase 3: Process all results
            for (match_id, league_name), result in zip(all_match_info, detail_results):
                try:
                    if isinstance(result, Exception):
                        logger.warning(f"[Mozzart] Error fetching match {match_id}: {result}")
                        continue

                    match_data = result
                    if not match_data:
                        continue

                    match = match_data.get("match", {})

                    # Skip special matches
                    if "specialMatchGroupId" in match:
                        continue

                    home = match.get("home", {}).get("name")
                    away = match.get("visitor", {}).get("name")

                    if not home or not away:
                        continue

                    # Deduplicate
                    match_key = f"{home}_{away}"
                    if match_key in processed_matches:
                        continue
                    processed_matches.add(match_key)

                    start_time = self.parse_timestamp(match.get("startTime"))
                    if not start_time:
                        continue

                    scraped = ScrapedMatch(
                        team1=home,
                        team2=away,
                        sport_id=sport_id,
                        start_time=start_time,
                        league_name=league_name,
                        external_id=str(match.get("id")),
                    )

                    scraped.odds = self.parse_odds(match_data, sport_id)

                    if scraped.odds:
                        matches.append(scraped)

                except Exception as e:
                    logger.warning(f"[Mozzart] Error processing match {match_id}: {e}")

        except Exception as e:
            logger.error(f"[Mozzart] Error scraping sport {sport_id}: {e}")

        return matches
