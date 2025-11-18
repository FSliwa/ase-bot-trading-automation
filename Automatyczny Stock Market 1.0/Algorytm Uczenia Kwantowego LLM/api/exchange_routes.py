"""
FastAPI Routes for Exchange Connection Management
Comprehensive API endpoints for user panel integration

Note: This module requires FastAPI and Pydantic to be installed.
Install with: pip install fastapi pydantic uvicorn
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Union

# Import optional dependencies
try:
    from fastapi import APIRouter, HTTPException, Depends, Query, Body, BackgroundTasks
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field, validator
    FASTAPI_AVAILABLE = True
    
    # Security
    security = HTTPBearer()
    
except ImportError as e:
    # Provide fallback classes for development/testing
    FASTAPI_AVAILABLE = False
    print(f"FastAPI not available: {e}")
    print("To use Exchange API routes, install: pip install fastapi pydantic uvicorn")
    
    # Minimal fallback classes
    class APIRouter:
        def __init__(self, *args, **kwargs):
            pass
        def get(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        def post(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        def delete(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        def on_event(self, event):
            def decorator(func):
                return func
            return decorator
    
    class HTTPException(Exception):
        def __init__(self, status_code, detail):
            self.status_code = status_code
            self.detail = detail
    
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    def Depends(dependency):
        return dependency
    
    def Query(*args, **kwargs):
        return None
        
    def Body(*args, **kwargs):
        return None
        
    def Field(*args, **kwargs):
        if args:
            return args[0]
        return None
    
    def validator(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    class HTTPBearer:
        pass
    
    class HTTPAuthorizationCredentials:
        pass
    
    class JSONResponse:
        def __init__(self, content, status_code=200):
            self.content = content
            self.status_code = status_code
    
    class BackgroundTasks:
        pass
    
    security = HTTPBearer()

from core.exchange_connection_manager import (
    ExchangeConnectionManager, ExchangeType, ExchangeCredentials, 
    ConnectionMode, ConnectionStatus
)
from core.performance_optimizer import performance_optimizer, optimize_api_request, get_system_performance_stats

logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()

# Pydantic models for API
class ExchangeTypeEnum(str, Enum):
    binance = "binance"
    coinbase_pro = "coinbasepro"
    kraken = "kraken"
    okx = "okx"
    bybit = "bybit"

class ConnectionModeEnum(str, Enum):
    testnet = "testnet"
    production = "production"

class CreateConnectionRequest(BaseModel):
    exchange: ExchangeTypeEnum
    connection_mode: ConnectionModeEnum = ConnectionModeEnum.testnet
    
    # API Key authentication
    api_key: Optional[str] = Field(None, description="Exchange API key")
    api_secret: Optional[str] = Field(None, description="Exchange API secret") 
    passphrase: Optional[str] = Field(None, description="API passphrase (required for Coinbase Pro, OKX)")
    
    # OAuth authentication 
    oauth_code: Optional[str] = Field(None, description="OAuth authorization code")
    oauth_state: Optional[str] = Field(None, description="OAuth state parameter")
    
    @validator('api_key', 'api_secret')
    def validate_credentials(cls, v, values):
        # At least one authentication method should be provided
        return v

class ConnectionResponse(BaseModel):
    id: str
    user_id: str
    exchange: str
    status: str
    created_at: str
    last_used: str
    testnet: bool
    connection_type: str
    stats: Dict[str, Union[int, float]]

class ExchangeInfoResponse(BaseModel):
    exchange: str
    display_name: str
    supports_oauth: bool
    supports_testnet: bool
    rate_limits: Dict[str, int]
    required_credentials: List[str]
    connection_methods: List[str]

class ConnectionStatsResponse(BaseModel):
    total_connections: int
    active_connections: int
    successful_connections: int
    failed_connections: int
    oauth_connections: int
    api_key_connections: int
    connections_by_exchange: Dict[str, int]
    connections_by_status: Dict[str, int]
    oauth_percentage: float

class TestCredentialsRequest(BaseModel):
    exchange: ExchangeTypeEnum
    connection_mode: ConnectionModeEnum = ConnectionModeEnum.testnet
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None

class OAuthInitRequest(BaseModel):
    exchange: ExchangeTypeEnum
    redirect_uri: str = Field(..., description="OAuth redirect URI")

class QRCodeRequest(BaseModel):
    exchange: ExchangeTypeEnum
    connection_data: Dict[str, Any] = Field(default_factory=dict)

class ExchangeRequestModel(BaseModel):
    method: str = Field(..., description="Exchange method to call")
    args: List[Any] = Field(default_factory=list, description="Method arguments")
    kwargs: Dict[str, Any] = Field(default_factory=dict, description="Method keyword arguments")

# Initialize exchange manager
exchange_manager = None

# Dependency to get current user (placeholder - integrate with your auth system)
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Get current user ID from JWT token - integrate with your auth system"""
    # This is a placeholder - implement your actual authentication logic
    # For now, return a test user ID
    return "user_12345"

