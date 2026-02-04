"""
User routes for BetSnipe.ai v3.0

Endpoints for user preferences, watchlist, and history.
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.db import db
from api.middleware import get_current_user, AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])


# ============================================
# Request/Response Models
# ============================================

class NotificationSettings(BaseModel):
    """Notification preference settings."""
    arbitrage_alerts: bool = True
    watchlist_odds_change: bool = True
    match_start_reminder: bool = False
    daily_summary: bool = False
    quiet_hours_start: Optional[str] = None  # HH:MM format
    quiet_hours_end: Optional[str] = None


class DisplaySettings(BaseModel):
    """Display preference settings."""
    default_sport: int = 1
    odds_format: str = "decimal"  # decimal, american, fractional
    theme: str = "system"  # light, dark, system


class UserPreferences(BaseModel):
    """User preferences model."""
    min_profit_percentage: float = Field(1.0, ge=0.1, le=20.0)
    sports: List[int] = Field(default=[1, 2, 3, 4, 5])
    bookmakers: List[int] = Field(default=[1, 2, 3, 4, 5, 6, 7, 10])
    notification_settings: NotificationSettings = NotificationSettings()
    display_settings: DisplaySettings = DisplaySettings()


class UserPreferencesResponse(UserPreferences):
    """User preferences response with metadata."""
    created_at: datetime
    updated_at: datetime


class WatchlistItem(BaseModel):
    """Watchlist item model."""
    match_id: int
    notify_on_odds_change: bool = True
    odds_change_threshold: float = Field(0.05, ge=0.01, le=1.0)
    notes: Optional[str] = None


class WatchlistItemResponse(BaseModel):
    """Watchlist item response with match details."""
    id: int
    match_id: int
    notify_on_odds_change: bool
    odds_change_threshold: float
    notes: Optional[str]
    created_at: datetime
    # Match details
    team1: str
    team2: str
    start_time: datetime
    match_status: str
    sport_name: str
    sport_id: int
    league_name: Optional[str]


class ArbitrageHistoryItem(BaseModel):
    """User's arbitrage interaction history."""
    id: int
    arbitrage_id: Optional[int]
    match_id: Optional[int]
    action: str
    profit_percentage: Optional[float]
    best_odds: Optional[dict]
    notes: Optional[str]
    created_at: datetime
    # Match details (if available)
    team1: Optional[str] = None
    team2: Optional[str] = None
    sport_name: Optional[str] = None


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True


# ============================================
# Preferences Endpoints
# ============================================

