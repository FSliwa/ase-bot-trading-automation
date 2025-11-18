"""
Advanced Exchange Connection Manager for ASE Trading Bot
Supports top 5 exchanges: Binance, Coinbase Pro, Kraken, OKX, Bybit
Features: OAuth, API key management, QR codes, testnet/production modes
"""

import asyncio
import ccxt.async_support as ccxt
import logging
import json
import os
import qrcode
import io
import base64
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import hashlib
import hmac
import time
import httpx
from urllib.parse import urlencode, quote
import secrets
import uuid
from enum import Enum

logger = logging.getLogger(__name__)

class ExchangeType(Enum):
    BINANCE = "binance"
    COINBASE_PRO = "coinbasepro"
    KRAKEN = "kraken"
    OKX = "okx"
    BYBIT = "bybit"

class ConnectionMode(Enum):
    TESTNET = "testnet"
    PRODUCTION = "production"

class ConnectionStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    ERROR = "error"

@dataclass
class ExchangeCredentials:
    """Secure storage for exchange credentials"""
    exchange: ExchangeType
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None  # For Coinbase Pro
    testnet: bool = True
    
    # OAuth specific fields
    oauth_token: Optional[str] = None
    oauth_refresh_token: Optional[str] = None
    oauth_expires_at: Optional[datetime] = None
    
    # Connection metadata
    created_at: datetime = field(default_factory=datetime.now)
    last_used: Optional[datetime] = None
    
    def is_oauth_valid(self) -> bool:
        """Check if OAuth token is still valid"""
        if not self.oauth_token or not self.oauth_expires_at:
            return False
        return datetime.now() < self.oauth_expires_at
    
    def to_dict(self, include_secrets: bool = False) -> Dict[str, Any]:
        """Convert to dictionary, optionally excluding secrets"""
        data = {
            'exchange': self.exchange.value,
            'testnet': self.testnet,
            'created_at': self.created_at.isoformat(),
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'has_api_key': bool(self.api_key),
            'has_oauth': bool(self.oauth_token),
            'oauth_valid': self.is_oauth_valid()
        }
        
        if include_secrets:
            data.update({
                'api_key': self.api_key,
                'api_secret': self.api_secret,
                'passphrase': self.passphrase,
                'oauth_token': self.oauth_token,
                'oauth_refresh_token': self.oauth_refresh_token,
                'oauth_expires_at': self.oauth_expires_at.isoformat() if self.oauth_expires_at else None
            })
        
        return data

@dataclass
class ExchangeConfig:
    """Configuration for each exchange"""
    exchange_type: ExchangeType
    display_name: str
    supports_oauth: bool
    supports_testnet: bool
    oauth_url: Optional[str] = None
    testnet_urls: Optional[Dict[str, str]] = None
    rate_limits: Dict[str, int] = field(default_factory=dict)
    required_credentials: List[str] = field(default_factory=list)
    
    # Exchange-specific settings
    sandbox_suffix: str = ""
    api_version: str = "v1"

