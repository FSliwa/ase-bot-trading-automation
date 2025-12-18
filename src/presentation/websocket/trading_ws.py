"""WebSocket endpoints for real-time trading data."""

import json
import asyncio
import random
from typing import Dict, List, Set
from fastapi import WebSocket, WebSocketDisconnect, Depends
from datetime import datetime

from src.application.services.user_service import UserService
from src.presentation.api.dependencies import get_user_service
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_connections: Dict[int, Set[str]] = {}
        self.subscriptions: Dict[str, Set[str]] = {}  # channel -> connection_ids
        
    async def connect(self, websocket: WebSocket, connection_id: str, user_id: int):
        """Accept WebSocket connection."""
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(connection_id)
        
        logger.info(f"WebSocket connected: {connection_id} (user: {user_id})")

    def disconnect(self, connection_id: str, user_id: int):
        """Remove WebSocket connection."""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
                
        # Remove from all subscriptions
        for channel_subs in self.subscriptions.values():
            channel_subs.discard(connection_id)
            
        logger.info(f"WebSocket disconnected: {connection_id}")

    async def send_personal_message(self, message: str, connection_id: str):
        """Send message to specific connection."""
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_text(message)
            except:
                # Connection might be closed
                pass

    async def send_to_user(self, message: str, user_id: int):
        """Send message to all user's connections."""
        if user_id in self.user_connections:
            for connection_id in self.user_connections[user_id].copy():
                await self.send_personal_message(message, connection_id)

    async def broadcast_to_channel(self, message: str, channel: str):
        """Broadcast message to all subscribers of a channel."""
        if channel in self.subscriptions:
            for connection_id in self.subscriptions[channel].copy():
                await self.send_personal_message(message, connection_id)

    def subscribe_to_channel(self, connection_id: str, channel: str):
        """Subscribe connection to a channel."""
        if channel not in self.subscriptions:
            self.subscriptions[channel] = set()
        self.subscriptions[channel].add(connection_id)

    def unsubscribe_from_channel(self, connection_id: str, channel: str):
        """Unsubscribe connection from a channel."""
        if channel in self.subscriptions:
            self.subscriptions[channel].discard(connection_id)


# Global connection manager
manager = ConnectionManager()


class TradingWebSocket:
    """WebSocket handler for trading data."""
    
    def __init__(self, websocket: WebSocket, user_service: UserService):
        self.websocket = websocket
        self.user_service = user_service
        self.connection_id = f"ws_{datetime.now().timestamp()}"
        self.user = None
        
    async def handle_connection(self):
        """Handle WebSocket connection lifecycle."""
        try:
            # Authenticate user
            await self.authenticate()
            
            if not self.user:
                await self.websocket.close(code=4001, reason="Authentication required")
                return
                
            # Connect to manager
            await manager.connect(self.websocket, self.connection_id, self.user.id)
            
            # Send welcome message
            await self.send_message({
                "type": "connected",
                "user": {
                    "id": self.user.id,
                    "username": self.user.username
                },
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Start message loop
            await self.message_loop()
            
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {self.connection_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            if self.user:
                manager.disconnect(self.connection_id, self.user.id)

    async def authenticate(self):
        """Authenticate WebSocket connection."""
        try:
            # Wait for auth message
            auth_message = await asyncio.wait_for(
                self.websocket.receive_text(), 
                timeout=10.0
            )
            
            auth_data = json.loads(auth_message)
            token = auth_data.get("token")
            
            if token:
                self.user = await self.user_service.get_user_by_session(token)
                
        except (asyncio.TimeoutError, json.JSONDecodeError, KeyError):
            logger.warning("WebSocket authentication failed")

    async def message_loop(self):
        """Handle incoming WebSocket messages."""
        try:
            while True:
                data = await self.websocket.receive_text()
                message = json.loads(data)
                await self.handle_message(message)
                
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"Message loop error: {e}")

    async def handle_message(self, message: Dict):
        """Handle incoming WebSocket message."""
        message_type = message.get("type")
        
        if message_type == "subscribe":
            channel = message.get("channel")
            if channel:
                manager.subscribe_to_channel(self.connection_id, channel)
                await self.send_message({
                    "type": "subscribed",
                    "channel": channel
                })
                
        elif message_type == "unsubscribe":
            channel = message.get("channel")
            if channel:
                manager.unsubscribe_from_channel(self.connection_id, channel)
                await self.send_message({
                    "type": "unsubscribed", 
                    "channel": channel
                })
                
        elif message_type == "ping":
            await self.send_message({"type": "pong"})
            
        else:
            logger.warning(f"Unknown message type: {message_type}")

    async def send_message(self, data: Dict):
        """Send message to WebSocket."""
        try:
            await self.websocket.send_text(json.dumps(data))
        except:
            # Connection might be closed
            pass


# Price feed simulator
class PriceFeedService:
    """Simulate real-time price feeds."""
    
    def __init__(self):
        self.symbols = ["BTC/USDT", "ETH/USDT", "ADA/USDT", "DOT/USDT"]
        self.prices = {
            "BTC/USDT": 43250.00,
            "ETH/USDT": 2650.00,
            "ADA/USDT": 0.45,
            "DOT/USDT": 7.25
        }
        self.running = False

    async def start_price_feed(self):
        """Start broadcasting price updates."""
        self.running = True
        
        while self.running:
            for symbol in self.symbols:
                # Simulate price movement
                current_price = self.prices[symbol]
                change_percent = (random.random() - 0.5) * 0.02  # ±1% change
                new_price = current_price * (1 + change_percent)
                self.prices[symbol] = new_price
                
                # Broadcast to subscribers
                price_update = {
                    "type": "price_update",
                    "symbol": symbol,
                    "price": round(new_price, 2),
                    "change": round((new_price - current_price) / current_price * 100, 2),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                await manager.broadcast_to_channel(
                    json.dumps(price_update),
                    f"prices.{symbol}"
                )
            
            await asyncio.sleep(1)  # Update every second

    def stop_price_feed(self):
        """Stop price feed."""
        self.running = False


# Global price feed service
price_feed = PriceFeedService()


# WebSocket endpoint
async def websocket_endpoint(
    websocket: WebSocket,
    user_service: UserService = Depends(get_user_service)
):
    """WebSocket endpoint for real-time data."""
    ws_handler = TradingWebSocket(websocket, user_service)
    await ws_handler.handle_connection()


# Background task to start price feed
async def start_background_tasks():
    """Start background tasks."""
    asyncio.create_task(price_feed.start_price_feed())
