"""
Push Notifications Service for BetSnipe.ai v3.0

Uses Expo Push Notifications to send alerts to mobile apps.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushServerError,
    PushTicketError,
)
from aiohttp import ClientSession

from core.config import settings
from core.db import db

logger = logging.getLogger(__name__)


class PushNotificationService:
    """
    Service for sending push notifications via Expo.

    Handles:
    - Arbitrage alerts
    - Watchlist odds change notifications
    - Match start reminders
    - Test notifications
    """

    def __init__(self):
        self.client = PushClient()
        self._session: Optional[ClientSession] = None

    async def _get_session(self) -> ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = ClientSession()
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def _create_message(
        self,
        push_token: str,
        title: str,
        body: str,
        data: Optional[Dict] = None,
        badge: Optional[int] = None,
        sound: str = "default",
        channel_id: Optional[str] = None
    ) -> PushMessage:
        """Create an Expo push message."""
        return PushMessage(
            to=push_token,
            title=title,
            body=body,
            data=data or {},
            badge=badge,
            sound=sound,
            channel_id=channel_id or "default"
        )

    async def send_notification(
        self,
        push_token: str,
        title: str,
        body: str,
        data: Optional[Dict] = None,
        notification_type: str = "general",
        user_id: Optional[str] = None,
        device_id: Optional[int] = None
    ) -> bool:
        """
        Send a single push notification.

        Returns True if sent successfully, False otherwise.
        """
        try:
            message = self._create_message(
                push_token=push_token,
                title=title,
                body=body,
                data=data,
                channel_id=notification_type
            )

            # Send synchronously (expo SDK is sync)
            response = self.client.publish(message)

            # Log the notification
            status = 'sent'
            expo_receipt_id = response.id if hasattr(response, 'id') else None
            error_message = None

            if response.status != 'ok':
                status = 'failed'
                error_message = str(response.message) if hasattr(response, 'message') else 'Unknown error'
                logger.warning(f"Push notification failed: {error_message}")

            if user_id:
                await db.log_push_notification(
                    user_id=user_id,
                    device_id=device_id,
                    notification_type=notification_type,
                    title=title,
                    body=body,
                    data=data,
                    status=status,
                    expo_receipt_id=expo_receipt_id,
                    error_message=error_message
                )

            return response.status == 'ok'

        except DeviceNotRegisteredError:
            logger.warning(f"Device not registered: {push_token[:20]}...")
            # Deactivate the device
            if user_id and device_id:
                await db.deactivate_user_device(user_id, device_id)
            return False

        except PushServerError as e:
            logger.error(f"Push server error: {e}")
            return False

        except Exception as e:
            logger.error(f"Failed to send push notification: {e}")
            return False

    async def send_bulk_notifications(
        self,
        messages: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Send multiple push notifications in bulk.

        Args:
            messages: List of dicts with keys: push_token, title, body, data, user_id, device_id

        Returns:
            Dict with sent/failed counts
        """
        results = {'sent': 0, 'failed': 0}

        if not messages:
            return results

        # Create PushMessage objects
        push_messages = []
        message_map = {}  # Map index to user info for logging

        for i, msg in enumerate(messages):
            push_msg = self._create_message(
                push_token=msg['push_token'],
                title=msg['title'],
                body=msg['body'],
                data=msg.get('data'),
                channel_id=msg.get('notification_type', 'general')
            )
            push_messages.append(push_msg)
            message_map[i] = {
                'user_id': msg.get('user_id'),
                'device_id': msg.get('device_id'),
                'notification_type': msg.get('notification_type', 'general'),
                'title': msg['title'],
                'body': msg['body'],
                'data': msg.get('data')
            }

        try:
            # Send in chunks of 100 (Expo limit)
            chunk_size = 100
            for chunk_start in range(0, len(push_messages), chunk_size):
                chunk = push_messages[chunk_start:chunk_start + chunk_size]
                responses = self.client.publish_multiple(chunk)

                for j, response in enumerate(responses):
                    idx = chunk_start + j
                    info = message_map.get(idx, {})

                    if response.status == 'ok':
                        results['sent'] += 1
                        status = 'sent'
                    else:
                        results['failed'] += 1
                        status = 'failed'
                        logger.warning(f"Bulk push failed for user {info.get('user_id')}: {response.message if hasattr(response, 'message') else 'Unknown'}")

                    # Log each notification
                    if info.get('user_id'):
                        await db.log_push_notification(
                            user_id=info['user_id'],
                            device_id=info.get('device_id'),
                            notification_type=info['notification_type'],
                            title=info['title'],
                            body=info['body'],
                            data=info.get('data'),
                            status=status,
                            expo_receipt_id=response.id if hasattr(response, 'id') else None,
                            error_message=str(response.message) if hasattr(response, 'message') and response.status != 'ok' else None
                        )

        except Exception as e:
            logger.error(f"Bulk push error: {e}")
            results['failed'] += len(push_messages) - results['sent']

        return results

    async def send_arbitrage_alert(
        self,
        arbitrage_id: int,
        match_id: int,
        team1: str,
        team2: str,
        profit_percentage: float,
        sport_id: int,
        best_odds: List[Dict]
    ) -> int:
        """
        Send arbitrage alert to all subscribed users.

        Returns number of notifications sent.
        """
        # Get recipients
        recipients = await db.get_arbitrage_notification_recipients(
            profit_percentage=profit_percentage,
            sport_id=sport_id
        )

        if not recipients:
            logger.debug(f"No recipients for arbitrage alert (profit: {profit_percentage}%, sport: {sport_id})")
            return 0

        # Build notification
        title = f"Arbitrage: {profit_percentage:.2f}% profit"
        body = f"{team1} vs {team2}"

        # Add bookmaker info to body
        bookmaker_info = [f"{o.get('bookmaker_name', 'Unknown')}: {o.get('odd', 0):.2f}" for o in best_odds[:3]]
        if bookmaker_info:
            body += f"\n{' | '.join(bookmaker_info)}"

        data = {
            'type': 'arbitrage',
            'arbitrage_id': arbitrage_id,
            'match_id': match_id,
            'profit_percentage': profit_percentage
        }

        # Build message list
        messages = []
        for r in recipients:
            messages.append({
                'push_token': r['expo_push_token'],
                'title': title,
                'body': body,
                'data': data,
                'notification_type': 'arbitrage',
                'user_id': str(r['user_id'])
            })

        results = await self.send_bulk_notifications(messages)
        logger.info(f"Sent {results['sent']} arbitrage alerts for match {match_id}")

        return results['sent']

    async def send_watchlist_alert(
        self,
        match_id: int,
        team1: str,
        team2: str,
        bookmaker_name: str,
        old_odds: Dict[str, float],
        new_odds: Dict[str, float],
        odds_change: float
    ) -> int:
        """
        Send odds change alert to users watching this match.

        Returns number of notifications sent.
        """
        # Get recipients
        recipients = await db.get_watchlist_notification_recipients(
            match_id=match_id,
            odds_change=odds_change
        )

        if not recipients:
            return 0

        # Build notification
        direction = "" if odds_change > 0 else ""
        title = f"Odds {direction} {team1} vs {team2}"

        # Show the change
        changes = []
        for key in ['odd1', 'odd2', 'odd3']:
            if key in old_odds and key in new_odds:
                old_val = old_odds[key]
                new_val = new_odds[key]
                if old_val and new_val and old_val != new_val:
                    diff = new_val - old_val
                    changes.append(f"{old_val:.2f}{new_val:.2f}")

        body = f"{bookmaker_name}: {' | '.join(changes)}" if changes else f"{bookmaker_name}: Odds changed"

        data = {
            'type': 'watchlist_odds',
            'match_id': match_id,
            'bookmaker': bookmaker_name,
            'change': odds_change
        }

        # Build message list
        messages = []
        for r in recipients:
            messages.append({
                'push_token': r['expo_push_token'],
                'title': title,
                'body': body,
                'data': data,
                'notification_type': 'watchlist',
                'user_id': str(r['user_id'])
            })

        results = await self.send_bulk_notifications(messages)
        logger.info(f"Sent {results['sent']} watchlist alerts for match {match_id}")

        return results['sent']

    async def send_match_reminder(
        self,
        match_id: int,
        team1: str,
        team2: str,
        start_time: datetime,
        sport_name: str
    ) -> int:
        """
        Send match start reminder to users watching this match.

        Returns number of notifications sent.
        """
        # Get all watchers (using threshold 0 to get everyone)
        recipients = await db.get_watchlist_notification_recipients(
            match_id=match_id,
            odds_change=0
        )

        if not recipients:
            return 0

        title = f"Match Starting: {team1} vs {team2}"
        body = f"{sport_name} - Starting at {start_time.strftime('%H:%M')}"

        data = {
            'type': 'match_reminder',
            'match_id': match_id
        }

        messages = []
        for r in recipients:
            messages.append({
                'push_token': r['expo_push_token'],
                'title': title,
                'body': body,
                'data': data,
                'notification_type': 'reminder',
                'user_id': str(r['user_id'])
            })

        results = await self.send_bulk_notifications(messages)
        return results['sent']

    async def send_test_notification(
        self,
        user_id: str,
        push_token: str,
        device_id: Optional[int] = None
    ) -> bool:
        """
        Send a test notification to verify device setup.
        """
        return await self.send_notification(
            push_token=push_token,
            title="BetSnipe.ai Test",
            body="Push notifications are working! ",
            data={'type': 'test', 'timestamp': datetime.utcnow().isoformat()},
            notification_type='test',
            user_id=user_id,
            device_id=device_id
        )


# Global push service instance
push_service = PushNotificationService()
