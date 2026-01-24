"""
WebSocket handler for BetSnipe.ai v2.0

Real-time updates for odds and arbitrage opportunities.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Set, Optional, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState

from core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.

    Supports subscriptions to specific channels:
    - 'odds': All odds updates
    - 'arbitrage': Arbitrage alerts only
    - 'match:{id}': Updates for specific match
    - 'sport:{id}': Updates for specific sport
    """

    def __init__(self):
        # All active connections
        self._connections: Set[WebSocket] = set()
        # Connection to subscription mapping
        self._subscriptions: Dict[WebSocket, Set[str]] = {}
        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
            self._subscriptions[websocket] = {'all'}  # Default subscription
        logger.info(f"WebSocket connected. Total: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self._connections.discard(websocket)
            self._subscriptions.pop(websocket, None)
        logger.info(f"WebSocket disconnected. Total: {len(self._connections)}")

    async def subscribe(self, websocket: WebSocket, channels: List[str]) -> None:
        """Subscribe a connection to specific channels."""
        async with self._lock:
            if websocket in self._subscriptions:
                self._subscriptions[websocket].update(channels)
        logger.debug(f"Subscribed to channels: {channels}")

    async def unsubscribe(self, websocket: WebSocket, channels: List[str]) -> None:
        """Unsubscribe a connection from specific channels."""
        async with self._lock:
            if websocket in self._subscriptions:
                self._subscriptions[websocket] -= set(channels)

    def _should_send(self, websocket: WebSocket, message: Dict) -> bool:
        """Check if a message should be sent to a connection based on subscriptions."""
        if websocket not in self._subscriptions:
            return False

        subs = self._subscriptions[websocket]

        # 'all' subscription receives everything
        if 'all' in subs:
            return True

        msg_type = message.get('type', '')
        msg_data = message.get('data', {})

        # Check type-based subscriptions
        if msg_type in subs:
            return True

        # Check match-specific subscriptions
        match_id = msg_data.get('match_id')
        if match_id and f'match:{match_id}' in subs:
            return True

        # Check sport-specific subscriptions
        sport_id = msg_data.get('sport_id')
        if sport_id and f'sport:{sport_id}' in subs:
            return True

        return False

    async def send_personal(self, websocket: WebSocket, message: Dict) -> None:
        """Send a message to a specific connection."""
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Error sending personal message: {e}")
            await self.disconnect(websocket)

    async def broadcast(self, message: Dict) -> None:
        """Broadcast a message to all relevant connections."""
        disconnected = []

        async with self._lock:
            connections = list(self._connections)

        for websocket in connections:
            if self._should_send(websocket, message):
                try:
                    if websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.send_json(message)
                except Exception as e:
                    logger.warning(f"Error broadcasting: {e}")
                    disconnected.append(websocket)

        # Clean up disconnected clients
        for ws in disconnected:
            await self.disconnect(ws)

    async def broadcast_to_channel(self, channel: str, message: Dict) -> None:
        """Broadcast a message to a specific channel."""
        message['channel'] = channel
        await self.broadcast(message)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    channels: Optional[str] = Query(None, description="Comma-separated channels to subscribe")
):
    """
    Main WebSocket endpoint for real-time updates.

    Query parameters:
    - channels: Comma-separated list of channels to subscribe to
      Examples: 'odds', 'arbitrage', 'match:123', 'sport:1'

    Message format (incoming):
    {
        "action": "subscribe" | "unsubscribe",
        "channels": ["odds", "arbitrage"]
    }

    Message format (outgoing):
    {
        "type": "odds_update" | "arbitrage",
        "data": {...},
        "timestamp": "2024-01-15T12:00:00Z"
    }
    """
    await manager.connect(websocket)

    # Handle initial channel subscription from query params
    if channels:
        channel_list = [c.strip() for c in channels.split(',')]
        await manager.subscribe(websocket, channel_list)

    try:
        # Send welcome message
        await manager.send_personal(websocket, {
            'type': 'connected',
            'message': 'Connected to BetSnipe.ai real-time feed',
            'timestamp': datetime.utcnow().isoformat(),
        })

        while True:
            # Wait for incoming messages
            data = await websocket.receive_json()

            action = data.get('action')
            msg_channels = data.get('channels', [])

            if action == 'subscribe':
                await manager.subscribe(websocket, msg_channels)
                await manager.send_personal(websocket, {
                    'type': 'subscribed',
                    'channels': msg_channels,
                    'timestamp': datetime.utcnow().isoformat(),
                })

            elif action == 'unsubscribe':
                await manager.unsubscribe(websocket, msg_channels)
                await manager.send_personal(websocket, {
                    'type': 'unsubscribed',
                    'channels': msg_channels,
                    'timestamp': datetime.utcnow().isoformat(),
                })

            elif action == 'ping':
                await manager.send_personal(websocket, {
                    'type': 'pong',
                    'timestamp': datetime.utcnow().isoformat(),
                })

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(websocket)


@router.websocket("/ws/odds")
async def odds_websocket(websocket: WebSocket):
    """WebSocket endpoint specifically for odds updates."""
    await manager.connect(websocket)
    await manager.subscribe(websocket, ['odds_update'])

    try:
        await manager.send_personal(websocket, {
            'type': 'connected',
            'channel': 'odds',
            'timestamp': datetime.utcnow().isoformat(),
        })

        while True:
            # Keep connection alive, handle pings
            data = await websocket.receive_json()
            if data.get('action') == 'ping':
                await manager.send_personal(websocket, {
                    'type': 'pong',
                    'timestamp': datetime.utcnow().isoformat(),
                })

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Odds WebSocket error: {e}")
        await manager.disconnect(websocket)


@router.websocket("/ws/arbitrage")
async def arbitrage_websocket(websocket: WebSocket):
    """WebSocket endpoint specifically for arbitrage alerts."""
    await manager.connect(websocket)
    await manager.subscribe(websocket, ['arbitrage'])

    try:
        await manager.send_personal(websocket, {
            'type': 'connected',
            'channel': 'arbitrage',
            'timestamp': datetime.utcnow().isoformat(),
        })

        while True:
            # Keep connection alive, handle pings
            data = await websocket.receive_json()
            if data.get('action') == 'ping':
                await manager.send_personal(websocket, {
                    'type': 'pong',
                    'timestamp': datetime.utcnow().isoformat(),
                })

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Arbitrage WebSocket error: {e}")
        await manager.disconnect(websocket)
