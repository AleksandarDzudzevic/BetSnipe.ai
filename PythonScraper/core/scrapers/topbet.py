"""
TopBet scraper for BetSnipe.ai v2.0

Scrapes odds from TopBet Serbia API (NSoft platform).
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

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


class TopbetScraper(BaseScraper):
    """
    Scraper for TopBet Serbia (NSoft platform).

    API is different from other Serbian bookmakers - uses NSoft distribution API.
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
        return [1, 2, 3, 4, 5]  # Football, Basketball, Tennis, Hockey, Table Tennis

    async def fetch_events(self, sport_id: int) -> Optional[Dict]:
        """Fetch events for a sport."""
        topbet_sport_id = None
        for tb_id, internal_id in TOPBET_SPORTS.items():
            if internal_id == sport_id:
                topbet_sport_id = tb_id
                break

        if topbet_sport_id is None:
            return None

        url = f"{self.get_base_url()}/events"
        params = {
            "deliveryPlatformId": "3",
            "dataFormat": '{"default":"object","events":"array","outcomes":"array"}',
            "language": '{"default":"sr-Latn","events":"sr-Latn","sport":"sr-Latn","category":"sr-Latn","tournament":"sr-Latn","team":"sr-Latn","market":"sr-Latn"}',
            "timezone": "Europe/Budapest",
            "company": "{}",
            "companyUuid": "4dd61a16-9691-4277-9027-8cd05a647844",
            "filter[sportId]": str(topbet_sport_id),
            "filter[from]": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "sort": "categoryPosition,categoryName,tournamentPosition,tournamentName,startsAt",
            "offerTemplate": "WEB_OVERVIEW",
            "shortProps": "1"
        }

        return await self.fetch_json(url, params=params)

    def parse_football_odds(self, event: Dict) -> List[ScrapedOdds]:
        """Parse football odds from TopBet event data."""
        odds_list = []
        markets = event.get("o", {})
        gg_ng_added = False

        for market_id, market_data in markets.items():
            outcomes = market_data.get("h", [])

            # 1X2 market (b=6, d=1)
            if market_data.get("b") == 6 and market_data.get("d") == 1:
                if len(outcomes) == 3:
                    odd1 = next((o.get("g") for o in outcomes if o.get("e") == "1"), None)
                    oddX = next((o.get("g") for o in outcomes if o.get("e") == "X"), None)
                    odd2 = next((o.get("g") for o in outcomes if o.get("e") == "2"), None)

                    if all([odd1, oddX, odd2]):
                        odds_list.append(ScrapedOdds(
                            bet_type_id=2,
                            odd1=float(odd1),
                            odd2=float(oddX),
                            odd3=float(odd2)
                        ))

            # GG/NG market
            if not gg_ng_added and outcomes:
                gg = next((o.get("g") for o in outcomes if o.get("e") == "GG"), None)
                ng = next((o.get("g") for o in outcomes if o.get("e") == "NG"), None)

                if gg and ng:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=8,
                        odd1=float(gg),
                        odd2=float(ng)
                    ))
                    gg_ng_added = True

            # Total Goals (Over/Under)
            # Check for markets with "Više" (over) and "Manje" (under) outcomes
            margin = market_data.get("n")  # Margin/special value
            if margin and outcomes:
                over = next((o.get("g") for o in outcomes if o.get("e") in ["Više", "+"]), None)
                under = next((o.get("g") for o in outcomes if o.get("e") in ["Manje", "-"]), None)

                if over and under:
                    try:
                        margin_val = float(margin)
                        if margin_val in [1.5, 2.5, 3.5, 4.5]:
                            odds_list.append(ScrapedOdds(
                                bet_type_id=5,
                                odd1=float(under),
                                odd2=float(over),
                                margin=margin_val
                            ))
                    except (ValueError, TypeError):
                        pass

        return odds_list

    def parse_basketball_odds(self, event: Dict) -> List[ScrapedOdds]:
        """Parse basketball odds from TopBet event data."""
        odds_list = []
        markets = event.get("o", {})

        for market_id, market_data in markets.items():
            outcomes = market_data.get("h", [])

            # Winner (12) - look for 2-way markets
            if len(outcomes) == 2:
                odd1 = next((o.get("g") for o in outcomes if o.get("e") == "1"), None)
                odd2 = next((o.get("g") for o in outcomes if o.get("e") == "2"), None)

                if odd1 and odd2:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=1,
                        odd1=float(odd1),
                        odd2=float(odd2)
                    ))
                    break  # Only add winner once

        return odds_list

    def parse_tennis_odds(self, event: Dict) -> List[ScrapedOdds]:
        """Parse tennis odds from TopBet event data."""
        odds_list = []
        markets = event.get("o", {})

        for market_id, market_data in markets.items():
            outcomes = market_data.get("h", [])

            # Match Winner (12)
            if len(outcomes) == 2:
                odd1 = next((o.get("g") for o in outcomes if o.get("e") == "1"), None)
                odd2 = next((o.get("g") for o in outcomes if o.get("e") == "2"), None)

                if odd1 and odd2:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=1,
                        odd1=float(odd1),
                        odd2=float(odd2)
                    ))
                    break  # Only add winner once

        return odds_list

    def parse_hockey_odds(self, event: Dict) -> List[ScrapedOdds]:
        """Parse hockey odds from TopBet event data."""
        odds_list = []
        markets = event.get("o", {})

        for market_id, market_data in markets.items():
            outcomes = market_data.get("h", [])

            # 1X2 market
            if len(outcomes) == 3:
                odd1 = next((o.get("g") for o in outcomes if o.get("e") == "1"), None)
                oddX = next((o.get("g") for o in outcomes if o.get("e") == "X"), None)
                odd2 = next((o.get("g") for o in outcomes if o.get("e") == "2"), None)

                if all([odd1, oddX, odd2]):
                    odds_list.append(ScrapedOdds(
                        bet_type_id=2,
                        odd1=float(odd1),
                        odd2=float(oddX),
                        odd3=float(odd2)
                    ))
                    break  # Only add 1X2 once

        return odds_list

    def parse_table_tennis_odds(self, event: Dict) -> List[ScrapedOdds]:
        """Parse table tennis odds from TopBet event data."""
        odds_list = []
        markets = event.get("o", {})

        for market_id, market_data in markets.items():
            outcomes = market_data.get("h", [])

            # Winner (12)
            if len(outcomes) == 2:
                odd1 = next((o.get("g") for o in outcomes if o.get("e") == "1"), None)
                odd2 = next((o.get("g") for o in outcomes if o.get("e") == "2"), None)

                if odd1 and odd2:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=1,
                        odd1=float(odd1),
                        odd2=float(odd2)
                    ))
                    break  # Only add winner once

        return odds_list

    def parse_odds(self, event: Dict, sport_id: int) -> List[ScrapedOdds]:
        """Parse odds based on sport type."""
        if sport_id == 1:
            return self.parse_football_odds(event)
        elif sport_id == 2:
            return self.parse_basketball_odds(event)
        elif sport_id == 3:
            return self.parse_tennis_odds(event)
        elif sport_id == 4:
            return self.parse_hockey_odds(event)
        elif sport_id == 5:
            return self.parse_table_tennis_odds(event)
        return []

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Scrape all matches for a sport."""
        matches: List[ScrapedMatch] = []

        data = await self.fetch_events(sport_id)

        if not data or "data" not in data or "events" not in data["data"]:
            return matches

        events = data["data"]["events"]
        logger.debug(f"[Topbet] Found {len(events)} events for sport {sport_id}")

        for event in events:
            try:
                # Parse team names (separated by " - ")
                match_name = event.get("j", "")
                teams = match_name.split(" - ")
                if len(teams) != 2:
                    continue

                team1, team2 = teams

                # Parse start time
                start_time_str = event.get("n")
                if not start_time_str:
                    continue

                try:
                    start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                except ValueError:
                    start_time = self.parse_timestamp(start_time_str)
                    if not start_time:
                        continue

                scraped = ScrapedMatch(
                    team1=team1,
                    team2=team2,
                    sport_id=sport_id,
                    start_time=start_time,
                    external_id=str(event.get("a")),  # Event ID
                )

                scraped.odds = self.parse_odds(event, sport_id)

                if scraped.odds:
                    matches.append(scraped)

            except Exception as e:
                logger.warning(f"[Topbet] Error processing event: {e}")

        return matches
