"""
Soccerbet scraper for BetSnipe.ai v2.0

Scrapes odds from Soccerbet Serbia API.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)


# Soccerbet bet code mappings for football
SOCCERBET_FOOTBALL_BETS = {
    '1X2': {'1': '1', 'X': '2', '2': '3'},
    '1X2_H1': {'1': '4', 'X': '5', '2': '6'},
    '1X2_H2': {'1': '235', 'X': '236', '2': '237'},
    'BTTS': {'GG': '272', 'NG': '273'},
    'TOTAL': {
        1.5: {'under': '21', 'over': '242'},
        2.5: {'under': '22', 'over': '24'},
        3.5: {'under': '219', 'over': '25'},
        4.5: {'under': '453', 'over': '27'},
    },
    'TOTAL_H1': {
        0.5: {'under': '267', 'over': '207'},
        1.5: {'under': '211', 'over': '208'},
        2.5: {'under': '472', 'over': '209'},
    },
    'TOTAL_H2': {
        0.5: {'under': '269', 'over': '213'},
        1.5: {'under': '217', 'over': '214'},
        2.5: {'under': '474', 'over': '215'},
    },
}

# Sport code mappings (Soccerbet to our internal)
SPORT_CODES = {
    1: 'S',   # Football
    2: 'B',   # Basketball
    3: 'T',   # Tennis
    4: 'H',   # Hockey
    5: 'TT',  # Table Tennis
}


class SoccerbetScraper(BaseScraper):
    """
    Scraper for Soccerbet Serbia.

    API endpoints:
    - /categories/ext/sport/{code}/g: Get leagues for a sport
    - /sport/{code}/league-group/{id}/mob: Get matches for a league
    - /match/{id}: Get detailed odds for a match
    """

    def __init__(self):
        super().__init__(bookmaker_id=5, bookmaker_name="Soccerbet")

    def get_base_url(self) -> str:
        return "https://www.soccerbet.rs/restapi/offer/sr"

    def get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        }

    def get_params(self) -> Dict[str, str]:
        """Common query parameters."""
        return {
            "annex": "0",
            "desktopVersion": "2.36.3.9",
            "locale": "sr"
        }

    def get_supported_sports(self) -> List[int]:
        return [1, 2, 3, 4, 5]  # Football, Basketball, Tennis, Hockey, Table Tennis

    async def fetch_leagues(self, sport_id: int) -> List[Tuple[str, str]]:
        """Fetch all leagues for a sport."""
        sport_code = SPORT_CODES.get(sport_id)
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
                leagues.append((str(league_id), league_name))

        return leagues

    async def fetch_league_matches(
        self,
        sport_id: int,
        league_id: str
    ) -> List[Dict[str, Any]]:
        """Fetch matches for a specific league."""
        sport_code = SPORT_CODES.get(sport_id)
        if not sport_code:
            return []

        url = f"{self.get_base_url()}/sport/{sport_code}/league-group/{league_id}/mob"
        data = await self.fetch_json(url, params=self.get_params())

        if not data:
            return []

        return data.get("esMatches", [])

    async def fetch_match_details(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed odds for a match."""
        url = f"{self.get_base_url()}/match/{match_id}"
        return await self.fetch_json(url, params=self.get_params())

    def parse_football_odds(self, bet_map: Dict) -> List[ScrapedOdds]:
        """Parse football-specific odds from Soccerbet bet map."""
        odds_list = []

        # 1X2 Full Time
        try:
            odd1 = bet_map.get("1", {}).get("NULL", {}).get("ov")
            oddX = bet_map.get("2", {}).get("NULL", {}).get("ov")
            odd2 = bet_map.get("3", {}).get("NULL", {}).get("ov")

            if all(x is not None for x in [odd1, oddX, odd2]):
                odds_list.append(ScrapedOdds(
                    bet_type_id=2,  # 1X2
                    odd1=float(odd1),
                    odd2=float(oddX),
                    odd3=float(odd2),
                    margin=0
                ))
        except (ValueError, TypeError, KeyError):
            pass

        # 1X2 First Half
        try:
            odd1 = bet_map.get("4", {}).get("NULL", {}).get("ov")
            oddX = bet_map.get("5", {}).get("NULL", {}).get("ov")
            odd2 = bet_map.get("6", {}).get("NULL", {}).get("ov")

            if all(x is not None for x in [odd1, oddX, odd2]):
                odds_list.append(ScrapedOdds(
                    bet_type_id=3,  # 1X2_H1
                    odd1=float(odd1),
                    odd2=float(oddX),
                    odd3=float(odd2),
                    margin=0
                ))
        except (ValueError, TypeError, KeyError):
            pass

        # 1X2 Second Half
        try:
            odd1 = bet_map.get("235", {}).get("NULL", {}).get("ov")
            oddX = bet_map.get("236", {}).get("NULL", {}).get("ov")
            odd2 = bet_map.get("237", {}).get("NULL", {}).get("ov")

            if all(x is not None for x in [odd1, oddX, odd2]):
                odds_list.append(ScrapedOdds(
                    bet_type_id=4,  # 1X2_H2
                    odd1=float(odd1),
                    odd2=float(oddX),
                    odd3=float(odd2),
                    margin=0
                ))
        except (ValueError, TypeError, KeyError):
            pass

        # BTTS (Both Teams to Score)
        try:
            gg = bet_map.get("272", {}).get("NULL", {}).get("ov")
            ng = bet_map.get("273", {}).get("NULL", {}).get("ov")

            if all(x is not None for x in [gg, ng]):
                odds_list.append(ScrapedOdds(
                    bet_type_id=8,  # BTTS
                    odd1=float(gg),
                    odd2=float(ng),
                    odd3=None,
                    margin=0
                ))
        except (ValueError, TypeError, KeyError):
            pass

        # Total Goals Full Time
        total_goals_map = {
            1.5: {"under": "21", "over": "242"},
            2.5: {"under": "22", "over": "24"},
            3.5: {"under": "219", "over": "25"},
            4.5: {"under": "453", "over": "27"},
        }

        for total, codes in total_goals_map.items():
            try:
                under = bet_map.get(codes["under"], {}).get("NULL", {}).get("ov")
                over = bet_map.get(codes["over"], {}).get("NULL", {}).get("ov")

                if all(x is not None for x in [under, over]):
                    odds_list.append(ScrapedOdds(
                        bet_type_id=5,  # total_over_under
                        odd1=float(under),
                        odd2=float(over),
                        odd3=None,
                        margin=total
                    ))
            except (ValueError, TypeError, KeyError):
                pass

        # Total Goals First Half
        total_goals_h1_map = {
            0.5: {"under": "267", "over": "207"},
            1.5: {"under": "211", "over": "208"},
            2.5: {"under": "472", "over": "209"},
        }

        for total, codes in total_goals_h1_map.items():
            try:
                under = bet_map.get(codes["under"], {}).get("NULL", {}).get("ov")
                over = bet_map.get(codes["over"], {}).get("NULL", {}).get("ov")

                if all(x is not None for x in [under, over]):
                    odds_list.append(ScrapedOdds(
                        bet_type_id=6,  # total_h1
                        odd1=float(under),
                        odd2=float(over),
                        odd3=None,
                        margin=total
                    ))
            except (ValueError, TypeError, KeyError):
                pass

        # Total Goals Second Half
        total_goals_h2_map = {
            0.5: {"under": "269", "over": "213"},
            1.5: {"under": "217", "over": "214"},
            2.5: {"under": "474", "over": "215"},
        }

        for total, codes in total_goals_h2_map.items():
            try:
                under = bet_map.get(codes["under"], {}).get("NULL", {}).get("ov")
                over = bet_map.get(codes["over"], {}).get("NULL", {}).get("ov")

                if all(x is not None for x in [under, over]):
                    odds_list.append(ScrapedOdds(
                        bet_type_id=7,  # total_h2
                        odd1=float(under),
                        odd2=float(over),
                        odd3=None,
                        margin=total
                    ))
            except (ValueError, TypeError, KeyError):
                pass

        return odds_list

    def parse_basketball_odds(self, bet_map: Dict) -> List[ScrapedOdds]:
        """Parse basketball-specific odds."""
        odds_list = []

        # Winner (12)
        try:
            odd1 = bet_map.get("1", {}).get("NULL", {}).get("ov")
            odd2 = bet_map.get("3", {}).get("NULL", {}).get("ov")

            if all(x is not None for x in [odd1, odd2]):
                odds_list.append(ScrapedOdds(
                    bet_type_id=1,  # 12
                    odd1=float(odd1),
                    odd2=float(odd2),
                    odd3=None,
                    margin=0
                ))
        except (ValueError, TypeError, KeyError):
            pass

        # Total Points (common lines)
        # Note: Soccerbet uses different codes for different totals
        # This would need to be expanded based on actual API response

        return odds_list

    def parse_tennis_odds(self, bet_map: Dict) -> List[ScrapedOdds]:
        """Parse tennis-specific odds."""
        odds_list = []

        # Winner (12)
        try:
            odd1 = bet_map.get("1", {}).get("NULL", {}).get("ov")
            odd2 = bet_map.get("3", {}).get("NULL", {}).get("ov")

            if all(x is not None for x in [odd1, odd2]):
                odds_list.append(ScrapedOdds(
                    bet_type_id=1,  # 12
                    odd1=float(odd1),
                    odd2=float(odd2),
                    odd3=None,
                    margin=0
                ))
        except (ValueError, TypeError, KeyError):
            pass

        return odds_list

    def parse_hockey_odds(self, bet_map: Dict) -> List[ScrapedOdds]:
        """Parse hockey-specific odds (1X2)."""
        odds_list = []

        # 1X2
        try:
            odd1 = bet_map.get("1", {}).get("NULL", {}).get("ov")
            oddX = bet_map.get("2", {}).get("NULL", {}).get("ov")
            odd2 = bet_map.get("3", {}).get("NULL", {}).get("ov")

            if all(x is not None for x in [odd1, oddX, odd2]):
                odds_list.append(ScrapedOdds(
                    bet_type_id=2,  # 1X2
                    odd1=float(odd1),
                    odd2=float(oddX),
                    odd3=float(odd2),
                    margin=0
                ))
        except (ValueError, TypeError, KeyError):
            pass

        return odds_list

    def parse_table_tennis_odds(self, bet_map: Dict) -> List[ScrapedOdds]:
        """Parse table tennis-specific odds (Winner)."""
        odds_list = []

        # Winner (12)
        try:
            odd1 = bet_map.get("1", {}).get("NULL", {}).get("ov")
            odd2 = bet_map.get("3", {}).get("NULL", {}).get("ov")

            if all(x is not None for x in [odd1, odd2]):
                odds_list.append(ScrapedOdds(
                    bet_type_id=1,  # 12
                    odd1=float(odd1),
                    odd2=float(odd2),
                    odd3=None,
                    margin=0
                ))
        except (ValueError, TypeError, KeyError):
            pass

        return odds_list

    def parse_odds(self, bet_map: Dict, sport_id: int) -> List[ScrapedOdds]:
        """Parse odds based on sport type."""
        if sport_id == 1:
            return self.parse_football_odds(bet_map)
        elif sport_id == 2:
            return self.parse_basketball_odds(bet_map)
        elif sport_id == 3:
            return self.parse_tennis_odds(bet_map)
        elif sport_id == 4:
            return self.parse_hockey_odds(bet_map)
        elif sport_id == 5:
            return self.parse_table_tennis_odds(bet_map)
        return []

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Scrape all matches for a sport."""
        matches: List[ScrapedMatch] = []

        # Get leagues
        leagues = await self.fetch_leagues(sport_id)

        if not leagues:
            logger.debug(f"[Soccerbet] No leagues for sport {sport_id}")
            return matches

        logger.debug(f"[Soccerbet] Found {len(leagues)} leagues for sport {sport_id}")

        # Process each league
        for league_id, league_name in leagues:
            try:
                league_matches = await self.fetch_league_matches(sport_id, league_id)

                if not league_matches:
                    continue

                # Fetch match details in batches
                batch_size = 10
                for i in range(0, len(league_matches), batch_size):
                    batch = league_matches[i:i + batch_size]

                    # Fetch details concurrently
                    detail_tasks = [
                        self.fetch_match_details(str(m["id"]))
                        for m in batch
                    ]
                    details = await asyncio.gather(*detail_tasks, return_exceptions=True)

                    # Process each match
                    for match_data, detail in zip(batch, details):
                        try:
                            if isinstance(detail, Exception):
                                continue

                            if not detail:
                                continue

                            team1 = match_data.get("home", "")
                            team2 = match_data.get("away", "")

                            if not team1 or not team2:
                                continue

                            # Parse timestamp (milliseconds)
                            kick_off = detail.get("kickOffTime", 0)
                            if kick_off:
                                start_time = datetime.utcfromtimestamp(kick_off / 1000)
                            else:
                                continue

                            # Create match
                            scraped_match = ScrapedMatch(
                                team1=team1,
                                team2=team2,
                                sport_id=sport_id,
                                start_time=start_time,
                                league_name=league_name,
                                external_id=str(match_data.get("id")),
                            )

                            # Parse odds based on sport
                            bet_map = detail.get("betMap", {})
                            scraped_match.odds = self.parse_odds(bet_map, sport_id)

                            if scraped_match.odds:
                                matches.append(scraped_match)

                        except Exception as e:
                            logger.warning(f"[Soccerbet] Error processing match: {e}")
                            continue

                    # Small delay between batches
                    await asyncio.sleep(0.05)

            except Exception as e:
                logger.warning(f"[Soccerbet] Error processing league {league_name}: {e}")
                continue

        return matches
