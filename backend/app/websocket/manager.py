from fastapi import WebSocket
from typing import Dict, Set
import logging
import json

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # user_id -> set of WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = {}
        # symbol -> set of user_ids subscribed
        self._subscriptions: Dict[str, Set[str]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(websocket)
        logger.info(f"WebSocket connected: user={user_id}")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info(f"WebSocket disconnected: user={user_id}")

    def subscribe(self, user_id: str, symbol: str):
        if symbol not in self._subscriptions:
            self._subscriptions[symbol] = set()
        self._subscriptions[symbol].add(user_id)

    def unsubscribe(self, user_id: str, symbol: str):
        if symbol in self._subscriptions:
            self._subscriptions[symbol].discard(user_id)

    async def send_to_user(self, user_id: str, message: dict):
        """Send a message to all connections of a user."""
        for ws in list(self._connections.get(user_id, [])):
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to {user_id}: {e}")

    async def broadcast_price(self, symbol: str, price: float, change_pct: float):
        """Broadcast a price update to all subscribers of a symbol."""
        message = {
            "type": "price_update",
            "symbol": symbol,
            "price": price,
            "change_pct": change_pct,
        }
        for user_id in list(self._subscriptions.get(symbol, [])):
            await self.send_to_user(user_id, message)

    async def broadcast_signal(self, symbol: str, signal: dict):
        """Broadcast a new signal to all subscribers of a symbol."""
        message = {"type": "signal_update", "symbol": symbol, "signal": signal}
        for user_id in list(self._subscriptions.get(symbol, [])):
            await self.send_to_user(user_id, message)


manager = ConnectionManager()