class CredentialEncryption:
    """Handle encryption/decryption of sensitive credentials"""
    
    def __init__(self, encryption_key: Optional[str] = None):
        if encryption_key:
            self.fernet = Fernet(encryption_key.encode())
        else:
            # Generate or load encryption key
            key_file = "/tmp/ase_trading_key.txt"
            if os.path.exists(key_file):
                with open(key_file, 'rb') as f:
                    key = f.read()
                self.fernet = Fernet(key)
            else:
                key = Fernet.generate_key()
                with open(key_file, 'wb') as f:
                    f.write(key)
                os.chmod(key_file, 0o600)  # Read-write for owner only
                self.fernet = Fernet(key)
    
    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data"""
        if not data:
            return ""
        return self.fernet.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        if not encrypted_data:
            return ""
        return self.fernet.decrypt(encrypted_data.encode()).decode()

class OAuthHandler:
    """Handle OAuth flows for supported exchanges"""
    
    def __init__(self, encryption: CredentialEncryption):
        self.encryption = encryption
        self.oauth_states: Dict[str, Dict[str, Any]] = {}  # Track OAuth states
        
        # OAuth configurations for exchanges
        self.oauth_configs = {
            ExchangeType.COINBASE_PRO: {
                'client_id': os.getenv('COINBASE_CLIENT_ID'),
                'client_secret': os.getenv('COINBASE_CLIENT_SECRET'),
                'auth_url': 'https://www.coinbase.com/oauth/authorize',
                'token_url': 'https://api.exchange.coinbase.com/oauth/token',
                'scopes': ['wallet:accounts:read', 'wallet:trades:read', 'wallet:buys:create', 'wallet:sells:create']
            },
            ExchangeType.BINANCE: {
                'auth_url': 'https://accounts.binance.com/oauth/authorize',
                'token_url': 'https://api.binance.com/api/v3/oauth/token',
                'scopes': ['spot', 'futures']
            },
            ExchangeType.BYBIT: {
                'client_id': os.getenv('BYBIT_CLIENT_ID'),
                'client_secret': os.getenv('BYBIT_CLIENT_SECRET'),
                'auth_url': 'https://www.bybit.com/oauth/authorize',
                'token_url': 'https://api.bybit.com/oauth/token',
                'scopes': ['spot', 'contract']
            }
        }
    
    def generate_oauth_url(self, exchange: ExchangeType, redirect_uri: str) -> Tuple[str, str]:
        """Generate OAuth authorization URL and state"""
        
        config = self.oauth_configs.get(exchange)
        if not config:
            raise ValueError(f"OAuth not supported for {exchange.value}")
        
        # Generate random state for security
        state = secrets.token_urlsafe(32)
        
        # Store OAuth state
        self.oauth_states[state] = {
            'exchange': exchange,
            'redirect_uri': redirect_uri,
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(minutes=10)
        }
        
        # Build authorization URL
        params = {
            'client_id': config['client_id'],
            'redirect_uri': redirect_uri,
            'scope': ' '.join(config['scopes']),
            'state': state,
            'response_type': 'code'
        }
        
        auth_url = f"{config['auth_url']}?{urlencode(params)}"
        
        return auth_url, state
    
    async def handle_oauth_callback(self, exchange: ExchangeType, code: str, state: str) -> ExchangeCredentials:
        """Handle OAuth callback and exchange code for tokens"""
        
        # Validate state
        if state not in self.oauth_states:
            raise ValueError("Invalid OAuth state")
        
        oauth_state = self.oauth_states[state]
        if datetime.now() > oauth_state['expires_at']:
            del self.oauth_states[state]
            raise ValueError("OAuth state expired")
        
        if oauth_state['exchange'] != exchange:
            raise ValueError("Exchange mismatch in OAuth state")
        
        config = self.oauth_configs[exchange]
        
        # Exchange code for tokens
        token_data = {
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': oauth_state['redirect_uri']
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(config['token_url'], data=token_data)
            response.raise_for_status()
            
            tokens = response.json()
        
        # Create credentials
        credentials = ExchangeCredentials(
            exchange=exchange,
            oauth_token=self.encryption.encrypt(tokens['access_token']),
            oauth_refresh_token=self.encryption.encrypt(tokens.get('refresh_token', '')),
            oauth_expires_at=datetime.now() + timedelta(seconds=tokens.get('expires_in', 3600)),
            testnet=False  # OAuth is typically production only
        )
        
        # Clean up state
        del self.oauth_states[state]
        
        return credentials
    
    async def refresh_oauth_token(self, credentials: ExchangeCredentials) -> ExchangeCredentials:
        """Refresh OAuth token"""
        
        if not credentials.oauth_refresh_token:
            raise ValueError("No refresh token available")
        
        config = self.oauth_configs[credentials.exchange]
        
        token_data = {
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'refresh_token': self.encryption.decrypt(credentials.oauth_refresh_token),
            'grant_type': 'refresh_token'
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(config['token_url'], data=token_data)
            response.raise_for_status()
            
            tokens = response.json()
        
        # Update credentials
        credentials.oauth_token = self.encryption.encrypt(tokens['access_token'])
        credentials.oauth_expires_at = datetime.now() + timedelta(seconds=tokens.get('expires_in', 3600))
        
        if 'refresh_token' in tokens:
            credentials.oauth_refresh_token = self.encryption.encrypt(tokens['refresh_token'])
        
        return credentials

class QRCodeGenerator:
    """Generate QR codes for mobile app connections"""
    
    @staticmethod
    def generate_connection_qr(exchange: ExchangeType, connection_data: Dict[str, Any]) -> str:
        """Generate QR code for mobile connection"""
        
        # Create connection payload
        qr_data = {
            'type': 'exchange_connection',
            'exchange': exchange.value,
            'timestamp': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(minutes=5)).isoformat(),
            **connection_data
        }
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(json.dumps(qr_data))
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64 string
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return f"data:image/png;base64,{img_str}"

class ExchangeConnectionManager:
    """Main exchange connection manager"""
    
    def __init__(self, connection_manager):
        self.connection_manager = connection_manager  # Performance optimizer connection manager
        self.encryption = CredentialEncryption()
        self.oauth_handler = OAuthHandler(self.encryption)
        
        # Exchange configurations
        self.exchange_configs = {
            ExchangeType.BINANCE: ExchangeConfig(
                exchange_type=ExchangeType.BINANCE,
                display_name="Binance",
                supports_oauth=True,
                supports_testnet=True,
                oauth_url="https://accounts.binance.com/oauth/authorize",
                testnet_urls={
                    'api': 'https://testnet.binance.vision',
                    'stream': 'wss://testnet.binance.vision/ws'
                },
                rate_limits={'requests_per_minute': 1200, 'orders_per_day': 100000},
                required_credentials=['api_key', 'api_secret'],
                sandbox_suffix='_testnet'
            ),
            ExchangeType.COINBASE_PRO: ExchangeConfig(
                exchange_type=ExchangeType.COINBASE_PRO,
                display_name="Coinbase Pro",
                supports_oauth=True,
                supports_testnet=True,
                oauth_url="https://www.coinbase.com/oauth/authorize",
                testnet_urls={
                    'api': 'https://api-public.sandbox.exchange.coinbase.com',
                    'stream': 'wss://ws-feed-public.sandbox.exchange.coinbase.com'
                },
                rate_limits={'requests_per_minute': 600, 'orders_per_day': 50000},
                required_credentials=['api_key', 'api_secret', 'passphrase']
            ),
            ExchangeType.KRAKEN: ExchangeConfig(
                exchange_type=ExchangeType.KRAKEN,
                display_name="Kraken",
                supports_oauth=False,
                supports_testnet=True,
                testnet_urls={
                    'api': 'https://api.demo-futures.kraken.com',
                    'stream': 'wss://demo-futures.kraken.com/ws/v1'
                },
                rate_limits={'requests_per_minute': 120, 'orders_per_day': 25000},
                required_credentials=['api_key', 'api_secret']
            ),
            ExchangeType.OKX: ExchangeConfig(
                exchange_type=ExchangeType.OKX,
                display_name="OKX",
                supports_oauth=False,
                supports_testnet=True,
                testnet_urls={
                    'api': 'https://www.okx.com',
                    'stream': 'wss://wspap.okx.com:8443/ws/v5/public'
                },
                rate_limits={'requests_per_minute': 600, 'orders_per_day': 100000},
                required_credentials=['api_key', 'api_secret', 'passphrase']
            ),
            ExchangeType.BYBIT: ExchangeConfig(
                exchange_type=ExchangeType.BYBIT,
                display_name="Bybit",
                supports_oauth=True,
                supports_testnet=True,
                oauth_url="https://www.bybit.com/oauth/authorize",
                testnet_urls={
                    'api': 'https://api-testnet.bybit.com',
                    'stream': 'wss://stream-testnet.bybit.com'
                },
                rate_limits={'requests_per_minute': 600, 'orders_per_day': 75000},
                required_credentials=['api_key', 'api_secret']
            )
        }
        
        # Active connections
        self.connections: Dict[str, Dict[str, Any]] = {}
        self.connection_stats = {
            'total_connections': 0,
            'active_connections': 0,
            'successful_connections': 0,
            'failed_connections': 0,
            'oauth_connections': 0,
            'api_key_connections': 0
        }
    
    async def get_exchange_info(self, exchange: ExchangeType) -> Dict[str, Any]:
        """Get exchange information and capabilities"""
        config = self.exchange_configs.get(exchange)
        if not config:
            raise ValueError(f"Unsupported exchange: {exchange.value}")
        
        return {
            'exchange': exchange.value,
            'display_name': config.display_name,
            'supports_oauth': config.supports_oauth,
            'supports_testnet': config.supports_testnet,
            'rate_limits': config.rate_limits,
            'required_credentials': config.required_credentials,
            'connection_methods': [
                'api_key' if config.required_credentials else None,
                'oauth' if config.supports_oauth else None,
                'qr_code'
            ]
        }
    
    async def list_supported_exchanges(self) -> List[Dict[str, Any]]:
        """List all supported exchanges"""
        exchanges = []
        for exchange_type in self.exchange_configs:
            info = await self.get_exchange_info(exchange_type)
            exchanges.append(info)
        return exchanges
    
    async def create_connection(self, exchange: ExchangeType, credentials: ExchangeCredentials, 
                              user_id: str) -> str:
        """Create new exchange connection"""
        
        connection_id = f"{user_id}_{exchange.value}_{uuid.uuid4().hex[:8]}"
        
        try:
            # Validate credentials
            await self._validate_credentials(exchange, credentials)
            
            # Create CCXT exchange instance
            exchange_instance = await self._create_exchange_instance(exchange, credentials)
            
            # Test connection
            await self._test_connection(exchange_instance)
            
            # Store connection
            self.connections[connection_id] = {
                'id': connection_id,
                'user_id': user_id,
                'exchange': exchange,
                'credentials': credentials,
                'instance': exchange_instance,
                'status': ConnectionStatus.CONNECTED,
                'created_at': datetime.now(),
                'last_used': datetime.now(),
                'stats': {
                    'requests_made': 0,
                    'successful_requests': 0,
                    'failed_requests': 0,
                    'total_volume_traded': 0.0
                }
            }
            
            # Update global stats
            self.connection_stats['total_connections'] += 1
            self.connection_stats['active_connections'] += 1
            self.connection_stats['successful_connections'] += 1
            
            if credentials.oauth_token:
                self.connection_stats['oauth_connections'] += 1
            else:
                self.connection_stats['api_key_connections'] += 1
            
            logger.info(f"Successfully created connection {connection_id} for {exchange.value}")
            return connection_id
            
        except Exception as e:
            self.connection_stats['failed_connections'] += 1
            logger.error(f"Failed to create connection for {exchange.value}: {str(e)}")
            raise
    
    async def _validate_credentials(self, exchange: ExchangeType, credentials: ExchangeCredentials):
        """Validate exchange credentials"""
        config = self.exchange_configs[exchange]
        
        # Check OAuth credentials
        if credentials.oauth_token:
            if not config.supports_oauth:
                raise ValueError(f"{exchange.value} does not support OAuth")
            
            if not credentials.is_oauth_valid():
                # Try to refresh token
                try:
                    await self.oauth_handler.refresh_oauth_token(credentials)
                except Exception as e:
                    raise ValueError(f"OAuth token invalid and refresh failed: {str(e)}")
        
        # Check API key credentials
        else:
            for field in config.required_credentials:
                value = getattr(credentials, field, None)
                if not value:
                    raise ValueError(f"Missing required credential: {field}")
    
    async def _create_exchange_instance(self, exchange: ExchangeType, 
                                      credentials: ExchangeCredentials) -> Any:
        """Create CCXT exchange instance"""
        
        config = self.exchange_configs[exchange]
        exchange_class_name = exchange.value
        
        # Special handling for exchange names
        if exchange == ExchangeType.COINBASE_PRO:
            exchange_class_name = 'coinbasepro'
        
        # Get exchange class from CCXT
        exchange_class = getattr(ccxt, exchange_class_name)
        
        # Build configuration
        exchange_config = {
            'apiKey': self.encryption.decrypt(credentials.api_key) if credentials.api_key else None,
            'secret': self.encryption.decrypt(credentials.api_secret) if credentials.api_secret else None,
            'password': self.encryption.decrypt(credentials.passphrase) if credentials.passphrase else None,
            'enableRateLimit': True,
            'timeout': 30000,  # 30 seconds
        }
        
        # Configure testnet if needed
        if credentials.testnet and config.supports_testnet:
            if config.testnet_urls:
                exchange_config['urls'] = config.testnet_urls
            exchange_config['sandbox'] = True
        
        # Handle OAuth
        if credentials.oauth_token and credentials.is_oauth_valid():
            exchange_config['oauth_token'] = self.encryption.decrypt(credentials.oauth_token)
        
        return exchange_class(exchange_config)
    
    async def _test_connection(self, exchange_instance: Any):
        """Test exchange connection"""
        try:
            # Test by fetching markets (lightweight operation)
            await exchange_instance.load_markets()
            
            # Test authentication if possible
            try:
                await exchange_instance.fetch_balance()
            except Exception as e:
                # Some exchanges might not support balance fetching in testnet
                logger.warning(f"Balance fetch test failed (might be expected in testnet): {str(e)}")
        
        except Exception as e:
            await exchange_instance.close()
            raise Exception(f"Connection test failed: {str(e)}")
    
    async def get_connection(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """Get connection by ID"""
        connection = self.connections.get(connection_id)
        if not connection:
            return None
        
        # Update last used
        connection['last_used'] = datetime.now()
        
        # Return connection info (without sensitive data)
        return {
            'id': connection['id'],
            'user_id': connection['user_id'],
            'exchange': connection['exchange'].value,
            'status': connection['status'].value,
            'created_at': connection['created_at'].isoformat(),
            'last_used': connection['last_used'].isoformat(),
            'stats': connection['stats'],
            'testnet': connection['credentials'].testnet,
            'connection_type': 'oauth' if connection['credentials'].oauth_token else 'api_key'
        }
    
    async def list_user_connections(self, user_id: str) -> List[Dict[str, Any]]:
        """List all connections for a user"""
        user_connections = []
        
        for connection in self.connections.values():
            if connection['user_id'] == user_id:
                info = await self.get_connection(connection['id'])
                user_connections.append(info)
        
        return user_connections
    
    async def disconnect_connection(self, connection_id: str) -> bool:
        """Disconnect and remove connection"""
        connection = self.connections.get(connection_id)
        if not connection:
            return False
        
        try:
            # Close exchange instance
            if connection['instance']:
                await connection['instance'].close()
            
            # Remove from active connections
            del self.connections[connection_id]
            self.connection_stats['active_connections'] -= 1
            
            logger.info(f"Successfully disconnected connection {connection_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting {connection_id}: {str(e)}")
            return False
    
    async def test_connection_credentials(self, exchange: ExchangeType, 
                                        credentials: ExchangeCredentials) -> Dict[str, Any]:
        """Test credentials without creating persistent connection"""
        try:
            # Validate credentials
            await self._validate_credentials(exchange, credentials)
            
            # Create temporary instance
            exchange_instance = await self._create_exchange_instance(exchange, credentials)
            
            # Test connection
            await self._test_connection(exchange_instance)
            
            # Get basic info
            markets = await exchange_instance.load_markets()
            
            try:
                balance = await exchange_instance.fetch_balance()
                account_info = {
                    'total_balance_usd': sum(balance.get('total', {}).values()),
                    'currencies': len(balance.get('total', {}))
                }
            except:
                account_info = {'message': 'Balance not available (testnet or permission issue)'}
            
            # Close temporary instance
            await exchange_instance.close()
            
            return {
                'success': True,
                'exchange': exchange.value,
                'testnet': credentials.testnet,
                'markets_available': len(markets),
                'account_info': account_info,
                'connection_type': 'oauth' if credentials.oauth_token else 'api_key'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'exchange': exchange.value
            }
    
    async def generate_oauth_url(self, exchange: ExchangeType, redirect_uri: str) -> Dict[str, str]:
        """Generate OAuth URL for exchange"""
        try:
            auth_url, state = self.oauth_handler.generate_oauth_url(exchange, redirect_uri)
            return {
                'success': True,
                'auth_url': auth_url,
                'state': state
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def handle_oauth_callback(self, exchange: ExchangeType, code: str, 
                                  state: str) -> Dict[str, Any]:
        """Handle OAuth callback"""
        try:
            credentials = await self.oauth_handler.handle_oauth_callback(exchange, code, state)
            return {
                'success': True,
                'credentials': credentials.to_dict()
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def generate_connection_qr(self, exchange: ExchangeType, 
                                   connection_data: Dict[str, Any]) -> str:
        """Generate QR code for mobile connection"""
        return QRCodeGenerator.generate_connection_qr(exchange, connection_data)
    
    async def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        # Calculate additional stats
        connection_by_exchange = {}
        active_by_status = {}
        
        for connection in self.connections.values():
            exchange = connection['exchange'].value
            status = connection['status'].value
            
            connection_by_exchange[exchange] = connection_by_exchange.get(exchange, 0) + 1
            active_by_status[status] = active_by_status.get(status, 0) + 1
        
        return {
            **self.connection_stats,
            'connections_by_exchange': connection_by_exchange,
            'connections_by_status': active_by_status,
            'oauth_percentage': (
                (self.connection_stats['oauth_connections'] / self.connection_stats['total_connections'] * 100)
                if self.connection_stats['total_connections'] > 0 else 0
            )
        }
    
    async def execute_exchange_request(self, connection_id: str, method: str, 
                                     *args, **kwargs) -> Dict[str, Any]:
        """Execute request on exchange connection"""
        connection = self.connections.get(connection_id)
        if not connection:
            return {'success': False, 'error': 'Connection not found'}
        
        if connection['status'] != ConnectionStatus.CONNECTED:
            return {'success': False, 'error': 'Connection not active'}
        
        try:
            # Get exchange instance
            exchange = connection['instance']
            
            # Execute method
            if hasattr(exchange, method):
                result = await getattr(exchange, method)(*args, **kwargs)
                
                # Update stats
                connection['stats']['requests_made'] += 1
                connection['stats']['successful_requests'] += 1
                connection['last_used'] = datetime.now()
                
                return {'success': True, 'data': result}
            else:
                return {'success': False, 'error': f'Method {method} not supported'}
                
        except Exception as e:
            connection['stats']['failed_requests'] += 1
            logger.error(f"Exchange request error on {connection_id}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def cleanup(self):
        """Cleanup all connections"""
        logger.info("Cleaning up exchange connections...")
        
        for connection_id in list(self.connections.keys()):
            await self.disconnect_connection(connection_id)
        
        logger.info("Exchange connection cleanup completed")

# Example usage
if __name__ == "__main__":
    async def main():
        from core.performance_optimizer import performance_optimizer
        
        # Initialize performance optimizer
        await performance_optimizer.initialize()
        
        # Create exchange manager
        exchange_manager = ExchangeConnectionManager(performance_optimizer.connection_manager)
        
        # List supported exchanges
        exchanges = await exchange_manager.list_supported_exchanges()
        print("Supported exchanges:", json.dumps(exchanges, indent=2))
        
        # Test connection (would need real credentials)
        # credentials = ExchangeCredentials(
        #     exchange=ExchangeType.BINANCE,
        #     api_key="test_key",
        #     api_secret="test_secret",
        #     testnet=True
        # )
        
        # test_result = await exchange_manager.test_connection_credentials(
        #     ExchangeType.BINANCE, credentials
        # )
        # print("Connection test:", test_result)
        
        # Cleanup
        await exchange_manager.cleanup()
        await performance_optimizer.cleanup()
    
    # Run example
    asyncio.run(main())
