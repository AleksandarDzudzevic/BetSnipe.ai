"""
MaxBet scraper for BetSnipe.ai v2.0

Scrapes odds from MaxBet Serbia API.
Supports: Football, Basketball, Tennis, Hockey, Table Tennis
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)

# Sport code mappings (MaxBet to internal)
MAXBET_SPORTS = {
    'S': 1,   # Football
    'B': 2,   # Basketball
    'T': 3,   # Tennis
    'H': 4,   # Hockey
    'TT': 5,  # Table Tennis
}

# Reverse mapping
INTERNAL_TO_MAXBET = {v: k for k, v in MAXBET_SPORTS.items()}

# Odds code mappings per sport
FOOTBALL_ODDS = {
    '1X2': ('1', '2', '3'),           # Full time 1X2
    '1X2_H1': ('4', '5', '6'),        # First half 1X2
    '1X2_H2': ('235', '236', '237'),  # Second half 1X2
    'BTTS': ('272', '273'),           # Both teams to score
}

FOOTBALL_TOTALS = {
    'FT': [
        (1.5, '211', '242'),
        (2.5, '22', '24'),
        (3.5, '219', '25'),
        (4.5, '453', '27'),
        (5.5, '266', '223'),
    ],
    'H1': [
        (0.5, '188', '207'),
        (1.5, '211', '208'),
        (2.5, '472', '209'),
    ],
    'H2': [
        (0.5, '269', '213'),
        (1.5, '217', '214'),
        (2.5, '474', '215'),
    ],
}

BASKETBALL_ODDS = {
    'winner': ('50291', '50293'),  # Winner (no draw)
    'handicap': {
        'handicapOvertime': ('50458', '50459'),
        'handicapOvertime2': ('50432', '50433'),
        'handicapOvertime3': ('50434', '50435'),
        'handicapOvertime4': ('50436', '50437'),
        'handicapOvertime5': ('50438', '50439'),
        'handicapOvertime6': ('50440', '50441'),
        'handicapOvertime7': ('50442', '50443'),
        'handicapOvertime8': ('50981', '50982'),
        'handicapOvertime9': ('51626', '51627'),
    },
    'total': {
        'overUnderOvertime3': ('50448', '50449'),
        'overUnderOvertime4': ('50450', '50451'),
        'overUnderOvertime5': ('50452', '50453'),
        'overUnderOvertime6': ('50454', '50455'),
    },
}

TENNIS_ODDS = {
    'winner': ('1', '3'),           # Match winner
    'set1_winner': ('50510', '50511'),  # First set winner
}

HOCKEY_ODDS = {
    '1X2': ('1', '2', '3'),  # Full time 1X2
}

TABLE_TENNIS_ODDS = {
    'winner': ('1', '3'),  # Match winner
}


class MaxbetScraper(BaseScraper):
    """
    Scraper for MaxBet Serbia.

    Uses same API structure as Soccerbet (similar platform).
    Supports: Football, Basketball, Tennis, Hockey, Table Tennis
    """

    def __init__(self):
        super().__init__(bookmaker_id=3, bookmaker_name="Maxbet")

    def get_base_url(self) -> str:
        return "https://www.maxbet.rs/restapi/offer/sr"

    def get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Origin": "https://www.maxbet.rs",
            "Referer": "https://www.maxbet.rs/betting",
        }

    def get_params(self) -> Dict[str, str]:
        return {"annex": "3", "desktopVersion": "1.2.1.10", "locale": "sr"}

    def get_supported_sports(self) -> List[int]:
        return [1, 2, 3, 4, 5]

    async def fetch_leagues(self, sport_id: int) -> Dict[str, int]:
        """Fetch leagues for a sport."""
        sport_code = INTERNAL_TO_MAXBET.get(sport_id)
        if not sport_code:
            return {}

        url = f"{self.get_base_url()}/categories/sport/{sport_code}/l"
        data = await self.fetch_json(url, params=self.get_params())

        if not data:
            return {}

        leagues = {}
        for category in data.get('categories', []):
            league_id = category.get('id')
            league_name = category.get('name')
            if league_id and league_name:
                # Skip bonus leagues
                if "Bonus Tip" in league_name or "Max Bonus" in league_name:
                    continue
                leagues[league_name] = league_id

        return leagues

    async def fetch_league_matches(self, sport_id: int, league_id: int) -> List[Dict]:
        """Fetch matches for a league."""
        sport_code = INTERNAL_TO_MAXBET.get(sport_id)
        if not sport_code:
            return []

        url = f"{self.get_base_url()}/sport/{sport_code}/league/{league_id}/mob"
        data = await self.fetch_json(url, params=self.get_params())

        if not data:
            return []

        return data.get("esMatches", [])

    async def fetch_match_details(self, match_id: int) -> Optional[Dict]:
        """Fetch detailed match data."""
        url = f"{self.get_base_url()}/match/{match_id}"
        return await self.fetch_json(url, params=self.get_params())

    def parse_football_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse football-specific odds."""
        odds_list = []
        odds = match_data.get("odds", {})

        # 1X2 Full Time
        odd1 = odds.get("1")
        oddX = odds.get("2")
        odd2 = odds.get("3")
        if all([odd1, oddX, odd2]):
            odds_list.append(ScrapedOdds(
                bet_type_id=2, odd1=float(odd1), odd2=float(oddX), odd3=float(odd2)
            ))

        # 1X2 First Half
        odd1 = odds.get("4")
        oddX = odds.get("5")
        odd2 = odds.get("6")
        if all([odd1, oddX, odd2]):
            odds_list.append(ScrapedOdds(
                bet_type_id=3, odd1=float(odd1), odd2=float(oddX), odd3=float(odd2)
            ))

        # 1X2 Second Half
        odd1 = odds.get("235")
        oddX = odds.get("236")
        odd2 = odds.get("237")
        if all([odd1, oddX, odd2]):
            odds_list.append(ScrapedOdds(
                bet_type_id=4, odd1=float(odd1), odd2=float(oddX), odd3=float(odd2)
            ))

        # BTTS
        gg = odds.get("272")
        ng = odds.get("273")
        if gg and ng:
            odds_list.append(ScrapedOdds(
                bet_type_id=8, odd1=float(gg), odd2=float(ng)
            ))

        # Total Goals Full Time
        total_pairs = [
            (1.5, "211", "242"),
            (2.5, "22", "24"),
            (3.5, "219", "25"),
            (4.5, "453", "27"),
            (5.5, "266", "223"),
        ]
        for total, under_code, over_code in total_pairs:
            under = odds.get(under_code)
            over = odds.get(over_code)
            if under and over:
                odds_list.append(ScrapedOdds(
                    bet_type_id=5, odd1=float(under), odd2=float(over), margin=total
                ))

        # Total Goals First Half
        total_h1_pairs = [
            (0.5, "188", "207"),
            (1.5, "211", "208"),
            (2.5, "472", "209"),
        ]
        for total, under_code, over_code in total_h1_pairs:
            under = odds.get(under_code)
            over = odds.get(over_code)
            if under and over:
                odds_list.append(ScrapedOdds(
                    bet_type_id=6, odd1=float(under), odd2=float(over), margin=total
                ))

        # Total Goals Second Half
        total_h2_pairs = [
            (0.5, "269", "213"),
            (1.5, "217", "214"),
            (2.5, "474", "215"),
        ]
        for total, under_code, over_code in total_h2_pairs:
            under = odds.get(under_code)
            over = odds.get(over_code)
            if under and over:
                odds_list.append(ScrapedOdds(
                    bet_type_id=7, odd1=float(under), odd2=float(over), margin=total
                ))

        return odds_list

    def parse_basketball_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse basketball-specific odds."""
        odds_list = []
        odds = match_data.get("odds", {})
        params = match_data.get("params", {})

        # Winner (12)
        home_odd = odds.get("50291")
        away_odd = odds.get("50293")
        if home_odd and away_odd:
            odds_list.append(ScrapedOdds(
                bet_type_id=1, odd1=float(home_odd), odd2=float(away_odd)
            ))

        # Handicap
        handicap_mapping = {
            "handicapOvertime": ("50458", "50459"),
            "handicapOvertime2": ("50432", "50433"),
            "handicapOvertime3": ("50434", "50435"),
            "handicapOvertime4": ("50436", "50437"),
            "handicapOvertime5": ("50438", "50439"),
            "handicapOvertime6": ("50440", "50441"),
            "handicapOvertime7": ("50442", "50443"),
            "handicapOvertime8": ("50981", "50982"),
            "handicapOvertime9": ("51626", "51627"),
        }

        for handicap_key, (home_code, away_code) in handicap_mapping.items():
            if home_code in odds and away_code in odds:
                handicap_value = params.get(handicap_key)
                if handicap_value:
                    try:
                        # Flip the handicap sign for home team
                        handicap = float(handicap_value)
                        odds_list.append(ScrapedOdds(
                            bet_type_id=9,
                            odd1=float(odds[home_code]),
                            odd2=float(odds[away_code]),
                            margin=-handicap  # Flipped
                        ))
                    except (ValueError, TypeError):
                        continue

        # Total Points
        total_mapping = {
            "overUnderOvertime3": ("50448", "50449"),
            "overUnderOvertime4": ("50450", "50451"),
            "overUnderOvertime5": ("50452", "50453"),
            "overUnderOvertime6": ("50454", "50455"),
        }

        for total_key, (under_code, over_code) in total_mapping.items():
            if under_code in odds and over_code in odds:
                total_value = params.get(total_key)
                if total_value:
                    try:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=10,
                            odd1=float(odds[under_code]),
                            odd2=float(odds[over_code]),
                            margin=float(total_value)
                        ))
                    except (ValueError, TypeError):
                        continue

        return odds_list

    def parse_tennis_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse tennis-specific odds."""
        odds_list = []
        odds = match_data.get("odds", {})

        # Match Winner
        home_win = odds.get("1")
        away_win = odds.get("3")
        if home_win and away_win:
            odds_list.append(ScrapedOdds(
                bet_type_id=1, odd1=float(home_win), odd2=float(away_win)
            ))

        # First Set Winner
        first_set_home = odds.get("50510")
        first_set_away = odds.get("50511")
        if first_set_home and first_set_away:
            odds_list.append(ScrapedOdds(
                bet_type_id=11, odd1=float(first_set_home), odd2=float(first_set_away)
            ))

        return odds_list

    def parse_hockey_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse hockey-specific odds."""
        odds_list = []
        odds = match_data.get("odds", {})

        # 1X2
        home_win = odds.get("1")
        draw = odds.get("2")
        away_win = odds.get("3")
        if home_win and draw and away_win:
            odds_list.append(ScrapedOdds(
                bet_type_id=2,
                odd1=float(home_win),
                odd2=float(draw),
                odd3=float(away_win)
            ))

        return odds_list

    def parse_table_tennis_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse table tennis-specific odds."""
        odds_list = []
        odds = match_data.get("odds", {})

        # Winner
        home_win = odds.get("1")
        away_win = odds.get("3")
        if home_win and away_win:
            odds_list.append(ScrapedOdds(
                bet_type_id=1, odd1=float(home_win), odd2=float(away_win)
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

        leagues = await self.fetch_leagues(sport_id)
        if not leagues:
            return matches

        logger.debug(f"[Maxbet] Found {len(leagues)} leagues for sport {sport_id}")

        # Fetch all league matches concurrently
        league_tasks = [
            self.fetch_league_matches(sport_id, lid)
            for lid in leagues.values()
        ]
        league_results = await asyncio.gather(*league_tasks, return_exceptions=True)

        # Collect match IDs
        match_ids = []
        for result in league_results:
            if isinstance(result, Exception):
                continue
            for match in result:
                league_name = match.get("leagueName", "")
                if "Bonus Tip" not in league_name and "Max Bonus" not in league_name:
                    match_ids.append(match.get("id"))

        # Fetch match details concurrently
        detail_tasks = [
            self.fetch_match_details(mid)
            for mid in match_ids
        ]
        details = await asyncio.gather(*detail_tasks, return_exceptions=True)

        for detail in details:
            if isinstance(detail, Exception) or not detail:
                continue

            try:
                team1 = detail.get("home", "")
                team2 = detail.get("away", "")
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
                    league_name=detail.get("leagueName"),
                    external_id=str(detail.get("id")),
                )

                scraped.odds = self.parse_odds(detail, sport_id)

                if scraped.odds:
                    matches.append(scraped)

            except Exception as e:
                logger.warning(f"[Maxbet] Error processing match: {e}")

        return matches
