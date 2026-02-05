"""
SuperBet scraper for BetSnipe.ai v2.0

Scrapes odds from SuperBet Serbia API.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)

# Sport ID mapping (SuperBet to internal)
SUPERBET_SPORTS = {
    5: 1,   # Football
    2: 2,   # Basketball
    3: 3,   # Tennis
    4: 4,   # Hockey
    16: 5,  # Table Tennis
}


class SuperbetScraper(BaseScraper):
    """
    Scraper for SuperBet Serbia.

    API endpoints:
    - /events/by-date: Get event IDs
    - /events/{id}: Get event details with odds
    """

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

    def parse_football_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse football odds from SuperBet match data."""
        odds_list = []

        markets = {
            "1X2": {"1": None, "X": None, "2": None},
            "1X2F": {"1": None, "X": None, "2": None},
            "1X2S": {"1": None, "X": None, "2": None},
            "GGNG": {"GG": None, "NG": None},
            "TG": {},
            "TGF": {},
            "TGS": {}
        }

        for odd in match_data.get("odds", []):
            market_name = odd.get("marketName")
            code = odd.get("code")
            price = odd.get("price")
            margin = odd.get("specialBetValue")

            if market_name == "Konačan ishod" and code in ["1", "0", "2"]:
                key = "1" if code == "1" else "X" if code == "0" else "2"
                markets["1X2"][key] = price

            elif market_name == "1. poluvreme - 1X2" and code in ["1", "0", "2"]:
                key = "1" if code == "1" else "X" if code == "0" else "2"
                markets["1X2F"][key] = price

            elif market_name == "2. poluvreme - 1X2" and code in ["1", "0", "2"]:
                key = "1" if code == "1" else "X" if code == "0" else "2"
                markets["1X2S"][key] = price

            elif market_name == "Oba tima daju gol (GG)" and code in ["1", "2"]:
                markets["GGNG"]["GG" if code == "1" else "NG"] = price

            elif market_name == "Ukupno golova" and margin:
                if margin not in markets["TG"]:
                    markets["TG"][margin] = {"under": None, "over": None}
                if "Manje" in odd.get("name", ""):
                    markets["TG"][margin]["under"] = price
                elif "Više" in odd.get("name", ""):
                    markets["TG"][margin]["over"] = price

            elif market_name == "1. poluvreme - ukupno golova" and margin:
                if margin not in markets["TGF"]:
                    markets["TGF"][margin] = {"under": None, "over": None}
                if "Manje" in odd.get("name", ""):
                    markets["TGF"][margin]["under"] = price
                elif "Više" in odd.get("name", ""):
                    markets["TGF"][margin]["over"] = price

            elif market_name == "2. poluvreme - ukupno golova" and margin:
                if margin not in markets["TGS"]:
                    markets["TGS"][margin] = {"under": None, "over": None}
                if "Manje" in odd.get("name", ""):
                    markets["TGS"][margin]["under"] = price
                elif "Više" in odd.get("name", ""):
                    markets["TGS"][margin]["over"] = price

        # Convert to ScrapedOdds
        if all(markets["1X2"].values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=2,
                odd1=float(markets["1X2"]["1"]),
                odd2=float(markets["1X2"]["X"]),
                odd3=float(markets["1X2"]["2"])
            ))

        if all(markets["1X2F"].values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=3,
                odd1=float(markets["1X2F"]["1"]),
                odd2=float(markets["1X2F"]["X"]),
                odd3=float(markets["1X2F"]["2"])
            ))

        if all(markets["1X2S"].values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=4,
                odd1=float(markets["1X2S"]["1"]),
                odd2=float(markets["1X2S"]["X"]),
                odd3=float(markets["1X2S"]["2"])
            ))

        if all(markets["GGNG"].values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=8,
                odd1=float(markets["GGNG"]["GG"]),
                odd2=float(markets["GGNG"]["NG"])
            ))

        for margin, totals in markets["TG"].items():
            if all(totals.values()):
                try:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=5,
                        odd1=float(totals["under"]),
                        odd2=float(totals["over"]),
                        margin=float(margin)
                    ))
                except (ValueError, TypeError):
                    pass

        for margin, totals in markets["TGF"].items():
            if all(totals.values()):
                try:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=6,
                        odd1=float(totals["under"]),
                        odd2=float(totals["over"]),
                        margin=float(margin)
                    ))
                except (ValueError, TypeError):
                    pass

        for margin, totals in markets["TGS"].items():
            if all(totals.values()):
                try:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=7,
                        odd1=float(totals["under"]),
                        odd2=float(totals["over"]),
                        margin=float(margin)
                    ))
                except (ValueError, TypeError):
                    pass

        return odds_list

    def parse_basketball_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse basketball odds from SuperBet match data."""
        odds_list = []
        winner = {"1": None, "2": None}
        handicaps = {}
        totals = {}

        for odd in match_data.get("odds", []):
            market_name = odd.get("marketName", "")
            code = odd.get("code")
            price = odd.get("price")
            margin = odd.get("specialBetValue")

            # Winner (12)
            if market_name in ["Pobednik", "Pobednik meča"] and code in ["1", "2"]:
                winner[code] = price

            # Handicap
            elif "Hendikep" in market_name and margin:
                if margin not in handicaps:
                    handicaps[margin] = {"1": None, "2": None}
                if code in ["1", "2"]:
                    handicaps[margin][code] = price

            # Total Points
            elif "Ukupno poena" in market_name and margin:
                try:
                    total_val = float(margin)
                    if total_val > 130:  # Basketball totals
                        if margin not in totals:
                            totals[margin] = {"under": None, "over": None}
                        if "Manje" in odd.get("name", ""):
                            totals[margin]["under"] = price
                        elif "Više" in odd.get("name", ""):
                            totals[margin]["over"] = price
                except ValueError:
                    pass

        # Winner
        if all(winner.values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=1,
                odd1=float(winner["1"]),
                odd2=float(winner["2"])
            ))

        # Handicaps
        for margin, hcp in handicaps.items():
            if all(hcp.values()):
                try:
                    # Parse margin - handle formats like '1.5', '-1.5', '1.5-1'
                    margin_str = str(margin).split('-')[0] if '-' in str(margin) and not str(margin).startswith('-') else str(margin)
                    margin_val = float(margin_str)
                    odds_list.append(ScrapedOdds(
                        bet_type_id=9,
                        odd1=float(hcp["1"]),
                        odd2=float(hcp["2"]),
                        margin=margin_val
                    ))
                except (ValueError, TypeError):
                    pass

        # Totals
        for margin, tot in totals.items():
            if all(tot.values()):
                try:
                    margin_val = float(margin)
                    odds_list.append(ScrapedOdds(
                        bet_type_id=10,
                        odd1=float(tot["under"]),
                        odd2=float(tot["over"]),
                        margin=margin_val
                    ))
                except (ValueError, TypeError):
                    pass

        return odds_list

    def parse_tennis_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse tennis odds from SuperBet match data."""
        odds_list = []
        winner = {"1": None, "2": None}
        first_set = {"1": None, "2": None}

        for odd in match_data.get("odds", []):
            market_name = odd.get("marketName", "")
            code = odd.get("code")
            price = odd.get("price")

            # Match Winner
            if market_name in ["Pobednik", "Pobednik meča"] and code in ["1", "2"]:
                winner[code] = price

            # First Set Winner
            elif market_name in ["1. set - pobednik", "1. Set Pobednik"] and code in ["1", "2"]:
                first_set[code] = price

        if all(winner.values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=1,
                odd1=float(winner["1"]),
                odd2=float(winner["2"])
            ))

        if all(first_set.values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=11,
                odd1=float(first_set["1"]),
                odd2=float(first_set["2"])
            ))

        return odds_list

    def parse_hockey_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse hockey odds from SuperBet match data."""
        odds_list = []
        result_1x2 = {"1": None, "X": None, "2": None}

        for odd in match_data.get("odds", []):
            market_name = odd.get("marketName", "")
            code = odd.get("code")
            price = odd.get("price")

            # 1X2
            if market_name == "Konačan ishod" and code in ["1", "0", "2"]:
                key = "1" if code == "1" else "X" if code == "0" else "2"
                result_1x2[key] = price

        if all(result_1x2.values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=2,
                odd1=float(result_1x2["1"]),
                odd2=float(result_1x2["X"]),
                odd3=float(result_1x2["2"])
            ))

        return odds_list

    def parse_table_tennis_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse table tennis odds from SuperBet match data."""
        odds_list = []
        winner = {"1": None, "2": None}

        for odd in match_data.get("odds", []):
            market_name = odd.get("marketName", "")
            code = odd.get("code")
            price = odd.get("price")

            # Winner
            if market_name in ["Pobednik", "Pobednik meča"] and code in ["1", "2"]:
                winner[code] = price

        if all(winner.values()):
            odds_list.append(ScrapedOdds(
                bet_type_id=1,
                odd1=float(winner["1"]),
                odd2=float(winner["2"])
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
