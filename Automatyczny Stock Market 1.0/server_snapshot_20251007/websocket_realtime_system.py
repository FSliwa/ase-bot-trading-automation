"""
WEBSOCKET REAL-TIME DATA STREAMING SYSTEM
System WebSocket dla strumieniowego przesyłania danych w czasie rzeczywistym
"""

# ==================================================================================
# 🔄 REAL-TIME WEBSOCKET SYSTEM
# ==================================================================================

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Set, Any, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import weakref
from collections import defaultdict, deque
import hashlib
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MessageType(Enum):
    """Typy wiadomości WebSocket"""
    POSITION_UPDATE = "position_update"
    PRICE_FEED = "price_feed" 
    PORTFOLIO_CHANGE = "portfolio_change"
    RISK_ALERT = "risk_alert"
    ORDER_STATUS = "order_status"
    MARKET_DATA = "market_data"
    TRADE_EXECUTION = "trade_execution"
    SYSTEM_STATUS = "system_status"
    AI_SIGNAL = "ai_signal"
    NEWS_UPDATE = "news_update"
    HEARTBEAT = "heartbeat"
    ERROR = "error"

@dataclass
class WebSocketMessage:
    """Struktura wiadomości WebSocket"""
    message_type: MessageType
    data: Dict[str, Any]
    timestamp: float
    message_id: str
    correlation_id: Optional[str] = None
    priority: int = 1  # 1=low, 5=high
    expires_at: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje do słownika"""
        return {
            "type": self.message_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
            "priority": self.priority,
            "expires_at": self.expires_at
        }
    
    def to_json(self) -> str:
        """Konwertuje do JSON"""
        return json.dumps(self.to_dict())

class ConnectionState(Enum):
    """Stany połączenia"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    SUBSCRIBING = "subscribing"
    ACTIVE = "active"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"

@dataclass
class ConnectionInfo:
    """Informacje o połączeniu WebSocket"""
    connection_id: str
    user_id: str
    session_id: str
    client_ip: str
    user_agent: str
    connected_at: datetime
    last_activity: datetime
    state: ConnectionState
    subscriptions: Set[str]
    message_count: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    error_count: int = 0
    
class SubscriptionManager:
    """Zarządzanie subskrypcjami WebSocket"""
    
    def __init__(self):
        self.subscriptions: Dict[str, Set[str]] = defaultdict(set)
        self.connection_subscriptions: Dict[str, Set[str]] = defaultdict(set)
        self.subscription_patterns: Dict[str, Set[str]] = defaultdict(set)
        
    def subscribe(self, connection_id: str, channel: str) -> bool:
        """Dodaje subskrypcję dla połączenia"""
        try:
            # Add to channel subscribers
            self.subscriptions[channel].add(connection_id)
            
            # Add to connection subscriptions
            self.connection_subscriptions[connection_id].add(channel)
            
            # Handle pattern subscriptions
            if '*' in channel or '?' in channel:
                self.subscription_patterns[connection_id].add(channel)
            
            logger.info(f"Connection {connection_id} subscribed to {channel}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to subscribe {connection_id} to {channel}: {e}")
            return False
    
    def unsubscribe(self, connection_id: str, channel: str) -> bool:
        """Usuwa subskrypcję dla połączenia"""
        try:
            # Remove from channel subscribers
            self.subscriptions[channel].discard(connection_id)
            
            # Remove from connection subscriptions
            self.connection_subscriptions[connection_id].discard(channel)
            
            # Remove from pattern subscriptions
            self.subscription_patterns[connection_id].discard(channel)
            
            # Clean up empty channels
            if not self.subscriptions[channel]:
                del self.subscriptions[channel]
            
            logger.info(f"Connection {connection_id} unsubscribed from {channel}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe {connection_id} from {channel}: {e}")
            return False
    
    def unsubscribe_all(self, connection_id: str):
        """Usuwa wszystkie subskrypcje dla połączenia"""
        channels = list(self.connection_subscriptions.get(connection_id, set()))
        for channel in channels:
            self.unsubscribe(connection_id, channel)
        
        # Clean up pattern subscriptions
        self.subscription_patterns.pop(connection_id, None)
        self.connection_subscriptions.pop(connection_id, None)
    
    def get_subscribers(self, channel: str) -> Set[str]:
        """Pobiera subskrybentów kanału"""
        subscribers = set(self.subscriptions.get(channel, set()))
        
        # Add pattern-based subscribers
        for connection_id, patterns in self.subscription_patterns.items():
            for pattern in patterns:
                if self._match_pattern(channel, pattern):
                    subscribers.add(connection_id)
        
        return subscribers
    
    def get_connection_subscriptions(self, connection_id: str) -> Set[str]:
        """Pobiera subskrypcje dla połączenia"""
        return self.connection_subscriptions.get(connection_id, set()).copy()
    
    def _match_pattern(self, channel: str, pattern: str) -> bool:
        """Sprawdza czy kanał pasuje do wzorca"""
        # Simple pattern matching (* for any characters, ? for single character)
        import fnmatch
        return fnmatch.fnmatch(channel, pattern)

