"""
Authentication routes for BetSnipe.ai v3.0

Endpoints for user authentication and device registration.
Note: Actual login/signup is handled by Supabase Auth on the client side.
These endpoints are for authenticated user operations.
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from api.middleware import get_current_user, AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ============================================
# Request/Response Models
# ============================================

class DeviceRegistration(BaseModel):
    """Request model for registering a push notification device."""
    expo_push_token: str = Field(..., description="Expo push notification token")
    platform: str = Field(..., pattern="^(ios|android)$", description="Device platform")
    device_id: Optional[str] = Field(None, description="Unique device identifier")
    device_name: Optional[str] = Field(None, description="User-friendly device name")


class DeviceResponse(BaseModel):
    """Response model for device registration."""
    id: int
    expo_push_token: str
    platform: str
    device_id: Optional[str]
    device_name: Optional[str]
    is_active: bool
    last_used_at: datetime
    created_at: datetime


class UserProfile(BaseModel):
    """User profile information."""
    id: str
    email: Optional[str]
    created_at: Optional[datetime] = None
    preferences: Optional[dict] = None
    device_count: int = 0
    watchlist_count: int = 0


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True


# ============================================
# Endpoints
# ============================================

@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Get the current authenticated user's profile.

    Returns user info, preferences, and counts.
    """
    # Get or create user preferences
    preferences = await db.get_user_preferences(user.id)
    if not preferences:
        await db.create_user_preferences(user.id)
        preferences = await db.get_user_preferences(user.id)

    # Get counts
    device_count = await db.get_user_device_count(user.id)
    watchlist_count = await db.get_user_watchlist_count(user.id)

    return UserProfile(
        id=user.id,
        email=user.email,
        created_at=preferences.get("created_at") if preferences else None,
        preferences=preferences,
        device_count=device_count,
        watchlist_count=watchlist_count
    )


@router.post("/register-device", response_model=DeviceResponse)
async def register_device(
    device: DeviceRegistration,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Register a device for push notifications.

    If the device already exists, updates the last_used_at timestamp.
    """
    result = await db.register_user_device(
        user_id=user.id,
        expo_push_token=device.expo_push_token,
        platform=device.platform,
        device_id=device.device_id,
        device_name=device.device_name
    )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Failed to register device"
        )

    return DeviceResponse(**result)


@router.delete("/devices/{device_id}", response_model=MessageResponse)
async def unregister_device(
    device_id: int,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Unregister a device from push notifications.

    Sets is_active to false rather than deleting.
    """
    success = await db.deactivate_user_device(user.id, device_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Device not found or already deactivated"
        )

    return MessageResponse(message="Device unregistered successfully")


@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    List all registered devices for the current user.
    """
    devices = await db.get_user_devices(user.id)
    return [DeviceResponse(**d) for d in devices]


@router.post("/devices/{device_id}/test", response_model=MessageResponse)
async def test_device_notification(
    device_id: int,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Send a test push notification to a specific device.
    """
    # Import here to avoid circular imports
    from core.push_notifications import push_service

    device = await db.get_user_device(user.id, device_id)
    if not device:
        raise HTTPException(
            status_code=404,
            detail="Device not found"
        )

    success = await push_service.send_test_notification(
        user_id=user.id,
        push_token=device["expo_push_token"],
        device_id=device_id
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to send test notification"
        )

    return MessageResponse(message="Test notification sent successfully")
