"""
Real-time WebSocket streaming for trading data.
Provides live price feeds, portfolio updates, and trading notifications.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
import websockets
from websockets.server import WebSocketServerProtocol
from fastapi import WebSocket, WebSocketDisconnect
import redis
from dataclasses import dataclass
from enum import Enum

from bot.user_manager import get_user_manager
from bot.balance_fetcher import get_balance_fetcher

logger = logging.getLogger(__name__)

class StreamType(str, Enum):
    """Types of data streams"""
    PRICE_FEED = "price_feed"
    PORTFOLIO = "portfolio"
    TRADES = "trades"
    NOTIFICATIONS = "notifications"
    MARKET_DATA = "market_data"
    AI_SIGNALS = "ai_signals"

@dataclass
class StreamMessage:
    """WebSocket stream message structure"""
    type: StreamType
    data: Dict[str, Any]
    timestamp: datetime
    user_id: Optional[int] = None
    
    def to_json(self) -> str:
        return json.dumps({
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id
        })

class ConnectionManager:
    """Manages WebSocket connections for real-time data streaming"""
    
    def __init__(self):
        # Active connections: user_id -> {websocket, subscriptions}
        self.active_connections: Dict[int, Dict[str, Any]] = {}
        
        # Stream subscriptions: stream_type -> set of user_ids
        self.subscriptions: Dict[StreamType, Set[int]] = {
            stream_type: set() for stream_type in StreamType
        }
        
        # Redis for pub/sub messaging
        try:
            self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
            self.redis_client.ping()
            logger.info("Connected to Redis for streaming")
        except Exception as e:
            logger.warning(f"Redis not available for streaming: {e}")
            self.redis_client = None
        
        self.user_manager = get_user_manager()
        self.balance_fetcher = get_balance_fetcher()
    
    async def connect(self, websocket: WebSocket, user_id: int):
        """Connect a new WebSocket client"""
        try:
            await websocket.accept()
            
            self.active_connections[user_id] = {
                "websocket": websocket,
                "subscriptions": set(),
                "connected_at": datetime.utcnow(),
                "last_ping": datetime.utcnow()
            }
            
            logger.info(f"WebSocket connected for user {user_id}")
            
            # Send welcome message
            welcome_msg = StreamMessage(
                type=StreamType.NOTIFICATIONS,
                data={
                    "message": "Connected to trading stream",
                    "user_id": user_id,
                    "available_streams": [stream.value for stream in StreamType]
                },
                timestamp=datetime.utcnow(),
                user_id=user_id
            )
            
            await self.send_to_user(user_id, welcome_msg)
            
        except Exception as e:
            logger.error(f"Error connecting WebSocket for user {user_id}: {e}")
            raise
    
    def disconnect(self, user_id: int):
        """Disconnect a WebSocket client"""
        try:
            if user_id in self.active_connections:
                # Remove from all subscriptions
                user_subscriptions = self.active_connections[user_id]["subscriptions"]
                for stream_type in user_subscriptions:
                    if stream_type in self.subscriptions:
                        self.subscriptions[stream_type].discard(user_id)
                
                # Remove connection
                del self.active_connections[user_id]
                logger.info(f"WebSocket disconnected for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket for user {user_id}: {e}")
    
    async def subscribe(self, user_id: int, stream_type: StreamType):
        """Subscribe user to a data stream"""
        try:
            if user_id not in self.active_connections:
                raise ValueError("User not connected")
            
            # Check user permissions
            permissions = self.user_manager.get_user_permissions(user_id)
            if not self._can_access_stream(stream_type, permissions):
                raise ValueError(f"Access denied to {stream_type.value} stream")
            
            # Add subscription
            self.active_connections[user_id]["subscriptions"].add(stream_type)
            self.subscriptions[stream_type].add(user_id)
            
            logger.info(f"User {user_id} subscribed to {stream_type.value}")
            
            # Send confirmation
            confirmation = StreamMessage(
                type=StreamType.NOTIFICATIONS,
                data={
                    "message": f"Subscribed to {stream_type.value}",
                    "stream_type": stream_type.value
                },
                timestamp=datetime.utcnow(),
                user_id=user_id
            )
            
            await self.send_to_user(user_id, confirmation)
            
            # Send initial data for some streams
            if stream_type == StreamType.PORTFOLIO:
                await self._send_initial_portfolio(user_id)
            elif stream_type == StreamType.PRICE_FEED:
                await self._send_initial_prices(user_id)
            
        except Exception as e:
            logger.error(f"Error subscribing user {user_id} to {stream_type.value}: {e}")
            await self._send_error(user_id, f"Subscription failed: {e}")
    
    async def unsubscribe(self, user_id: int, stream_type: StreamType):
        """Unsubscribe user from a data stream"""
        try:
            if user_id in self.active_connections:
                self.active_connections[user_id]["subscriptions"].discard(stream_type)
                self.subscriptions[stream_type].discard(user_id)
                
                logger.info(f"User {user_id} unsubscribed from {stream_type.value}")
                
                confirmation = StreamMessage(
                    type=StreamType.NOTIFICATIONS,
                    data={
                        "message": f"Unsubscribed from {stream_type.value}",
                        "stream_type": stream_type.value
                    },
                    timestamp=datetime.utcnow(),
                    user_id=user_id
                )
                
                await self.send_to_user(user_id, confirmation)
                
        except Exception as e:
            logger.error(f"Error unsubscribing user {user_id} from {stream_type.value}: {e}")
    
    async def send_to_user(self, user_id: int, message: StreamMessage):
        """Send message to specific user"""
        try:
            if user_id in self.active_connections:
                websocket = self.active_connections[user_id]["websocket"]
                await websocket.send_text(message.to_json())
                
        except Exception as e:
            logger.error(f"Error sending message to user {user_id}: {e}")
            # Remove disconnected user
            self.disconnect(user_id)
    
    async def broadcast_to_stream(self, stream_type: StreamType, message: StreamMessage):
        """Broadcast message to all users subscribed to a stream"""
        try:
            if stream_type in self.subscriptions:
                subscribers = self.subscriptions[stream_type].copy()
                
                for user_id in subscribers:
                    await self.send_to_user(user_id, message)
                    
        except Exception as e:
            logger.error(f"Error broadcasting to {stream_type.value}: {e}")
    
    async def handle_message(self, user_id: int, message: str):
        """Handle incoming WebSocket message from client"""
        try:
            data = json.loads(message)
            action = data.get("action")
            
            if action == "subscribe":
                stream_type = StreamType(data.get("stream_type"))
                await self.subscribe(user_id, stream_type)
                
            elif action == "unsubscribe":
                stream_type = StreamType(data.get("stream_type"))
                await self.unsubscribe(user_id, stream_type)
                
            elif action == "ping":
                # Update last ping time
                if user_id in self.active_connections:
                    self.active_connections[user_id]["last_ping"] = datetime.utcnow()
                
                pong_msg = StreamMessage(
                    type=StreamType.NOTIFICATIONS,
                    data={"message": "pong"},
                    timestamp=datetime.utcnow(),
                    user_id=user_id
                )
                await self.send_to_user(user_id, pong_msg)
                
            elif action == "get_subscriptions":
                subscriptions = list(self.active_connections[user_id]["subscriptions"])
                
                status_msg = StreamMessage(
                    type=StreamType.NOTIFICATIONS,
                    data={
                        "message": "Current subscriptions",
                        "subscriptions": [s.value for s in subscriptions]
                    },
                    timestamp=datetime.utcnow(),
                    user_id=user_id
                )
                await self.send_to_user(user_id, status_msg)
                
        except Exception as e:
            logger.error(f"Error handling message from user {user_id}: {e}")
            await self._send_error(user_id, f"Message handling failed: {e}")
    
    async def start_price_stream(self, symbols: List[str] = None):
        """Start price streaming for specified symbols"""
        if symbols is None:
            symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
        
        async def price_streamer():
            while True:
                try:
                    # Mock price data - in production, connect to real exchange WebSockets
                    import random
                    
                    for symbol in symbols:
                        price = 50000 if symbol.startswith("BTC") else 3000 if symbol.startswith("ETH") else 0.4
                        price *= random.uniform(0.98, 1.02)  # ±2% variation
                        
                        price_data = StreamMessage(
                            type=StreamType.PRICE_FEED,
                            data={
                                "symbol": symbol,
                                "price": round(price, 2),
                                "change_24h": round(random.uniform(-5, 5), 2),
                                "volume_24h": random.randint(1000000, 10000000)
                            },
                            timestamp=datetime.utcnow()
                        )
                        
                        await self.broadcast_to_stream(StreamType.PRICE_FEED, price_data)
                    
                    await asyncio.sleep(5)  # Update every 5 seconds
                    
                except Exception as e:
                    logger.error(f"Error in price streamer: {e}")
                    await asyncio.sleep(10)
        
        # Start price streaming task
        asyncio.create_task(price_streamer())
        logger.info("Started price streaming")
    
    async def send_portfolio_update(self, user_id: int):
        """Send portfolio update to user"""
        try:
            if user_id in self.subscriptions[StreamType.PORTFOLIO]:
                balance_data = self.balance_fetcher.get_balance_all_exchanges(str(user_id))
                
                portfolio_msg = StreamMessage(
                    type=StreamType.PORTFOLIO,
                    data={
                        "total_balance_usd": balance_data["total_balance_usd"],
                        "exchanges": balance_data["exchanges"],
                        "last_updated": balance_data["last_updated"]
                    },
                    timestamp=datetime.utcnow(),
                    user_id=user_id
                )
                
                await self.send_to_user(user_id, portfolio_msg)
                
        except Exception as e:
            logger.error(f"Error sending portfolio update to user {user_id}: {e}")
    
    async def send_trade_notification(self, user_id: int, trade_data: Dict[str, Any]):
        """Send trade execution notification"""
        try:
            trade_msg = StreamMessage(
                type=StreamType.TRADES,
                data=trade_data,
                timestamp=datetime.utcnow(),
                user_id=user_id
            )
            
            await self.send_to_user(user_id, trade_msg)
            
        except Exception as e:
            logger.error(f"Error sending trade notification to user {user_id}: {e}")
    
    async def send_ai_signal(self, signal_data: Dict[str, Any], target_users: List[int] = None):
        """Send AI trading signal to users"""
        try:
            ai_signal_msg = StreamMessage(
                type=StreamType.AI_SIGNALS,
                data=signal_data,
                timestamp=datetime.utcnow()
            )
            
            if target_users:
                for user_id in target_users:
                    if user_id in self.subscriptions[StreamType.AI_SIGNALS]:
                        await self.send_to_user(user_id, ai_signal_msg)
            else:
                await self.broadcast_to_stream(StreamType.AI_SIGNALS, ai_signal_msg)
                
        except Exception as e:
            logger.error(f"Error sending AI signal: {e}")
    
    def _can_access_stream(self, stream_type: StreamType, permissions: Dict[str, Any]) -> bool:
        """Check if user can access specific stream type"""
        features = permissions.get("features", [])
        
        if stream_type == StreamType.AI_SIGNALS:
            return "ai_signals" in features
        elif stream_type == StreamType.PORTFOLIO:
            return True  # All users can see their portfolio
        elif stream_type == StreamType.PRICE_FEED:
            return True  # All users can see price feeds
        elif stream_type == StreamType.TRADES:
            return "live_trading" in features or "demo_mode" in features
        else:
            return True
    
    async def _send_initial_portfolio(self, user_id: int):
        """Send initial portfolio data when user subscribes"""
        await self.send_portfolio_update(user_id)
    
    async def _send_initial_prices(self, user_id: int):
        """Send initial price data when user subscribes"""
        # This would be called automatically by the price streamer
        pass
    
    async def _send_error(self, user_id: int, error_message: str):
        """Send error message to user"""
        try:
            error_msg = StreamMessage(
                type=StreamType.NOTIFICATIONS,
                data={
                    "error": True,
                    "message": error_message
                },
                timestamp=datetime.utcnow(),
                user_id=user_id
            )
            
            await self.send_to_user(user_id, error_msg)
            
        except Exception as e:
            logger.error(f"Error sending error message to user {user_id}: {e}")


# Global instance
_connection_manager: Optional[ConnectionManager] = None

def get_connection_manager() -> ConnectionManager:
    """Get or create global ConnectionManager instance"""
    global _connection_manager
    
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    
    return _connection_manager
