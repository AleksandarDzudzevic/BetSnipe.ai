"""
Meridian Bet scraper for BetSnipe.ai v2.0

Scrapes odds from Meridian Bet Serbia API.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import aiohttp

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
    Odds are embedded inline in the leagues response — no per-event market calls needed.
    """

    def __init__(self):
        super().__init__(bookmaker_id=2, bookmaker_name="Meridian")
        self._auth_token: Optional[str] = None
        self._rate_semaphore = asyncio.Semaphore(MERIDIAN_MAX_CONCURRENT)

    def get_base_url(self) -> str:
        return "https://online.meridianbet.com/betshop/api"

    def get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "sr-Latn-RS,sr;q=0.9,en-US;q=0.8",
            "Origin": "https://meridianbet.rs",
            "Referer": "https://meridianbet.rs/sr/kladjenje/fudbal",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "medium": "PREMATCH_WEB",
            "language": "sr",
            "x-timezone-offset": "-60",
        }
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    def get_supported_sports(self) -> List[int]:
        return [1, 2, 3, 4, 5]

    async def fetch_auth_token(self) -> Optional[str]:
        """Fetch auth token from main page using regex on raw HTML."""
        try:
            url = "https://meridianbet.rs/sr/kladjenje/fudbal"
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "sr-Latn-RS,sr;q=0.9",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            }
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.warning(f"[Meridian] Auth page returned {response.status}")
                    return None
                text = await response.text()
                # The HTML embeds: {"NEW_TOKEN":"{\"access_token\":\"eyJ...\"}"}
                # JWT is base64url chars (A-Za-z0-9._-) in escaped JSON
                m = re.search(r'\\\"access_token\\\":\\\"([A-Za-z0-9._-]+)\\\"', text)
                if m:
                    token = m.group(1)
                    logger.info(f"[Meridian] Successfully extracted auth token ({len(token)} chars)")
                    return token
                # Fallback: try Nigerian site
                logger.warning("[Meridian] Token not found on .rs site, trying .ng fallback")
                return await self._fetch_token_from_ng()
        except Exception as e:
            logger.warning(f"[Meridian] Error fetching auth token: {e}")
        return None

    async def _fetch_token_from_ng(self) -> Optional[str]:
        """Fallback: fetch token from Nigerian Meridian site (same token format)."""
        try:
            url = "https://meridianbet.ng/en/betting"
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            }
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    return None
                text = await response.text()
                m = re.search(r'\\\"access_token\\\":\\\"([A-Za-z0-9._-]+)\\\"', text)
                if m:
                    logger.info("[Meridian] Using token from .ng fallback site")
                    return m.group(1)
        except Exception as e:
            logger.warning(f"[Meridian] Error fetching .ng fallback token: {e}")
        return None

    async def ensure_token(self) -> bool:
        """Ensure we have a valid auth token."""
        if not self._auth_token:
            self._auth_token = await self.fetch_auth_token()
        return self._auth_token is not None

    async def fetch_events(self, sport_id: int, page: int = 0) -> Optional[Dict]:
        """Fetch events (with embedded odds) for a sport page."""
        meridian_sport_id = next((mid for mid, sid in MERIDIAN_SPORTS.items() if sid == sport_id), None)
        if not meridian_sport_id:
            return None

        url = f"{self.get_base_url()}/v1/standard/sport/{meridian_sport_id}/leagues"
        params = {
            "page": str(page),
            "time": "ALL",
            "groupIndices": "0,0,0"
        }

        return await self.fetch_json(url, params=params)

    def parse_football_odds(self, groups: List[Dict]) -> List[ScrapedOdds]:
        """Parse football odds from Meridian groups (flat list of group dicts)."""
        odds_list = []

        for group in groups:
            market_name = group.get("name", "")
            selections = group.get("selections", [])
            # Filter to only ACTIVE selections
            active = [s for s in selections if s.get("state") == "ACTIVE"]
            over_under = group.get("overUnder")
            handicap = group.get("handicap")

            if market_name == "Konačan Ishod":
                if len(active) >= 3:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=2,
                        odd1=float(active[0].get("price", 0)),
                        odd2=float(active[1].get("price", 0)),
                        odd3=float(active[2].get("price", 0))
                    ))

            elif market_name in ("I Pol. Konačan Ishod", "Prvo Poluvreme - Konačan Ishod"):
                if len(active) >= 3:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=3,
                        odd1=float(active[0].get("price", 0)),
                        odd2=float(active[1].get("price", 0)),
                        odd3=float(active[2].get("price", 0))
                    ))

            elif market_name in ("II Pol. Konačan Ishod", "Drugo Poluvreme - Konačan Ishod"):
                if len(active) >= 3:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=4,
                        odd1=float(active[0].get("price", 0)),
                        odd2=float(active[1].get("price", 0)),
                        odd3=float(active[2].get("price", 0))
                    ))

            elif market_name == "Oba Tima Daju Gol":
                gg = next((s.get("price") for s in active if s.get("name") == "GG"), None)
                ng = next((s.get("price") for s in active if s.get("name") == "NG"), None)
                if gg and ng:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=8,
                        odd1=float(gg),
                        odd2=float(ng)
                    ))

            elif market_name == "Ukupno Golova":
                if over_under and len(active) >= 2:
                    # Assign Over/Under explicitly by name to avoid positional errors
                    over_price = next((s.get("price") for s in active if s.get("name") in ("Više", "Over", "V")), None)
                    under_price = next((s.get("price") for s in active if s.get("name") in ("Manje", "Under", "M")), None)
                    # Fallback to positional if names not found
                    if over_price is None:
                        over_price = active[0].get("price", 0)
                    if under_price is None:
                        under_price = active[1].get("price", 0)
                    odds_list.append(ScrapedOdds(
                        bet_type_id=5,
                        odd1=float(over_price),
                        odd2=float(under_price),
                        margin=float(over_under)
                    ))

            elif market_name in ("I Pol. Ukupno", "Prvo Poluvreme - Ukupno Golova"):
                if over_under and len(active) >= 2:
                    over_price = next((s.get("price") for s in active if s.get("name") in ("Više", "Over", "V")), None)
                    under_price = next((s.get("price") for s in active if s.get("name") in ("Manje", "Under", "M")), None)
                    if over_price is None:
                        over_price = active[0].get("price", 0)
                    if under_price is None:
                        under_price = active[1].get("price", 0)
                    odds_list.append(ScrapedOdds(
                        bet_type_id=6,
                        odd1=float(over_price),
                        odd2=float(under_price),
                        margin=float(over_under)
                    ))

            elif market_name in ("II Pol. Ukupno", "Drugo Poluvreme - Ukupno Golova"):
                if over_under and len(active) >= 2:
                    over_price = next((s.get("price") for s in active if s.get("name") in ("Više", "Over", "V")), None)
                    under_price = next((s.get("price") for s in active if s.get("name") in ("Manje", "Under", "M")), None)
                    if over_price is None:
                        over_price = active[0].get("price", 0)
                    if under_price is None:
                        under_price = active[1].get("price", 0)
                    odds_list.append(ScrapedOdds(
                        bet_type_id=7,
                        odd1=float(over_price),
                        odd2=float(under_price),
                        margin=float(over_under)
                    ))

        return odds_list

    def parse_basketball_odds(self, groups: List[Dict]) -> List[ScrapedOdds]:
        """Parse basketball odds from Meridian groups (flat list of group dicts)."""
        odds_list = []

        for group in groups:
            market_name = group.get("name", "")
            selections = group.get("selections", [])
            active = [s for s in selections if s.get("state") == "ACTIVE"]
            over_under = group.get("overUnder")
            handicap = group.get("handicap")

            # Winner (12)
            if market_name in ["Pobednik", "Pobednik Meča"]:
                if len(active) >= 2:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=1,
                        odd1=float(active[0].get("price", 0)),
                        odd2=float(active[1].get("price", 0))
                    ))

            # Total Points
            elif market_name == "Ukupno Poena":
                if over_under and len(active) >= 2:
                    total = float(over_under)
                    if total > 130:  # Basketball totals
                        odds_list.append(ScrapedOdds(
                            bet_type_id=10,
                            odd1=float(active[0].get("price", 0)),
                            odd2=float(active[1].get("price", 0)),
                            margin=total
                        ))

            # Handicap
            elif market_name == "Hendikep":
                if handicap and len(active) >= 2:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=9,
                        odd1=float(active[0].get("price", 0)),
                        odd2=float(active[1].get("price", 0)),
                        margin=float(handicap)
                    ))

        return odds_list

    def parse_tennis_odds(self, groups: List[Dict]) -> List[ScrapedOdds]:
        """Parse tennis odds from Meridian groups (flat list of group dicts)."""
        odds_list = []

        for group in groups:
            market_name = group.get("name", "")
            selections = group.get("selections", [])
            active = [s for s in selections if s.get("state") == "ACTIVE"]

            # Match Winner (12)
            if market_name in ["Pobednik", "Pobednik Meča"]:
                if len(active) >= 2:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=1,
                        odd1=float(active[0].get("price", 0)),
                        odd2=float(active[1].get("price", 0))
                    ))

            # First Set Winner — bt57 (2-way set winner)
            elif market_name in ["1. Set - Pobednik", "I Set Pobednik"]:
                if len(active) >= 2:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=57,
                        odd1=float(active[0].get("price", 0)),
                        odd2=float(active[1].get("price", 0))
                    ))

        return odds_list

    def parse_hockey_odds(self, groups: List[Dict]) -> List[ScrapedOdds]:
        """Parse hockey odds from Meridian groups (flat list of group dicts)."""
        odds_list = []

        for group in groups:
            market_name = group.get("name", "")
            selections = group.get("selections", [])
            active = [s for s in selections if s.get("state") == "ACTIVE"]

            # 1X2
            if market_name == "Konačan Ishod":
                if len(active) >= 3:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=2,
                        odd1=float(active[0].get("price", 0)),
                        odd2=float(active[1].get("price", 0)),
                        odd3=float(active[2].get("price", 0))
                    ))

        return odds_list

    def parse_table_tennis_odds(self, groups: List[Dict]) -> List[ScrapedOdds]:
        """Parse table tennis odds from Meridian groups (flat list of group dicts)."""
        odds_list = []

        for group in groups:
            market_name = group.get("name", "")
            selections = group.get("selections", [])
            active = [s for s in selections if s.get("state") == "ACTIVE"]

            # Winner (12)
            if market_name in ["Pobednik", "Pobednik Meča"]:
                if len(active) >= 2:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=1,
                        odd1=float(active[0].get("price", 0)),
                        odd2=float(active[1].get("price", 0))
                    ))

        return odds_list

    def parse_odds(self, groups: List[Dict], sport_id: int) -> List[ScrapedOdds]:
        """Parse odds based on sport type. groups is a flat list of group dicts."""
        if sport_id == 1:
            return self.parse_football_odds(groups)
        elif sport_id == 2:
            return self.parse_basketball_odds(groups)
        elif sport_id == 3:
            return self.parse_tennis_odds(groups)
        elif sport_id == 4:
            return self.parse_hockey_odds(groups)
        elif sport_id == 5:
            return self.parse_table_tennis_odds(groups)
        return []

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Scrape all matches for a sport. Odds are embedded inline in the leagues response."""
        matches: List[ScrapedMatch] = []

        if not await self.ensure_token():
            logger.warning("[Meridian] Could not obtain auth token")
            return matches

        meridian_sport_id = next((mid for mid, sid in MERIDIAN_SPORTS.items() if sid == sport_id), None)
        if not meridian_sport_id:
            return matches

        page = 0
        total_events = 0

        while True:
            data = await self.fetch_events(sport_id, page)
            if not data:
                break

            payload = data.get("payload", {})
            leagues = payload.get("leagues", [])
            if not leagues:
                break

            for league in leagues:
                league_name = league.get("leagueName", "")
                for event in league.get("events", []):
                    header = event.get("header", {})
                    event_id = header.get("eventId")
                    rivals = header.get("rivals", [])
                    start_time_ms = header.get("startTime", 0)
                    state = header.get("state", "")

                    if not event_id or len(rivals) < 2 or state != "ACTIVE":
                        continue

                    start_time = datetime.fromtimestamp(start_time_ms / 1000, tz=timezone.utc) if start_time_ms else None
                    if not start_time:
                        continue

                    # Extract all groups from all positions (the embedded odds)
                    all_groups = []
                    for position in event.get("positions", []):
                        all_groups.extend(position.get("groups", []))

                    if not all_groups:
                        continue

                    try:
                        scraped = ScrapedMatch(
                            team1=rivals[0],
                            team2=rivals[1],
                            sport_id=sport_id,
                            start_time=start_time,
                            league_name=league_name,
                            external_id=str(event_id),
                        )
                        scraped.odds = self.parse_odds(all_groups, sport_id)
                        if scraped.odds:
                            matches.append(scraped)
                            total_events += 1
                    except Exception as e:
                        logger.warning(f"[Meridian] Error processing event {event_id}: {e}")

            page += 1

        logger.info(f"[Meridian] Sport {sport_id}: scraped {total_events} events across {page} pages")
        return matches
