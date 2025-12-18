"""
FASTAPI WEBSOCKET INTEGRATION
Integracja WebSocket z FastAPI - łączy real-time system z API
"""

# ==================================================================================
# 🔗 FASTAPI WEBSOCKET INTEGRATION
# ==================================================================================

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import uuid

# Import our WebSocket system
from websocket_realtime_system import WebSocketServer, DataStreamPublisher, WebSocketMessage, MessageType

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FastAPIWebSocketIntegration:
    """Integracja WebSocket z FastAPI"""
    
    def __init__(self, app: FastAPI):
        self.app = app
        self.websocket_server = WebSocketServer()
        self.data_publisher = DataStreamPublisher(self.websocket_server)
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_info: Dict[str, Dict[str, Any]] = {}
        
        # Setup WebSocket routes
        self._setup_websocket_routes()
        
        # Setup CORS for WebSocket
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_websocket_routes(self):
        """Konfiguruje trasy WebSocket w FastAPI"""
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self._handle_websocket_connection(websocket)
        
        @self.app.websocket("/ws/trading")
        async def trading_websocket(websocket: WebSocket):
            await self._handle_trading_websocket(websocket)
        
        @self.app.websocket("/ws/analytics")
        async def analytics_websocket(websocket: WebSocket):
            await self._handle_analytics_websocket(websocket)
        
        @self.app.websocket("/ws/portfolio/{user_id}")
        async def portfolio_websocket(websocket: WebSocket, user_id: str):
            await self._handle_portfolio_websocket(websocket, user_id)
    
    async def _handle_websocket_connection(self, websocket: WebSocket):
        """Obsługuje główne połączenie WebSocket"""
        connection_id = str(uuid.uuid4())
        
        try:
            await websocket.accept()
            self.active_connections[connection_id] = websocket
            
            # Store connection info
            self.connection_info[connection_id] = {
                "connected_at": datetime.utcnow(),
                "subscriptions": set(),
                "user_id": None,
                "last_activity": datetime.utcnow()
            }
            
            logger.info(f"WebSocket connection established: {connection_id}")
            
            # Send welcome message
            await self._send_message(connection_id, {
                "type": "connection_established",
                "data": {
                    "connection_id": connection_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "server_time": datetime.utcnow().timestamp()
                }
            })
            
            # Handle incoming messages
            while True:
                try:
                    # Receive message with timeout
                    message = await asyncio.wait_for(
                        websocket.receive_text(), 
                        timeout=300.0  # 5 minutes timeout
                    )
                    
                    await self._process_websocket_message(connection_id, message)
                    
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    await self._send_heartbeat(connection_id)
                    
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected: {connection_id}")
                    break
                    
        except Exception as e:
            logger.error(f"WebSocket error for {connection_id}: {e}")
        finally:
            await self._cleanup_connection(connection_id)
    
    async def _handle_trading_websocket(self, websocket: WebSocket):
        """Obsługuje WebSocket dedykowany tradingowi"""
        connection_id = f"trading_{uuid.uuid4()}"
        
        try:
            await websocket.accept()
            self.active_connections[connection_id] = websocket
            
            # Auto-subscribe to trading channels
            await self._auto_subscribe_trading(connection_id)
            
            logger.info(f"Trading WebSocket established: {connection_id}")
            
            while True:
                message = await websocket.receive_text()
                await self._process_trading_message(connection_id, message)
                
        except WebSocketDisconnect:
            logger.info(f"Trading WebSocket disconnected: {connection_id}")
        finally:
            await self._cleanup_connection(connection_id)
    
    async def _handle_analytics_websocket(self, websocket: WebSocket):
        """Obsługuje WebSocket dla analityki"""
        connection_id = f"analytics_{uuid.uuid4()}"
        
        try:
            await websocket.accept()
            self.active_connections[connection_id] = websocket
            
            # Auto-subscribe to analytics channels
            await self._auto_subscribe_analytics(connection_id)
            
            logger.info(f"Analytics WebSocket established: {connection_id}")
            
            while True:
                message = await websocket.receive_text()
                await self._process_analytics_message(connection_id, message)
                
        except WebSocketDisconnect:
            logger.info(f"Analytics WebSocket disconnected: {connection_id}")
        finally:
            await self._cleanup_connection(connection_id)
    
    async def _handle_portfolio_websocket(self, websocket: WebSocket, user_id: str):
        """Obsługuje WebSocket dla konkretnego portfolio użytkownika"""
        connection_id = f"portfolio_{user_id}_{uuid.uuid4()}"
        
        try:
            await websocket.accept()
            self.active_connections[connection_id] = websocket
            
            # Store user info
            if connection_id not in self.connection_info:
                self.connection_info[connection_id] = {"subscriptions": set()}
            
            self.connection_info[connection_id]["user_id"] = user_id
            
            # Auto-subscribe to user-specific channels
            await self._auto_subscribe_portfolio(connection_id, user_id)
            
            logger.info(f"Portfolio WebSocket established for user {user_id}: {connection_id}")
            
            while True:
                message = await websocket.receive_text()
                await self._process_portfolio_message(connection_id, message, user_id)
                
        except WebSocketDisconnect:
            logger.info(f"Portfolio WebSocket disconnected for user {user_id}: {connection_id}")
        finally:
            await self._cleanup_connection(connection_id)
    
    async def _process_websocket_message(self, connection_id: str, raw_message: str):
        """Przetwarza ogólne wiadomości WebSocket"""
        try:
            message = json.loads(raw_message)
            message_type = message.get("type")
            
            # Update last activity
            if connection_id in self.connection_info:
                self.connection_info[connection_id]["last_activity"] = datetime.utcnow()
            
            if message_type == "subscribe":
                await self._handle_subscription(connection_id, message)
                
            elif message_type == "unsubscribe":
                await self._handle_unsubscription(connection_id, message)
                
            elif message_type == "authenticate":
                await self._handle_authentication(connection_id, message)
                
            elif message_type == "ping":
                await self._send_message(connection_id, {"type": "pong", "timestamp": datetime.utcnow().timestamp()})
                
            elif message_type == "get_status":
                await self._send_status_update(connection_id)
                
            else:
                logger.warning(f"Unknown message type from {connection_id}: {message_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from {connection_id}: {raw_message}")
            await self._send_error(connection_id, "Invalid JSON format")
        except Exception as e:
            logger.error(f"Error processing message from {connection_id}: {e}")
            await self._send_error(connection_id, f"Message processing error: {str(e)}")
    
    async def _process_trading_message(self, connection_id: str, raw_message: str):
        """Przetwarza wiadomości z trading WebSocket"""
        try:
            message = json.loads(raw_message)
            action = message.get("action")
            
            if action == "place_order":
                await self._handle_place_order(connection_id, message)
            elif action == "cancel_order":
                await self._handle_cancel_order(connection_id, message)
            elif action == "close_position":
                await self._handle_close_position(connection_id, message)
            elif action == "get_positions":
                await self._handle_get_positions(connection_id, message)
            else:
                logger.warning(f"Unknown trading action: {action}")
                
        except Exception as e:
            logger.error(f"Error processing trading message: {e}")
            await self._send_error(connection_id, f"Trading error: {str(e)}")
    
    async def _process_analytics_message(self, connection_id: str, raw_message: str):
        """Przetwarza wiadomości z analytics WebSocket"""
        try:
            message = json.loads(raw_message)
            request_type = message.get("type")
            
            if request_type == "calculate_metrics":
                await self._handle_calculate_metrics(connection_id, message)
            elif request_type == "get_performance":
                await self._handle_get_performance(connection_id, message)
            elif request_type == "risk_analysis":
                await self._handle_risk_analysis(connection_id, message)
            else:
                logger.warning(f"Unknown analytics request: {request_type}")
                
        except Exception as e:
            logger.error(f"Error processing analytics message: {e}")
            await self._send_error(connection_id, f"Analytics error: {str(e)}")
    
    async def _process_portfolio_message(self, connection_id: str, raw_message: str, user_id: str):
        """Przetwarza wiadomości z portfolio WebSocket"""
        try:
            message = json.loads(raw_message)
            action = message.get("action")
            
            if action == "get_portfolio":
                await self._handle_get_portfolio(connection_id, user_id)
            elif action == "get_history":
                await self._handle_get_history(connection_id, user_id, message)
            elif action == "set_alerts":
                await self._handle_set_alerts(connection_id, user_id, message)
            else:
                logger.warning(f"Unknown portfolio action: {action}")
                
        except Exception as e:
            logger.error(f"Error processing portfolio message: {e}")
            await self._send_error(connection_id, f"Portfolio error: {str(e)}")
    
    async def _handle_subscription(self, connection_id: str, message: Dict[str, Any]):
        """Obsługuje subskrypcję kanału"""
        channel = message.get("channel")
        if not channel:
            await self._send_error(connection_id, "Channel required for subscription")
            return
        
        # Add to connection subscriptions
        if connection_id in self.connection_info:
            self.connection_info[connection_id]["subscriptions"].add(channel)
        
        await self._send_message(connection_id, {
            "type": "subscription_confirmed",
            "data": {
                "channel": channel,
                "status": "subscribed"
            }
        })
        
        logger.info(f"Connection {connection_id} subscribed to {channel}")
    
    async def _auto_subscribe_trading(self, connection_id: str):
        """Auto-subskrypcja do kanałów tradingowych"""
        channels = [
            "positions.all",
            "orders.all", 
            "trades.all",
            "prices.all",
            "market_data.all"
        ]
        
        for channel in channels:
            await self._handle_subscription(connection_id, {"channel": channel})
    
    async def _auto_subscribe_analytics(self, connection_id: str):
        """Auto-subskrypcja do kanałów analitycznych"""
        channels = [
            "analytics.performance",
            "analytics.risk",
            "analytics.portfolio",
            "analytics.market"
        ]
        
        for channel in channels:
            await self._handle_subscription(connection_id, {"channel": channel})
    
    async def _auto_subscribe_portfolio(self, connection_id: str, user_id: str):
        """Auto-subskrypcja do kanałów portfolio użytkownika"""
        channels = [
            f"user.{user_id}.portfolio",
            f"user.{user_id}.positions", 
            f"user.{user_id}.orders",
            f"user.{user_id}.alerts",
            f"user.{user_id}.analytics"
        ]
        
        for channel in channels:
            await self._handle_subscription(connection_id, {"channel": channel})
    
    async def _send_message(self, connection_id: str, message: Dict[str, Any]):
        """Wysyła wiadomość do konkretnego połączenia"""
        if connection_id in self.active_connections:
            try:
                websocket = self.active_connections[connection_id]
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Failed to send message to {connection_id}: {e}")
                await self._cleanup_connection(connection_id)
    
    async def _send_error(self, connection_id: str, error_message: str):
        """Wysyła wiadomość o błędzie"""
        await self._send_message(connection_id, {
            "type": "error",
            "data": {
                "message": error_message,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def _send_heartbeat(self, connection_id: str):
        """Wysyła heartbeat"""
        await self._send_message(connection_id, {
            "type": "heartbeat",
            "data": {
                "timestamp": datetime.utcnow().timestamp(),
                "server_time": datetime.utcnow().isoformat()
            }
        })
    
    async def _send_status_update(self, connection_id: str):
        """Wysyła aktualizację statusu"""
        conn_info = self.connection_info.get(connection_id, {})
        
        await self._send_message(connection_id, {
            "type": "status_update",
            "data": {
                "connection_id": connection_id,
                "connected_at": conn_info.get("connected_at", datetime.utcnow()).isoformat(),
                "subscriptions": list(conn_info.get("subscriptions", set())),
                "user_id": conn_info.get("user_id"),
                "last_activity": conn_info.get("last_activity", datetime.utcnow()).isoformat(),
                "server_time": datetime.utcnow().isoformat()
            }
        })
    
    async def _cleanup_connection(self, connection_id: str):
        """Czyści połączenie"""
        self.active_connections.pop(connection_id, None)
        self.connection_info.pop(connection_id, None)
        logger.info(f"Cleaned up connection: {connection_id}")
    
    # Trading-specific handlers
    async def _handle_place_order(self, connection_id: str, message: Dict[str, Any]):
        """Obsługuje składanie zlecenia"""
        # This requires integration with a real trading system
        await self._send_message(connection_id, {
            "type": "order_response", 
            "data": {
                "status": "error",
                "message": "Trading functionality not implemented",
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def _handle_get_positions(self, connection_id: str, message: Dict[str, Any]):
        """Obsługuje pobieranie pozycji"""
        # This requires integration with a real trading system
        await self._send_message(connection_id, {
            "type": "positions_data",
            "data": {
                "positions": [],
                "message": "Position data not available - trading system not integrated",
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    # Analytics-specific handlers
    async def _handle_calculate_metrics(self, connection_id: str, message: Dict[str, Any]):
        """Obsługuje obliczanie metryk"""
        # This requires integration with real analytics system
        await self._send_message(connection_id, {
            "type": "metrics_calculated",
            "data": {
                "metrics": {},
                "message": "Analytics not available - metrics calculation system not integrated",
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    # Portfolio-specific handlers  
    async def _handle_get_portfolio(self, connection_id: str, user_id: str):
        """Obsługuje pobieranie portfolio"""
        # This requires integration with real portfolio system
        await self._send_message(connection_id, {
            "type": "portfolio_update",
            "data": {
                "portfolio": {},
                "message": "Portfolio data not available - portfolio system not integrated", 
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def broadcast_to_channel(self, channel: str, message: Dict[str, Any]):
        """Broadcastuje wiadomość do wszystkich subskrybentów kanału"""
        for connection_id, conn_info in self.connection_info.items():
            if channel in conn_info.get("subscriptions", set()):
                await self._send_message(connection_id, message)
    
    async def broadcast_to_user(self, user_id: str, message: Dict[str, Any]):
        """Broadcastuje wiadomość do konkretnego użytkownika"""
        for connection_id, conn_info in self.connection_info.items():
            if conn_info.get("user_id") == user_id:
                await self._send_message(connection_id, message)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Pobiera statystyki połączeń"""
        return {
            "total_connections": len(self.active_connections),
            "connections_by_type": {
                "general": len([c for c in self.active_connections.keys() if not c.startswith(("trading_", "analytics_", "portfolio_"))]),
                "trading": len([c for c in self.active_connections.keys() if c.startswith("trading_")]),
                "analytics": len([c for c in self.active_connections.keys() if c.startswith("analytics_")]),
                "portfolio": len([c for c in self.active_connections.keys() if c.startswith("portfolio_")])
            },
            "total_subscriptions": sum(len(info.get("subscriptions", set())) for info in self.connection_info.values()),
            "authenticated_users": len({info.get("user_id") for info in self.connection_info.values() if info.get("user_id")})
        }

# ==================================================================================
# 📊 USAGE WITH EXISTING FASTAPI APP
# ==================================================================================

def setup_websocket_integration(app: FastAPI) -> FastAPIWebSocketIntegration:
    """Konfiguruje integrację WebSocket z istniejącą aplikacją FastAPI"""
    
    # Create WebSocket integration
    ws_integration = FastAPIWebSocketIntegration(app)
    
    # Add WebSocket status endpoint
    @app.get("/ws/status")
    async def websocket_status():
        """Zwraca status połączeń WebSocket"""
        return ws_integration.get_connection_stats()
    
    # Add WebSocket test page
    @app.get("/ws/test")
    async def websocket_test():
        """Strona testowa WebSocket"""
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>WebSocket Test</title>
        </head>
        <body>
            <h1>WebSocket Connection Test</h1>
            <div id="status">Disconnected</div>
            <button onclick="connect()">Connect</button>
            <button onclick="disconnect()">Disconnect</button>
            <button onclick="subscribe()">Subscribe to Prices</button>
            <div id="messages"></div>
            
            <script>
                let ws = null;
                
                function connect() {
                    ws = new WebSocket('ws://localhost:8000/ws');
                    
                    ws.onopen = function() {
                        document.getElementById('status').textContent = 'Connected';
                    };
                    
                    ws.onmessage = function(event) {
                        const message = JSON.parse(event.data);
                        const div = document.createElement('div');
                        div.textContent = JSON.stringify(message, null, 2);
                        document.getElementById('messages').appendChild(div);
                    };
                    
                    ws.onclose = function() {
                        document.getElementById('status').textContent = 'Disconnected';
                    };
                }
                
                function disconnect() {
                    if (ws) {
                        ws.close();
                    }
                }
                
                function subscribe() {
                    if (ws) {
                        ws.send(JSON.stringify({
                            type: 'subscribe',
                            channel: 'prices.all'
                        }));
                    }
                }
            </script>
        </body>
        </html>
        """)
    
    logger.info("✅ WebSocket integration setup completed")
    return ws_integration

# ==================================================================================
# 📝 EXAMPLE USAGE
# ==================================================================================

if __name__ == "__main__":
    # Example of how to integrate with existing FastAPI app
    from fastapi import FastAPI
    
    app = FastAPI(title="Trading Platform with WebSocket")
    
    # Setup WebSocket integration
    ws_integration = setup_websocket_integration(app)
    
    # Example API endpoints that can trigger WebSocket broadcasts
    @app.post("/api/orders")
    async def create_order(order_data: dict):
        # Process order...
        
        # Broadcast order update
        await ws_integration.broadcast_to_channel("orders.all", {
            "type": "order_update",
            "data": order_data,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {"status": "order_created", "order_id": str(uuid.uuid4())}
    
    @app.post("/api/positions/{position_id}/close")
    async def close_position(position_id: str):
        # Close position...
        
        # Broadcast position update
        await ws_integration.broadcast_to_channel("positions.all", {
            "type": "position_closed",
            "data": {"position_id": position_id, "status": "closed"},
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {"status": "position_closed", "position_id": position_id}
    
    print("FastAPI WebSocket Integration Example")
    print("Run with: uvicorn filename:app --reload")
    print("Test at: http://localhost:8000/ws/test")