class MessageBuffer:
    """Bufor wiadomości dla połączeń WebSocket"""
    
    def __init__(self, max_size: int = 1000, max_age_seconds: int = 300):
        self.max_size = max_size
        self.max_age_seconds = max_age_seconds
        self.buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_size))
        self.message_timestamps: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_size))
    
    def add_message(self, connection_id: str, message: WebSocketMessage):
        """Dodaje wiadomość do bufora"""
        current_time = time.time()
        
        # Add message to buffer
        self.buffers[connection_id].append(message)
        self.message_timestamps[connection_id].append(current_time)
        
        # Clean old messages
        self._clean_old_messages(connection_id)
    
    def get_messages(self, connection_id: str, since_timestamp: Optional[float] = None) -> List[WebSocketMessage]:
        """Pobiera wiadomości z bufora"""
        if connection_id not in self.buffers:
            return []
        
        messages = list(self.buffers[connection_id])
        
        if since_timestamp:
            messages = [
                msg for msg in messages 
                if msg.timestamp > since_timestamp
            ]
        
        return messages
    
    def clear_buffer(self, connection_id: str):
        """Czyści bufor dla połączenia"""
        self.buffers.pop(connection_id, None)
        self.message_timestamps.pop(connection_id, None)
    
    def _clean_old_messages(self, connection_id: str):
        """Usuwa stare wiadomości"""
        current_time = time.time()
        cutoff_time = current_time - self.max_age_seconds
        
        timestamps = self.message_timestamps[connection_id]
        messages = self.buffers[connection_id]
        
        # Remove old messages
        while timestamps and timestamps[0] < cutoff_time:
            timestamps.popleft()
            messages.popleft()