# Dependency to get exchange manager
async def get_exchange_manager() -> ExchangeConnectionManager:
    """Get exchange manager instance"""
    global exchange_manager
    if not exchange_manager:
        if not performance_optimizer.initialized:
            await performance_optimizer.initialize()
        exchange_manager = ExchangeConnectionManager(performance_optimizer.connection_manager)
    return exchange_manager

# Create router
router = APIRouter(prefix="/api/v1/exchanges", tags=["exchanges"])

@router.get("/supported", response_model=List[ExchangeInfoResponse])
async def list_supported_exchanges(
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """List all supported exchanges with their capabilities"""
    
    async def _get_exchanges():
        return await exchange_mgr.list_supported_exchanges()
    
    exchanges = await optimize_api_request(_get_exchanges)
    return exchanges

@router.get("/{exchange}/info", response_model=ExchangeInfoResponse)
async def get_exchange_info(
    exchange: ExchangeTypeEnum,
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Get detailed information about a specific exchange"""
    
    try:
        exchange_type = ExchangeType(exchange.value)
        
        async def _get_info():
            return await exchange_mgr.get_exchange_info(exchange_type)
        
        info = await optimize_api_request(_get_info)
        return info
    
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported exchange: {exchange}")
    except Exception as e:
        logger.error(f"Error getting exchange info: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get exchange information")

@router.post("/test-credentials")
async def test_credentials(
    request: TestCredentialsRequest,
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Test exchange credentials without creating a connection"""
    
    try:
        # Create credentials object
        credentials = ExchangeCredentials(
            exchange=ExchangeType(request.exchange.value),
            api_key=exchange_mgr.encryption.encrypt(request.api_key) if request.api_key else None,
            api_secret=exchange_mgr.encryption.encrypt(request.api_secret) if request.api_secret else None,
            passphrase=exchange_mgr.encryption.encrypt(request.passphrase) if request.passphrase else None,
            testnet=request.connection_mode == ConnectionModeEnum.testnet
        )
        
        async def _test_credentials():
            return await exchange_mgr.test_connection_credentials(
                ExchangeType(request.exchange.value), credentials
            )
        
        result = await optimize_api_request(_test_credentials)
        
        if result['success']:
            return JSONResponse(content=result, status_code=200)
        else:
            return JSONResponse(content=result, status_code=400)
    
    except Exception as e:
        logger.error(f"Credential test error: {str(e)}")
        return JSONResponse(
            content={'success': False, 'error': str(e)}, 
            status_code=500
        )

@router.post("/connections", response_model=Dict[str, Any])
async def create_connection(
    request: CreateConnectionRequest,
    current_user: str = Depends(get_current_user),
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Create a new exchange connection"""
    
    try:
        exchange_type = ExchangeType(request.exchange.value)
        
        # Create credentials based on authentication method
        if request.oauth_code and request.oauth_state:
            # OAuth flow
            oauth_result = await exchange_mgr.handle_oauth_callback(
                exchange_type, request.oauth_code, request.oauth_state
            )
            
            if not oauth_result['success']:
                raise HTTPException(status_code=400, detail=oauth_result['error'])
            
            credentials = ExchangeCredentials(**oauth_result['credentials'])
        
        elif request.api_key and request.api_secret:
            # API Key flow
            credentials = ExchangeCredentials(
                exchange=exchange_type,
                api_key=exchange_mgr.encryption.encrypt(request.api_key),
                api_secret=exchange_mgr.encryption.encrypt(request.api_secret),
                passphrase=exchange_mgr.encryption.encrypt(request.passphrase) if request.passphrase else None,
                testnet=request.connection_mode == ConnectionModeEnum.testnet
            )
        
        else:
            raise HTTPException(
                status_code=400, 
                detail="Either OAuth credentials or API key/secret must be provided"
            )
        
        # Create connection
        async def _create_connection():
            return await exchange_mgr.create_connection(exchange_type, credentials, current_user)
        
        connection_id = await optimize_api_request(_create_connection)
        
        # Get connection info
        connection_info = await exchange_mgr.get_connection(connection_id)
        
        return {
            'success': True,
            'connection_id': connection_id,
            'connection': connection_info
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Connection creation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create connection: {str(e)}")

@router.get("/connections", response_model=List[ConnectionResponse])
async def list_connections(
    current_user: str = Depends(get_current_user),
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """List all connections for the current user"""
    
    async def _list_connections():
        return await exchange_mgr.list_user_connections(current_user)
    
    connections = await optimize_api_request(_list_connections)
    return connections

@router.get("/connections/{connection_id}", response_model=ConnectionResponse)
async def get_connection(
    connection_id: str,
    current_user: str = Depends(get_current_user),
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Get specific connection details"""
    
    async def _get_connection():
        return await exchange_mgr.get_connection(connection_id)
    
    connection = await optimize_api_request(_get_connection)
    
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # Verify ownership
    if connection['user_id'] != current_user:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return connection

@router.delete("/connections/{connection_id}")
async def disconnect_connection(
    connection_id: str,
    current_user: str = Depends(get_current_user),
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Disconnect and remove an exchange connection"""
    
    # Verify connection exists and ownership
    connection = await exchange_mgr.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    if connection['user_id'] != current_user:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Disconnect
    async def _disconnect():
        return await exchange_mgr.disconnect_connection(connection_id)
    
    success = await optimize_api_request(_disconnect)
    
    if success:
        return {'success': True, 'message': 'Connection disconnected successfully'}
    else:
        raise HTTPException(status_code=500, detail="Failed to disconnect connection")

@router.post("/oauth/init")
async def initialize_oauth(
    request: OAuthInitRequest,
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Initialize OAuth flow for an exchange"""
    
    try:
        exchange_type = ExchangeType(request.exchange.value)
        
        async def _init_oauth():
            return await exchange_mgr.generate_oauth_url(exchange_type, request.redirect_uri)
        
        result = await optimize_api_request(_init_oauth)
        
        if result['success']:
            return result
        else:
            raise HTTPException(status_code=400, detail=result['error'])
    
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Exchange does not support OAuth: {request.exchange}")
    except Exception as e:
        logger.error(f"OAuth initialization error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to initialize OAuth")

@router.post("/qr-code")
async def generate_qr_code(
    request: QRCodeRequest,
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Generate QR code for mobile connection"""
    
    try:
        exchange_type = ExchangeType(request.exchange.value)
        
        async def _generate_qr():
            return await exchange_mgr.generate_connection_qr(exchange_type, request.connection_data)
        
        qr_code = await optimize_api_request(_generate_qr)
        
        return {
            'success': True,
            'qr_code': qr_code,
            'exchange': request.exchange.value
        }
    
    except Exception as e:
        logger.error(f"QR code generation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate QR code")

@router.post("/connections/{connection_id}/execute")
async def execute_exchange_request(
    connection_id: str,
    request: ExchangeRequestModel,
    current_user: str = Depends(get_current_user),
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Execute a method on an exchange connection"""
    
    # Verify connection exists and ownership
    connection = await exchange_mgr.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    if connection['user_id'] != current_user:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Execute request
    async def _execute_request():
        return await exchange_mgr.execute_exchange_request(
            connection_id, request.method, *request.args, **request.kwargs
        )
    
    result = await optimize_api_request(_execute_request)
    
    if result['success']:
        return result
    else:
        raise HTTPException(status_code=400, detail=result['error'])

@router.get("/connections/{connection_id}/balance")
async def get_balance(
    connection_id: str,
    current_user: str = Depends(get_current_user),
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Get account balance from exchange connection"""
    
    return await execute_exchange_request(
        connection_id,
        ExchangeRequestModel(method="fetch_balance"),
        current_user,
        exchange_mgr
    )

@router.get("/connections/{connection_id}/markets")
async def get_markets(
    connection_id: str,
    current_user: str = Depends(get_current_user),
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Get available markets from exchange connection"""
    
    return await execute_exchange_request(
        connection_id,
        ExchangeRequestModel(method="fetch_markets"),
        current_user,
        exchange_mgr
    )

@router.get("/connections/{connection_id}/ticker")
async def get_ticker(
    connection_id: str,
    symbol: str = Query(..., description="Trading pair symbol (e.g., BTC/USDT)"),
    current_user: str = Depends(get_current_user),
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Get ticker information for a symbol"""
    
    return await execute_exchange_request(
        connection_id,
        ExchangeRequestModel(method="fetch_ticker", args=[symbol]),
        current_user,
        exchange_mgr
    )

@router.get("/connections/{connection_id}/orderbook")
async def get_orderbook(
    connection_id: str,
    symbol: str = Query(..., description="Trading pair symbol"),
    limit: Optional[int] = Query(None, description="Number of orders to fetch"),
    current_user: str = Depends(get_current_user),
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Get order book for a symbol"""
    
    args = [symbol]
    if limit:
        args.append(limit)
    
    return await execute_exchange_request(
        connection_id,
        ExchangeRequestModel(method="fetch_order_book", args=args),
        current_user,
        exchange_mgr
    )

@router.get("/connections/{connection_id}/orders")
async def get_orders(
    connection_id: str,
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    since: Optional[int] = Query(None, description="Filter orders since timestamp"),
    limit: Optional[int] = Query(None, description="Maximum number of orders"),
    current_user: str = Depends(get_current_user),
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Get orders from exchange"""
    
    args = []
    if symbol:
        args.append(symbol)
    if since:
        args.append(since)
    if limit:
        args.append(limit)
    
    return await execute_exchange_request(
        connection_id,
        ExchangeRequestModel(method="fetch_orders", args=args),
        current_user,
        exchange_mgr
    )

@router.get("/stats", response_model=ConnectionStatsResponse)
async def get_connection_stats(
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Get global connection statistics"""
    
    async def _get_stats():
        return await exchange_mgr.get_connection_stats()
    
    stats = await optimize_api_request(_get_stats)
    return stats

@router.get("/performance")
async def get_performance_stats():
    """Get system performance statistics"""
    
    async def _get_performance():
        return await get_system_performance_stats()
    
    stats = await optimize_api_request(_get_performance)
    return stats

# Background task to monitor connections
async def monitor_connections_health(exchange_mgr: ExchangeConnectionManager):
    """Background task to monitor connection health"""
    logger.info("Starting connection health monitoring...")
    
    while True:
        try:
            # Check connection health every 5 minutes
            await asyncio.sleep(300)
            
            # Get all connections
            for connection_id, connection in exchange_mgr.connections.items():
                try:
                    # Test connection by fetching markets (lightweight)
                    await connection['instance'].load_markets()
                    connection['status'] = ConnectionStatus.CONNECTED
                    
                except Exception as e:
                    logger.warning(f"Connection {connection_id} health check failed: {str(e)}")
                    connection['status'] = ConnectionStatus.ERROR
                    
        except Exception as e:
            logger.error(f"Connection monitoring error: {str(e)}")

@router.on_event("startup")
async def startup_event():
    """Initialize exchange manager on startup"""
    global exchange_manager
    
    try:
        # Initialize performance optimizer
        if not performance_optimizer.initialized:
            await performance_optimizer.initialize()
        
        # Initialize exchange manager
        exchange_manager = ExchangeConnectionManager(performance_optimizer.connection_manager)
        
        # Start background monitoring
        import asyncio
        asyncio.create_task(monitor_connections_health(exchange_manager))
        
        logger.info("Exchange API routes initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize exchange routes: {str(e)}")
        raise

@router.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global exchange_manager
    
    if exchange_manager:
        await exchange_manager.cleanup()
    
    await performance_optimizer.cleanup()
    
    logger.info("Exchange API routes shutdown completed")

# Additional utility endpoints
@router.post("/connections/{connection_id}/test")
async def test_connection_health(
    connection_id: str,
    current_user: str = Depends(get_current_user),
    exchange_mgr: ExchangeConnectionManager = Depends(get_exchange_manager)
):
    """Test health of a specific connection"""
    
    connection = await exchange_mgr.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    if connection['user_id'] != current_user:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        # Test connection health
        result = await execute_exchange_request(
            connection_id,
            ExchangeRequestModel(method="load_markets"),
            current_user,
            exchange_mgr
        )
        
        return {
            'success': result['success'],
            'connection_id': connection_id,
            'health_status': 'healthy' if result['success'] else 'unhealthy',
            'test_timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            'success': False,
            'connection_id': connection_id,
            'health_status': 'unhealthy',
            'error': str(e),
            'test_timestamp': datetime.now().isoformat()
        }

# Export router
__all__ = ['router']
