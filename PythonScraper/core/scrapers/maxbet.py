"""
MaxBet scraper for BetSnipe.ai v2.0

Scrapes odds from MaxBet Serbia API.
Supports: Football, Basketball, Tennis, Hockey, Table Tennis

Code mappings derived from MaxBet's /restapi/offer/sr/ttg_lang configuration endpoint.
Each match returns a flat odds dict {code: value} and params dict {param_key: margin_value}.
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

# ============================================================================
# FOOTBALL CODE MAPPINGS (tipType codes from betPickMap with _S suffix)
# ============================================================================

# Simple 3-way markets: bet_type_id -> (home_code, draw_code, away_code)
FOOTBALL_3WAY = {
    2:  ('1', '2', '3'),         # 1X2 Full Time
    3:  ('4', '5', '6'),         # 1X2 First Half
    4:  ('235', '236', '237'),   # 1X2 Second Half
    13: ('7', '8', '9'),         # Double Chance (1X, 12, X2)
    20: ('397', '398', '399'),   # Double Chance H1 (P1X, P12, PX2)
    18: ('204', '205', '206'),   # First Goal (home, nobody, away)
    19: ('29', '30', '31'),      # Half with More Goals (1st, equal, 2nd)
}

# Simple 2-way markets: bet_type_id -> (code1, code2)
FOOTBALL_2WAY = {
    8:  ('272', '273'),    # BTTS (GG, NG)
    15: ('231', '232'),    # Odd/Even (PAR, NEP)
    14: ('264', '265'),    # Draw No Bet (W1, W2)
    16: ('295', '296'),    # Double Win (DP1, DP2)
    17: ('282', '283'),    # Win to Nil / Super Win (SP1, SP2)
    21: ('611', '612'),    # Draw No Bet H1 (1PW1, 1PW2)
}

# Fixed-margin O/U total pairs: bet_type_id -> [(margin, under_code, over_code)]
FOOTBALL_FIXED_TOTALS = {
    5: [  # Total O/U Full Time
        (1.5, '21', '242'),    # ug 0-1 / ug 2+
        (2.5, '22', '24'),     # ug 0-2 / ug 3+
        (3.5, '219', '25'),    # ug 0-3 / ug 4+
        (4.5, '453', '27'),    # ug 0-4 / ug 5+
        (5.5, '266', '223'),   # ug 0-5 / ug 6+
    ],
    6: [  # Total O/U First Half
        (0.5, '267', '207'),   # 1PT0 / 1P1+
        (1.5, '211', '208'),   # 1P0-1 / 1P2+
        (2.5, '472', '209'),   # 1P0-2 / 1P3+
    ],
    7: [  # Total O/U Second Half
        (0.5, '269', '213'),   # 2PT0 / 2P1+
        (1.5, '217', '214'),   # 2P0-1 / 2P2+
        (2.5, '474', '215'),   # 2P0-2 / 2P3+
    ],
}

# Param-based 2-way O/U: bet_type_id -> [(param_key, under_code, over_code)]
FOOTBALL_PARAM_TOTALS = {
    48: [('homeOverUnder', '355', '356')],              # Team 1 total O/U
    49: [('awayOverUnder', '357', '358')],              # Team 2 total O/U
    51: [('homeOverUnderFirstHalf', '371', '372')],     # Team 1 H1 total O/U
    52: [('awayOverUnderFirstHalf', '373', '374')],     # Team 2 H1 total O/U
}

# Param-based 3-way handicap: bet_type_id -> [(param_key, home, draw, away)]
FOOTBALL_PARAM_HANDICAPS_3WAY = {
    9: [  # Handicap (3-way)
        ('hd2', '201', '202', '203'),
        ('handicap2', '421', '422', '423'),
        ('handicap3', '424', '425', '426'),
    ],
}

# Param-based 2-way handicap H1: bet_type_id -> [(param_key, home, away)]
FOOTBALL_PARAM_HANDICAPS_2WAY = {
    50: [('hdp', '224', '226')],   # H1 handicap (2-way: home, away)
}

# Selection-based markets: bet_type_id -> {code: selection_key}
FOOTBALL_SELECTIONS = {
    23: {  # Correct Score
        '51': '0:0', '52': '1:0', '54': '2:0', '56': '3:0', '58': '4:0',
        '53': '0:1', '67': '1:1', '68': '2:1', '70': '3:1', '72': '4:1',
        '55': '0:2', '69': '1:2', '82': '2:2', '83': '3:2', '85': '4:2',
        '57': '0:3', '71': '1:3', '84': '2:3', '95': '3:3', '96': '4:3',
        '59': '0:4', '73': '1:4', '86': '2:4', '97': '3:4', '106': '4:4',
    },
    24: {  # HT/FT
        '10': '1/1', '11': '1/X', '12': '1/2',
        '13': 'X/1', '14': 'X/X', '15': 'X/2',
        '16': '2/1', '17': '2/X', '18': '2/2',
    },
    37: {  # HT/FT Double Chance
        '831': '1X/1X', '832': '1X/12', '833': '1X/X2',
        '834': '12/1X', '835': '12/12', '836': '12/X2',
        '837': 'X2/1X', '838': 'X2/12', '839': 'X2/X2',
        '840': '1/1X', '841': '1/12', '842': '1/X2',
        '843': 'X/1X', '844': 'X/12', '845': 'X/X2',
        '846': '2/1X', '847': '2/12', '848': '2/X2',
        '849': '1X/1', '850': '1X/X', '851': '1X/2',
        '852': '12/1', '853': '12/X', '854': '12/2',
        '855': 'X2/1', '856': 'X2/X', '857': 'X2/2',
    },
    26: {  # Exact Goals
        '320': '1', '221': '2', '222': '3', '321': '4',
    },
    25: {  # Total Goals Range (selection-based)
        '278': '1-2', '279': '1-3', '280': '1-4', '380': '1-5', '381': '1-6',
        '23': '2-3', '243': '2-4', '333': '2-5', '220': '2-6',
        '244': '3-4', '281': '3-5', '382': '3-6',
        '379': '4-5', '26': '4-6',
    },
    27: {  # Team 1 Goals (ranges/exact)
        '247': '0-1', '551': '0-2', '553': '0-3',
        '478': '1-2', '479': '1-3', '480': '2-3',
        '248': '2+', '276': '3+', '555': '4+',
        '323': 'T1', '324': 'T2', '484': 'T3',
    },
    28: {  # Team 2 Goals (ranges/exact)
        '249': '0-1', '552': '0-2', '554': '0-3',
        '481': '1-2', '482': '1-3', '483': '2-3',
        '250': '2+', '277': '3+', '556': '4+',
        '325': 'T1', '326': 'T2', '485': 'T3',
    },
    29: {  # H1 Total Goals Range
        '267': 'T0', '268': 'T1', '777': 'T2', '779': 'T3',
        '476': '1-2', '477': '1-3',
        '212': '2-3',
    },
    30: {  # H2 Total Goals Range
        '269': 'T0', '270': 'T1', '782': 'T2', '784': 'T3',
        '606': '1-2', '607': '1-3',
        '218': '2-3',
    },
    31: {  # Team 1 Goals H1
        '337': 'T0', '341': 'T1',
        '307': '1+', '274': '2+', '349': '3+',
    },
    32: {  # Team 2 Goals H1
        '338': 'T0', '342': 'T1',
        '308': '1+', '275': '2+', '350': '3+',
    },
    33: {  # Team 1 Goals H2
        '339': 'T0', '343': 'T1',
        '312': '1+', '297': '2+', '351': '3+',
    },
    34: {  # Team 2 Goals H2
        '340': 'T0', '344': 'T1',
        '313': '1+', '298': '2+', '352': '3+',
    },
    36: {  # First Goal + Final Result (PG combos)
        '806': 'H_scores_first', '808': 'A_scores_first',
    },
}

# ============================================================================
# BASKETBALL CODE MAPPINGS (tipType codes with _B suffix)
# ============================================================================

# Simple 2-way: bet_type_id -> (home_code, away_code)
BASKETBALL_2WAY = {
    1: ('50291', '50293'),   # Winner (incl. OT)
}

# Param-based 2-way handicap: bet_type_id -> [(param_key, home_code, away_code)]
BASKETBALL_PARAM_HANDICAPS = {
    9: [
        ('handicapOvertime', '50458', '50459'),
        ('handicapOvertime2', '50432', '50433'),
        ('handicapOvertime3', '50434', '50435'),
        ('handicapOvertime4', '50436', '50437'),
        ('handicapOvertime5', '50438', '50439'),
        ('handicapOvertime6', '50440', '50441'),
        ('handicapOvertime7', '50442', '50443'),
        ('handicapOvertime8', '50981', '50982'),
        ('handicapOvertime9', '51626', '51627'),
    ],
    50: [  # H1 handicap
        ('handicapFirstHalf', '50460', '50461'),
    ],
}

# Param-based 2-way O/U: bet_type_id -> [(param_key, under_code, over_code)]
BASKETBALL_PARAM_TOTALS = {
    10: [  # Total points
        ('overUnderOvertime', '50444', '50445'),
        ('overUnderOvertime3', '50448', '50449'),
        ('overUnderOvertime4', '50450', '50451'),
        ('overUnderOvertime5', '50452', '50453'),
        ('overUnderOvertime6', '50454', '50455'),
    ],
    6: [  # H1 total
        ('overUnderFirstHalf', '50446', '50447'),
    ],
    48: [  # Team 1 total
        ('homeOverUnderOvertime', '50462', '50463'),
    ],
    49: [  # Team 2 total
        ('awayOverUnderOvertime', '50464', '50465'),
    ],
    51: [  # Team 1 H1 total
        ('homeOverUnderFirstHalf', '50466', '50467'),
    ],
    52: [  # Team 2 H1 total
        ('awayOverUnderFirstHalf', '50468', '50469'),
    ],
}

# ============================================================================
# TENNIS CODE MAPPINGS (tipType codes with _T suffix)
# ============================================================================

TENNIS_2WAY = {
    1:  ('1', '3'),              # Match Winner
    57: ('50510', '50511'),      # First Set Winner
}

# Param-based O/U: bet_type_id -> [(param_key, under_code, over_code)]
TENNIS_PARAM_TOTALS = {
    5: [  # Total Games
        ('overUnderGames', '254', '256'),
    ],
}

# Param-based handicap: bet_type_id -> [(param_key, home_code, away_code)]
TENNIS_PARAM_HANDICAPS = {
    56: [  # Set Handicap
        ('hd2', '251', '253'),
    ],
    58: [  # Game Handicap S1
        ('handicapGames', '50538', '50539'),
    ],
}

# Simple 2-way (no margin)
TENNIS_SIMPLE_2WAY = {
    60: ('51196', '51197'),  # Tiebreak S1 (yes, no)
    59: ('50520', '50521'),  # Odd/Even S1 (games under/over... actually S2 odd/even)
}

# Tennis 3-way
TENNIS_3WAY = {
    63: ('51061', '51062', '51063'),  # Set with More Games (S1>, equal, S2>)
}

# Selection-based tennis markets
TENNIS_SELECTIONS = {
    65: {  # Exact Sets
        '50544': '2:0', '50545': '0:2',
        '50548': '2:1', '50549': '1:2',
    },
    64: {  # First Set + Match Combo
        '50540': '1/1', '50541': '1/2',
        '50542': '2/1', '50543': '2/2',
    },
    66: {  # Games Range S1 (Player 1 wins S1)
        '51198': 'T6', '51199': '7-8', '51200': '9-12', '51201': 'T13',
    },
    67: {  # Games Range S2 (Player 2 wins S1 -> S1 range)
        '51202': 'T6', '51203': '7-8', '51204': '9-12', '51205': 'T13',
    },
}

# ============================================================================
# HOCKEY CODE MAPPINGS (tipType codes with _H suffix)
# ============================================================================

HOCKEY_3WAY = {
    2:  ('1', '2', '3'),   # 1X2 Full Time
}

HOCKEY_2WAY = {
    14: ('264', '265'),    # Draw No Bet / Winner
    8:  ('272', '273'),    # BTTS (GG, NG)
    15: ('231', '232'),    # Odd/Even
}

HOCKEY_SIMPLE_3WAY = {
    13: ('7', '8', '9'),   # Double Chance
}

# Period 1X2 markets: no specific bet_type in our schema yet, but include as 1X2 variant
# Using bet_type_id=3 for P1 1X2 (period1 ≈ H1)
HOCKEY_PERIOD_3WAY = {
    3: ('50495', '50496', '50497'),    # Period 1 1X2
    4: ('50498', '50499', '50500'),    # Period 2 1X2
}

# Param-based O/U: bet_type_id -> [(param_key, under_code, over_code)]
HOCKEY_PARAM_TOTALS = {
    5: [  # Total O/U FT
        ('overUnder', '228', '227'),
        ('overUnder2', '427', '429'),
        ('overUnder3', '430', '432'),
    ],
    6: [  # Period 1 total
        ('overUnderFirstPeriod', '50504', '50505'),
    ],
    48: [('homeOverUnder', '355', '356')],     # Team 1 total
    49: [('awayOverUnder', '357', '358')],     # Team 2 total
}

# Param-based handicap: bet_type_id -> [(param_key, home_code, away_code)]
HOCKEY_PARAM_HANDICAPS = {
    9: [('hd2', '201', '203')],   # 2-way handicap
}

# Hockey selection markets
HOCKEY_SELECTIONS = {
    74: {  # H1/P1 result + total goals (combo)
        '50818': '1&U', '50819': 'X&U', '50820': '2&U',
        '50821': '1&O', '50822': 'X&O', '50823': '2&O',
    },
}

# ============================================================================
# TABLE TENNIS CODE MAPPINGS (tipType codes with _TT suffix)
# ============================================================================

TABLE_TENNIS_2WAY = {
    1: ('1', '3'),   # Match Winner
}


class MaxbetScraper(BaseScraper):
    """
    Scraper for MaxBet Serbia.

    Uses MaxBet REST API with flat odds dict (code→value) and params dict.
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

    # ========================================================================
    # Helper methods for parsing odds from flat code→value dict
    # ========================================================================

    @staticmethod
    def _parse_3way_markets(
        odds: Dict, odds_list: List[ScrapedOdds], mapping: Dict[int, Tuple[str, str, str]]
    ) -> None:
        """Parse simple 3-way markets from code mapping."""
        for bt, (c1, c2, c3) in mapping.items():
            o1, o2, o3 = odds.get(c1), odds.get(c2), odds.get(c3)
            if o1 and o2 and o3:
                odds_list.append(ScrapedOdds(
                    bet_type_id=bt, odd1=float(o1), odd2=float(o2), odd3=float(o3)
                ))

    @staticmethod
    def _parse_2way_markets(
        odds: Dict, odds_list: List[ScrapedOdds], mapping: Dict[int, Tuple[str, str]]
    ) -> None:
        """Parse simple 2-way markets from code mapping."""
        for bt, (c1, c2) in mapping.items():
            o1, o2 = odds.get(c1), odds.get(c2)
            if o1 and o2:
                odds_list.append(ScrapedOdds(
                    bet_type_id=bt, odd1=float(o1), odd2=float(o2)
                ))

    @staticmethod
    def _parse_fixed_totals(
        odds: Dict, odds_list: List[ScrapedOdds],
        mapping: Dict[int, List[Tuple[float, str, str]]]
    ) -> None:
        """Parse fixed-margin O/U pairs (margin baked into code)."""
        for bt, pairs in mapping.items():
            for margin, under_code, over_code in pairs:
                under = odds.get(under_code)
                over = odds.get(over_code)
                if under and over:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=bt, odd1=float(under), odd2=float(over), margin=margin
                    ))

    @staticmethod
    def _parse_param_totals(
        odds: Dict, params: Dict, odds_list: List[ScrapedOdds],
        mapping: Dict[int, List[Tuple[str, str, str]]]
    ) -> None:
        """Parse param-based O/U pairs (margin from match params)."""
        for bt, entries in mapping.items():
            for param_key, under_code, over_code in entries:
                if under_code in odds and over_code in odds:
                    margin_val = params.get(param_key)
                    if margin_val is not None:
                        try:
                            odds_list.append(ScrapedOdds(
                                bet_type_id=bt,
                                odd1=float(odds[under_code]),
                                odd2=float(odds[over_code]),
                                margin=float(margin_val)
                            ))
                        except (ValueError, TypeError):
                            continue

    @staticmethod
    def _parse_param_handicaps_3way(
        odds: Dict, params: Dict, odds_list: List[ScrapedOdds],
        mapping: Dict[int, List[Tuple[str, str, str, str]]]
    ) -> None:
        """Parse param-based 3-way handicap (margin from match params)."""
        for bt, entries in mapping.items():
            for param_key, h_code, x_code, a_code in entries:
                if h_code in odds and x_code in odds and a_code in odds:
                    margin_val = params.get(param_key)
                    if margin_val is not None:
                        try:
                            odds_list.append(ScrapedOdds(
                                bet_type_id=bt,
                                odd1=float(odds[h_code]),
                                odd2=float(odds[x_code]),
                                odd3=float(odds[a_code]),
                                margin=float(margin_val)
                            ))
                        except (ValueError, TypeError):
                            continue

    @staticmethod
    def _parse_param_handicaps_2way(
        odds: Dict, params: Dict, odds_list: List[ScrapedOdds],
        mapping: Dict[int, List[Tuple[str, str, str]]]
    ) -> None:
        """Parse param-based 2-way handicap (margin from match params)."""
        for bt, entries in mapping.items():
            for param_key, h_code, a_code in entries:
                if h_code in odds and a_code in odds:
                    margin_val = params.get(param_key)
                    if margin_val is not None:
                        try:
                            margin = float(margin_val)
                            odds_list.append(ScrapedOdds(
                                bet_type_id=bt,
                                odd1=float(odds[h_code]),
                                odd2=float(odds[a_code]),
                                margin=-margin  # Flip sign: positive = home advantage
                            ))
                        except (ValueError, TypeError):
                            continue

    @staticmethod
    def _parse_selections(
        odds: Dict, odds_list: List[ScrapedOdds],
        mapping: Dict[int, Dict[str, str]]
    ) -> None:
        """Parse selection-based markets (each code = one selection)."""
        for bt, code_map in mapping.items():
            for code, selection in code_map.items():
                value = odds.get(code)
                if value:
                    try:
                        odds_list.append(ScrapedOdds(
                            bet_type_id=bt, odd1=float(value), selection=selection
                        ))
                    except (ValueError, TypeError):
                        continue

    # ========================================================================
    # Sport-specific parse methods
    # ========================================================================

    def parse_football_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse all football odds from MaxBet match data."""
        odds_list: List[ScrapedOdds] = []
        odds = match_data.get("odds", {})
        params = match_data.get("params", {})

        # 3-way markets (1X2, DC, first goal, etc.)
        self._parse_3way_markets(odds, odds_list, FOOTBALL_3WAY)

        # 2-way markets (BTTS, odd/even, DNB, etc.)
        self._parse_2way_markets(odds, odds_list, FOOTBALL_2WAY)

        # Fixed-margin totals (FT, H1, H2)
        self._parse_fixed_totals(odds, odds_list, FOOTBALL_FIXED_TOTALS)

        # Param-based team totals O/U
        self._parse_param_totals(odds, params, odds_list, FOOTBALL_PARAM_TOTALS)

        # Param-based 3-way handicaps
        self._parse_param_handicaps_3way(odds, params, odds_list, FOOTBALL_PARAM_HANDICAPS_3WAY)

        # Param-based 2-way H1 handicap
        self._parse_param_handicaps_2way(odds, params, odds_list, FOOTBALL_PARAM_HANDICAPS_2WAY)

        # Selection-based markets (correct score, HT/FT, ranges, etc.)
        self._parse_selections(odds, odds_list, FOOTBALL_SELECTIONS)

        return odds_list

    def parse_basketball_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse all basketball odds from MaxBet match data."""
        odds_list: List[ScrapedOdds] = []
        odds = match_data.get("odds", {})
        params = match_data.get("params", {})

        # Winner (2-way, incl. overtime)
        self._parse_2way_markets(odds, odds_list, BASKETBALL_2WAY)

        # Param-based handicaps (2-way, multiple lines)
        self._parse_param_handicaps_2way(odds, params, odds_list, BASKETBALL_PARAM_HANDICAPS)

        # Param-based totals (total points, H1, team totals)
        self._parse_param_totals(odds, params, odds_list, BASKETBALL_PARAM_TOTALS)

        return odds_list

    def parse_tennis_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse all tennis odds from MaxBet match data."""
        odds_list: List[ScrapedOdds] = []
        odds = match_data.get("odds", {})
        params = match_data.get("params", {})

        # Match winner, first set winner
        self._parse_2way_markets(odds, odds_list, TENNIS_2WAY)

        # Simple 2-way (tiebreak, odd/even)
        self._parse_2way_markets(odds, odds_list, TENNIS_SIMPLE_2WAY)

        # 3-way (set with more games)
        self._parse_3way_markets(odds, odds_list, TENNIS_3WAY)

        # Param-based total games
        self._parse_param_totals(odds, params, odds_list, TENNIS_PARAM_TOTALS)

        # Param-based handicaps (set handicap, game handicap S1)
        self._parse_param_handicaps_2way(odds, params, odds_list, TENNIS_PARAM_HANDICAPS)

        # Selection-based (exact sets, first set+match combo, games range)
        self._parse_selections(odds, odds_list, TENNIS_SELECTIONS)

        return odds_list

    def parse_hockey_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse all hockey odds from MaxBet match data."""
        odds_list: List[ScrapedOdds] = []
        odds = match_data.get("odds", {})
        params = match_data.get("params", {})

        # 1X2 Full Time
        self._parse_3way_markets(odds, odds_list, HOCKEY_3WAY)

        # Double chance
        self._parse_3way_markets(odds, odds_list, HOCKEY_SIMPLE_3WAY)

        # Period 1X2 (periods mapped to H1/H2 bet types)
        self._parse_3way_markets(odds, odds_list, HOCKEY_PERIOD_3WAY)

        # 2-way markets (DNB, BTTS, odd/even)
        self._parse_2way_markets(odds, odds_list, HOCKEY_2WAY)

        # Param-based totals (FT, period, team)
        self._parse_param_totals(odds, params, odds_list, HOCKEY_PARAM_TOTALS)

        # Param-based handicap (2-way)
        self._parse_param_handicaps_2way(odds, params, odds_list, HOCKEY_PARAM_HANDICAPS)

        # Selection-based markets
        self._parse_selections(odds, odds_list, HOCKEY_SELECTIONS)

        return odds_list

    def parse_table_tennis_odds(self, match_data: Dict) -> List[ScrapedOdds]:
        """Parse table tennis odds from MaxBet match data."""
        odds_list: List[ScrapedOdds] = []
        odds = match_data.get("odds", {})

        # Winner only
        self._parse_2way_markets(odds, odds_list, TABLE_TENNIS_2WAY)

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

    # ========================================================================
    # Network methods (unchanged)
    # ========================================================================

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
                start_time = self.parse_timestamp(kick_off)
                if not start_time:
                    continue

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