class WebSocketServer:
    """Serwer WebSocket dla strumieniowych danych"""
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.connections: Dict[str, Any] = {}  # WebSocket connections
        self.connection_info: Dict[str, ConnectionInfo] = {}
        self.subscription_manager = SubscriptionManager()
        self.message_buffer = MessageBuffer()
        self.message_handlers: Dict[str, Callable] = {}
        self.middleware: List[Callable] = []
        self.running = False
        
        # Statistics
        self.stats = {
            'total_connections': 0,
            'active_connections': 0,
            'messages_sent': 0,
            'messages_received': 0,
            'bytes_sent': 0,
            'bytes_received': 0,
            'errors': 0,
            'start_time': None
        }
        
        # Rate limiting
        self.rate_limits: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.max_messages_per_minute = 60
        
    async def start_server(self):
        """Uruchamia serwer WebSocket"""
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")
        self.running = True
        self.stats['start_time'] = time.time()
        
        # Start periodic tasks
        asyncio.create_task(self._periodic_cleanup())
        asyncio.create_task(self._periodic_heartbeat())
        asyncio.create_task(self._periodic_stats())
        
        logger.info("WebSocket server started successfully")
    
    async def stop_server(self):
        """Zatrzymuje serwer WebSocket"""
        logger.info("Stopping WebSocket server...")
        self.running = False
        
        # Disconnect all clients
        for connection_id in list(self.connections.keys()):
            await self.disconnect_client(connection_id)
        
        logger.info("WebSocket server stopped")
    
    def register_handler(self, message_type: str, handler: Callable):
        """Rejestruje handler dla typu wiadomości"""
        self.message_handlers[message_type] = handler
        logger.info(f"Registered handler for message type: {message_type}")
    
    def add_middleware(self, middleware: Callable):
        """Dodaje middleware"""
        self.middleware.append(middleware)
        logger.info("Added middleware to WebSocket server")
    
    async def handle_connection(self, websocket, path: str):
        """Obsługuje nowe połączenie WebSocket"""
        connection_id = str(uuid.uuid4())
        
        try:
            # Extract connection info
            client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
            user_agent = websocket.request_headers.get('User-Agent', 'unknown')
            
            # Create connection info
            conn_info = ConnectionInfo(
                connection_id=connection_id,
                user_id="anonymous",  # Will be updated after authentication
                session_id=str(uuid.uuid4()),
                client_ip=client_ip,
                user_agent=user_agent,
                connected_at=datetime.utcnow(),
                last_activity=datetime.utcnow(),
                state=ConnectionState.CONNECTING,
                subscriptions=set()
            )
            
            # Store connection
            self.connections[connection_id] = websocket
            self.connection_info[connection_id] = conn_info
            
            # Update stats
            self.stats['total_connections'] += 1
            self.stats['active_connections'] += 1
            
            logger.info(f"New WebSocket connection: {connection_id} from {client_ip}")
            
            # Send welcome message
            await self.send_message(connection_id, WebSocketMessage(
                message_type=MessageType.SYSTEM_STATUS,
                data={
                    "status": "connected",
                    "connection_id": connection_id,
                    "server_time": time.time()
                },
                timestamp=time.time(),
                message_id=str(uuid.uuid4())
            ))
            
            # Handle incoming messages
            async for message in websocket:
                await self._handle_incoming_message(connection_id, message)
                
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            self.stats['errors'] += 1
        finally:
            await self.disconnect_client(connection_id)
    
    async def disconnect_client(self, connection_id: str):
        """Rozłącza klienta"""
        if connection_id not in self.connections:
            return
        
        try:
            # Get connection info
            conn_info = self.connection_info.get(connection_id)
            if conn_info:
                logger.info(f"Disconnecting client {connection_id} (user: {conn_info.user_id})")
                
                # Send goodbye message
                await self.send_message(connection_id, WebSocketMessage(
                    message_type=MessageType.SYSTEM_STATUS,
                    data={"status": "disconnecting"},
                    timestamp=time.time(),
                    message_id=str(uuid.uuid4())
                ))
            
            # Close WebSocket connection
            websocket = self.connections.get(connection_id)
            if websocket and not websocket.closed:
                await websocket.close()
            
            # Clean up subscriptions
            self.subscription_manager.unsubscribe_all(connection_id)
            
            # Clear message buffer
            self.message_buffer.clear_buffer(connection_id)
            
            # Remove from connections
            self.connections.pop(connection_id, None)
            self.connection_info.pop(connection_id, None)
            
            # Update stats
            self.stats['active_connections'] = max(0, self.stats['active_connections'] - 1)
            
        except Exception as e:
            logger.error(f"Error disconnecting client {connection_id}: {e}")
    
    async def send_message(self, connection_id: str, message: WebSocketMessage) -> bool:
        """Wysyła wiadomość do konkretnego połączenia"""
        if connection_id not in self.connections:
            logger.warning(f"Attempted to send message to non-existent connection: {connection_id}")
            return False
        
        try:
            websocket = self.connections[connection_id]
            
            # Check if message is expired
            if message.expires_at and time.time() > message.expires_at:
                return False
            
            # Apply middleware
            for middleware in self.middleware:
                message = await middleware(message, connection_id)
                if not message:  # Middleware can block message
                    return False
            
            # Send message
            message_json = message.to_json()
            await websocket.send(message_json)
            
            # Update stats
            self.stats['messages_sent'] += 1
            self.stats['bytes_sent'] += len(message_json)
            
            # Update connection info
            if connection_id in self.connection_info:
                conn_info = self.connection_info[connection_id]
                conn_info.message_count += 1
                conn_info.bytes_sent += len(message_json)
                conn_info.last_activity = datetime.utcnow()
            
            # Buffer message for potential resend
            self.message_buffer.add_message(connection_id, message)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message to {connection_id}: {e}")
            self.stats['errors'] += 1
            # Connection might be dead, remove it
            await self.disconnect_client(connection_id)
            return False
    
    async def broadcast_to_channel(self, channel: str, message: WebSocketMessage) -> int:
        """Wysyła wiadomość do wszystkich subskrybentów kanału"""
        subscribers = self.subscription_manager.get_subscribers(channel)
        sent_count = 0
        
        # Sort by priority (higher priority first)
        message_batches = defaultdict(list)
        for connection_id in subscribers:
            conn_info = self.connection_info.get(connection_id)
            if conn_info and conn_info.state == ConnectionState.ACTIVE:
                priority = message.priority
                message_batches[priority].append(connection_id)
        
        # Send to highest priority connections first
        for priority in sorted(message_batches.keys(), reverse=True):
            connections = message_batches[priority]
            
            # Send messages in parallel for this priority level
            tasks = []
            for connection_id in connections:
                task = asyncio.create_task(self.send_message(connection_id, message))
                tasks.append(task)
            
            # Wait for this priority batch to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            sent_count += sum(1 for result in results if result is True)
        
        logger.debug(f"Broadcasted message to {sent_count}/{len(subscribers)} subscribers of channel '{channel}'")
        return sent_count
    
    async def _handle_incoming_message(self, connection_id: str, raw_message: str):
        """Obsługuje przychodzącą wiadomość"""
        try:
            # Parse message
            message_data = json.loads(raw_message)
            message_type = message_data.get('type')
            
            # Update stats
            self.stats['messages_received'] += 1
            self.stats['bytes_received'] += len(raw_message)
            
            # Update connection info
            if connection_id in self.connection_info:
                conn_info = self.connection_info[connection_id]
                conn_info.last_activity = datetime.utcnow()
            
            # Check rate limiting
            if not self._check_rate_limit(connection_id):
                await self.send_message(connection_id, WebSocketMessage(
                    message_type=MessageType.ERROR,
                    data={"error": "Rate limit exceeded"},
                    timestamp=time.time(),
                    message_id=str(uuid.uuid4())
                ))
                return
            
            # Handle different message types
            if message_type == 'subscribe':
                await self._handle_subscribe(connection_id, message_data)
            elif message_type == 'unsubscribe':
                await self._handle_unsubscribe(connection_id, message_data)
            elif message_type == 'authenticate':
                await self._handle_authenticate(connection_id, message_data)
            elif message_type == 'heartbeat':
                await self._handle_heartbeat(connection_id)
            else:
                # Route to registered handlers
                if message_type in self.message_handlers:
                    await self.message_handlers[message_type](connection_id, message_data)
                else:
                    logger.warning(f"Unknown message type: {message_type}")
                    
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from connection {connection_id}")
            await self.send_message(connection_id, WebSocketMessage(
                message_type=MessageType.ERROR,
                data={"error": "Invalid JSON"},
                timestamp=time.time(),
                message_id=str(uuid.uuid4())
            ))
        except Exception as e:
            logger.error(f"Error handling message from {connection_id}: {e}")
            self.stats['errors'] += 1
    
    async def _handle_subscribe(self, connection_id: str, message_data: Dict[str, Any]):
        """Obsługuje żądanie subskrypcji"""
        channel = message_data.get('channel')
        if not channel:
            await self.send_message(connection_id, WebSocketMessage(
                message_type=MessageType.ERROR,
                data={"error": "Channel required for subscription"},
                timestamp=time.time(),
                message_id=str(uuid.uuid4())
            ))
            return
        
        success = self.subscription_manager.subscribe(connection_id, channel)
        
        await self.send_message(connection_id, WebSocketMessage(
            message_type=MessageType.SYSTEM_STATUS,
            data={
                "action": "subscribe",
                "channel": channel,
                "success": success
            },
            timestamp=time.time(),
            message_id=str(uuid.uuid4())
        ))
    
    async def _handle_unsubscribe(self, connection_id: str, message_data: Dict[str, Any]):
        """Obsługuje żądanie anulowania subskrypcji"""
        channel = message_data.get('channel')
        if not channel:
            await self.send_message(connection_id, WebSocketMessage(
                message_type=MessageType.ERROR,
                data={"error": "Channel required for unsubscription"},
                timestamp=time.time(),
                message_id=str(uuid.uuid4())
            ))
            return
        
        success = self.subscription_manager.unsubscribe(connection_id, channel)
        
        await self.send_message(connection_id, WebSocketMessage(
            message_type=MessageType.SYSTEM_STATUS,
            data={
                "action": "unsubscribe",
                "channel": channel,
                "success": success
            },
            timestamp=time.time(),
            message_id=str(uuid.uuid4())
        ))
    
    async def _handle_authenticate(self, connection_id: str, message_data: Dict[str, Any]):
        """Obsługuje uwierzytelnienie"""
        # Extract authentication data
        auth_token = message_data.get('token')
        user_id = message_data.get('user_id')
        
        # Update connection state
        if connection_id in self.connection_info:
            conn_info = self.connection_info[connection_id]
            conn_info.user_id = user_id or "anonymous"
            conn_info.state = ConnectionState.AUTHENTICATED
        
        await self.send_message(connection_id, WebSocketMessage(
            message_type=MessageType.SYSTEM_STATUS,
            data={
                "action": "authenticate",
                "success": True,
                "user_id": user_id
            },
            timestamp=time.time(),
            message_id=str(uuid.uuid4())
        ))
    
    async def _handle_heartbeat(self, connection_id: str):
        """Obsługuje heartbeat"""
        await self.send_message(connection_id, WebSocketMessage(
            message_type=MessageType.HEARTBEAT,
            data={"timestamp": time.time()},
            timestamp=time.time(),
            message_id=str(uuid.uuid4())
        ))
    
    def _check_rate_limit(self, connection_id: str) -> bool:
        """Sprawdza ograniczenia częstotliwości"""
        current_time = time.time()
        window_start = current_time - 60  # 1 minute window
        
        # Clean old timestamps
        rate_queue = self.rate_limits[connection_id]
        while rate_queue and rate_queue[0] < window_start:
            rate_queue.popleft()
        
        # Check if under limit
        if len(rate_queue) >= self.max_messages_per_minute:
            return False
        
        # Add current timestamp
        rate_queue.append(current_time)
        return True
    
    async def _periodic_cleanup(self):
        """Okresowe czyszczenie zasobów"""
        while self.running:
            try:
                # Clean up dead connections
                dead_connections = []
                for connection_id, websocket in self.connections.items():
                    if websocket.closed:
                        dead_connections.append(connection_id)
                
                for connection_id in dead_connections:
                    await self.disconnect_client(connection_id)
                
                # Clean up old rate limit data
                current_time = time.time()
                cutoff_time = current_time - 300  # 5 minutes
                
                for connection_id in list(self.rate_limits.keys()):
                    rate_queue = self.rate_limits[connection_id]
                    while rate_queue and rate_queue[0] < cutoff_time:
                        rate_queue.popleft()
                    
                    # Remove empty queues
                    if not rate_queue and connection_id not in self.connections:
                        del self.rate_limits[connection_id]
                
                logger.debug("Periodic cleanup completed")
                
            except Exception as e:
                logger.error(f"Error during periodic cleanup: {e}")
            
            await asyncio.sleep(60)  # Run every minute
    
    async def _periodic_heartbeat(self):
        """Okresowy heartbeat"""
        while self.running:
            try:
                # Send heartbeat to all active connections
                heartbeat_message = WebSocketMessage(
                    message_type=MessageType.HEARTBEAT,
                    data={
                        "server_time": time.time(),
                        "uptime": time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
                    },
                    timestamp=time.time(),
                    message_id=str(uuid.uuid4()),
                    expires_at=time.time() + 30  # Expire after 30 seconds
                )
                
                tasks = []
                for connection_id in list(self.connections.keys()):
                    task = asyncio.create_task(self.send_message(connection_id, heartbeat_message))
                    tasks.append(task)
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    logger.debug(f"Sent heartbeat to {len(tasks)} connections")
                
            except Exception as e:
                logger.error(f"Error during periodic heartbeat: {e}")
            
            await asyncio.sleep(30)  # Send heartbeat every 30 seconds
    
    async def _periodic_stats(self):
        """Okresowe statystyki"""
        while self.running:
            try:
                if self.stats['start_time']:
                    uptime = time.time() - self.stats['start_time']
                    messages_per_second = self.stats['messages_sent'] / uptime if uptime > 0 else 0
                    
                    logger.info(f"WebSocket Server Stats - "
                              f"Connections: {self.stats['active_connections']}, "
                              f"Messages/s: {messages_per_second:.2f}, "
                              f"Errors: {self.stats['errors']}")
                
            except Exception as e:
                logger.error(f"Error during periodic stats: {e}")
            
            await asyncio.sleep(300)  # Log stats every 5 minutes

    def get_connection_stats(self) -> Dict[str, Any]:
        """Pobiera statystyki połączeń"""
        return {
            'total_connections': self.stats['total_connections'],
            'active_connections': self.stats['active_connections'],
            'messages_sent': self.stats['messages_sent'],
            'messages_received': self.stats['messages_received'],
            'bytes_sent': self.stats['bytes_sent'],
            'bytes_received': self.stats['bytes_received'],
            'errors': self.stats['errors'],
            'uptime': time.time() - self.stats['start_time'] if self.stats['start_time'] else 0,
            'channels': len(self.subscription_manager.subscriptions),
            'total_subscriptions': sum(len(subs) for subs in self.subscription_manager.subscriptions.values())
        }

