"""
Merkur scraper for BetSnipe.ai v2.0

Scrapes odds from Merkur Serbia API (same platform as Soccerbet).
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)

# Sport code mappings
MERKUR_SPORTS = {
    'S': 1,   # Football
    'B': 2,   # Basketball
    'T': 3,   # Tennis
    'H': 4,   # Hockey
    'TT': 5,  # Table Tennis
}

INTERNAL_TO_MERKUR = {v: k for k, v in MERKUR_SPORTS.items()}


class MerkurScraper(BaseScraper):
    """
    Scraper for Merkur Serbia.

    Uses same API structure as Soccerbet (same platform).
    """

    def __init__(self):
        super().__init__(bookmaker_id=7, bookmaker_name="Merkur")

    def get_base_url(self) -> str:
        return "https://www.merkurxtip.rs/restapi/offer/sr"

    def get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        }

    def get_params(self) -> Dict[str, str]:
        return {"annex": "0", "desktopVersion": "1.3.2.6", "locale": "sr"}

    def get_supported_sports(self) -> List[int]:
        return [1, 2, 3, 4, 5]  # Football, Basketball, Tennis, Hockey, Table Tennis

    async def fetch_leagues(self, sport_id: int) -> List[Tuple[int, str]]:
        """Fetch leagues for a sport."""
        sport_code = None
        for code, sid in MERKUR_SPORTS.items():
            if sid == sport_id:
                sport_code = code
                break

        if not sport_code:
            return []

        url = f"{self.get_base_url()}/categories/ext/sport/{sport_code}/g"
        data = await self.fetch_json(url, params=self.get_params())

        if not data:
            return []

        leagues = []
        for category in data.get("categories", []):
            league_id = category.get("id")
            league_name = category.get("name")
            if league_id and league_name:
                leagues.append((league_id, league_name))

        return leagues

    async def fetch_league_matches(self, sport_id: int, league_id: int) -> List[Dict]:
        """Fetch matches for a league."""
        sport_code = None
        for code, sid in MERKUR_SPORTS.items():
            if sid == sport_id:
                sport_code = code
                break

        if not sport_code:
            return []

        url = f"{self.get_base_url()}/sport/{sport_code}/league-group/{league_id}/mob"
        data = await self.fetch_json(url, params=self.get_params())

        if not data:
            return []

        return data.get("esMatches", [])

    async def fetch_match_details(self, match_id: int) -> Optional[Dict]:
        """Fetch detailed match data."""
        url = f"{self.get_base_url()}/match/{match_id}"
        return await self.fetch_json(url, params=self.get_params())

    def parse_odds(self, match_data: Dict, sport_id: int) -> List[ScrapedOdds]:
        """Parse odds from Merkur match data."""
        odds_list = []
        odds = match_data.get("odds", {})

        if sport_id == 1:  # Football
            # 1X2
            odd1 = odds.get("1")
            oddX = odds.get("2")
            odd2 = odds.get("3")
            if all([odd1, oddX, odd2]) and all(x != "N/A" for x in [odd1, oddX, odd2]):
                odds_list.append(ScrapedOdds(
                    bet_type_id=2, odd1=float(odd1), odd2=float(oddX), odd3=float(odd2)
                ))

            # 1X2 First Half
            odd1 = odds.get("4")
            oddX = odds.get("5")
            odd2 = odds.get("6")
            if all([odd1, oddX, odd2]) and all(x != "N/A" for x in [odd1, oddX, odd2]):
                odds_list.append(ScrapedOdds(
                    bet_type_id=3, odd1=float(odd1), odd2=float(oddX), odd3=float(odd2)
                ))

            # 1X2 Second Half
            odd1 = odds.get("235")
            oddX = odds.get("236")
            odd2 = odds.get("237")
            if all([odd1, oddX, odd2]) and all(x != "N/A" for x in [odd1, oddX, odd2]):
                odds_list.append(ScrapedOdds(
                    bet_type_id=4, odd1=float(odd1), odd2=float(oddX), odd3=float(odd2)
                ))

            # BTTS
            gg = odds.get("272")
            ng = odds.get("273")
            if gg and ng and gg != "N/A" and ng != "N/A":
                odds_list.append(ScrapedOdds(
                    bet_type_id=8, odd1=float(gg), odd2=float(ng)
                ))

            # Total Goals Full Time
            total_pairs = {
                1.5: ("21", "242"),
                2.5: ("22", "24"),
                3.5: ("219", "25"),
                4.5: ("453", "27"),
            }
            for total, (under_code, over_code) in total_pairs.items():
                under = odds.get(under_code)
                over = odds.get(over_code)
                if under and over and under != "N/A" and over != "N/A":
                    odds_list.append(ScrapedOdds(
                        bet_type_id=5, odd1=float(under), odd2=float(over), margin=total
                    ))

            # Total Goals First Half
            total_h1_pairs = {
                0.5: ("267", "207"),
                1.5: ("211", "208"),
                2.5: ("472", "209"),
            }
            for total, (under_code, over_code) in total_h1_pairs.items():
                under = odds.get(under_code)
                over = odds.get(over_code)
                if under and over and under != "N/A" and over != "N/A":
                    odds_list.append(ScrapedOdds(
                        bet_type_id=6, odd1=float(under), odd2=float(over), margin=total
                    ))

            # Total Goals Second Half
            total_h2_pairs = {
                0.5: ("269", "213"),
                1.5: ("217", "214"),
                2.5: ("474", "215"),
            }
            for total, (under_code, over_code) in total_h2_pairs.items():
                under = odds.get(under_code)
                over = odds.get(over_code)
                if under and over and under != "N/A" and over != "N/A":
                    odds_list.append(ScrapedOdds(
                        bet_type_id=7, odd1=float(under), odd2=float(over), margin=total
                    ))

        elif sport_id in [2, 3, 5]:  # Basketball, Tennis, Table Tennis
            odd1 = odds.get("1")
            odd2 = odds.get("3")
            if odd1 and odd2 and odd1 != "N/A" and odd2 != "N/A":
                odds_list.append(ScrapedOdds(
                    bet_type_id=1, odd1=float(odd1), odd2=float(odd2)
                ))

        elif sport_id == 4:  # Hockey - 1X2
            odd1 = odds.get("1")
            oddX = odds.get("2")
            odd2 = odds.get("3")
            if all([odd1, oddX, odd2]) and all(x != "N/A" for x in [odd1, oddX, odd2]):
                odds_list.append(ScrapedOdds(
                    bet_type_id=2, odd1=float(odd1), odd2=float(oddX), odd3=float(odd2)
                ))

        return odds_list

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Scrape all matches for a sport."""
        matches: List[ScrapedMatch] = []

        leagues = await self.fetch_leagues(sport_id)
        if not leagues:
            return matches

        logger.debug(f"[Merkur] Found {len(leagues)} leagues for sport {sport_id}")

        for league_id, league_name in leagues:
            try:
                league_matches = await self.fetch_league_matches(sport_id, league_id)
                if not league_matches:
                    continue

                # Process in batches
                batch_size = 10
                for i in range(0, len(league_matches), batch_size):
                    batch = league_matches[i:i + batch_size]

                    tasks = [
                        self.fetch_match_details(m["id"])
                        for m in batch
                    ]
                    details = await asyncio.gather(*tasks, return_exceptions=True)

                    for match_info, detail in zip(batch, details):
                        if isinstance(detail, Exception) or not detail:
                            continue

                        try:
                            team1 = match_info.get("home", "")
                            team2 = match_info.get("away", "")
                            if not team1 or not team2:
                                continue

                            kick_off = detail.get("kickOffTime")
                            if not kick_off:
                                continue
                            start_time = datetime.utcfromtimestamp(kick_off / 1000)

                            scraped = ScrapedMatch(
                                team1=team1,
                                team2=team2,
                                sport_id=sport_id,
                                start_time=start_time,
                                league_name=league_name,
                                external_id=str(match_info.get("id")),
                            )

                            scraped.odds = self.parse_odds(detail, sport_id)

                            if scraped.odds:
                                matches.append(scraped)

                        except Exception as e:
                            logger.warning(f"[Merkur] Error processing match: {e}")

                    await asyncio.sleep(0.05)

            except Exception as e:
                logger.warning(f"[Merkur] Error processing league {league_name}: {e}")

        return matches
