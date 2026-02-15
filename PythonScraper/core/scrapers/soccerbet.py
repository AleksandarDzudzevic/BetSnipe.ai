"""
Soccerbet scraper for BetSnipe.ai v2.0 — fully expanded

Scrapes odds from Soccerbet Serbia API (same platform as MaxBet/Merkur).
Uses betMap dict {code: {"NULL": {"ov": value}}} structure.
Code mappings derived from ttg_lang endpoint (shared with MaxBet).

Key difference from MaxBet: NO param-based markets (handicaps, team totals
with variable margins). All odds are fixed-margin with "NULL" sv key.

v2.0 expansion: ~600+ football codes mapped (was ~188).
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from .base import BaseScraper, ScrapedMatch, ScrapedOdds

logger = logging.getLogger(__name__)

# Sport code mappings
SPORT_CODES = {
    1: 'S',   # Football
    2: 'B',   # Basketball
    3: 'T',   # Tennis
    4: 'H',   # Hockey
    5: 'TT',  # Table Tennis
}

# ============================================================================
# FOOTBALL CODE MAPPINGS (same codes as MaxBet, verified via ttg_lang)
# No param-based markets — Soccerbet only has fixed-margin codes.
# ============================================================================

FOOTBALL_3WAY = {
    2:  ('1', '2', '3'),         # 1X2 Full Time
    3:  ('4', '5', '6'),         # 1X2 First Half
    4:  ('235', '236', '237'),   # 1X2 Second Half
    13: ('7', '8', '9'),         # Double Chance (1X, 12, X2)
    20: ('397', '398', '399'),   # Double Chance H1
    75: ('608', '609', '610'),   # Double Chance H2
    18: ('204', '205', '206'),   # First Goal (home, nobody, away)
    19: ('29', '30', '31'),      # Half with More Goals (1st, equal, 2nd)
}

FOOTBALL_2WAY = {
    8:  ('272', '273'),    # BTTS (GG, NG)
    15: ('231', '232'),    # Odd/Even
    14: ('264', '265'),    # Draw No Bet
    16: ('295', '296'),    # Double Win
    17: ('282', '283'),    # Win to Nil
    21: ('611', '612'),    # Draw No Bet H1
    76: ('613', '614'),    # Draw No Bet H2
}

FOOTBALL_FIXED_TOTALS = {
    5: [  # Total O/U Full Time
        (1.5, '21', '242'),
        (2.5, '22', '24'),
        (3.5, '219', '25'),
        (4.5, '453', '27'),
        (5.5, '266', '223'),
    ],
    6: [  # Total O/U First Half
        (0.5, '267', '207'),
        (1.5, '211', '208'),
        (2.5, '472', '209'),
    ],
    7: [  # Total O/U Second Half
        (0.5, '269', '213'),
        (1.5, '217', '214'),
        (2.5, '474', '215'),
    ],
}

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
        '388': '!1/1|!1/X|!1/2',   # home doesn't win HT or FT
        '389': '!2/1|!2/X|!2/2',   # away doesn't win HT or FT
        '50589': '!X/X&!1/X&!X/1',  # no draw on HT or home doesn't win FT
        '50590': '!X/X&!X/X',       # no draw on HT or no draw on FT
        '50591': '!X/X&!2/X&!X/2',  # no draw on HT or away doesn't win FT
    },
    # === HT/FT OR combos (bt124) ===
    124: {
        '50202': '1/1|X/1X',   # H wins both OR draw+H1X
        '50203': '1/1|X/X',    # H wins both OR draw both
        '50204': '1/1|2/2',    # H wins both OR A wins both
        '50205': 'X/X|X/1X',   # draw both OR draw+H1X
        '50206': 'X/1|X/X',    # draw→H OR draw both
        '50207': 'X/X|X/X2',   # draw both OR draw+AX2
        '50208': '2/2|X/X2',   # A wins both OR draw+AX2
        '50209': '1/1&4+',     # H wins H1+FT & 4+ goals (double win + goals)
        '50273': '2/2|X/X',    # A wins both OR draw both
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
        '50219': 'GG2+',  # both teams score 2+
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
        '284': '1|1_H1|1_H2',  # home wins in at least one period
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
        '57304': '1/2|2/1',  # reversal
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
        '301': '1+&1+',  # scores both halves
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
        '302': '1+&1+',  # scores both halves
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
    # === Misc combo goal ranges ===
    # NOT exactly X goals markets (no standard bt, use bt39 = result combos)
    39: {
        '505': 'N1', '506': 'N2', '507': 'N3',  # not exactly 1/2/3 goals
        '776': 'H1_N1', '778': 'H1_N2',   # H1 not exactly 1/2 goals
        '781': 'H2_N1', '783': 'H2_N2',   # H2 not exactly 1/2 goals
        '55190': 'N1-2', '55191': 'N1-3', '55192': 'N1-4',
        '55196': 'N3-4', '55197': 'N3-5', '55198': 'N4-6',
        '57335': 'N3-6', '57336': 'N4-5',
        '51769': 'A0-1|H0-1',   # at least one team scores ≤1
        '623': 'H1:0|H2:0',     # at least one half goalless
        '624': 'H1:0|H2:0-1',   # no goals H1 or ≤1 in H2
        '625': 'H1:0-1|H2:0',   # ≤1 in H1 or no goals H2
        '57294': 'H_NG_H1|H2:0', '57295': 'A_NG_H1|H2:0',
        '57337': 'H1:N1-3|H2:N1-3',
        '519': '1&2+', '520': '2&2+',  # result + 2+
    },
    # === HT/FT combos (bt45) ===
    45: {
        # Result + goals deep combos
        '56519': '1&H1:1-3&H2:1-3', '56523': '2&H1:1-3&H2:1-3',
        '56520': '1&H1:2+&4+', '56524': '2&H1:2+&4+',
    },
}

# ============================================================================
# BASKETBALL CODE MAPPINGS
# ============================================================================

BASKETBALL_2WAY = {
    1: ('50291', '50293'),   # Winner (incl. OT)
}

BASKETBALL_3WAY = {
    2: ('1', '2', '3'),      # Regulation time 1X2
    3: ('4', '5', '6'),      # H1 1X2
}

BASKETBALL_SIMPLE_2WAY = {
    15: ('233', '234'),      # Odd/Even (basketball uses 233/234, not 231/232)
    16: ('295', '296'),      # Double Win
}

BASKETBALL_SIMPLE_3WAY = {
    19: ('29', '30', '31'),  # Half with More Points
}

BASKETBALL_SELECTIONS = {
    24: {  # HT/FT (with OT)
        '50296': '1/1', '50298': '1/2', '50299': 'X/1',
        '50301': 'X/2', '50302': '2/1', '50304': '2/2',
    },
}

# ============================================================================
# TENNIS CODE MAPPINGS
# ============================================================================

TENNIS_2WAY = {
    1:  ('1', '3'),              # Match Winner
    57: ('50510', '50511'),      # First Set Winner
}

TENNIS_SIMPLE_2WAY = {
    60: ('51196', '51197'),      # Tiebreak S1 (yes, no)
    59: ('50520', '50521'),      # Odd/Even S1
}

TENNIS_3WAY = {
    63: ('51061', '51062', '51063'),  # Set with More Games (S1>, equal, S2>)
}

TENNIS_SELECTIONS = {
    65: {  # Exact Sets
        '50544': '2:0', '50545': '0:2',
        '50548': '2:1', '50549': '1:2',
    },
    64: {  # First Set + Match Combo
        '50540': '1/1', '50541': '1/2',
        '50542': '2/1', '50543': '2/2',
    },
    66: {  # Games Range S1
        '51198': 'T6', '51199': '7-8', '51200': '9-12', '51201': 'T13',
    },
    67: {  # Games Range S2
        '51202': 'T6', '51203': '7-8', '51204': '9-12', '51205': 'T13',
    },
}

# ============================================================================
# HOCKEY CODE MAPPINGS
# ============================================================================

HOCKEY_3WAY = {
    2: ('1', '2', '3'),                      # 1X2 Full Time
    3: ('50495', '50496', '50497'),           # Period 1 1X2
    4: ('50498', '50499', '50500'),           # Period 2 1X2
}

HOCKEY_SIMPLE_3WAY = {
    13: ('7', '8', '9'),                     # Double Chance
}

HOCKEY_2WAY = {
    14: ('264', '265'),                      # Draw No Bet / Winner
    8:  ('272', '273'),                      # BTTS (GG, NG)
    15: ('231', '232'),                      # Odd/Even
}

HOCKEY_SELECTIONS = {
    74: {  # P1 result + total goals combo
        '50818': '1&U', '50819': 'X&U', '50820': '2&U',
        '50821': '1&O', '50822': 'X&O', '50823': '2&O',
    },
}

# ============================================================================
# TABLE TENNIS CODE MAPPINGS
# ============================================================================

TABLE_TENNIS_2WAY = {
    1:  ('1', '3'),              # Match Winner
    57: ('50510', '50511'),      # First Set Winner
}


class SoccerbetScraper(BaseScraper):
    """
    Scraper for Soccerbet Serbia.

    Same platform as MaxBet/Merkur. Uses betMap with "NULL" sv key.
    No param-based markets (no handicaps or variable-margin totals).
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
        return {
            "annex": "0",
            "desktopVersion": "2.36.3.9",
            "locale": "sr"
        }

    def get_supported_sports(self) -> List[int]:
        return [1, 2, 3, 4, 5]

    # ========================================================================
    # BetMap flattening: convert {code: {"NULL": {"ov": val}}} -> {code: val}
    # ========================================================================

    @staticmethod
    def _flatten_betmap(bet_map: Dict) -> Dict[str, Any]:
        """Convert Soccerbet betMap to flat code->value dict like MaxBet odds."""
        flat = {}
        for code, entry in bet_map.items():
            if isinstance(entry, dict):
                null_entry = entry.get("NULL")
                if isinstance(null_entry, dict):
                    ov = null_entry.get("ov")
                    if ov is not None:
                        flat[code] = ov
        return flat

    # ========================================================================
    # Generic helper methods (same pattern as MaxBet/Merkur)
    # ========================================================================

    @staticmethod
    def _parse_3way_markets(
        odds: Dict, odds_list: List[ScrapedOdds], mapping: Dict[int, Tuple[str, str, str]]
    ) -> None:
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
        for bt, pairs in mapping.items():
            for margin, under_code, over_code in pairs:
                under = odds.get(under_code)
                over = odds.get(over_code)
                if under and over:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=bt, odd1=float(under), odd2=float(over), margin=margin
                    ))

    @staticmethod
    def _parse_selections(
        odds: Dict, odds_list: List[ScrapedOdds], mapping: Dict[int, Dict[str, str]]
    ) -> None:
        for bt, code_map in mapping.items():
            for code, selection in code_map.items():
                val = odds.get(code)
                if val:
                    odds_list.append(ScrapedOdds(
                        bet_type_id=bt, odd1=float(val), odd2=0, selection=selection
                    ))

    # ========================================================================
    # Sport-specific parse methods
    # ========================================================================

    def _parse_football(self, odds: Dict) -> List[ScrapedOdds]:
        odds_list: List[ScrapedOdds] = []
        self._parse_3way_markets(odds, odds_list, FOOTBALL_3WAY)
        self._parse_2way_markets(odds, odds_list, FOOTBALL_2WAY)
        self._parse_fixed_totals(odds, odds_list, FOOTBALL_FIXED_TOTALS)
        self._parse_selections(odds, odds_list, FOOTBALL_SELECTIONS)
        return odds_list

    def _parse_basketball(self, odds: Dict) -> List[ScrapedOdds]:
        odds_list: List[ScrapedOdds] = []
        self._parse_2way_markets(odds, odds_list, BASKETBALL_2WAY)
        self._parse_3way_markets(odds, odds_list, BASKETBALL_3WAY)
        self._parse_2way_markets(odds, odds_list, BASKETBALL_SIMPLE_2WAY)
        self._parse_3way_markets(odds, odds_list, BASKETBALL_SIMPLE_3WAY)
        self._parse_selections(odds, odds_list, BASKETBALL_SELECTIONS)
        return odds_list

    def _parse_tennis(self, odds: Dict) -> List[ScrapedOdds]:
        odds_list: List[ScrapedOdds] = []
        self._parse_2way_markets(odds, odds_list, TENNIS_2WAY)
        self._parse_2way_markets(odds, odds_list, TENNIS_SIMPLE_2WAY)
        self._parse_3way_markets(odds, odds_list, TENNIS_3WAY)
        self._parse_selections(odds, odds_list, TENNIS_SELECTIONS)
        return odds_list

    def _parse_hockey(self, odds: Dict) -> List[ScrapedOdds]:
        odds_list: List[ScrapedOdds] = []
        self._parse_3way_markets(odds, odds_list, HOCKEY_3WAY)
        self._parse_3way_markets(odds, odds_list, HOCKEY_SIMPLE_3WAY)
        self._parse_2way_markets(odds, odds_list, HOCKEY_2WAY)
        self._parse_selections(odds, odds_list, HOCKEY_SELECTIONS)
        return odds_list

    def _parse_table_tennis(self, odds: Dict) -> List[ScrapedOdds]:
        odds_list: List[ScrapedOdds] = []
        self._parse_2way_markets(odds, odds_list, TABLE_TENNIS_2WAY)
        return odds_list

    def parse_odds(self, bet_map: Dict, sport_id: int) -> List[ScrapedOdds]:
        """Parse odds: flatten betMap then dispatch by sport."""
        odds = self._flatten_betmap(bet_map)
        if sport_id == 1:
            return self._parse_football(odds)
        elif sport_id == 2:
            return self._parse_basketball(odds)
        elif sport_id == 3:
            return self._parse_tennis(odds)
        elif sport_id == 4:
            return self._parse_hockey(odds)
        elif sport_id == 5:
            return self._parse_table_tennis(odds)
        return []

    # ========================================================================
    # Network methods (unchanged)
    # ========================================================================

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

    async def _process_league(
        self,
        sport_id: int,
        league_id: str,
        league_name: str
    ) -> List[ScrapedMatch]:
        """Process a single league and return its matches."""
        matches: List[ScrapedMatch] = []

        try:
            league_matches = await self.fetch_league_matches(sport_id, league_id)

            if not league_matches:
                return matches

            batch_size = 20
            for i in range(0, len(league_matches), batch_size):
                batch = league_matches[i:i + batch_size]

                detail_tasks = [
                    self.fetch_match_details(str(m["id"]))
                    for m in batch
                ]
                details = await asyncio.gather(*detail_tasks, return_exceptions=True)

                for match_data, detail in zip(batch, details):
                    try:
                        if isinstance(detail, Exception) or not detail:
                            continue

                        team1 = match_data.get("home", "")
                        team2 = match_data.get("away", "")

                        if not team1 or not team2:
                            continue

                        kick_off = detail.get("kickOffTime", 0)
                        start_time = self.parse_timestamp(kick_off)
                        if not start_time:
                            continue

                        scraped_match = ScrapedMatch(
                            team1=team1,
                            team2=team2,
                            sport_id=sport_id,
                            start_time=start_time,
                            league_name=league_name,
                            external_id=str(match_data.get("id")),
                        )

                        bet_map = detail.get("betMap", {})
                        scraped_match.odds = self.parse_odds(bet_map, sport_id)

                        if scraped_match.odds:
                            matches.append(scraped_match)

                    except Exception as e:
                        logger.warning(f"[Soccerbet] Error processing match: {e}")
                        continue

        except Exception as e:
            logger.warning(f"[Soccerbet] Error processing league {league_name}: {e}")

        return matches

    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """Scrape all matches for a sport."""
        leagues = await self.fetch_leagues(sport_id)

        if not leagues:
            logger.debug(f"[Soccerbet] No leagues for sport {sport_id}")
            return []

        logger.debug(f"[Soccerbet] Found {len(leagues)} leagues for sport {sport_id}")

        league_tasks = [
            self._process_league(sport_id, league_id, league_name)
            for league_id, league_name in leagues
        ]

        results = await asyncio.gather(*league_tasks, return_exceptions=True)

        all_matches: List[ScrapedMatch] = []
        for result in results:
            if isinstance(result, list):
                all_matches.extend(result)

        return all_matches