# ==================================================================================
# 🎯 DATA STREAM PUBLISHERS
# ==================================================================================

class DataStreamPublisher:
    """Publikuje różne typy danych do WebSocket"""
    
    def __init__(self, websocket_server: WebSocketServer):
        self.server = websocket_server
        
    async def publish_position_update(self, position_data: Dict[str, Any]):
        """Publikuje aktualizację pozycji"""
        message = WebSocketMessage(
            message_type=MessageType.POSITION_UPDATE,
            data=position_data,
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
            priority=4
        )
        
        # Broadcast to position subscribers
        channel = f"positions.{position_data.get('symbol', 'all')}"
        await self.server.broadcast_to_channel(channel, message)
        
        # Broadcast to user-specific channel
        user_id = position_data.get('user_id')
        if user_id:
            user_channel = f"user.{user_id}.positions"
            await self.server.broadcast_to_channel(user_channel, message)
    
    async def publish_price_update(self, symbol: str, price_data: Dict[str, Any]):
        """Publikuje aktualizację ceny"""
        message = WebSocketMessage(
            message_type=MessageType.PRICE_FEED,
            data={
                'symbol': symbol,
                **price_data
            },
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
            priority=3,
            expires_at=time.time() + 10  # Price data expires quickly
        )
        
        # Broadcast to price subscribers
        await self.server.broadcast_to_channel(f"prices.{symbol}", message)
        await self.server.broadcast_to_channel("prices.all", message)
    
    async def publish_portfolio_change(self, user_id: str, portfolio_data: Dict[str, Any]):
        """Publikuje zmianę portfolio"""
        message = WebSocketMessage(
            message_type=MessageType.PORTFOLIO_CHANGE,
            data=portfolio_data,
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
            priority=4
        )
        
        # Broadcast to user's portfolio channel
        await self.server.broadcast_to_channel(f"user.{user_id}.portfolio", message)
    
    async def publish_risk_alert(self, alert_data: Dict[str, Any]):
        """Publikuje alert ryzyka"""
        message = WebSocketMessage(
            message_type=MessageType.RISK_ALERT,
            data=alert_data,
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
            priority=5  # High priority
        )
        
        # Broadcast to risk alert channels
        severity = alert_data.get('severity', 'medium')
        await self.server.broadcast_to_channel(f"alerts.risk.{severity}", message)
        
        # User-specific alerts
        user_id = alert_data.get('user_id')
        if user_id:
            await self.server.broadcast_to_channel(f"user.{user_id}.alerts", message)
    
    async def publish_order_status(self, order_data: Dict[str, Any]):
        """Publikuje status zamówienia"""
        message = WebSocketMessage(
            message_type=MessageType.ORDER_STATUS,
            data=order_data,
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
            priority=4
        )
        
        # Broadcast to order channels
        user_id = order_data.get('user_id')
        if user_id:
            await self.server.broadcast_to_channel(f"user.{user_id}.orders", message)
        
        symbol = order_data.get('symbol')
        if symbol:
            await self.server.broadcast_to_channel(f"orders.{symbol}", message)
    
    async def publish_ai_signal(self, signal_data: Dict[str, Any]):
        """Publikuje sygnał AI"""
        message = WebSocketMessage(
            message_type=MessageType.AI_SIGNAL,
            data=signal_data,
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
            priority=3
        )
        
        # Broadcast to AI signal channels
        signal_type = signal_data.get('type', 'general')
        await self.server.broadcast_to_channel(f"signals.ai.{signal_type}", message)
        
        symbol = signal_data.get('symbol')
        if symbol:
            await self.server.broadcast_to_channel(f"signals.{symbol}", message)

