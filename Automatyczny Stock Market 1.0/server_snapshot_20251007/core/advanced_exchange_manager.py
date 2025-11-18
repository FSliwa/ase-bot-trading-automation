"""
Advanced Exchange Connection Manager
Obsługuje 5 głównych giełd: Binance, Coinbase Pro, Kraken, OKX, Bybit
OAuth, API keys, szyfrowanie, użytkowny panel zarządzania
"""

import asyncio
import json
import logging
import os
import secrets
import hashlib
import hmac
import time
import base64
import urllib.parse
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from contextlib import asynccontextmanager

import aiohttp
import ccxt
import ccxt.async_support as ccxt_async
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import qrcode
from io import BytesIO
import base64 as b64

logger = logging.getLogger(__name__)

class ExchangeType(str, Enum):
    """Supported exchange types"""
    BINANCE = "binance"
    COINBASE_PRO = "coinbasepro" 
    KRAKEN = "kraken"
    OKX = "okx"
    BYBIT = "bybit"

class ConnectionMode(str, Enum):
    """Connection modes"""
    API_KEY = "api_key"
    OAUTH = "oauth" 
    SANDBOX = "sandbox"

class ConnectionStatus(str, Enum):
    """Connection status"""
    CONNECTED = "connected"
    CONNECTING = "connecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    EXPIRED = "expired"

@dataclass
class ExchangeCredentials:
    """Secure exchange credentials"""
    exchange: ExchangeType
    mode: ConnectionMode
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None  # For OKX
    oauth_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    sandbox: bool = False
    user_id: str = None

@dataclass
class ExchangeConnection:
    """Exchange connection with metadata"""
    exchange: ExchangeType
    status: ConnectionStatus
    credentials: ExchangeCredentials
    ccxt_client: Optional[ccxt_async.Exchange] = None
    last_ping: Optional[datetime] = None
    error_message: Optional[str] = None
    balance_cache: Dict[str, Any] = None
    positions_cache: List[Dict] = None

