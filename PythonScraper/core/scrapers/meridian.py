"""
Meridian Bet scraper for BetSnipe.ai v2.0

Scrapes odds from Meridian Bet Serbia API.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any

import aiohttp
from bs4 import BeautifulSoup

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)

# Rate limiting: max concurrent requests and delay between requests
MERIDIAN_MAX_CONCURRENT = 2
MERIDIAN_REQUEST_DELAY = 0.5  # seconds between requests

# Sport ID mapping (Meridian to internal)
MERIDIAN_SPORTS = {
    58: 1,   # Football
    67: 2,   # Basketball
    69: 3,   # Tennis
    64: 4,   # Hockey
    92: 5,   # Table Tennis
}


class MeridianScraper(BaseScraper):
    """
    Scraper for Meridian Bet Serbia.

    Requires auth token from main page, then uses API endpoints.
    """

    def __init__(self):
        super().__init__(bookmaker_id=2, bookmaker_name="Meridian")
        self._auth_token: Optional[str] = None
        self._rate_semaphore = asyncio.Semaphore(MERIDIAN_MAX_CONCURRENT)

    def get_base_url(self) -> str:
        return "https://online.meridianbet.com/betshop/api"

    def get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Accept-Language": "sr",
            "Origin": "https://meridianbet.rs",
            "Referer": "https://meridianbet.rs/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    def get_supported_sports(self) -> List[int]:
        return [1, 2, 3, 4, 5]

    async def fetch_auth_token(self) -> Optional[str]:
        """Fetch auth token from main page."""
        try:
            url = "https://meridianbet.rs/sr/kladjenje/fudbal"
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            }

            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    return None

                text = await response.text()
                soup = BeautifulSoup(text, "html.parser")

                for script in soup.find_all("script"):
                    if script.string and "NEW_TOKEN" in script.string:
                        try:
                            import json
                            json_data = json.loads(script.string)
                            if "NEW_TOKEN" in json_data:
                                token_data = json.loads(json_data["NEW_TOKEN"])
                                if "access_token" in token_data:
                                    return token_data["access_token"]
                        except (json.JSONDecodeError, KeyError):
                            continue

        except Exception as e:
            logger.warning(f"[Meridian] Error fetching auth token: {e}")

        return None

    async def ensure_token(self) -> bool:
        """Ensure we have a valid auth token."""
        if not self._auth_token:
            self._auth_token = await self.fetch_auth_token()
        return self._auth_token is not None

    async def fetch_events(self, sport_id: int, page: int = 0) -> Optional[Dict]:
        """Fetch events for a sport page."""
        meridian_sport_id = None
        for mid, sid in MERIDIAN_SPORTS.items():
            if sid == sport_id:
                meridian_sport_id = mid
                break

        if not meridian_sport_id:
            return None

        url = f"{self.get_base_url()}/v1/standard/sport/{meridian_sport_id}/leagues"
        params = {
            "page": str(page),
            "time": "ALL",
            "groupIndices": "0,0,0"
        }

        return await self.fetch_json(url, params=params)

    async def fetch_event_markets(self, event_id: int) -> Optional[List[Dict]]:
        """Fetch markets/odds for an event with rate limiting."""
        async with self._rate_semaphore:
            url = f"{self.get_base_url()}/v2/events/{event_id}/markets"

            data = await self.fetch_json(url)
            await asyncio.sleep(MERIDIAN_REQUEST_DELAY)

            if data:
                return data.get("payload", [])
            return None

    def parse_football_odds(self, markets: List[Dict]) -> List[ScrapedOdds]:
        """Parse football odds from Meridian markets."""
        odds_list = []

        for market_group in markets:
            market_name = market_group.get("marketName", "")

            if market_name == "Konačan Ishod":
                for market in market_group.get("markets", []):
                    selections = market.get("selections", [])
                    if len(selections) >= 3:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=2,
                            odd1=float(selections[0].get("price", 0)),
                            odd2=float(selections[1].get("price", 0)),
                            odd3=float(selections[2].get("price", 0))
                        ))

            elif market_name in ("I Pol. Konačan Ishod", "Prvo Poluvreme - Konačan Ishod"):
                for market in market_group.get("markets", []):
                    selections = market.get("selections", [])
                    if len(selections) >= 3:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=3,
                            odd1=float(selections[0].get("price", 0)),
                            odd2=float(selections[1].get("price", 0)),
                            odd3=float(selections[2].get("price", 0))
                        ))

            elif market_name in ("II Pol. Konačan Ishod", "Drugo Poluvreme - Konačan Ishod"):
                for market in market_group.get("markets", []):
                    selections = market.get("selections", [])
                    if len(selections) >= 3:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=4,
                            odd1=float(selections[0].get("price", 0)),
                            odd2=float(selections[1].get("price", 0)),
                            odd3=float(selections[2].get("price", 0))
                        ))

            elif market_name == "Oba Tima Daju Gol":
                for market in market_group.get("markets", []):
                    selections = market.get("selections", [])
                    gg = next((s.get("price") for s in selections if s.get("name") == "GG"), None)
                    ng = next((s.get("price") for s in selections if s.get("name") == "NG"), None)
                    if gg and ng:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=8,
                            odd1=float(gg),
                            odd2=float(ng)
                        ))

            elif market_name == "Ukupno Golova":
                for market in market_group.get("markets", []):
                    over_under = market.get("overUnder")
                    selections = market.get("selections", [])
                    if over_under and len(selections) >= 2:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=5,
                            odd1=float(selections[0].get("price", 0)),  # Over
                            odd2=float(selections[1].get("price", 0)),  # Under
                            margin=float(over_under)
                        ))

            elif market_name in ("I Pol. Ukupno", "Prvo Poluvreme - Ukupno Golova"):
                for market in market_group.get("markets", []):
                    over_under = market.get("overUnder")
                    selections = market.get("selections", [])
                    if over_under and len(selections) >= 2:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=6,
                            odd1=float(selections[0].get("price", 0)),
                            odd2=float(selections[1].get("price", 0)),
                            margin=float(over_under)
                        ))

            elif market_name in ("II Pol. Ukupno", "Drugo Poluvreme - Ukupno Golova"):
                for market in market_group.get("markets", []):
                    over_under = market.get("overUnder")
                    selections = market.get("selections", [])
                    if over_under and len(selections) >= 2:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=7,
                            odd1=float(selections[0].get("price", 0)),
                            odd2=float(selections[1].get("price", 0)),
                            margin=float(over_under)
                        ))

        return odds_list

    def parse_basketball_odds(self, markets: List[Dict]) -> List[ScrapedOdds]:
        """Parse basketball odds from Meridian markets."""
        odds_list = []

        for market_group in markets:
            market_name = market_group.get("marketName", "")

            # Winner (12)
            if market_name in ["Pobednik", "Pobednik Meča"]:
                for market in market_group.get("markets", []):
                    selections = market.get("selections", [])
                    if len(selections) >= 2:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=1,
                            odd1=float(selections[0].get("price", 0)),
                            odd2=float(selections[1].get("price", 0))
                        ))

            # Total Points
            elif market_name == "Ukupno Poena":
                for market in market_group.get("markets", []):
                    over_under = market.get("overUnder")
                    selections = market.get("selections", [])
                    if over_under and len(selections) >= 2:
                        total = float(over_under)
                        if total > 130:  # Basketball totals
                            odds_list.append(ScrapedOdds(
                                bet_type_id=10,
                                odd1=float(selections[0].get("price", 0)),
                                odd2=float(selections[1].get("price", 0)),
                                margin=total
                            ))

            # Handicap
            elif market_name == "Hendikep":
                for market in market_group.get("markets", []):
                    handicap = market.get("handicap")
                    selections = market.get("selections", [])
                    if handicap and len(selections) >= 2:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=9,
                            odd1=float(selections[0].get("price", 0)),
                            odd2=float(selections[1].get("price", 0)),
                            margin=float(handicap)
                        ))

        return odds_list

    def parse_tennis_odds(self, markets: List[Dict]) -> List[ScrapedOdds]:
        """Parse tennis odds from Meridian markets."""
        odds_list = []

        for market_group in markets:
            market_name = market_group.get("marketName", "")

            # Match Winner (12)
            if market_name in ["Pobednik", "Pobednik Meča"]:
                for market in market_group.get("markets", []):
                    selections = market.get("selections", [])
                    if len(selections) >= 2:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=1,
                            odd1=float(selections[0].get("price", 0)),
                            odd2=float(selections[1].get("price", 0))
                        ))

            # First Set Winner
            elif market_name in ["1. Set - Pobednik", "I Set Pobednik"]:
                for market in market_group.get("markets", []):
                    selections = market.get("selections", [])
                    if len(selections) >= 2:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=11,
                            odd1=float(selections[0].get("price", 0)),
                            odd2=float(selections[1].get("price", 0))
                        ))

        return odds_list

    def parse_hockey_odds(self, markets: List[Dict]) -> List[ScrapedOdds]:
        """Parse hockey odds from Meridian markets."""
        odds_list = []

        for market_group in markets:
            market_name = market_group.get("marketName", "")

            # 1X2
            if market_name == "Konačan Ishod":
                for market in market_group.get("markets", []):
                    selections = market.get("selections", [])
                    if len(selections) >= 3:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=2,
                            odd1=float(selections[0].get("price", 0)),
                            odd2=float(selections[1].get("price", 0)),
                            odd3=float(selections[2].get("price", 0))
                        ))

        return odds_list

    def parse_table_tennis_odds(self, markets: List[Dict]) -> List[ScrapedOdds]:
        """Parse table tennis odds from Meridian markets."""
        odds_list = []

        for market_group in markets:
            market_name = market_group.get("marketName", "")

            # Winner (12)
            if market_name in ["Pobednik", "Pobednik Meča"]:
                for market in market_group.get("markets", []):
                    selections = market.get("selections", [])
                    if len(selections) >= 2:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=1,
                            odd1=float(selections[0].get("price", 0)),
                            odd2=float(selections[1].get("price", 0))
                        ))

        return odds_list

    def parse_odds(self, markets: List[Dict], sport_id: int) -> List[ScrapedOdds]:
        """Parse odds based on sport type."""
        if sport_id == 1:
            return self.parse_football_odds(markets)
        elif sport_id == 2:
            return self.parse_basketball_odds(markets)
        elif sport_id == 3:
            return self.parse_tennis_odds(markets)
        elif sport_id == 4:
            return self.parse_hockey_odds(markets)
        elif sport_id == 5:
            return self.parse_table_tennis_odds(markets)
        return []

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Scrape all matches for a sport with rate-limited market fetching."""
        matches: List[ScrapedMatch] = []

        # Ensure we have auth token
        if not await self.ensure_token():
            logger.warning("[Meridian] Could not obtain auth token")
            return matches

        # Step 1: Collect all events from league pages
        page = 0
        events = []

        while True:
            data = await self.fetch_events(sport_id, page)

            if not data or "payload" not in data:
                break

            leagues = data.get("payload", {}).get("leagues", [])
            if not leagues:
                break

            for league in leagues:
                for event in league.get("events", []):
                    header = event.get("header", {})
                    event_id = header.get("eventId")
                    rivals = header.get("rivals", [])
                    start_time_ms = header.get("startTime", 0)

                    if not event_id or len(rivals) < 2:
                        continue

                    events.append({
                        'event_id': event_id,
                        'team1': rivals[0],
                        'team2': rivals[1],
                        'start_time': datetime.utcfromtimestamp(start_time_ms / 1000) if start_time_ms else None,
                        'league_name': league.get("name", ""),
                    })

            page += 1

        logger.info(f"[Meridian] Found {len(events)} events for sport {sport_id}, fetching markets ({MERIDIAN_MAX_CONCURRENT} concurrent, {MERIDIAN_REQUEST_DELAY}s delay)...")

        # Step 2: Fetch markets with rate limiting (semaphore + delay in fetch_event_markets)
        market_tasks = [
            self.fetch_event_markets(evt['event_id'])
            for evt in events
        ]
        market_results = await asyncio.gather(*market_tasks, return_exceptions=True)

        # Step 3: Parse results
        errors = 0
        for evt, market_data in zip(events, market_results):
            if isinstance(market_data, Exception):
                errors += 1
                logger.debug(f"[Meridian] Market fetch error for {evt['event_id']}: {market_data}")
                continue
            if not market_data:
                errors += 1
                continue

            try:
                scraped = ScrapedMatch(
                    team1=evt['team1'],
                    team2=evt['team2'],
                    sport_id=sport_id,
                    start_time=evt['start_time'],
                    league_name=evt['league_name'],
                    external_id=str(evt['event_id']),
                )

                scraped.odds = self.parse_odds(market_data, sport_id)

                if scraped.odds:
                    matches.append(scraped)

            except Exception as e:
                logger.warning(f"[Meridian] Error processing event {evt['event_id']}: {e}")

        if errors:
            logger.warning(f"[Meridian] {errors}/{len(events)} market fetches failed for sport {sport_id}")

        return matches
