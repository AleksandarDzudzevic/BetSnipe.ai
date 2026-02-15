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
    75: ('608', '609', '610'),   # Double Chance H2
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
    76: ('613', '614'),    # Draw No Bet H2
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
    # === Correct Score (bt23) ===
    23: {
        '51': '0:0', '52': '1:0', '54': '2:0', '56': '3:0', '58': '4:0',
        '53': '0:1', '67': '1:1', '68': '2:1', '70': '3:1', '72': '4:1',
        '55': '0:2', '69': '1:2', '82': '2:2', '83': '3:2', '85': '4:2',
        '57': '0:3', '71': '1:3', '84': '2:3', '95': '3:3', '96': '4:3',
        '59': '0:4', '73': '1:4', '86': '2:4', '97': '3:4', '106': '4:4',
    },
    # === H1 Correct Score (bt79) ===
    79: {
        '188': '0:0', '189': '1:1', '190': '2:2',
        '191': '1:0', '192': '2:0', '193': '2:1',
        '194': '0:1', '195': '0:2', '196': '1:2',
        '50259': '3:1', '50260': '3:2', '50261': '0:3',
        '50262': '1:3', '50263': '2:3', '50270': '3:0', '50375': '3:3',
    },
    # === HT/FT (bt24) ===
    24: {
        '10': '1/1', '11': '1/X', '12': '1/2',
        '13': 'X/1', '14': 'X/X', '15': 'X/2',
        '16': '2/1', '17': '2/X', '18': '2/2',
    },
    # === HT/FT Double Chance (bt37) ===
    37: {
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
    # === HT/FT NOT (bt113) ===
    113: {
        '388': '!1/1|!1/X|!1/2',
        '389': '!2/1|!2/X|!2/2',
        '50589': '!X/X&!1/X&!X/1',
        '50590': '!X/X&!X/X',
        '50591': '!X/X&!2/X&!X/2',
    },
    # === HT/FT OR combos (bt124) ===
    124: {
        '50202': '1/1|X/1X',
        '50203': '1/1|X/X',
        '50204': '1/1|2/2',
        '50205': 'X/X|X/1X',
        '50206': 'X/1|X/X',
        '50207': 'X/X|X/X2',
        '50208': '2/2|X/X2',
        '50209': '1/1&4+',
        '50273': '2/2|X/X',
    },
    # === Exact Goals (bt26) ===
    26: {
        '320': '1', '221': '2', '222': '3', '321': '4', '322': '5',
    },
    # === Total Goals Range (bt25) ===
    25: {
        '278': '1-2', '279': '1-3', '280': '1-4', '380': '1-5', '381': '1-6',
        '23': '2-3', '243': '2-4', '333': '2-5', '220': '2-6',
        '244': '3-4', '281': '3-5', '382': '3-6',
        '379': '4-5', '26': '4-6',
        '28': '7+',
        '406': '1+',
    },
    # === Team 1 Goals (bt27) ===
    27: {
        '247': '0-1', '551': '0-2', '553': '0-3',
        '478': '1-2', '479': '1-3', '480': '2-3',
        '248': '2+', '276': '3+', '555': '4+',
        '323': 'T1', '324': 'T2', '484': 'T3',
        '238': '1+', '239': '0',
        '50224': '2-4', '50225': '2-5', '50226': '3-4', '50227': '3-5',
        '50404': '2-6', '57333': '3-6',
    },
    # === Team 2 Goals (bt28) ===
    28: {
        '249': '0-1', '552': '0-2', '554': '0-3',
        '481': '1-2', '482': '1-3', '483': '2-3',
        '250': '2+', '277': '3+', '556': '4+',
        '325': 'T1', '326': 'T2', '485': 'T3',
        '240': '1+', '241': '0',
        '50234': '2-4', '50235': '2-5', '50236': '3-4', '50237': '3-5',
        '50405': '2-6', '57334': '3-6',
    },
    # === H1 Total Goals Range (bt29) ===
    29: {
        '267': 'T0', '268': 'T1', '777': 'T2', '779': 'T3',
        '476': '1-2', '477': '1-3',
        '212': '2-3',
        '210': '4+', '55345': '2-4',
    },
    # === H2 Total Goals Range (bt30) ===
    30: {
        '269': 'T0', '270': 'T1', '782': 'T2', '784': 'T3',
        '606': '1-2', '607': '1-3',
        '218': '2-3',
        '216': '4+', '55346': '2-4',
    },
    # === Team 1 Goals H1 (bt31) ===
    31: {
        '337': 'T0', '341': 'T1',
        '307': '1+', '274': '2+', '349': '3+',
        '50112': '1-2', '817': '0-1', '50229': '4+', '50230': '2-3',
    },
    # === Team 2 Goals H1 (bt32) ===
    32: {
        '338': 'T0', '342': 'T1',
        '308': '1+', '275': '2+', '350': '3+',
        '50113': '1-2', '821': '0-1', '50239': '4+', '50240': '2-3',
    },
    # === Team 1 Goals H2 (bt33) ===
    33: {
        '339': 'T0', '343': 'T1',
        '312': '1+', '297': '2+', '351': '3+',
        '825': '0-1', '50231': '4+', '50232': '1-2', '50233': '2-3',
    },
    # === Team 2 Goals H2 (bt34) ===
    34: {
        '340': 'T0', '344': 'T1',
        '313': '1+', '298': '2+', '352': '3+',
        '829': '0-1', '50241': '4+', '50242': '1-2', '50243': '2-3',
    },
    # === Win Margin (bt121) ===
    121: {
        '50275': '1by1', '50276': '1by2', '50277': '1by3+',
        '50278': '2by1', '50279': '2by2', '50280': '2by3+',
        '755': '1by2+', '756': '2by2+',
    },
    # === Correct Score Combos (bt118) ===
    118: {
        '53967': '1:0|2:0|3:0', '53968': '0:1|0:2|0:3',
        '53971': '2:1|3:1|4:1', '53972': '1:2|1:3|1:4',
    },
    # === First Goal + Final Result (bt36) ===
    36: {
        '806': 'H_scores_first', '808': 'A_scores_first',
        '433': '1&H_first', '436': '2&A_first',
        '434': '2&H_first', '435': '1&A_first',
        '50661': 'X&H_first', '50662': 'X&A_first',
    },
    # === First Goal + Total (bt122) ===
    122: {
        '51569': 'H_first&2+', '51570': 'A_first&2+',
        '53346': 'H_first&3+', '53347': 'A_first&3+',
        '53348': 'H_first&4+', '53349': 'A_first&4+',
        '55864': 'H_first&GG', '55866': 'A_first&GG',
        '55865': 'H_first&H2+', '55867': 'A_first&A2+',
    },
    # === Result + Total Goals (bt38) ===
    38: {
        # Home wins + total
        '287': '1&3+', '314': '1&4+', '50246': '1&5+',
        '369': '1&2-3', '400': '1&0-2', '514': '1&0-3',
        '50188': '1&2-4', '50190': '1&3-5', '50628': '1&0-4',
        '50723': '1&2-5', '50724': '1&3-4', '50725': '1&3-6',
        '51396': '1&4-6', '55145': '1&1-6', '51784': '1&2-6',
        '55868': '1&4-5',
        # Away wins + total
        '288': '2&3+', '315': '2&4+', '50249': '2&5+',
        '370': '2&2-3', '401': '2&0-2', '515': '2&0-3',
        '50189': '2&2-4', '50191': '2&3-5', '50630': '2&0-4',
        '50727': '2&2-5', '50728': '2&3-4', '50729': '2&3-6',
        '51397': '2&4-6', '55148': '2&1-6', '51785': '2&2-6',
        '55871': '2&4-5',
        # Draw + total
        '50252': 'X&2+', '334': 'X&0-2', '50253': 'X&4+',
        # Home/Away (12) + total
        '580': '12&0-1', '579': '12&2+', '583': '12&2-3',
        '574': '12&0-3', '561': '12&3+', '573': '12&4+',
        '53330': '12&1-2', '53331': '12&1-3', '56537': '12&0-4',
        '55857': '12&2-6',
        # Home wins + team-specific goals
        '50266': '1&H3+', '55870': '1&H2-3', '55869': '1&H1:1-2',
        # Away wins + team-specific goals
        '50267': '2&A3+', '55873': '2&A2-3', '55872': '2&H1:1-2',
        # Home wins + H1 goals
        '50247': '1&H1:1+', '50248': '1&H1:2-3',
        '50592': '1&H2:1+', '50384': '1&H2:2+',
        '55146': '1&H1:1+&2+', '55147': '1&H1:1+&3+',
        # Away wins + H1 goals
        '50250': '2&H1:1+', '50251': '2&H1:2-3',
        '50593': '2&H2:1+', '50385': '2&H2:2+',
        '55149': '2&H1:1+&2+', '55150': '2&H1:1+&3+',
        # Home wins + goals in both halves
        '50726': '1&H1:1+&H2:1+',
        # Away wins + goals in both halves
        '50730': '2&H1:1+&H2:1+',
        # Result + H1 goals
        '305': '1&H1_2+', '306': '2&H1_2+',
    },
    # === DC + Total Goals (bt41) ===
    41: {
        # 1X (home or draw) + total
        '557': '1X&3+', '569': '1X&4+', '576': '1X&0-1',
        '558': '1X&0-2', '570': '1X&0-3', '575': '1X&2+',
        '581': '1X&2-3', '563': '1X&GG',
        '50731': '1X&H1:0-1', '50732': '1X&H1:2+',
        '51399': '1X&1-2', '51400': '1X&1-3', '51401': '1X&2-4',
        '51402': '1X&2-5', '51403': '1X&3-5', '51404': '1X&3-6',
        '51405': '1X&4-6', '51406': '1X&H1:1+',
        '51408': '1X&H2+', '55690': '1X&H1:1+&H2:1+',
        '56531': '1X&0-4',
        '55855': '1X&2-6', '55856': '1X&H1:1-2',
        # X2 (away or draw) + total
        '559': 'X2&3+', '571': 'X2&4+', '578': 'X2&0-1',
        '560': 'X2&0-2', '572': 'X2&0-3', '577': 'X2&2+',
        '582': 'X2&2-3', '565': 'X2&GG',
        '50733': 'X2&H1:0-1', '50734': 'X2&H1:2+',
        '51409': 'X2&1-2', '51410': 'X2&1-3', '51411': 'X2&2-4',
        '51412': 'X2&2-5', '51413': 'X2&3-5', '51414': 'X2&3-6',
        '51415': 'X2&4-6', '51416': 'X2&H1:1+',
        '51418': 'X2&A2+', '55691': 'X2&H1:1+&H2:1+',
        '56533': 'X2&0-4', '55862': 'X2&2-6', '55863': 'X2&H1:1-2',
        # 12 (home or away) + total -- some already in bt38
        '562': '12&0-2', '567': '12&GG',
    },
    # === Result + Half With More Goals (bt40) ===
    40: {
        '50213': '1&H1>H2', '50214': '1&H1=H2', '50215': '1&H1<H2',
        '50216': '2&H1>H2', '50217': '2&H1=H2', '50218': '2&H1<H2',
        '50676': '1X&H1>H2', '50677': '1X&H1=H2', '50678': '1X&H1<H2',
        '50679': 'X2&H1>H2', '50680': 'X2&H1=H2', '50681': 'X2&H1<H2',
        '50682': '12&H1>H2', '50683': '12&H1=H2', '50684': '12&H1<H2',
    },
    # === BTTS Combos (bt46) ===
    46: {
        # BTTS + total
        '303': 'GG&3+', '304': 'GG&4+',
        '536': 'GG|3+', '537': 'NG&0-2',
        '50219': 'GG2+',
        '50314': 'GG&2-3',
        '50400': 'GG_H1&3+', '50401': 'GG_H2&3+',
        '54030': 'GG_H1&4+', '54031': 'GG_H2&4+',
        '55204': 'GG_H1&3+_FT', '55205': 'GG_H2&3+_FT',
        # BTTS + result
        '365': '1&GG', '366': '2&GG',
        '526': '1|GG', '528': '2|GG',
        # BTTS + team goals
        '753': 'GG&H2+', '754': 'GG&A2+',
        '55184': 'GG&H3+', '55185': 'GG&A3+',
        # BTTS in halves
        '291': 'GG_H1', '292': 'NG_H1',
        '299': 'GG_H2', '300': 'NG_H2',
        '443': 'GG_H1&GG_H2',
        '864': 'GG_H1|GG_H2',
        '701': 'GG_H1&NG_H2|NG_H1',
        '703': 'NG_H1&NG_H2',
        '50110': 'GG_H1|NG_H2',
        '50111': 'NG_H1|GG_H2',
        # BTTS + H1 goals
        '55199': 'GG&H1:1+', '55200': 'GG&H1:2+',
        '55201': 'GG&H2:1+', '55202': 'GG&H2:2+',
        '55203': 'GG&H1:1+&H2:1+',
        '55854': 'GG&H1:1-2',
        # BTTS + halftime result
        '635': '1_H1&GG_H1', '637': '2_H1&GG_H1',
        '636': 'X_H1&GG_H1',
        '654': '1_H2&GG_H2', '656': '2_H2&GG_H2',
        '655': 'X_H2&GG_H2',
        '51670': '1&GG_H1', '51672': '2&GG_H1',
        '51671': 'X&GG_H1',
        '51673': '1&GG_H2', '51675': '2&GG_H2',
        '51674': 'X&GG_H2',
    },
    # === OR Combinations (bt114) ===
    114: {
        '284': '1|1_H1|1_H2',
        '285': 'X|X_H1|X_H2',
        '286': '2|2_H1|2_H2',
        '402': '1|3+', '403': '2|3+',
        '532': '1|4+', '533': '2|4+',
        '50256': '1|H1:2+', '50257': '2|H1:2+',
        '50258': 'H4+|A4+',
        '50313': 'H1:2+|H2:2+',
        '523': 'X|3+',
        '50312': 'H1:2+|FT:4+',
        '51621': 'H1:3+|H2:3+',
        '57296': '1|H1:3+', '57297': '2|H1:3+',
        '57298': 'H1:2+|H2:2+_alt',
        '57299': 'H1:2-3|H2:2-3',
        '57300': '1|GG&3+', '57301': '2|GG&3+',
        '57302': '1_H1|1_H2', '57303': '2_H1|2_H2',
    },
    # === HT/FT + Total Goals (bt44) ===
    44: {
        # 1/1 + total
        '289': '1/1&3+', '862': '1/1&2+', '50254': '1/1&2-3',
        '50091': '1/1&0-2', '50096': '1/1&0-3',
        '50094': '1/1&NG', '50698': '1/1&2-5', '50699': '1/1&3-4',
        '50700': '1/1&3-6', '51420': '1/1&4-6',
        '50192': '1/1&2-4', '50194': '1/1&3-5',
        '55835': '1/1&2-6', '55836': '1/1&4-5', '55837': '1/1&5+',
        '331': '1/1&H1:2+', '50701': '1/1&H2:1+',
        '55838': '1/1&H2:1+_alt', '55839': '1/1&H2-3',
        '55840': '1/1&H3+',
        '55841': '1/1&H1<H2', '55842': '1/1&H1:1+&H2:1+',
        '55843': '1/1&H1>H2',
        '54032': '1/1&GG', '54033': '1/1&GG_H2',
        '367': '1/1&GG_FT', '50211': '1/1&NG_A',
        '327': '1/1&4+_FT',
        '757': '1/1&1by2+',
        '50749': '1/1&H1:1+_H2:1+',
        # 2/2 + total
        '290': '2/2&3+', '863': '2/2&2+', '50255': '2/2&2-3',
        '50092': '2/2&0-2', '50097': '2/2&0-3',
        '50095': '2/2&NG', '50718': '2/2&2-5', '50719': '2/2&3-4',
        '50720': '2/2&3-6', '51423': '2/2&4-6',
        '50193': '2/2&2-4', '50195': '2/2&3-5',
        '55846': '2/2&2-6', '55847': '2/2&4-5', '55848': '2/2&5+',
        '332': '2/2&H1:2+', '50721': '2/2&H2:1+',
        '55849': '2/2&H2:1+_alt', '55850': '2/2&A2-3',
        '55851': '2/2&A3+',
        '55852': '2/2&H1<H2', '55874': '2/2&H1:1+&H2:1+',
        '55875': '2/2&H1>H2',
        '54034': '2/2&GG', '54035': '2/2&GG_H2',
        '368': '2/2&GG_FT', '50212': '2/2&NG_H',
        '328': '2/2&4+_FT',
        '758': '2/2&2by2+',
        '50750': '2/2&H1:1+_H2:1+',
        # X/1 + total
        '50378': 'X/1&0-1', '50379': 'X/1&0-2', '50380': 'X/1&2+',
        '50381': 'X/1&2-3', '50382': 'X/1&3+', '50383': 'X/1&4+',
        '50268': 'X/1&GG_H',
        '50704': 'X/1&2-4', '50705': 'X/1&2-5',
        '50706': 'X/1&3-4', '50707': 'X/1&3-6',
        '50708': 'X/1&GG',
        '50402': 'X/1&NG_A', '51558': 'X/1&GG_alt',
        '55844': 'X/1&2-6',
        # X/2 + total
        '50387': 'X/2&0-1', '50388': 'X/2&0-2', '50389': 'X/2&2+',
        '50390': 'X/2&2-3', '50391': 'X/2&3+', '50392': 'X/2&4+',
        '50269': 'X/2&GG_A',
        '50710': 'X/2&2-4', '50711': 'X/2&2-5',
        '50712': 'X/2&3-4', '50713': 'X/2&3-6',
        '50714': 'X/2&GG',
        '50403': 'X/2&NG_H', '50715': 'X/2&GG_alt',
        '55845': 'X/2&2-6',
        # X/X + total
        '50393': 'X/X&0-2', '50394': 'X/X&2+',
        '50220': 'X/1&GG', '50221': 'X/2&GG',
        # 1/2 + total
        '50703': '1/2&GG',
        # 2/1 + total
        '50717': '2/1&GG',
        # Misc HT/FT combos
        '57304': '1/2|2/1',
        '57307': '1&H1:1-2&H2:1-2',
        '57316': 'X&H1:1-2&H2:1-2',
        '57317': 'X&H1:0-2&H2:0-2',
        '57318': 'X&H1:0-2&H2:1-3',
        '57320': '2&H1:1-2&H2:1-2',
        '57325': '1/1&H1:1-3&H2:1-3',
        '57326': '2/2&H1:1-3&H2:1-3',
        '57327': '1/1&H1:1-2&H2:1-2',
        '57328': '2/2&H1:1-2&H2:1-2',
        '57331': '1/1&H1:2+&H2:1-3',
        '57332': '2/2&H1:2+&H2:1-3',
    },
    # === HT Result + BTTS (bt123) ===
    123: {
        '638': '1_H1&NG_H1', '639': 'X_H1&NG_H1', '640': '2_H1&NG_H1',
        '657': '1_H2&NG_H2', '658': 'X_H2&NG_H2', '659': '2_H2&NG_H2',
    },
    # === Goals H1 & H2 Combo (bt35) ===
    35: {
        '363': 'H1:1+&H2:1+', '364': 'H1:2+&H2:2+',
        '316': 'H1:1+&H2:2+', '317': 'H1:2+&H2:1+',
        '615': 'H1:1+&H2:3+', '50685': 'H1:2+&H2:3+',
        '50244': 'H1:2+&FT:4+', '50245': 'H1:2-3&FT:4+',
        '50310': 'H1:1+&FT:2+', '50311': 'H1:1+&FT:3+',
        '50739': 'H1:0-1&H2:0-1', '50740': 'H1:0-1&H2:0-2',
        '50741': 'H1:0-1&H2:0-3',
        '50742': 'H1:0-2&H2:0-1', '50743': 'H1:0-2&H2:0-2',
        '50744': 'H1:0-2&H2:0-3',
        '51426': 'H1:0-1&H2:2-3', '51427': 'H1:0-1&H2:2+',
        '51428': 'H1:1-2&H2:1-2',
        '51429': 'H1:2-3&H2:0-1', '51430': 'H1:2-3&H2:2-3',
        '51568': 'H1:1-3&H2:1-3',
        '53197': 'H1:1-2&FT:3+',
        '55151': 'H1:0-1&H2:1+', '55152': 'H1:0-1&H2:1-2',
        '55153': 'H1:0-1&H2:1-3', '55154': 'H1:0-2&H2:1-2',
        '55155': 'H1:0-2&H2:1-3', '55156': 'H1:0-2&H2:2+',
        '55157': 'H1:0-2&H2:2-3',
        '55159': 'H1:1+&H2:0-2', '55160': 'H1:1+&H2:1-2',
        '55161': 'H1:1+&H2:1-3', '55162': 'H1:1+&H2:2-3',
        '55163': 'H1:1-2&H2:0-1', '55164': 'H1:1-2&H2:0-2',
        '55165': 'H1:1-2&H2:0-3', '55166': 'H1:1-2&H2:1+',
        '55167': 'H1:1-2&H2:1-3', '55168': 'H1:1-2&H2:2+',
        '55169': 'H1:1-2&H2:2-3',
        '55170': 'H1:1-3&H2:1+', '55171': 'H1:1-3&H2:1-2',
        '55172': 'H1:1-3&H2:2+',
        '55174': 'H1:2-3&H2:0-2', '55175': 'H1:2-3&H2:1+',
        '55176': 'H1:2-3&H2:1-2', '55177': 'H1:2-3&H2:1-3',
        '55178': 'H1:2-3&H2:2+',
        '56525': 'X&H1:1-3&H2:1-3',
        '56527': 'H1:1+&FT:4+',
    },
    # === Team 1 H1 & H2 Goal Combos (bt119) ===
    119: {
        '301': '1+&1+',
        '437': 'H1>H2', '438': 'H1=H2', '439': 'H1<H2',
        '413': 'H1:1+&H2:2+', '414': 'H1:2+&H2:1+', '415': 'H1:2+&H2:2+',
        '50686': 'H1:0-1&H2:0-1', '50687': 'H1:0-1&H2:0-2',
        '50688': 'H1:0-2&H2:0-1', '50689': 'H1:0-2&H2:0-2',
        '50690': 'H1:1+&H2:2+', '50691': 'H1:1+&H2:3+',
        '56511': 'H1:1-2&H2:1-2', '56512': 'H1:1-3&H2:1-3',
        '55881': 'H1:2+&FT:3+',
    },
    # === Team 2 H1 & H2 Goal Combos (bt120) ===
    120: {
        '302': '1+&1+',
        '440': 'H1>H2', '441': 'H1=H2', '442': 'H1<H2',
        '416': 'H1:1+&H2:2+', '417': 'H1:2+&H2:1+', '418': 'H1:2+&H2:2+',
        '50692': 'H1:0-1&H2:0-1', '50693': 'H1:0-1&H2:0-2',
        '50694': 'H1:0-2&H2:0-1', '50695': 'H1:0-2&H2:0-2',
        '50696': 'H1:1+&H2:2+', '50697': 'H1:1+&H2:3+',
        '56515': 'H1:1-2&H2:1-2', '56516': 'H1:1-3&H2:1-3',
        '55853': 'H1:2+&FT:3+',
    },
    # === DC + Half Goals (bt116) ===
    116: {
        '57308': '1X&H1:1+&H2:1+', '57309': 'X2&H1:1+&H2:1+',
        '57310': '1X&H1:1-2&H2:1-2', '57311': 'X2&H1:1-2&H2:1-2',
        '57312': '1X&H1:1+&H2:1-3', '57313': 'X2&H1:1+&H2:1-3',
        '57314': '1X&H1:2+&H2:1-3', '57315': 'X2&H1:2+&H2:1-3',
        '56534': '1X&H1:1-3&H2:1-3', '56535': 'X2&H1:1-3&H2:1-3',
    },
    # === DC + H1 goals result combos (bt42) ===
    42: {
        '57305': '12&H2+', '57306': '12&A2+',
    },
    # === Misc combo goal ranges (bt39) ===
    39: {
        '505': 'N1', '506': 'N2', '507': 'N3',
        '776': 'H1_N1', '778': 'H1_N2',
        '781': 'H2_N1', '783': 'H2_N2',
        '55190': 'N1-2', '55191': 'N1-3', '55192': 'N1-4',
        '55196': 'N3-4', '55197': 'N3-5', '55198': 'N4-6',
        '57335': 'N3-6', '57336': 'N4-5',
        '51769': 'A0-1|H0-1',
        '623': 'H1:0|H2:0',
        '624': 'H1:0|H2:0-1',
        '625': 'H1:0-1|H2:0',
        '57294': 'H_NG_H1|H2:0', '57295': 'A_NG_H1|H2:0',
        '57337': 'H1:N1-3|H2:N1-3',
        '519': '1&2+', '520': '2&2+',
    },
    # === HT/FT combos (bt45) ===
    45: {
        '56519': '1&H1:1-3&H2:1-3', '56523': '2&H1:1-3&H2:1-3',
        '56520': '1&H1:2+&4+', '56524': '2&H1:2+&4+',
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
        """Parse param-based 3-way handicap (margin from match params).

        Football (European HC): sign is negated so positive = home
        advantage.  MaxBet API returns negative values when home team
        receives goals (opposite of Admiral/Merkur convention).
        """
        for bt, entries in mapping.items():
            for param_key, h_code, x_code, a_code in entries:
                if h_code in odds and x_code in odds and a_code in odds:
                    margin_val = params.get(param_key)
                    if margin_val is not None:
                        try:
                            margin = float(margin_val)
                            odds_list.append(ScrapedOdds(
                                bet_type_id=bt,
                                odd1=float(odds[h_code]),
                                odd2=float(odds[x_code]),
                                odd3=float(odds[a_code]),
                                margin=-margin  # Flip sign: positive = home advantage
                            ))
                        except (ValueError, TypeError):
                            continue

    @staticmethod
    def _parse_param_handicaps_2way(
        odds: Dict, params: Dict, odds_list: List[ScrapedOdds],
        mapping: Dict[int, List[Tuple[str, str, str]]]
    ) -> None:
        """Parse param-based 2-way handicap (margin from match params).

        Basketball/Hockey (Asian HC): sign is negated so positive = home
        advantage.  API gives negative value for home handicap; we flip
        to match the cross-bookmaker convention.
        """
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
