"""
Arbitrage API routes for BetSnipe.ai v2.0

Endpoints for arbitrage opportunities.
"""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.db import db
from core.config import SPORTS, BOOKMAKERS

logger = logging.getLogger(__name__)

router = APIRouter()


# ==========================================
# RESPONSE MODELS
# ==========================================

class BestOdd(BaseModel):
    """Best odd for an outcome."""
    bookmaker_id: int
    bookmaker_name: str
    outcome: str
    odd: float


class ArbitrageResponse(BaseModel):
    """Arbitrage opportunity response."""
    id: int
    match_id: int
    team1: str
    team2: str
    sport_name: str
    start_time: datetime
    bet_type_name: str
    margin: float
    profit_percentage: float
    best_odds: List[BestOdd]
    stakes: List[float]
    detected_at: datetime
    is_active: bool


class ArbitrageListResponse(BaseModel):
    """List of arbitrage opportunities."""
    opportunities: List[ArbitrageResponse]
    total: int


class ArbitrageStats(BaseModel):
    """Arbitrage statistics."""
    active_count: int
    total_today: int
    avg_profit: float
    max_profit: float
    by_sport: dict


# ==========================================
# ENDPOINTS
# ==========================================

@router.get("/arbitrage", response_model=ArbitrageListResponse)
async def get_arbitrage_opportunities(
    sport_id: Optional[int] = Query(None, description="Filter by sport ID"),
    min_profit: Optional[float] = Query(None, ge=0, description="Minimum profit percentage"),
    active_only: bool = Query(True, description="Only show active opportunities"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
):
    """
    Get current arbitrage opportunities.

    Returns opportunities sorted by profit percentage (highest first).
    """
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected")

    opportunities = await db.get_active_arbitrage(
        min_profit=min_profit,
        sport_id=sport_id,
        limit=limit
    )

    results = []
    for opp in opportunities:
        best_odds = opp.get('best_odds', [])
        if isinstance(best_odds, str):
            import json
            best_odds = json.loads(best_odds)

        stakes = opp.get('stakes', [])
        if isinstance(stakes, str):
            import json
            stakes = json.loads(stakes)

        best_odds_list = [
            BestOdd(
                bookmaker_id=o.get('bookmaker_id', 0),
                bookmaker_name=o.get('bookmaker_name', ''),
                outcome=str(o.get('outcome', '')),
                odd=float(o.get('odd', 0))
            )
            for o in best_odds
        ]

        results.append(ArbitrageResponse(
            id=opp['id'],
            match_id=opp['match_id'],
            team1=opp.get('team1', ''),
            team2=opp.get('team2', ''),
            sport_name=opp.get('sport_name', ''),
            start_time=opp.get('start_time', datetime.utcnow()),
            bet_type_name=opp.get('bet_type_name', ''),
            margin=float(opp.get('margin', 0)),
            profit_percentage=float(opp['profit_percentage']),
            best_odds=best_odds_list,
            stakes=[float(s) for s in stakes],
            detected_at=opp['detected_at'],
            is_active=opp.get('is_active', True)
        ))

    return ArbitrageListResponse(
        opportunities=results,
        total=len(results)
    )


@router.get("/arbitrage/{arb_id}", response_model=ArbitrageResponse)
async def get_arbitrage_opportunity(arb_id: int):
    """Get a specific arbitrage opportunity by ID."""
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected")

    # Fetch single arbitrage opportunity
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ao.*, m.team1, m.team2, m.start_time,
                   s.name as sport_name, bt.name as bet_type_name
            FROM arbitrage_opportunities ao
            JOIN matches m ON ao.match_id = m.id
            JOIN sports s ON m.sport_id = s.id
            JOIN bet_types bt ON ao.bet_type_id = bt.id
            WHERE ao.id = $1
            """,
            arb_id
        )

    if not row:
        raise HTTPException(status_code=404, detail="Arbitrage opportunity not found")

    opp = dict(row)

    best_odds = opp.get('best_odds', [])
    if isinstance(best_odds, str):
        import json
        best_odds = json.loads(best_odds)

    stakes = opp.get('stakes', [])
    if isinstance(stakes, str):
        import json
        stakes = json.loads(stakes)

    best_odds_list = [
        BestOdd(
            bookmaker_id=o.get('bookmaker_id', 0),
            bookmaker_name=o.get('bookmaker_name', ''),
            outcome=str(o.get('outcome', '')),
            odd=float(o.get('odd', 0))
        )
        for o in best_odds
    ]

    return ArbitrageResponse(
        id=opp['id'],
        match_id=opp['match_id'],
        team1=opp.get('team1', ''),
        team2=opp.get('team2', ''),
        sport_name=opp.get('sport_name', ''),
        start_time=opp.get('start_time', datetime.utcnow()),
        bet_type_name=opp.get('bet_type_name', ''),
        margin=float(opp.get('margin', 0)),
        profit_percentage=float(opp['profit_percentage']),
        best_odds=best_odds_list,
        stakes=[float(s) for s in stakes],
        detected_at=opp['detected_at'],
        is_active=opp.get('is_active', True)
    )


@router.get("/arbitrage/stats", response_model=ArbitrageStats)
async def get_arbitrage_stats():
    """Get arbitrage statistics."""
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected")

    async with db.acquire() as conn:
        # Active count
        active_count = await conn.fetchval(
            "SELECT COUNT(*) FROM arbitrage_opportunities WHERE is_active = true"
        )

        # Today's total
        total_today = await conn.fetchval(
            """
            SELECT COUNT(*) FROM arbitrage_opportunities
            WHERE detected_at >= CURRENT_DATE
            """
        )

        # Average and max profit
        stats = await conn.fetchrow(
            """
            SELECT
                COALESCE(AVG(profit_percentage), 0) as avg_profit,
                COALESCE(MAX(profit_percentage), 0) as max_profit
            FROM arbitrage_opportunities
            WHERE is_active = true
            """
        )

        # By sport
        by_sport_rows = await conn.fetch(
            """
            SELECT s.name as sport_name, COUNT(*) as count
            FROM arbitrage_opportunities ao
            JOIN matches m ON ao.match_id = m.id
            JOIN sports s ON m.sport_id = s.id
            WHERE ao.is_active = true
            GROUP BY s.name
            ORDER BY count DESC
            """
        )

        by_sport = {row['sport_name']: row['count'] for row in by_sport_rows}

    return ArbitrageStats(
        active_count=active_count or 0,
        total_today=total_today or 0,
        avg_profit=float(stats['avg_profit']) if stats else 0,
        max_profit=float(stats['max_profit']) if stats else 0,
        by_sport=by_sport
    )


@router.get("/arbitrage/history")
async def get_arbitrage_history(
    sport_id: Optional[int] = Query(None, description="Filter by sport ID"),
    days: int = Query(7, ge=1, le=30, description="Days of history"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
):
    """
    Get historical arbitrage opportunities.

    Returns past opportunities including expired ones.
    """
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected")

    async with db.acquire() as conn:
        query = """
            SELECT ao.*, m.team1, m.team2, m.start_time,
                   s.name as sport_name, bt.name as bet_type_name
            FROM arbitrage_opportunities ao
            JOIN matches m ON ao.match_id = m.id
            JOIN sports s ON m.sport_id = s.id
            JOIN bet_types bt ON ao.bet_type_id = bt.id
            WHERE ao.detected_at >= NOW() - ($1 || ' days')::INTERVAL
        """
        params = [days]

        if sport_id:
            query += " AND m.sport_id = $2"
            params.append(sport_id)

        query += " ORDER BY ao.detected_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)

        rows = await conn.fetch(query, *params)

    results = []
    for opp in rows:
        opp = dict(opp)

        best_odds = opp.get('best_odds', [])
        if isinstance(best_odds, str):
            import json
            best_odds = json.loads(best_odds)

        stakes = opp.get('stakes', [])
        if isinstance(stakes, str):
            import json
            stakes = json.loads(stakes)

        results.append({
            'id': opp['id'],
            'match_id': opp['match_id'],
            'team1': opp.get('team1', ''),
            'team2': opp.get('team2', ''),
            'sport_name': opp.get('sport_name', ''),
            'start_time': opp.get('start_time').isoformat() if opp.get('start_time') else None,
            'bet_type_name': opp.get('bet_type_name', ''),
            'margin': float(opp.get('margin', 0)),
            'profit_percentage': float(opp['profit_percentage']),
            'best_odds': best_odds,
            'stakes': stakes,
            'detected_at': opp['detected_at'].isoformat() if opp.get('detected_at') else None,
            'is_active': opp.get('is_active', False)
        })

    return {
        'history': results,
        'total': len(results),
        'days': days
    }


@router.post("/arbitrage/calculate")
async def calculate_arbitrage(
    odds: List[dict] = None,
):
    """
    Calculate arbitrage from provided odds.

    Useful for testing or custom calculations.

    Request body:
    {
        "odds": [
            {"bookmaker": "Admiral", "odd1": 2.10, "odd2": 3.50, "odd3": 3.20},
            {"bookmaker": "Soccerbet", "odd1": 2.05, "odd2": 3.60, "odd3": 3.15}
        ]
    }
    """
    if not odds or len(odds) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 bookmaker odds required"
        )

    # Determine if 2-way or 3-way
    has_odd3 = any(o.get('odd3') for o in odds)

    if has_odd3:
        # Three-way arbitrage
        best_odd1 = max(odds, key=lambda x: x.get('odd1', 0))
        best_oddX = max(odds, key=lambda x: x.get('odd2', 0))
        best_odd2 = max(odds, key=lambda x: x.get('odd3', 0))

        prob1 = 1 / best_odd1['odd1']
        probX = 1 / best_oddX['odd2']
        prob2 = 1 / best_odd2['odd3']

        total_prob = prob1 + probX + prob2

        if total_prob >= 1:
            return {
                'is_arbitrage': False,
                'total_probability': round(total_prob * 100, 2),
                'margin': round((total_prob - 1) * 100, 2)
            }

        profit_pct = ((1 / total_prob) - 1) * 100

        stake1 = (prob1 / total_prob) * 100
        stakeX = (probX / total_prob) * 100
        stake2 = (prob2 / total_prob) * 100

        return {
            'is_arbitrage': True,
            'profit_percentage': round(profit_pct, 4),
            'total_probability': round(total_prob * 100, 2),
            'best_odds': {
                '1': {'value': best_odd1['odd1'], 'bookmaker': best_odd1.get('bookmaker', '')},
                'X': {'value': best_oddX['odd2'], 'bookmaker': best_oddX.get('bookmaker', '')},
                '2': {'value': best_odd2['odd3'], 'bookmaker': best_odd2.get('bookmaker', '')}
            },
            'stakes': {
                '1': round(stake1, 2),
                'X': round(stakeX, 2),
                '2': round(stake2, 2)
            }
        }

    else:
        # Two-way arbitrage
        best_odd1 = max(odds, key=lambda x: x.get('odd1', 0))
        best_odd2 = max(odds, key=lambda x: x.get('odd2', 0))

        prob1 = 1 / best_odd1['odd1']
        prob2 = 1 / best_odd2['odd2']

        total_prob = prob1 + prob2

        if total_prob >= 1:
            return {
                'is_arbitrage': False,
                'total_probability': round(total_prob * 100, 2),
                'margin': round((total_prob - 1) * 100, 2)
            }

        profit_pct = ((1 / total_prob) - 1) * 100

        stake1 = (prob1 / total_prob) * 100
        stake2 = (prob2 / total_prob) * 100

        return {
            'is_arbitrage': True,
            'profit_percentage': round(profit_pct, 4),
            'total_probability': round(total_prob * 100, 2),
            'best_odds': {
                '1': {'value': best_odd1['odd1'], 'bookmaker': best_odd1.get('bookmaker', '')},
                '2': {'value': best_odd2['odd2'], 'bookmaker': best_odd2.get('bookmaker', '')}
            },
            'stakes': {
                '1': round(stake1, 2),
                '2': round(stake2, 2)
            }
        }
