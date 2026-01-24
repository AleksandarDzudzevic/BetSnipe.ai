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

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

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
        self._semaphore = asyncio.Semaphore(3)  # Limit concurrent requests
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._initialized = False

    async def _ensure_initialized(self):
        """Initialize Playwright browser if not already done."""
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

    def parse_football_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse football odds from Mozzart match data."""
        odds_list = []
        match = match_data.get("match", {})

        if "specialMatchGroupId" in match:
            return odds_list

        odds_1x2 = {"1": 0, "X": 0, "2": 0}
        odds_1x2_h1 = {"1": 0, "X": 0, "2": 0}
        odds_1x2_h2 = {"1": 0, "X": 0, "2": 0}
        odds_ggng = {"gg": 0, "ng": 0}
        total_goals = {}
        total_goals_h1 = {}
        total_goals_h2 = {}

        for odds_group in match.get("oddsGroup", []):
            group_name = odds_group.get("groupName", "").lower()

            for odd in odds_group.get("odds", []):
                game_name = odd.get("game", {}).get("name", "")
                subgame_name = odd.get("subgame", {}).get("name", "")
                special_value = odd.get("specialOddValue", "")
                value_type = odd.get("game", {}).get("specialOddValueType", "")

                try:
                    value = float(odd.get("value", 0))
                except (ValueError, TypeError):
                    value = 0

                # Full time result
                if game_name == "Konačan ishod" and "poluvreme" not in group_name:
                    if subgame_name in ["1", "X", "2"]:
                        odds_1x2[subgame_name] = value

                # First half result
                elif "1. poluvreme" in group_name or game_name == "Prvo poluvreme":
                    if subgame_name in ["1", "X", "2"]:
                        odds_1x2_h1[subgame_name] = value

                # Second half result
                elif "2. poluvreme" in group_name or game_name == "Drugo poluvreme":
                    if subgame_name in ["1", "X", "2"]:
                        odds_1x2_h2[subgame_name] = value

                # BTTS
                elif game_name == "Oba tima daju gol":
                    if subgame_name == "da":
                        odds_ggng["gg"] = value
                    elif subgame_name == "ne":
                        odds_ggng["ng"] = value

                # Total goals (with MARGIN type)
                elif value_type == "MARGIN" and special_value:
                    try:
                        total = float(special_value)
                        if "1. poluvreme" in group_name:
                            if total not in total_goals_h1:
                                total_goals_h1[total] = {}
                            if subgame_name == "manje":
                                total_goals_h1[total]["under"] = value
                            elif subgame_name == "više":
                                total_goals_h1[total]["over"] = value
                        elif "2. poluvreme" in group_name:
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
                    except (ValueError, TypeError):
                        continue

        # Build odds list
        if all(odds_1x2.values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=2, odd1=odds_1x2["1"], odd2=odds_1x2["X"], odd3=odds_1x2["2"]
            ))

        if all(odds_1x2_h1.values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=3, odd1=odds_1x2_h1["1"], odd2=odds_1x2_h1["X"], odd3=odds_1x2_h1["2"]
            ))

        if all(odds_1x2_h2.values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=4, odd1=odds_1x2_h2["1"], odd2=odds_1x2_h2["X"], odd3=odds_1x2_h2["2"]
            ))

        if odds_ggng["gg"] and odds_ggng["ng"]:
            odds_list.append(ScrapedOdds(
                bet_type_id=8, odd1=odds_ggng["gg"], odd2=odds_ggng["ng"]
            ))

        for total, t_odds in total_goals.items():
            if "under" in t_odds and "over" in t_odds:
                odds_list.append(ScrapedOdds(
                    bet_type_id=5,
                    odd1=t_odds["under"],
                    odd2=t_odds["over"],
                    margin=total
                ))

        for total, t_odds in total_goals_h1.items():
            if "under" in t_odds and "over" in t_odds:
                odds_list.append(ScrapedOdds(
                    bet_type_id=6,
                    odd1=t_odds["under"],
                    odd2=t_odds["over"],
                    margin=total
                ))

        for total, t_odds in total_goals_h2.items():
            if "under" in t_odds and "over" in t_odds:
                odds_list.append(ScrapedOdds(
                    bet_type_id=7,
                    odd1=t_odds["under"],
                    odd2=t_odds["over"],
                    margin=total
                ))

        return odds_list

    def parse_basketball_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse basketball odds from Mozzart match data."""
        odds_list = []
        match = match_data.get("match", {})

        if "specialMatchGroupId" in match:
            return odds_list

        winner_odds = {"1": 0, "2": 0}
        handicap_odds = {}
        total_points_odds = {}

        for odds_group in match.get("oddsGroup", []):
            group_name = odds_group.get("groupName", "").lower()
            if "poluvreme" in group_name:
                continue

            for odd in odds_group.get("odds", []):
                game_name = odd.get("game", {}).get("name", "")
                subgame_name = odd.get("subgame", {}).get("name", "")
                special_value = odd.get("specialOddValue", "")
                value_type = odd.get("game", {}).get("specialOddValueType", "")

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

                # Handicap
                elif value_type == "HANDICAP" and special_value:
                    if special_value not in handicap_odds:
                        handicap_odds[special_value] = {}
                    if subgame_name == "1":
                        handicap_odds[special_value]["1"] = value
                    elif subgame_name == "2":
                        handicap_odds[special_value]["2"] = value

                # Total Points
                elif value_type == "MARGIN" and special_value:
                    try:
                        points = float(special_value)
                        if points > 130:
                            if special_value not in total_points_odds:
                                total_points_odds[special_value] = {}
                            if subgame_name == "manje":
                                total_points_odds[special_value]["under"] = value
                            elif subgame_name == "više":
                                total_points_odds[special_value]["over"] = value
                    except (ValueError, TypeError):
                        continue

        # Build odds list
        if winner_odds["1"] and winner_odds["2"]:
            odds_list.append(ScrapedOdds(
                bet_type_id=1,
                odd1=winner_odds["1"],
                odd2=winner_odds["2"]
            ))

        for handicap, h_odds in handicap_odds.items():
            if "1" in h_odds and "2" in h_odds:
                try:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=9,
                        odd1=h_odds["1"],
                        odd2=h_odds["2"],
                        margin=float(handicap)
                    ))
                except (ValueError, TypeError):
                    continue

        for points, t_odds in total_points_odds.items():
            if "under" in t_odds and "over" in t_odds:
                try:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=10,
                        odd1=t_odds["under"],
                        odd2=t_odds["over"],
                        margin=float(points)
                    ))
                except (ValueError, TypeError):
                    continue

        return odds_list

    def parse_tennis_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse tennis odds from Mozzart match data."""
        odds_list = []
        match = match_data.get("match", {})

        winner_odds = {"1": 0, "2": 0}
        set1_winner_odds = {"1": 0, "2": 0}

        for odds_group in match.get("oddsGroup", []):
            group_name = odds_group.get("groupName", "")

            for odd in odds_group.get("odds", []):
                game_name = odd.get("game", {}).get("name", "")
                subgame_name = odd.get("subgame", {}).get("name", "")

                try:
                    value = float(odd.get("value", 0))
                except (ValueError, TypeError):
                    continue

                # Match Winner - can be "Pobednik meča" or "Konačan ishod"
                if game_name in ["Pobednik meča", "Konačan ishod"] and group_name == "Konačan ishod":
                    if subgame_name == "1":
                        winner_odds["1"] = value
                    elif subgame_name == "2":
                        winner_odds["2"] = value

                # First Set Winner - "Prvi set" group
                elif game_name == "Prvi set" and group_name == "Prvi set":
                    if subgame_name == "1":
                        set1_winner_odds["1"] = value
                    elif subgame_name == "2":
                        set1_winner_odds["2"] = value

        if winner_odds["1"] and winner_odds["2"]:
            odds_list.append(ScrapedOdds(
                bet_type_id=1,
                odd1=winner_odds["1"],
                odd2=winner_odds["2"]
            ))

        if set1_winner_odds["1"] and set1_winner_odds["2"]:
            odds_list.append(ScrapedOdds(
                bet_type_id=11,
                odd1=set1_winner_odds["1"],
                odd2=set1_winner_odds["2"]
            ))

        return odds_list

    def parse_hockey_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse hockey odds from Mozzart match data."""
        odds_list = []
        match = match_data.get("match", {})

        result_odds = {"1": 0, "X": 0, "2": 0}

        for odds_group in match.get("oddsGroup", []):
            for odd in odds_group.get("odds", []):
                game_name = odd.get("game", {}).get("name", "")
                subgame_name = odd.get("subgame", {}).get("name", "")

                try:
                    value = float(odd.get("value", 0))
                except (ValueError, TypeError):
                    continue

                # 1X2
                if game_name == "Konačan ishod":
                    if subgame_name in ["1", "X", "2"]:
                        result_odds[subgame_name] = value

        if all(result_odds.values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=2,
                odd1=result_odds["1"],
                odd2=result_odds["X"],
                odd3=result_odds["2"]
            ))

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

            for league_id, league_name in leagues:
                try:
                    match_ids = await self.fetch_match_ids(sport_id, league_id)
                    if not match_ids:
                        continue

                    # Fetch match details with limited concurrency
                    for match_id in match_ids:
                        try:
                            match_data = await self.fetch_match_details(match_id, sport_id, league_id)
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
                    logger.warning(f"[Mozzart] Error processing league {league_name}: {e}")

        except Exception as e:
            logger.error(f"[Mozzart] Error scraping sport {sport_id}: {e}")

        return matches