# ==================================================================================
# 📝 USAGE EXAMPLE
# ==================================================================================

async def example_usage():
    """Przykład użycia systemu WebSocket"""
    
    # Create and start WebSocket server
    server = WebSocketServer(host="0.0.0.0", port=8765)
    
    # Register custom message handlers
    async def handle_custom_message(connection_id: str, message_data: Dict[str, Any]):
        logger.info(f"Received custom message from {connection_id}: {message_data}")
    
    server.register_handler("custom_message", handle_custom_message)
    
    # Add middleware for message filtering
    async def auth_middleware(message: WebSocketMessage, connection_id: str) -> Optional[WebSocketMessage]:
        # Example: Only allow certain message types for non-authenticated users
        conn_info = server.connection_info.get(connection_id)
        if conn_info and conn_info.state != ConnectionState.AUTHENTICATED:
            if message.message_type not in [MessageType.SYSTEM_STATUS, MessageType.HEARTBEAT]:
                return None  # Block message
        return message
    
    server.add_middleware(auth_middleware)
    
    # Start server
    await server.start_server()
    
    # Create data publisher
    publisher = DataStreamPublisher(server)
    
    # Example: Publish some data
    await publisher.publish_price_update("BTC/USDT", {
        "price": 50000.0,
        "bid": 49995.0,
        "ask": 50005.0,
        "volume": 1250.5
    })
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await server.stop_server()

if __name__ == "__main__":
    asyncio.run(example_usage())
