"""
Arbitrage detection for BetSnipe.ai v2.0

Detects arbitrage opportunities across bookmakers and calculates optimal stakes.
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from .config import settings, BOOKMAKERS, BET_TYPES
from .db import db

logger = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    """Represents a detected arbitrage opportunity."""
    match_id: int
    team1: str
    team2: str
    sport_id: int
    start_time: datetime
    bet_type_id: int
    bet_type_name: str
    margin: float
    profit_percentage: float
    best_odds: List[Dict[str, Any]]  # [{bookmaker_id, bookmaker_name, outcome, odd}]
    stakes: List[float]  # Optimal stakes for 100 unit total
    arb_hash: str
    is_two_way: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            'match_id': self.match_id,
            'team1': self.team1,
            'team2': self.team2,
            'sport_id': self.sport_id,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'bet_type_id': self.bet_type_id,
            'bet_type_name': self.bet_type_name,
            'margin': self.margin,
            'profit_percentage': round(self.profit_percentage, 4),
            'best_odds': self.best_odds,
            'stakes': [round(s, 2) for s in self.stakes],
            'arb_hash': self.arb_hash,
            'is_two_way': self.is_two_way,
        }


class ArbitrageDetector:
    """
    Detects arbitrage opportunities from current odds.

    Supports:
    - Two-way arbitrage (e.g., tennis winner, over/under)
    - Three-way arbitrage (e.g., football 1X2)
    - Selection-based N-way arbitrage (e.g., correct score, HT/FT)
    """

    MAX_PROFIT_PCT = 10.0  # Hard cap — higher values almost always indicate a data/matching error

    # Bet types excluded from arbitrage detection:
    # - Handicap IDs: European vs Asian handicap conventions produce systematic false arbs
    # - LAST_GOAL (89): doesn't cover the 0-0 outcome, so no true arbitrage is possible
    EXCLUDED_BET_TYPE_IDS = {9, 50, 56, 58, 80, 85, 95, 89}

    def __init__(self, min_profit: Optional[float] = None):
        self.min_profit = min_profit or settings.min_profit_percentage

    def calculate_two_way_arbitrage(
        self,
        odds: List[Tuple[int, str, float, float]]  # [(bookmaker_id, bookmaker_name, odd1, odd2)]
    ) -> Optional[Tuple[float, List[Dict], List[float]]]:
        """
        Calculate two-way arbitrage.

        Args:
            odds: List of (bookmaker_id, bookmaker_name, odd1, odd2) tuples

        Returns:
            Tuple of (profit_percentage, best_odds, stakes) or None if no arbitrage
        """
        if len(odds) < 2:
            return None

        # Fix 1.4: filter out rows with odds <= 1.0 (invalid odds)
        valid_odds = [o for o in odds if o[2] and o[3] and o[2] > 1.0 and o[3] > 1.0]
        if len(valid_odds) < 2:
            return None

        # Find best odds for each outcome
        best_odd1 = max(valid_odds, key=lambda x: x[2])
        best_odd2 = max(valid_odds, key=lambda x: x[3])

        # Fix 1.1: require different bookmakers for each leg
        if best_odd1[0] == best_odd2[0]:
            # Find best odd2 from a different bookmaker
            alt_odds = [o for o in valid_odds if o[0] != best_odd1[0]]
            if not alt_odds:
                return None  # only one bookmaker, no real arb
            best_odd2 = max(alt_odds, key=lambda x: x[3])

        # Calculate implied probabilities
        prob1 = 1 / best_odd1[2]
        prob2 = 1 / best_odd2[3]

        total_prob = prob1 + prob2

        # Arbitrage exists if total probability < 1
        if total_prob >= 1:
            return None

        # Calculate profit percentage
        profit_pct = ((1 / total_prob) - 1) * 100

        if profit_pct < self.min_profit or profit_pct > self.MAX_PROFIT_PCT:
            return None

        # Calculate optimal stakes for 100 unit total bet
        total_stake = 100
        stake1 = (prob1 / total_prob) * total_stake
        stake2 = (prob2 / total_prob) * total_stake

        best_odds = [
            {
                'bookmaker_id': best_odd1[0],
                'bookmaker_name': best_odd1[1],
                'outcome': 1,
                'odd': best_odd1[2]
            },
            {
                'bookmaker_id': best_odd2[0],
                'bookmaker_name': best_odd2[1],
                'outcome': 2,
                'odd': best_odd2[3]
            }
        ]

        stakes = [stake1, stake2]

        return profit_pct, best_odds, stakes

    def calculate_three_way_arbitrage(
        self,
        odds: List[Tuple[int, str, float, float, float]]  # [(bookmaker_id, name, odd1, oddX, odd2)]
    ) -> Optional[Tuple[float, List[Dict], List[float]]]:
        """
        Calculate three-way arbitrage (e.g., 1X2 markets).

        Args:
            odds: List of (bookmaker_id, bookmaker_name, odd1, oddX, odd2) tuples

        Returns:
            Tuple of (profit_percentage, best_odds, stakes) or None if no arbitrage
        """
        if len(odds) < 2:
            return None

        # Fix 1.4: filter out rows with any odds <= 1.0 (invalid odds)
        valid_odds = [o for o in odds if o[2] and o[3] and o[4] and o[2] > 1.0 and o[3] > 1.0 and o[4] > 1.0]
        if len(valid_odds) < 2:
            return None

        # Find best odds for each outcome
        best_odd1 = max(valid_odds, key=lambda x: x[2])
        best_oddX = max(valid_odds, key=lambda x: x[3])
        best_odd2 = max(valid_odds, key=lambda x: x[4])

        # Fix 1.2: require at least 2 different bookmakers across 3 legs
        bookmakers_used = {best_odd1[0], best_oddX[0], best_odd2[0]}
        if len(bookmakers_used) < 2:
            return None  # all legs from same bookmaker

        # Calculate implied probabilities
        prob1 = 1 / best_odd1[2]
        probX = 1 / best_oddX[3]
        prob2 = 1 / best_odd2[4]

        total_prob = prob1 + probX + prob2

        # Arbitrage exists if total probability < 1
        if total_prob >= 1:
            return None

        # Calculate profit percentage
        profit_pct = ((1 / total_prob) - 1) * 100

        if profit_pct < self.min_profit or profit_pct > self.MAX_PROFIT_PCT:
            return None

        # Calculate optimal stakes for 100 unit total bet
        total_stake = 100
        stake1 = (prob1 / total_prob) * total_stake
        stakeX = (probX / total_prob) * total_stake
        stake2 = (prob2 / total_prob) * total_stake

        best_odds = [
            {
                'bookmaker_id': best_odd1[0],
                'bookmaker_name': best_odd1[1],
                'outcome': 1,
                'odd': best_odd1[2]
            },
            {
                'bookmaker_id': best_oddX[0],
                'bookmaker_name': best_oddX[1],
                'outcome': 'X',
                'odd': best_oddX[3]
            },
            {
                'bookmaker_id': best_odd2[0],
                'bookmaker_name': best_odd2[1],
                'outcome': 2,
                'odd': best_odd2[4]
            }
        ]

        stakes = [stake1, stakeX, stake2]

        return profit_pct, best_odds, stakes

    def calculate_selection_arbitrage(
        self,
        selections: Dict[str, List[Tuple[int, str, float]]]
    ) -> Optional[Tuple[float, List[Dict], List[float]]]:
        """
        Calculate N-way arbitrage for selection-based markets.

        Each selection (e.g. "1:0", "2/1") is one mutually exclusive outcome.
        For each selection, multiple bookmakers offer odd1. We pick the best
        odd per selection, then check if sum(1/best_odd) < 1.

        Args:
            selections: {selection_key: [(bookmaker_id, bookmaker_name, odd1), ...]}
                        Only selections with 2+ bookmakers should be included.

        Returns:
            Tuple of (profit_percentage, best_odds, stakes) or None if no arbitrage
        """
        if len(selections) < 2:
            return None

        # Find best odd1 per selection
        best_per_selection = {}
        for sel, bookmaker_odds in selections.items():
            best = max(bookmaker_odds, key=lambda x: x[2] if x[2] else 0)
            if not best[2] or best[2] <= 1:
                continue
            best_per_selection[sel] = best

        if len(best_per_selection) < 2:
            return None

        # Fix 1.3: require at least 2 different bookmakers across all selection legs
        bk_ids = set(v[0] for v in best_per_selection.values())
        if len(bk_ids) < 2:
            return None  # all selections from one bookmaker, not real arb

        # Calculate implied probabilities
        total_prob = sum(1.0 / best[2] for best in best_per_selection.values())

        if total_prob >= 1:
            return None

        profit_pct = ((1 / total_prob) - 1) * 100

        if profit_pct < self.min_profit or profit_pct > self.MAX_PROFIT_PCT:
            return None

        # Calculate optimal stakes for 100 unit total bet
        total_stake = 100
        best_odds = []
        stakes = []

        for sel in sorted(best_per_selection.keys()):
            bm_id, bm_name, odd = best_per_selection[sel]
            prob = 1.0 / odd
            stake = (prob / total_prob) * total_stake

            best_odds.append({
                'bookmaker_id': bm_id,
                'bookmaker_name': bm_name,
                'outcome': sel,
                'odd': odd
            })
            stakes.append(stake)

        return profit_pct, best_odds, stakes

    def generate_arb_hash(
        self,
        match_id: int,
        bet_type_id: int,
        margin: float,
        best_odds: List[Dict],
        profit_pct: float,
        selection: str = ''
    ) -> str:
        """Generate unique hash for arbitrage opportunity."""
        # Sort odds for consistent hashing; use str() to handle mixed int/'X' outcomes
        sorted_odds = sorted(best_odds, key=lambda x: str(x.get('outcome', '')))

        hash_data = {
            'match_id': match_id,
            'bet_type_id': bet_type_id,
            'margin': float(margin),
            'selection': selection,
            'odds': [(o['bookmaker_id'], o['outcome'], round(o['odd'], 3)) for o in sorted_odds],
            'profit': round(profit_pct, 2)
        }

        hash_str = json.dumps(hash_data, sort_keys=True)
        return hashlib.md5(hash_str.encode()).hexdigest()

    async def detect_for_match(
        self,
        match_id: int,
        match_data: Dict[str, Any]
    ) -> List[ArbitrageOpportunity]:
        """
        Detect all arbitrage opportunities for a single match.

        Args:
            match_id: The match ID
            match_data: Match data including team names, sport, etc.

        Returns:
            List of ArbitrageOpportunity objects
        """
        opportunities = []

        # Get all current odds for this match
        current_odds = await db.get_current_odds_for_match(match_id)

        if len(current_odds) < 2:
            return opportunities

        # Group odds by bet_type_id, margin, and selection
        odds_groups: Dict[Tuple[int, float, str], List] = {}
        for odd in current_odds:
            key = (odd['bet_type_id'], float(odd.get('margin', 0)), odd.get('selection', ''))
            if key not in odds_groups:
                odds_groups[key] = []
            odds_groups[key].append(odd)

        # Collect selection-based odds for regrouping by (bet_type_id, margin)
        selection_markets: Dict[Tuple[int, float], Dict[str, List[Tuple[int, str, float]]]] = {}

        # Check each group for arbitrage
        for (bet_type_id, margin, selection), group_odds in odds_groups.items():
            if bet_type_id in self.EXCLUDED_BET_TYPE_IDS:
                continue
            if len(group_odds) < 2:
                # For selection markets, single-bookmaker selections are still
                # collected but filtered later by the 2+ bookmaker requirement
                bet_type = BET_TYPES.get(bet_type_id, {})
                if bet_type.get('outcomes', 2) == 1:
                    market_key = (bet_type_id, margin)
                    if market_key not in selection_markets:
                        selection_markets[market_key] = {}
                    if selection not in selection_markets[market_key]:
                        selection_markets[market_key][selection] = []
                    for o in group_odds:
                        if o['odd1']:
                            bm_name = o.get('bookmaker_name', BOOKMAKERS.get(o['bookmaker_id'], {}).get('name', 'Unknown'))
                            selection_markets[market_key][selection].append(
                                (o['bookmaker_id'], bm_name, float(o['odd1']))
                            )
                continue

            bet_type = BET_TYPES.get(bet_type_id, {})

            # Selection-based markets: collect odds for regrouping
            if bet_type.get('outcomes', 2) == 1:
                market_key = (bet_type_id, margin)
                if market_key not in selection_markets:
                    selection_markets[market_key] = {}
                if selection not in selection_markets[market_key]:
                    selection_markets[market_key][selection] = []
                for o in group_odds:
                    if o['odd1']:
                        bm_name = o.get('bookmaker_name', BOOKMAKERS.get(o['bookmaker_id'], {}).get('name', 'Unknown'))
                        selection_markets[market_key][selection].append(
                            (o['bookmaker_id'], bm_name, float(o['odd1']))
                        )
                continue

            is_three_way = bet_type.get('outcomes', 2) == 3

            if is_three_way:
                # Three-way arbitrage
                odds_tuples = [
                    (
                        o['bookmaker_id'],
                        o.get('bookmaker_name', BOOKMAKERS.get(o['bookmaker_id'], {}).get('name', 'Unknown')),
                        o['odd1'],
                        o['odd2'],
                        o['odd3']
                    )
                    for o in group_odds
                    if o['odd1'] and o['odd2'] and o['odd3']
                ]

                result = self.calculate_three_way_arbitrage(odds_tuples)
            else:
                # Two-way arbitrage
                odds_tuples = [
                    (
                        o['bookmaker_id'],
                        o.get('bookmaker_name', BOOKMAKERS.get(o['bookmaker_id'], {}).get('name', 'Unknown')),
                        o['odd1'],
                        o['odd2']
                    )
                    for o in group_odds
                    if o['odd1'] and o['odd2']
                ]

                result = self.calculate_two_way_arbitrage(odds_tuples)

            if result:
                profit_pct, best_odds, stakes = result

                arb_hash = self.generate_arb_hash(
                    match_id, bet_type_id, margin, best_odds, profit_pct
                )

                opportunity = ArbitrageOpportunity(
                    match_id=match_id,
                    team1=match_data.get('team1', ''),
                    team2=match_data.get('team2', ''),
                    sport_id=match_data.get('sport_id', 0),
                    start_time=match_data.get('start_time'),
                    bet_type_id=bet_type_id,
                    bet_type_name=bet_type.get('name', 'Unknown'),
                    margin=margin,
                    profit_percentage=profit_pct,
                    best_odds=best_odds,
                    stakes=stakes,
                    arb_hash=arb_hash,
                    is_two_way=not is_three_way
                )

                opportunities.append(opportunity)

        # Process selection-based markets (outcomes=1)
        # Each (bet_type_id, margin) group has multiple selections forming
        # a mutually exclusive set of outcomes
        for (bet_type_id, margin), sel_odds in selection_markets.items():
            if bet_type_id in self.EXCLUDED_BET_TYPE_IDS:
                continue
            # Only include selections offered by 2+ bookmakers
            filtered = {
                sel: odds_list
                for sel, odds_list in sel_odds.items()
                if len(set(o[0] for o in odds_list)) >= 2
            }

            if len(filtered) < 2:
                continue

            result = self.calculate_selection_arbitrage(filtered)

            if result:
                profit_pct, best_odds, stakes = result
                bet_type = BET_TYPES.get(bet_type_id, {})

                arb_hash = self.generate_arb_hash(
                    match_id, bet_type_id, margin, best_odds, profit_pct
                )

                opportunity = ArbitrageOpportunity(
                    match_id=match_id,
                    team1=match_data.get('team1', ''),
                    team2=match_data.get('team2', ''),
                    sport_id=match_data.get('sport_id', 0),
                    start_time=match_data.get('start_time'),
                    bet_type_id=bet_type_id,
                    bet_type_name=bet_type.get('name', 'Unknown'),
                    margin=margin,
                    profit_percentage=profit_pct,
                    best_odds=best_odds,
                    stakes=stakes,
                    arb_hash=arb_hash,
                    is_two_way=False
                )

                opportunities.append(opportunity)

        return opportunities

    async def detect_all(self) -> List[ArbitrageOpportunity]:
        """
        Detect arbitrage opportunities across all upcoming matches.

        Returns:
            List of new ArbitrageOpportunity objects (not previously detected)
        """
        opportunities = []

        # Get all upcoming matches
        matches = await db.get_upcoming_matches(hours_ahead=48, limit=5000)

        logger.info(f"Checking {len(matches)} matches for arbitrage")

        # Fix 1.6: run detect_for_match concurrently with a semaphore to cap parallelism
        semaphore = asyncio.Semaphore(50)

        async def bounded_detect(match):
            async with semaphore:
                try:
                    return await self.detect_for_match(match['id'], match)
                except Exception as e:
                    logger.warning(f"Error detecting arb for match {match.get('id')}: {e}")
                    return []

        all_results = await asyncio.gather(*[bounded_detect(m) for m in matches])
        match_opportunities_list = [opp for result in all_results if result for opp in result]

        for opp in match_opportunities_list:
            # Check if already detected
            if not await db.check_arbitrage_exists(opp.arb_hash):
                # Store new opportunity
                arb_id = await db.insert_arbitrage(
                    match_id=opp.match_id,
                    bet_type_id=opp.bet_type_id,
                    margin=opp.margin,
                    profit_percentage=opp.profit_percentage,
                    best_odds=opp.best_odds,
                    stakes=opp.stakes,
                    arb_hash=opp.arb_hash,
                    expires_at=opp.start_time
                )

                if arb_id:
                    opportunities.append(opp)
                    logger.info(
                        f"New arbitrage: {opp.team1} vs {opp.team2} "
                        f"({opp.bet_type_name}) - {opp.profit_percentage:.2f}%"
                    )

        return opportunities


# Global detector instance
detector = ArbitrageDetector()


def format_arbitrage_message(opp: ArbitrageOpportunity) -> str:
    """Format arbitrage opportunity for Telegram notification."""
    lines = [
        f"🎯 *ARBITRAGE ALERT* 🎯",
        f"",
        f"*{opp.team1}* vs *{opp.team2}*",
        f"📅 {opp.start_time.strftime('%Y-%m-%d %H:%M') if opp.start_time else 'TBD'}",
        f"",
        f"📊 *Bet Type:* {opp.bet_type_name}",
        f"💰 *Profit:* {opp.profit_percentage:.2f}%",
        f"",
        f"*Best Odds:*",
    ]

    for i, odd in enumerate(opp.best_odds):
        outcome = odd['outcome']
        if outcome == 1:
            outcome_label = opp.team1
        elif outcome == 2:
            outcome_label = opp.team2
        elif outcome == 'X':
            outcome_label = 'Draw'
        else:
            outcome_label = str(outcome)

        lines.append(
            f"• {outcome_label}: *{odd['odd']:.2f}* @ {odd['bookmaker_name']}"
        )

    lines.extend([
        f"",
        f"*Optimal Stakes (100 units):*",
    ])

    for i, (stake, odd) in enumerate(zip(opp.stakes, opp.best_odds)):
        outcome = odd['outcome']
        if outcome == 1:
            outcome_label = opp.team1
        elif outcome == 2:
            outcome_label = opp.team2
        elif outcome == 'X':
            outcome_label = 'Draw'
        else:
            outcome_label = str(outcome)

        lines.append(f"• {outcome_label}: {stake:.2f} units")

    return '\n'.join(lines)