class AdvancedExchangeManager:
    """Advanced multi-exchange connection manager"""
    
    def __init__(self):
        self.encryption_key = self._get_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key)
        
        # Exchange configurations
        self.exchange_configs = {
            ExchangeType.BINANCE: {
                "name": "Binance",
                "oauth_enabled": True,
                "api_key_enabled": True,
                "sandbox_url": "https://testnet.binance.vision",
                "oauth_url": "https://api.binance.com/oauth/authorize",
                "required_scopes": ["spot", "futures"],
                "rate_limits": {"requests_per_minute": 1200},
                "supported_features": ["spot", "futures", "margin", "options"]
            },
            ExchangeType.COINBASE_PRO: {
                "name": "Coinbase Advanced",
                "oauth_enabled": True,
                "api_key_enabled": True,
                "sandbox_url": "https://api.exchange.sandbox.coinbase.com",
                "oauth_url": "https://www.coinbase.com/oauth/authorize",
                "required_scopes": ["wallet:accounts:read", "wallet:trades:read"],
                "rate_limits": {"requests_per_minute": 600},
                "supported_features": ["spot", "portfolio"]
            },
            ExchangeType.KRAKEN: {
                "name": "Kraken",
                "oauth_enabled": False,
                "api_key_enabled": True,
                "sandbox_url": "https://api.demo.kraken.com",
                "required_scopes": ["trade", "balance"],
                "rate_limits": {"requests_per_minute": 300},
                "supported_features": ["spot", "futures", "staking"]
            },
            ExchangeType.OKX: {
                "name": "OKX",
                "oauth_enabled": False,
                "api_key_enabled": True,
                "sandbox_url": "https://aws.okx.com",
                "required_scopes": ["trade", "read"],
                "rate_limits": {"requests_per_minute": 600},
                "supported_features": ["spot", "futures", "options", "swap"]
            },
            ExchangeType.BYBIT: {
                "name": "Bybit", 
                "oauth_enabled": True,
                "api_key_enabled": True,
                "sandbox_url": "https://api-testnet.bybit.com",
                "oauth_url": "https://api.bybit.com/oauth/authorize",
                "required_scopes": ["trading", "wallet"],
                "rate_limits": {"requests_per_minute": 600},
                "supported_features": ["spot", "futures", "options"]
            }
        }
        
        # Active connections
        self.connections: Dict[str, Dict[ExchangeType, ExchangeConnection]] = {}
        self.oauth_states: Dict[str, Dict] = {}  # OAuth state tracking
        self.rate_limiters: Dict[ExchangeType, Dict] = {}
        
        # Initialize rate limiters
        for exchange in ExchangeType:
            self.rate_limiters[exchange] = {
                "requests": 0,
                "reset_time": time.time() + 60,
                "max_requests": self.exchange_configs[exchange]["rate_limits"]["requests_per_minute"]
            }

    def _get_encryption_key(self) -> bytes:
        """Get or generate encryption key"""
        key_env = os.getenv('EXCHANGE_ENCRYPTION_KEY')
        if key_env:
            return key_env.encode()[:32].ljust(32, b'0')
        
        # Generate key from password + salt
        password = os.getenv('ENCRYPTION_PASSWORD', 'default_trading_key_2024').encode()
        salt = os.getenv('ENCRYPTION_SALT', 'trading_salt_ase_bot').encode()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password))

    def encrypt_data(self, data: str) -> str:
        """Encrypt sensitive data"""
        return self.cipher_suite.encrypt(data.encode()).decode()

    def decrypt_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        return self.cipher_suite.decrypt(encrypted_data.encode()).decode()

    async def connect_api_key(
        self, 
        user_id: str, 
        exchange: ExchangeType, 
        api_key: str, 
        api_secret: str,
        passphrase: Optional[str] = None,
        sandbox: bool = False
    ) -> Dict[str, Any]:
        """Connect via API key"""
        try:
            # Validate inputs
            if not api_key or not api_secret:
                raise ValueError("API key and secret are required")
            
            # Create credentials
            credentials = ExchangeCredentials(
                exchange=exchange,
                mode=ConnectionMode.API_KEY,
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                sandbox=sandbox,
                user_id=user_id
            )
            
            # Test connection
            ccxt_client = await self._create_ccxt_client(credentials)
            
            # Verify API key with test request
            balance = await ccxt_client.fetch_balance()
            await ccxt_client.close()
            
            # Store connection
            connection = ExchangeConnection(
                exchange=exchange,
                status=ConnectionStatus.CONNECTED,
                credentials=credentials,
                last_ping=datetime.now(),
                balance_cache=balance
            )
            
            if user_id not in self.connections:
                self.connections[user_id] = {}
            self.connections[user_id][exchange] = connection
            
            # Save encrypted credentials to database
            await self._save_credentials(user_id, credentials)
            
            logger.info(f"✅ Connected {exchange.value} via API key for user {user_id}")
            
            return {
                "success": True,
                "exchange": exchange.value,
                "mode": "api_key",
                "balance_usd": self._calculate_balance_usd(balance),
                "supported_features": self.exchange_configs[exchange]["supported_features"]
            }
            
        except Exception as e:
            logger.error(f"❌ API key connection failed for {exchange.value}: {e}")
            return {
                "success": False,
                "error": str(e),
                "suggestions": self._get_connection_suggestions(exchange, "api_key")
            }

    def generate_oauth_url(self, user_id: str, exchange: ExchangeType) -> str:
        """Generate OAuth authorization URL"""
        config = self.exchange_configs[exchange]
        
        if not config["oauth_enabled"]:
            raise ValueError(f"{exchange.value} does not support OAuth")
        
        # Generate secure state
        state = secrets.token_urlsafe(32)
        self.oauth_states[state] = {
            "user_id": user_id,
            "exchange": exchange,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(minutes=10)
        }
        
        # Build OAuth URL
        params = {
            "client_id": os.getenv(f"{exchange.value.upper()}_CLIENT_ID"),
            "response_type": "code",
            "redirect_uri": os.getenv(f"{exchange.value.upper()}_REDIRECT_URI"),
            "scope": " ".join(config["required_scopes"]),
            "state": state
        }
        
        # Exchange-specific parameters
        if exchange == ExchangeType.BINANCE:
            params["permissions"] = "spot,futures"
        elif exchange == ExchangeType.COINBASE_PRO:
            params["account"] = "all"
        elif exchange == ExchangeType.BYBIT:
            params["type"] = "web"
        
        oauth_url = config["oauth_url"] + "?" + urllib.parse.urlencode(params)
        
        logger.info(f"🔗 Generated OAuth URL for {exchange.value}: {oauth_url[:100]}...")
        return oauth_url

    def generate_qr_code(self, oauth_url: str) -> str:
        """Generate QR code for mobile OAuth"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(oauth_url)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_str = b64.b64encode(buffer.getvalue()).decode()
        
        return f"data:image/png;base64,{img_str}"

    async def handle_oauth_callback(self, exchange: ExchangeType, code: str, state: str) -> Dict[str, Any]:
        """Handle OAuth callback"""
        try:
            # Validate state
            if state not in self.oauth_states:
                raise ValueError("Invalid OAuth state")
                
            oauth_data = self.oauth_states[state]
            if oauth_data["expires_at"] < datetime.now():
                raise ValueError("OAuth state expired")
                
            user_id = oauth_data["user_id"]
            
            # Exchange tokens
            token_data = await self._exchange_oauth_token(exchange, code)
            
            # Create credentials
            credentials = ExchangeCredentials(
                exchange=exchange,
                mode=ConnectionMode.OAUTH,
                oauth_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                expires_at=datetime.now() + timedelta(seconds=token_data.get("expires_in", 3600)),
                user_id=user_id
            )
            
            # Test connection
            ccxt_client = await self._create_ccxt_client(credentials)
            balance = await ccxt_client.fetch_balance()
            await ccxt_client.close()
            
            # Store connection
            connection = ExchangeConnection(
                exchange=exchange,
                status=ConnectionStatus.CONNECTED,
                credentials=credentials,
                last_ping=datetime.now(),
                balance_cache=balance
            )
            
            if user_id not in self.connections:
                self.connections[user_id] = {}
            self.connections[user_id][exchange] = connection
            
            # Save credentials
            await self._save_credentials(user_id, credentials)
            
            # Clean up OAuth state
            del self.oauth_states[state]
            
            logger.info(f"✅ OAuth connection successful for {exchange.value}")
            
            return {
                "success": True,
                "exchange": exchange.value,
                "mode": "oauth",
                "balance_usd": self._calculate_balance_usd(balance)
            }
            
        except Exception as e:
            logger.error(f"❌ OAuth callback failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_user_connections(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all connections for a user"""
        connections = []
        
        user_connections = self.connections.get(user_id, {})
        
        for exchange, connection in user_connections.items():
            # Ping connection to verify status
            await self._ping_connection(connection)
            
            connection_info = {
                "exchange": exchange.value,
                "exchange_name": self.exchange_configs[exchange]["name"],
                "status": connection.status.value,
                "mode": connection.credentials.mode.value,
                "connected_at": connection.credentials.user_id,  # Use as timestamp placeholder
                "last_ping": connection.last_ping.isoformat() if connection.last_ping else None,
                "sandbox": connection.credentials.sandbox,
                "features": self.exchange_configs[exchange]["supported_features"],
                "balance_usd": self._calculate_balance_usd(connection.balance_cache) if connection.balance_cache else 0,
                "error": connection.error_message
            }
            
            connections.append(connection_info)
        
        return connections

    async def get_aggregated_balance(self, user_id: str) -> Dict[str, Any]:
        """Get aggregated balance across all connected exchanges"""
        total_balance_usd = 0
        exchange_balances = []
        errors = []
        
        user_connections = self.connections.get(user_id, {})
        
        # Fetch balances concurrently
        tasks = []
        for exchange, connection in user_connections.items():
            tasks.append(self._fetch_exchange_balance(exchange, connection))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, (exchange, connection) in enumerate(user_connections.items()):
                result = results[i]
                
                if isinstance(result, Exception):
                    errors.append({
                        "exchange": exchange.value,
                        "error": str(result)
                    })
                    continue
                
                balance_usd = self._calculate_balance_usd(result)
                total_balance_usd += balance_usd
                
                exchange_balances.append({
                    "exchange": exchange.value,
                    "exchange_name": self.exchange_configs[exchange]["name"],
                    "balance_usd": balance_usd,
                    "assets": self._format_assets(result),
                    "last_updated": datetime.now().isoformat()
                })
        
        return {
            "total_balance_usd": round(total_balance_usd, 2),
            "exchanges": exchange_balances,
            "connected_exchanges": len(exchange_balances),
            "errors": errors,
            "timestamp": datetime.now().isoformat()
        }

    async def disconnect_exchange(self, user_id: str, exchange: ExchangeType) -> bool:
        """Disconnect from exchange"""
        try:
            user_connections = self.connections.get(user_id, {})
            
            if exchange in user_connections:
                connection = user_connections[exchange]
                
                # Close CCXT client if exists
                if connection.ccxt_client:
                    await connection.ccxt_client.close()
                
                # Remove from active connections
                del user_connections[exchange]
                
                # Remove from database
                await self._remove_credentials(user_id, exchange)
                
                logger.info(f"✅ Disconnected {exchange.value} for user {user_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error disconnecting {exchange.value}: {e}")
            return False

    # Private methods
    
    async def _create_ccxt_client(self, credentials: ExchangeCredentials) -> ccxt_async.Exchange:
        """Create CCXT client from credentials"""
        exchange_id = credentials.exchange.value
        
        # Base configuration
        config = {
            'apiKey': credentials.api_key if credentials.mode == ConnectionMode.API_KEY else None,
            'secret': credentials.api_secret if credentials.mode == ConnectionMode.API_KEY else None,
            'sandbox': credentials.sandbox,
            'enableRateLimit': True,
            'timeout': 30000,
        }
        
        # Exchange-specific configurations
        if credentials.exchange == ExchangeType.OKX and credentials.passphrase:
            config['password'] = credentials.passphrase
        elif credentials.exchange == ExchangeType.COINBASE_PRO:
            config['sandbox'] = credentials.sandbox
        elif credentials.exchange == ExchangeType.BINANCE:
            if credentials.sandbox:
                config['urls'] = {'api': 'https://testnet.binance.vision'}
        
        # OAuth configuration
        if credentials.mode == ConnectionMode.OAUTH:
            config['headers'] = {
                'Authorization': f'Bearer {credentials.oauth_token}'
            }
        
        # Create client
        exchange_class = getattr(ccxt_async, exchange_id)
        return exchange_class(config)

    async def _exchange_oauth_token(self, exchange: ExchangeType, code: str) -> Dict[str, Any]:
        """Exchange OAuth code for access token"""
        token_url_map = {
            ExchangeType.BINANCE: "https://api.binance.com/oauth/token",
            ExchangeType.COINBASE_PRO: "https://api.coinbase.com/oauth/token",
            ExchangeType.BYBIT: "https://api.bybit.com/oauth/token"
        }
        
        token_url = token_url_map.get(exchange)
        if not token_url:
            raise ValueError(f"OAuth not supported for {exchange.value}")
        
        client_id = os.getenv(f"{exchange.value.upper()}_CLIENT_ID")
        client_secret = os.getenv(f"{exchange.value.upper()}_CLIENT_SECRET")
        redirect_uri = os.getenv(f"{exchange.value.upper()}_REDIRECT_URI")
        
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    text = await response.text()
                    raise ValueError(f"Token exchange failed: {text}")

    async def _ping_connection(self, connection: ExchangeConnection):
        """Ping connection to verify status"""
        try:
            if not connection.ccxt_client:
                connection.ccxt_client = await self._create_ccxt_client(connection.credentials)
            
            # Simple API call to test connection
            await connection.ccxt_client.fetch_balance()
            connection.status = ConnectionStatus.CONNECTED
            connection.last_ping = datetime.now()
            connection.error_message = None
            
        except Exception as e:
            connection.status = ConnectionStatus.ERROR
            connection.error_message = str(e)
            logger.warning(f"Connection ping failed for {connection.exchange.value}: {e}")

    async def _fetch_exchange_balance(self, exchange: ExchangeType, connection: ExchangeConnection) -> Dict[str, Any]:
        """Fetch balance from specific exchange"""
        if not connection.ccxt_client:
            connection.ccxt_client = await self._create_ccxt_client(connection.credentials)
        
        balance = await connection.ccxt_client.fetch_balance()
        connection.balance_cache = balance
        return balance

    def _calculate_balance_usd(self, balance: Dict[str, Any]) -> float:
        """Calculate USD balance from exchange balance"""
        if not balance or 'total' not in balance:
            return 0.0

        total_usd = 0.0
        # In a real application, you would fetch live prices for each asset.
        # For now, we'll only sum up assets that are already in USD or stablecoins.
        stablecoins = ['USD', 'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD']

        for asset, amount in balance.get('total', {}).items():
            if asset in stablecoins:
                total_usd += amount
        
        # This is an incomplete calculation, as it ignores non-stablecoin assets.
        # A full implementation requires a price feed.
        if total_usd == 0.0:
            logger.warning("Could not calculate USD balance. No stablecoins found or price feed missing.")

        return round(total_usd, 2)

    def _format_assets(self, balance: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format assets for API response"""
        assets = []
        total_balance = balance.get('total', {})
        
        # This is an incomplete implementation as it lacks a price feed.
        # It will only show amounts, not their USD values.
        for asset, amount in total_balance.items():
            if amount > 0:
                assets.append({
                    "asset": asset,
                    "amount": amount,
                    "usd_value": None  # USD value cannot be determined without a price feed
                })
        
        return assets

    async def _save_credentials(self, user_id: str, credentials: ExchangeCredentials):
        """Save encrypted credentials to database"""
        # This would integrate with your database system
        # For now, just log
        logger.info(f"💾 Saving credentials for {user_id} - {credentials.exchange.value}")

    async def _remove_credentials(self, user_id: str, exchange: ExchangeType):
        """Remove credentials from database"""
        logger.info(f"🗑️ Removing credentials for {user_id} - {exchange.value}")

    def _get_connection_suggestions(self, exchange: ExchangeType, mode: str) -> List[str]:
        """Get connection troubleshooting suggestions"""
        base_suggestions = [
            "Verify API credentials are correct",
            "Check if API key has required permissions", 
            "Ensure IP whitelist is configured (if applicable)"
        ]
        
        exchange_specific = {
            ExchangeType.BINANCE: ["Enable futures trading if needed", "Check if testnet keys are used for testnet"],
            ExchangeType.OKX: ["Ensure passphrase is provided", "Verify trading permissions"],
            ExchangeType.KRAKEN: ["Check API key tier limits", "Verify nonce is not reused"],
        }
        
        return base_suggestions + exchange_specific.get(exchange, [])

# Global instance
exchange_manager = AdvancedExchangeManager()

# FastAPI integration helpers
async def get_exchange_manager():
    """Get exchange manager instance"""
    return exchange_manager