@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_preferences(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Get the current user's preferences.

    Creates default preferences if none exist.
    """
    prefs = await db.get_user_preferences(user.id)

    if not prefs:
        await db.create_user_preferences(user.id)
        prefs = await db.get_user_preferences(user.id)

    return UserPreferencesResponse(
        min_profit_percentage=prefs["min_profit_percentage"],
        sports=prefs["sports"],
        bookmakers=prefs["bookmakers"],
        notification_settings=NotificationSettings(**prefs["notification_settings"]),
        display_settings=DisplaySettings(**prefs["display_settings"]),
        created_at=prefs["created_at"],
        updated_at=prefs["updated_at"]
    )


@router.put("/preferences", response_model=UserPreferencesResponse)
async def update_preferences(
    preferences: UserPreferences,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Update the current user's preferences.

    All fields are optional - only provided fields are updated.
    """
    updated = await db.update_user_preferences(
        user_id=user.id,
        min_profit_percentage=preferences.min_profit_percentage,
        sports=preferences.sports,
        bookmakers=preferences.bookmakers,
        notification_settings=preferences.notification_settings.model_dump(),
        display_settings=preferences.display_settings.model_dump()
    )

    if not updated:
        # Try creating first
        await db.create_user_preferences(user.id)
        updated = await db.update_user_preferences(
            user_id=user.id,
            min_profit_percentage=preferences.min_profit_percentage,
            sports=preferences.sports,
            bookmakers=preferences.bookmakers,
            notification_settings=preferences.notification_settings.model_dump(),
            display_settings=preferences.display_settings.model_dump()
        )

    if not updated:
        raise HTTPException(
            status_code=500,
            detail="Failed to update preferences"
        )

    return UserPreferencesResponse(
        min_profit_percentage=updated["min_profit_percentage"],
        sports=updated["sports"],
        bookmakers=updated["bookmakers"],
        notification_settings=NotificationSettings(**updated["notification_settings"]),
        display_settings=DisplaySettings(**updated["display_settings"]),
        created_at=updated["created_at"],
        updated_at=updated["updated_at"]
    )


# ============================================
# Watchlist Endpoints
# ============================================

@router.get("/watchlist", response_model=List[WatchlistItemResponse])
async def get_watchlist(
    sport_id: Optional[int] = Query(None, description="Filter by sport ID"),
    status: Optional[str] = Query(None, pattern="^(upcoming|live|finished)$"),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Get the current user's watchlist.

    Returns matches with their current status and details.
    """
    items = await db.get_user_watchlist(user.id, sport_id=sport_id, status=status)
    return [WatchlistItemResponse(**item) for item in items]


@router.post("/watchlist", response_model=WatchlistItemResponse)
async def add_to_watchlist(
    item: WatchlistItem,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Add a match to the user's watchlist.
    """
    # Check if match exists
    match = await db.get_match(item.match_id)
    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found"
        )

    result = await db.add_to_watchlist(
        user_id=user.id,
        match_id=item.match_id,
        notify_on_odds_change=item.notify_on_odds_change,
        odds_change_threshold=item.odds_change_threshold,
        notes=item.notes
    )

    if not result:
        raise HTTPException(
            status_code=409,
            detail="Match already in watchlist"
        )

    return WatchlistItemResponse(**result)


@router.delete("/watchlist/{match_id}", response_model=MessageResponse)
async def remove_from_watchlist(
    match_id: int,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Remove a match from the user's watchlist.
    """
    success = await db.remove_from_watchlist(user.id, match_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Match not in watchlist"
        )

    return MessageResponse(message="Match removed from watchlist")


@router.put("/watchlist/{match_id}", response_model=WatchlistItemResponse)
async def update_watchlist_item(
    match_id: int,
    item: WatchlistItem,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Update watchlist item settings (notifications, threshold, notes).
    """
    result = await db.update_watchlist_item(
        user_id=user.id,
        match_id=match_id,
        notify_on_odds_change=item.notify_on_odds_change,
        odds_change_threshold=item.odds_change_threshold,
        notes=item.notes
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Match not in watchlist"
        )

    return WatchlistItemResponse(**result)


# ============================================
# Arbitrage History Endpoints
# ============================================

@router.get("/arbitrage-history", response_model=List[ArbitrageHistoryItem])
async def get_arbitrage_history(
    action: Optional[str] = Query(
        None,
        pattern="^(viewed|saved|executed|dismissed)$",
        description="Filter by action type"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Get the user's arbitrage interaction history.

    Shows opportunities the user has viewed, saved, or marked as executed.
    """
    items = await db.get_user_arbitrage_history(
        user_id=user.id,
        action=action,
        limit=limit,
        offset=offset
    )
    return [ArbitrageHistoryItem(**item) for item in items]


@router.post("/arbitrage-history", response_model=ArbitrageHistoryItem)
async def record_arbitrage_action(
    arbitrage_id: int,
    action: str = Query(..., pattern="^(viewed|saved|executed|dismissed)$"),
    notes: Optional[str] = None,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Record a user's interaction with an arbitrage opportunity.
    """
    # Get arbitrage details for snapshot
    arb = await db.get_arbitrage(arbitrage_id)
    if not arb:
        raise HTTPException(
            status_code=404,
            detail="Arbitrage opportunity not found"
        )

    result = await db.record_arbitrage_action(
        user_id=user.id,
        arbitrage_id=arbitrage_id,
        match_id=arb["match_id"],
        action=action,
        profit_percentage=arb["profit_percentage"],
        best_odds=arb["best_odds"],
        notes=notes
    )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Failed to record action"
        )

    return ArbitrageHistoryItem(**result)


@router.get("/arbitrage-history/stats")
async def get_arbitrage_history_stats(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Get statistics about user's arbitrage interactions.
    """
    stats = await db.get_user_arbitrage_stats(user.id)
    return stats
