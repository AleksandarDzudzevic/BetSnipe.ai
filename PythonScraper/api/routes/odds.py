"""
Odds API routes for BetSnipe.ai v2.0

Endpoints for matches and odds data.
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

class OddsResponse(BaseModel):
    """Single odds entry."""
    bookmaker_id: int
    bookmaker_name: str
    bet_type_id: int
    bet_type_name: str
    margin: float
    odd1: Optional[float]
    odd2: Optional[float]
    odd3: Optional[float]
    updated_at: datetime


class MatchResponse(BaseModel):
    """Match with current odds."""
    id: int
    team1: str
    team2: str
    sport_id: int
    sport_name: str
    start_time: datetime
    status: str
    odds: List[OddsResponse] = []


class MatchListResponse(BaseModel):
    """List of matches."""
    matches: List[MatchResponse]
    total: int
    page: int
    page_size: int


class OddsHistoryEntry(BaseModel):
    """Single odds history entry."""
    bookmaker_id: int
    bookmaker_name: str
    bet_type_id: int
    bet_type_name: str
    margin: float
    odd1: Optional[float]
    odd2: Optional[float]
    odd3: Optional[float]
    recorded_at: datetime


class OddsHistoryResponse(BaseModel):
    """Odds history for a match."""
    match_id: int
    team1: str
    team2: str
    history: List[OddsHistoryEntry]


class SportResponse(BaseModel):
    """Sport information."""
    id: int
    name: str
    name_sr: str


class BookmakerResponse(BaseModel):
    """Bookmaker information."""
    id: int
    name: str
    display_name: str
    enabled: bool


# ==========================================
# ENDPOINTS
# ==========================================

@router.get("/sports", response_model=List[SportResponse])
async def get_sports():
    """Get list of available sports."""
    return [
        SportResponse(
            id=sport_id,
            name=config['name'],
            name_sr=config['name_sr']
        )
        for sport_id, config in SPORTS.items()
    ]


@router.get("/bookmakers", response_model=List[BookmakerResponse])
async def get_bookmakers():
    """Get list of available bookmakers."""
    return [
        BookmakerResponse(
            id=book_id,
            name=config['name'],
            display_name=config['display'],
            enabled=config['enabled']
        )
        for book_id, config in BOOKMAKERS.items()
    ]


@router.get("/matches", response_model=MatchListResponse)
async def get_matches(
    sport_id: Optional[int] = Query(None, description="Filter by sport ID"),
    hours_ahead: int = Query(24, ge=1, le=168, description="Hours ahead to fetch"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
):
    """
    Get upcoming matches with current odds.

    Returns matches starting within the specified time window.
    """
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected")

    # Calculate offset
    offset = (page - 1) * page_size

    # Get matches
    matches = await db.get_upcoming_matches(
        sport_id=sport_id,
        hours_ahead=hours_ahead,
        limit=page_size + 1  # Fetch one extra to check if there are more
    )

    # Check if there are more results
    has_more = len(matches) > page_size
    matches = matches[:page_size]

    # Fetch odds for each match
    results = []
    for match in matches:
        odds_data = await db.get_current_odds_for_match(match['id'])

        odds_list = [
            OddsResponse(
                bookmaker_id=o['bookmaker_id'],
                bookmaker_name=o.get('bookmaker_name', ''),
                bet_type_id=o['bet_type_id'],
                bet_type_name=o.get('bet_type_name', ''),
                margin=float(o.get('margin', 0)),
                odd1=float(o['odd1']) if o['odd1'] else None,
                odd2=float(o['odd2']) if o['odd2'] else None,
                odd3=float(o['odd3']) if o['odd3'] else None,
                updated_at=o['updated_at']
            )
            for o in odds_data
        ]

        sport_config = SPORTS.get(match['sport_id'], {})

        results.append(MatchResponse(
            id=match['id'],
            team1=match['team1'],
            team2=match['team2'],
            sport_id=match['sport_id'],
            sport_name=sport_config.get('name', 'Unknown'),
            start_time=match['start_time'],
            status=match.get('status', 'upcoming'),
            odds=odds_list
        ))

    return MatchListResponse(
        matches=results,
        total=len(results),
        page=page,
        page_size=page_size
    )


@router.get("/matches/{match_id}", response_model=MatchResponse)
async def get_match(match_id: int):
    """Get a specific match with current odds."""
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected")

    match = await db.get_match_by_id(match_id)

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    odds_data = await db.get_current_odds_for_match(match_id)

    odds_list = [
        OddsResponse(
            bookmaker_id=o['bookmaker_id'],
            bookmaker_name=o.get('bookmaker_name', ''),
            bet_type_id=o['bet_type_id'],
            bet_type_name=o.get('bet_type_name', ''),
            margin=float(o.get('margin', 0)),
            odd1=float(o['odd1']) if o['odd1'] else None,
            odd2=float(o['odd2']) if o['odd2'] else None,
            odd3=float(o['odd3']) if o['odd3'] else None,
            updated_at=o['updated_at']
        )
        for o in odds_data
    ]

    sport_config = SPORTS.get(match['sport_id'], {})

    return MatchResponse(
        id=match['id'],
        team1=match['team1'],
        team2=match['team2'],
        sport_id=match['sport_id'],
        sport_name=sport_config.get('name', 'Unknown'),
        start_time=match['start_time'],
        status=match.get('status', 'upcoming'),
        odds=odds_list
    )


@router.get("/matches/{match_id}/odds-history", response_model=OddsHistoryResponse)
async def get_match_odds_history(
    match_id: int,
    bookmaker_id: Optional[int] = Query(None, description="Filter by bookmaker"),
    bet_type_id: Optional[int] = Query(None, description="Filter by bet type"),
    hours: int = Query(24, ge=1, le=168, description="Hours of history to fetch"),
):
    """
    Get historical odds for a match.

    Useful for tracking odds movements over time.
    """
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected")

    match = await db.get_match_by_id(match_id)

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    history = await db.get_odds_history(
        match_id=match_id,
        bookmaker_id=bookmaker_id,
        bet_type_id=bet_type_id,
        hours=hours
    )

    history_list = [
        OddsHistoryEntry(
            bookmaker_id=h['bookmaker_id'],
            bookmaker_name=h.get('bookmaker_name', ''),
            bet_type_id=h['bet_type_id'],
            bet_type_name=h.get('bet_type_name', ''),
            margin=float(h.get('margin', 0)),
            odd1=float(h['odd1']) if h['odd1'] else None,
            odd2=float(h['odd2']) if h['odd2'] else None,
            odd3=float(h['odd3']) if h['odd3'] else None,
            recorded_at=h['recorded_at']
        )
        for h in history
    ]

    return OddsHistoryResponse(
        match_id=match_id,
        team1=match['team1'],
        team2=match['team2'],
        history=history_list
    )


@router.get("/odds/best")
async def get_best_odds(
    sport_id: Optional[int] = Query(None, description="Filter by sport ID"),
    bet_type_id: Optional[int] = Query(None, description="Filter by bet type"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
):
    """
    Get matches with the best odds comparison.

    Returns matches where there's significant odds variation between bookmakers.
    """
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected")

    # Get upcoming matches
    matches = await db.get_upcoming_matches(
        sport_id=sport_id,
        hours_ahead=24,
        limit=100
    )

    results = []

    for match in matches:
        odds_data = await db.get_current_odds_for_match(match['id'])

        if len(odds_data) < 2:
            continue

        # Group by bet type
        by_bet_type = {}
        for o in odds_data:
            key = (o['bet_type_id'], o.get('margin', 0))
            if key not in by_bet_type:
                by_bet_type[key] = []
            by_bet_type[key].append(o)

        # Find best odds for each bet type
        for (bt_id, margin), group in by_bet_type.items():
            if bet_type_id and bt_id != bet_type_id:
                continue

            if len(group) < 2:
                continue

            best_odd1 = max(group, key=lambda x: x['odd1'] or 0)
            best_odd2 = max(group, key=lambda x: x['odd2'] or 0)

            # Calculate max difference percentage
            all_odd1 = [o['odd1'] for o in group if o['odd1']]
            all_odd2 = [o['odd2'] for o in group if o['odd2']]

            if all_odd1 and all_odd2:
                diff1 = (max(all_odd1) - min(all_odd1)) / min(all_odd1) * 100
                diff2 = (max(all_odd2) - min(all_odd2)) / min(all_odd2) * 100
                max_diff = max(diff1, diff2)

                if max_diff >= 3:  # At least 3% difference
                    results.append({
                        'match_id': match['id'],
                        'team1': match['team1'],
                        'team2': match['team2'],
                        'start_time': match['start_time'].isoformat(),
                        'bet_type_id': bt_id,
                        'margin': margin,
                        'max_difference_pct': round(max_diff, 2),
                        'best_odds': {
                            'odd1': {
                                'value': best_odd1['odd1'],
                                'bookmaker': best_odd1.get('bookmaker_name', '')
                            },
                            'odd2': {
                                'value': best_odd2['odd2'],
                                'bookmaker': best_odd2.get('bookmaker_name', '')
                            }
                        }
                    })

    # Sort by difference and limit
    results.sort(key=lambda x: x['max_difference_pct'], reverse=True)

    return {'best_odds': results[:limit]}
