"""
Admiral Bet scraper for BetSnipe.ai v2.0

Scrapes odds from Admiral Bet Serbia API.
Supports: Football, Basketball, Tennis, Hockey, Table Tennis
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)


# Admiral sport ID to internal sport ID mapping
SPORT_MAPPING = {
    1: 1,    # Football
    2: 2,    # Basketball
    3: 3,    # Tennis
    4: 4,    # Hockey
    17: 5,   # Table Tennis
}

# Reverse mapping for API calls
INTERNAL_TO_ADMIRAL = {v: k for k, v in SPORT_MAPPING.items()}

# Bet type mappings per sport
# Format: admiral_bet_type_id -> (internal_bet_type_id, name)

FOOTBALL_BET_TYPES = {
    135: (2, '1X2'),        # 1X2 Full Time
    148: (3, '1X2_H1'),     # 1X2 First Half
    149: (4, '1X2_H2'),     # 1X2 Second Half
    151: (8, 'BTTS'),       # Both Teams to Score
    137: (5, 'Total'),      # Total Goals Full Time
    143: (6, 'Total_H1'),   # Total Goals First Half
    144: (7, 'Total_H2'),   # Total Goals Second Half
}

BASKETBALL_BET_TYPES = {
    186: (1, '12'),         # Winner (Pobednik)
    213: (10, 'Total'),     # Total Points
    191: (9, 'Handicap'),   # Handicap
}

TENNIS_BET_TYPES = {
    # Will use betTypeName matching instead of IDs
}

HOCKEY_BET_TYPES = {
    # Will use betTypeName matching - "Konacan ishod" for 1X2
}

TABLE_TENNIS_BET_TYPES = {
    # Will use betTypeName matching - "Pobednik" for winner
}


class AdmiralScraper(BaseScraper):
    """
    Scraper for Admiral Bet Serbia.

    API endpoints:
    - webTree: Get list of sports/regions/competitions
    - getWebEventsSelections: Get matches for a competition
    - betsAndGroups: Get odds for a specific match
    """

    def __init__(self):
        super().__init__(bookmaker_id=4, bookmaker_name="Admiral")
        self._competitions_cache: Dict[int, List[Dict]] = {}

    def get_base_url(self) -> str:
        return "https://srboffer.admiralbet.rs/api/offer"

    def get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/utf8+json, application/json;q=0.9, text/plain;q=0.8, */*;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Host": "srboffer.admiralbet.rs",
            "Language": "sr-Latn",
            "Officeid": "138",
            "Origin": "https://admiralbet.rs",
            "Referer": "https://admiralbet.rs/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }

    def get_supported_sports(self) -> List[int]:
        return [1, 2, 3, 4, 5]  # Football, Basketball, Tennis, Hockey, Table Tennis

    async def fetch_competitions(self, sport_id: int) -> List[Dict[str, Any]]:
        """Fetch all competitions for a sport."""
        admiral_sport_id = INTERNAL_TO_ADMIRAL.get(sport_id)
        if admiral_sport_id is None:
            return []

        # Check cache
        if sport_id in self._competitions_cache:
            return self._competitions_cache[sport_id]

        url = f"{self.get_base_url()}/webTree/null/true/true/true/2025-02-10T20:48:46.651/2030-02-10T20:48:16.000/false"
        params = {"eventMappingTypes": ["1", "2", "3", "4", "5"]}

        data = await self.fetch_json(url, params=params)

        if not data:
            return []

        competitions = []
        for sport in data:
            if sport.get("id") == admiral_sport_id:
                for region in sport.get("regions", []):
                    for comp in region.get("competitions", []):
                        competitions.append({
                            "regionId": comp.get("regionId"),
                            "competitionId": comp.get("competitionId"),
                            "name": comp.get("competitionName", ""),
                            "regionName": region.get("regionName", ""),
                        })

        self._competitions_cache[sport_id] = competitions
        return competitions

    async def fetch_matches_for_competition(
        self,
        sport_id: int,
        competition: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Fetch all matches for a competition."""
        admiral_sport_id = INTERNAL_TO_ADMIRAL.get(sport_id)
        if admiral_sport_id is None:
            return []

        url = f"{self.get_base_url()}/getWebEventsSelections"
        params = {
            "pageId": "35",
            "sportId": str(admiral_sport_id),
            "regionId": competition["regionId"],
            "competitionId": competition["competitionId"],
            "isLive": "false",
            "dateFrom": "2025-01-18T19:42:15.955",
            "dateTo": "2030-01-18T19:41:45.000",
            "eventMappingTypes": ["1", "2", "3", "4", "5"],
        }

        matches = await self.fetch_json(url, params=params)
        return matches if matches else []

    async def fetch_match_odds(
        self,
        sport_id: int,
        competition: Dict[str, Any],
        match_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch odds for a specific match."""
        admiral_sport_id = INTERNAL_TO_ADMIRAL.get(sport_id)
        if admiral_sport_id is None:
            return None

        url = (
            f"{self.get_base_url()}/betsAndGroups/"
            f"{admiral_sport_id}/{competition['regionId']}/"
            f"{competition['competitionId']}/{match_id}"
        )

        return await self.fetch_json(url)

    def parse_football_odds(self, bets: List[Dict]) -> List[ScrapedOdds]:
        """Parse football-specific odds."""
        odds_list = []

        for bet in bets:
            bet_type_id = bet.get("betTypeId")

            if bet_type_id not in FOOTBALL_BET_TYPES:
                continue

            internal_bet_type, _ = FOOTBALL_BET_TYPES[bet_type_id]
            outcomes = sorted(bet.get("betOutcomes", []), key=lambda x: x.get("orderNo", 0))

            # Handle 1X2 bets (3-way)
            if internal_bet_type in [2, 3, 4]:
                if len(outcomes) >= 3:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=internal_bet_type,
                        odd1=float(outcomes[0].get("odd", 0)),
                        odd2=float(outcomes[1].get("odd", 0)),
                        odd3=float(outcomes[2].get("odd", 0)),
                        margin=0
                    ))

            # Handle BTTS (2-way)
            elif internal_bet_type == 8:
                if len(outcomes) >= 2:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=internal_bet_type,
                        odd1=float(outcomes[0].get("odd", 0)),
                        odd2=float(outcomes[1].get("odd", 0)),
                        odd3=None,
                        margin=0
                    ))

            # Handle Totals (Over/Under)
            elif internal_bet_type in [5, 6, 7]:
                totals: Dict[float, Dict[str, float]] = {}

                for outcome in bet.get("betOutcomes", []):
                    try:
                        total = float(outcome.get("sBV", 0))
                        if total not in totals:
                            totals[total] = {}

                        name = outcome.get("name", "").lower()
                        odd = float(outcome.get("odd", 0))

                        if name.startswith("vi") or "over" in name or "više" in name:
                            totals[total]["over"] = odd
                        else:
                            totals[total]["under"] = odd
                    except (ValueError, TypeError):
                        continue

                for total, total_odds in totals.items():
                    if "over" in total_odds and "under" in total_odds:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=internal_bet_type,
                            odd1=total_odds["under"],
                            odd2=total_odds["over"],
                            odd3=None,
                            margin=total
                        ))

        return odds_list

    def parse_basketball_odds(self, bets: List[Dict]) -> List[ScrapedOdds]:
        """Parse basketball-specific odds."""
        odds_list = []

        for bet in bets:
            bet_type_id = bet.get("betTypeId")

            # Winner (12)
            if bet_type_id == 186:
                outcomes = sorted(bet.get("betOutcomes", []), key=lambda x: x.get("orderNo", 0))
                if len(outcomes) >= 2:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=1,
                        odd1=float(outcomes[0].get("odd", 0)),
                        odd2=float(outcomes[1].get("odd", 0)),
                        odd3=None,
                        margin=0
                    ))

            # Total Points
            elif bet_type_id == 213:
                totals: Dict[float, Dict[str, float]] = {}

                for outcome in bet.get("betOutcomes", []):
                    try:
                        total = float(outcome.get("sBV", 0))
                        if total not in totals:
                            totals[total] = {}

                        name = outcome.get("name", "").lower()
                        odd = float(outcome.get("odd", 0))

                        if "vise" in name or "više" in name:
                            totals[total]["over"] = odd
                        elif "manje" in name:
                            totals[total]["under"] = odd
                    except (ValueError, TypeError):
                        continue

                for total, total_odds in totals.items():
                    if "over" in total_odds and "under" in total_odds:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=10,
                            odd1=total_odds["under"],
                            odd2=total_odds["over"],
                            odd3=None,
                            margin=total
                        ))

            # Handicap
            elif bet_type_id == 191:
                handicaps: Dict[float, Dict[str, float]] = {}

                for outcome in bet.get("betOutcomes", []):
                    try:
                        handicap = float(outcome.get("sBV", 0))
                        if handicap not in handicaps:
                            handicaps[handicap] = {}

                        name = outcome.get("name", "")
                        odd = float(outcome.get("odd", 0))

                        if name == "1":
                            handicaps[handicap]["team1"] = odd
                        elif name == "2":
                            handicaps[handicap]["team2"] = odd
                    except (ValueError, TypeError):
                        continue

                for handicap, h_odds in handicaps.items():
                    if "team1" in h_odds and "team2" in h_odds:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=9,
                            odd1=h_odds["team1"],
                            odd2=h_odds["team2"],
                            odd3=None,
                            margin=handicap
                        ))

        return odds_list

    def parse_tennis_odds(self, bets: List[Dict]) -> List[ScrapedOdds]:
        """Parse tennis-specific odds."""
        odds_list = []

        for bet in bets:
            bet_type_name = bet.get("betTypeName", "")
            outcomes = bet.get("betOutcomes", [])

            # Match Winner
            if bet_type_name == "Pobednik" and len(outcomes) >= 2:
                odds_list.append(ScrapedOdds(
                    bet_type_id=1,
                    odd1=float(outcomes[0].get("odd", 0)),
                    odd2=float(outcomes[1].get("odd", 0)),
                    odd3=None,
                    margin=0
                ))

            # First Set Winner
            elif bet_type_name == "1.set - Pobednik" and len(outcomes) >= 2:
                odds_list.append(ScrapedOdds(
                    bet_type_id=11,
                    odd1=float(outcomes[0].get("odd", 0)),
                    odd2=float(outcomes[1].get("odd", 0)),
                    odd3=None,
                    margin=0
                ))

        return odds_list

    def parse_hockey_odds(self, bets: List[Dict]) -> List[ScrapedOdds]:
        """Parse hockey-specific odds."""
        odds_list = []

        for bet in bets:
            bet_type_name = bet.get("betTypeName", "")
            outcomes = bet.get("betOutcomes", [])

            # 1X2 Full Time
            if bet_type_name == "Konacan ishod" and len(outcomes) >= 3:
                odds_list.append(ScrapedOdds(
                    bet_type_id=2,
                    odd1=float(outcomes[0].get("odd", 0)),
                    odd2=float(outcomes[1].get("odd", 0)),
                    odd3=float(outcomes[2].get("odd", 0)),
                    margin=0
                ))

        return odds_list

    def parse_table_tennis_odds(self, bets: List[Dict]) -> List[ScrapedOdds]:
        """Parse table tennis-specific odds."""
        odds_list = []

        for bet in bets:
            bet_type_name = bet.get("betTypeName", "")
            outcomes = bet.get("betOutcomes", [])

            # Match Winner
            if bet_type_name == "Pobednik" and len(outcomes) >= 2:
                odds_list.append(ScrapedOdds(
                    bet_type_id=1,
                    odd1=float(outcomes[0].get("odd", 0)),
                    odd2=float(outcomes[1].get("odd", 0)),
                    odd3=None,
                    margin=0
                ))

        return odds_list

    def parse_odds_from_bets(self, bets: List[Dict], sport_id: int) -> List[ScrapedOdds]:
        """Parse odds based on sport type."""
        if sport_id == 1:
            return self.parse_football_odds(bets)
        elif sport_id == 2:
            return self.parse_basketball_odds(bets)
        elif sport_id == 3:
            return self.parse_tennis_odds(bets)
        elif sport_id == 4:
            return self.parse_hockey_odds(bets)
        elif sport_id == 5:
            return self.parse_table_tennis_odds(bets)
        return []

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Scrape all matches for a sport."""
        matches: List[ScrapedMatch] = []

        # Get competitions
        competitions = await self.fetch_competitions(sport_id)

        if not competitions:
            logger.debug(f"[Admiral] No competitions for sport {sport_id}")
            return matches

        logger.debug(f"[Admiral] Found {len(competitions)} competitions for sport {sport_id}")

        # Fetch matches for all competitions concurrently
        match_tasks = [
            self.fetch_matches_for_competition(sport_id, comp)
            for comp in competitions
        ]
        competition_matches = await asyncio.gather(*match_tasks, return_exceptions=True)

        # Collect match data
        match_info_list = []
        for comp_idx, comp_matches in enumerate(competition_matches):
            if isinstance(comp_matches, Exception):
                logger.warning(f"[Admiral] Error fetching competition: {comp_matches}")
                continue

            if not comp_matches:
                continue

            competition = competitions[comp_idx]

            for match_data in comp_matches:
                name = match_data.get("name", "")
                if name.count(" - ") != 1:
                    continue

                match_info_list.append({
                    'match_data': match_data,
                    'competition': competition,
                })

        # Fetch odds for all matches concurrently
        odds_tasks = [
            self.fetch_match_odds(
                sport_id,
                info['competition'],
                str(info['match_data'].get('id'))
            )
            for info in match_info_list
        ]
        odds_results = await asyncio.gather(*odds_tasks, return_exceptions=True)

        # Process matches and odds
        for idx, info in enumerate(match_info_list):
            try:
                match_data = info['match_data']
                competition = info['competition']

                # Parse team names
                team1, team2 = self.parse_teams(match_data.get("name", ""))
                if not team1 or not team2:
                    continue

                # Parse timestamp
                start_time = self.parse_timestamp(match_data.get("dateTime"))
                if not start_time:
                    continue

                # Create match object
                scraped_match = ScrapedMatch(
                    team1=team1,
                    team2=team2,
                    sport_id=sport_id,
                    start_time=start_time,
                    league_name=competition.get("name"),
                    external_id=str(match_data.get("id")),
                    metadata={
                        'region': competition.get("regionName"),
                    }
                )

                # Parse odds
                odds_result = odds_results[idx]
                if isinstance(odds_result, dict) and "bets" in odds_result:
                    scraped_odds = self.parse_odds_from_bets(
                        odds_result["bets"],
                        sport_id
                    )
                    scraped_match.odds = scraped_odds

                # Only add if we have odds
                if scraped_match.odds:
                    matches.append(scraped_match)

            except Exception as e:
                logger.warning(f"[Admiral] Error processing match: {e}")
                continue

        return matches

    async def scrape_all(self) -> List[ScrapedMatch]:
        """Override to clear competition cache before scraping."""
        self._competitions_cache.clear()
        return await super().scrape_all()
