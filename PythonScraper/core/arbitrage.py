"""
Arbitrage detection for BetSnipe.ai v2.0

Detects arbitrage opportunities across bookmakers and calculates optimal stakes.
"""

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
    """

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

        # Find best odds for each outcome
        best_odd1 = max(odds, key=lambda x: x[2] if x[2] else 0)
        best_odd2 = max(odds, key=lambda x: x[3] if x[3] else 0)

        if not best_odd1[2] or not best_odd2[2]:
            return None

        # Calculate implied probabilities
        prob1 = 1 / best_odd1[2]
        prob2 = 1 / best_odd2[2]

        total_prob = prob1 + prob2

        # Arbitrage exists if total probability < 1
        if total_prob >= 1:
            return None

        # Calculate profit percentage
        profit_pct = ((1 / total_prob) - 1) * 100

        if profit_pct < self.min_profit:
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
                'odd': best_odd2[2]
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

        # Find best odds for each outcome
        best_odd1 = max(odds, key=lambda x: x[2] if x[2] else 0)
        best_oddX = max(odds, key=lambda x: x[3] if x[3] else 0)
        best_odd2 = max(odds, key=lambda x: x[4] if x[4] else 0)

        if not best_odd1[2] or not best_oddX[3] or not best_odd2[4]:
            return None

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

        if profit_pct < self.min_profit:
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

    def generate_arb_hash(
        self,
        match_id: int,
        bet_type_id: int,
        margin: float,
        best_odds: List[Dict],
        profit_pct: float
    ) -> str:
        """Generate unique hash for arbitrage opportunity."""
        # Sort odds for consistent hashing
        sorted_odds = sorted(best_odds, key=lambda x: x['outcome'])

        hash_data = {
            'match_id': match_id,
            'bet_type_id': bet_type_id,
            'margin': float(margin),
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

        # Group odds by bet_type_id and margin
        odds_groups: Dict[Tuple[int, float], List] = {}
        for odd in current_odds:
            key = (odd['bet_type_id'], float(odd.get('margin', 0)))
            if key not in odds_groups:
                odds_groups[key] = []
            odds_groups[key].append(odd)

        # Check each group for arbitrage
        for (bet_type_id, margin), group_odds in odds_groups.items():
            if len(group_odds) < 2:
                continue

            bet_type = BET_TYPES.get(bet_type_id, {})
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

        return opportunities

    async def detect_all(self) -> List[ArbitrageOpportunity]:
        """
        Detect arbitrage opportunities across all upcoming matches.

        Returns:
            List of new ArbitrageOpportunity objects (not previously detected)
        """
        opportunities = []

        # Get all upcoming matches
        matches = await db.get_upcoming_matches(hours_ahead=24, limit=500)

        logger.info(f"Checking {len(matches)} matches for arbitrage")

        for match in matches:
            match_opportunities = await self.detect_for_match(
                match['id'], match
            )

            for opp in match_opportunities:
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
