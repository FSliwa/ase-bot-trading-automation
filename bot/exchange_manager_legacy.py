"""
Exchange connection manager for OAuth and API Key authentication.
Handles secure storage and management of exchange credentials.
"""

import time
import hmac
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlencode
import requests
import logging
from dotenv import load_dotenv

# Load environment variables at module import
load_dotenv()

from sqlalchemy.orm import Session
from pydantic import BaseModel, SecretStr, ValidationError

from bot.db import SessionLocal, ExchangeCredential
from bot.security import get_security_manager
from bot.config import load_oauth_config

logger = logging.getLogger(__name__)


class ExchangeConnectionForm(BaseModel):
    """Form data for connecting exchange via API keys."""
    exchange: str
    api_key: str
    api_secret: SecretStr
    passphrase: Optional[SecretStr] = None
    testnet: bool = False
    
    class Config:
        str_strip_whitespace = True


class OAuthState(BaseModel):
    """OAuth state information for CSRF protection."""
    user_id: str
    exchange: str
    csrf_token: str
    created_at: datetime
    
    def is_expired(self, timeout_minutes: int = 10) -> bool:
        """Check if OAuth state has expired."""
        return datetime.utcnow() - self.created_at > timedelta(minutes=timeout_minutes)


class ExchangeManager:
    """Manages exchange connections and authentication."""
    
    def __init__(self):
        self.security = get_security_manager()
        self.oauth_config = load_oauth_config()
        self._oauth_states: Dict[str, OAuthState] = {}
        
    def _get_db(self) -> Session:
        """Get database session."""
        return SessionLocal()
    
    def mask_api_key(self, api_key: str) -> str:
        """Mask API key for display purposes."""
        if len(api_key) <= 8:
            return "*" * len(api_key)
        return api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]
    
    # =================== OAuth Methods ===================
    
    def generate_oauth_url(self, user_id: str, exchange: str) -> str:
        """Generate OAuth authorization URL for the exchange."""
        if exchange == "binance":
            return self._generate_binance_oauth_url(user_id)
        elif exchange == "bybit":
            return self._generate_bybit_oauth_url(user_id)
        else:
            raise ValueError(f"OAuth not supported for exchange: {exchange}")
    
    def _generate_binance_oauth_url(self, user_id: str) -> str:
        """Generate Binance OAuth URL."""
        if not self.oauth_config.binance_client_id:
            raise ValueError("Binance OAuth not configured. Missing CLIENT_ID.")
        
        csrf_token = str(uuid.uuid4())
        state = OAuthState(
            user_id=user_id,
            exchange="binance",
            csrf_token=csrf_token,
            created_at=datetime.utcnow()
        )
        
        # Store state for validation
        state_key = f"binance_{user_id}_{csrf_token}"
        self._oauth_states[state_key] = state
        
        params = {
            "response_type": "code",
            "client_id": self.oauth_config.binance_client_id,
            "redirect_uri": self.oauth_config.binance_redirect_uri,
            "scope": "user:openId,trade",  # Adjust based on Binance documentation
            "state": state_key
        }
        
        base_url = "https://accounts.binance.com/oauth/authorize"
        return f"{base_url}?{urlencode(params)}"
    
    def _generate_bybit_oauth_url(self, user_id: str) -> str:
        """Generate Bybit OAuth URL (Broker API)."""
        if not self.oauth_config.bybit_client_id:
            raise ValueError("Bybit OAuth not configured. Missing CLIENT_ID.")
        
        csrf_token = str(uuid.uuid4())
        state = OAuthState(
            user_id=user_id,
            exchange="bybit",
            csrf_token=csrf_token,
            created_at=datetime.utcnow()
        )
        
        state_key = f"bybit_{user_id}_{csrf_token}"
        self._oauth_states[state_key] = state
        
        params = {
            "response_type": "code",
            "client_id": self.oauth_config.bybit_client_id,
            "redirect_uri": self.oauth_config.bybit_redirect_uri,
            "scope": "openapi",
            "state": state_key
        }
        
        base_url = "https://api.bybit.com/oauth/authorize"
        return f"{base_url}?{urlencode(params)}"
    
    def handle_oauth_callback(self, exchange: str, code: str, state: str) -> Dict[str, Any]:
        """Handle OAuth callback and exchange code for tokens."""
        # Validate state
        if state not in self._oauth_states:
            raise ValueError("Invalid or expired OAuth state")
        
        oauth_state = self._oauth_states[state]
        if oauth_state.is_expired():
            del self._oauth_states[state]
            raise ValueError("OAuth state expired")
        
        if oauth_state.exchange != exchange:
            raise ValueError("Exchange mismatch in OAuth state")
        
        try:
            if exchange == "binance":
                result = self._handle_binance_callback(code, oauth_state)
            elif exchange == "bybit":
                result = self._handle_bybit_callback(code, oauth_state)
            else:
                raise ValueError(f"Unsupported exchange: {exchange}")
            
            # Clean up state
            del self._oauth_states[state]
            return result
            
        except Exception as e:
            logger.error(f"OAuth callback failed for {exchange}: {e}")
            # Clean up state even on error
            if state in self._oauth_states:
                del self._oauth_states[state]
            raise
    
    def _handle_binance_callback(self, code: str, oauth_state: OAuthState) -> Dict[str, Any]:
        """Handle Binance OAuth callback."""
        token_url = "https://accounts.binance.com/oauth/token"
        data = {
            "client_id": self.oauth_config.binance_client_id,
            "client_secret": self.oauth_config.binance_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.oauth_config.binance_redirect_uri
        }
        
        response = requests.post(token_url, data=data, timeout=30)
        if response.status_code != 200:
            logger.error(f"Binance token exchange failed: {response.text}")
            raise ValueError("Failed to exchange code for tokens")
        
        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        
        if not access_token:
            raise ValueError("No access token received from Binance")
        
        # Test the token with a simple API call
        user_info = self._test_binance_token(access_token)
        
        # Store credentials
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        self._store_oauth_credentials(
            user_id=oauth_state.user_id,
            exchange="binance",
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at
        )
        
        return {
            "exchange": "binance",
            "user_info": user_info,
            "expires_at": expires_at
        }
    
    def _handle_bybit_callback(self, code: str, oauth_state: OAuthState) -> Dict[str, Any]:
        """Handle Bybit OAuth callback."""
        token_url = "https://api.bybit.com/oauth/token"
        data = {
            "client_id": self.oauth_config.bybit_client_id,
            "client_secret": self.oauth_config.bybit_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.oauth_config.bybit_redirect_uri
        }
        
        response = requests.post(token_url, data=data, timeout=30)
        if response.status_code != 200:
            logger.error(f"Bybit token exchange failed: {response.text}")
            raise ValueError("Failed to exchange code for tokens")
        
        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        
        # Bybit may also provide API keys directly
        api_key = token_data.get("api_key")
        api_secret = token_data.get("api_secret")
        
        if not access_token:
            raise ValueError("No access token received from Bybit")
        
        # Test connection
        user_info = self._test_bybit_token(access_token)
        
        # Store credentials (both OAuth tokens and API keys if provided)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        self._store_oauth_credentials(
            user_id=oauth_state.user_id,
            exchange="bybit",
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            api_key=api_key,
            api_secret=api_secret
        )
        
        return {
            "exchange": "bybit",
            "user_info": user_info,
            "expires_at": expires_at
        }
    
    def _test_binance_token(self, access_token: str) -> Dict[str, Any]:
        """Test Binance access token by fetching user info."""
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(
            "https://api.binance.com/api/v3/account",
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            raise ValueError("Invalid access token or insufficient permissions")
        
        return response.json()
    
    def _test_bybit_token(self, access_token: str) -> Dict[str, Any]:
        """Test Bybit access token."""
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(
            "https://api.bybit.com/v5/user/query-api",
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            raise ValueError("Invalid access token or insufficient permissions")
        
        return response.json()
    
    def _store_oauth_credentials(
        self,
        user_id: str,
        exchange: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ):
        """Store OAuth credentials securely in database."""
        db = self._get_db()
        try:
            # Check if credentials already exist
            existing = db.query(ExchangeCredential).filter_by(
                user_id=user_id,
                exchange=exchange
            ).first()
            
            if existing:
                # Update existing
                existing.access_token_encrypted = self.security.encrypt(access_token)
                if refresh_token:
                    existing.refresh_token_encrypted = self.security.encrypt(refresh_token)
                existing.token_expires_at = expires_at
                existing.updated_at = datetime.utcnow()
                existing.last_used_at = datetime.utcnow()
                existing.is_active = True
                
                # Store API keys if provided (Bybit case)
                if api_key:
                    existing.api_key = self.mask_api_key(api_key)
                    existing.api_key_encrypted = self.security.encrypt(api_key)
                if api_secret:
                    existing.api_secret_encrypted = self.security.encrypt(api_secret)
                    
                credential = existing
            else:
                # Create new
                credential = ExchangeCredential(
                    user_id=user_id,
                    exchange=exchange,
                    access_token_encrypted=self.security.encrypt(access_token),
                    refresh_token_encrypted=self.security.encrypt(refresh_token) if refresh_token else None,
                    token_expires_at=expires_at,
                    api_key=self.mask_api_key(api_key) if api_key else None,
                    api_key_encrypted=self.security.encrypt(api_key) if api_key else None,
                    api_secret_encrypted=self.security.encrypt(api_secret) if api_secret else None,
                    created_at=datetime.utcnow(),
                    last_used_at=datetime.utcnow(),
                    is_active=True
                )
                db.add(credential)
            
            db.commit()
            logger.info(f"OAuth credentials stored for user {user_id} on {exchange}")
            
        finally:
            db.close()
    
    # =================== API Key Methods ===================
    
    def connect_via_api_key(self, user_id: str, form_data: ExchangeConnectionForm) -> Dict[str, Any]:
        """Connect exchange using API keys."""
        exchange = form_data.exchange.lower()
        
        # Validate exchange
        if exchange not in ["binance", "bybit", "primexbt"]:
            raise ValueError(f"Unsupported exchange: {exchange}")
        
        # Test API keys
        if exchange == "binance":
            account_info = self._test_binance_api_key(form_data)
        elif exchange == "bybit":
            account_info = self._test_bybit_api_key(form_data)
        elif exchange == "primexbt":
            account_info = self._test_primexbt_api_key(form_data)
        
        # Store credentials
        self._store_api_credentials(user_id, form_data, account_info)
        
        return {
            "exchange": exchange,
            "account_info": account_info,
            "api_key_masked": self.mask_api_key(form_data.api_key)
        }
    
    def _test_binance_api_key(self, form_data: ExchangeConnectionForm) -> Dict[str, Any]:
        """Test Binance API key by fetching account info."""
        api_key = form_data.api_key
        api_secret = form_data.api_secret.get_secret_value()
        
        base_url = "https://testnet.binance.vision" if form_data.testnet else "https://api.binance.com"
        endpoint = "/api/v3/account"
        
        timestamp = int(time.time() * 1000)
        query = f"timestamp={timestamp}"
        signature = hmac.new(
            api_secret.encode(),
            query.encode(),
            hashlib.sha256
        ).hexdigest()
        
        headers = {"X-MBX-APIKEY": api_key}
        url = f"{base_url}{endpoint}?{query}&signature={signature}"
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Binance API test failed: {response.text}")
            raise ValueError("Invalid API credentials or insufficient permissions")
        
        return response.json()
    
    def _test_bybit_api_key(self, form_data: ExchangeConnectionForm) -> Dict[str, Any]:
        """Test Bybit API key."""
        api_key = form_data.api_key
        api_secret = form_data.api_secret.get_secret_value()
        
        base_url = "https://api-testnet.bybit.com" if form_data.testnet else "https://api.bybit.com"
        endpoint = "/v5/account/wallet-balance"
        
        timestamp = str(int(time.time() * 1000))
        
        # Bybit signature method
        param_str = f"accountType=UNIFIED&timestamp={timestamp}"
        signature = hmac.new(
            api_secret.encode(),
            param_str.encode(),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": "5000"
        }
        
        url = f"{base_url}{endpoint}?accountType=UNIFIED"
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Bybit API test failed: {response.text}")
            raise ValueError("Invalid API credentials or insufficient permissions")
        
        data = response.json()
        if data.get("retCode") != 0:
            raise ValueError(f"Bybit API error: {data.get('retMsg', 'Unknown error')}")
        
        return data
    
    def _test_primexbt_api_key(self, form_data: ExchangeConnectionForm) -> Dict[str, Any]:
        """Test PrimeXBT API key."""
        api_key = form_data.api_key
        api_secret = form_data.api_secret.get_secret_value()
        
        # PrimeXBT doesn't have testnet, but has demo accounts
        base_url = "https://api.primexbt.com"
        endpoint = "/v1/account"
        
        nonce = str(int(time.time() * 1000))
        
        # PrimeXBT signature method (example - adjust based on actual documentation)
        message = f"nonce={nonce}"
        signature = hmac.new(
            api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            "X-API-KEY": api_key,
            "X-API-SIGNATURE": signature,
            "X-API-NONCE": nonce
        }
        
        response = requests.get(f"{base_url}{endpoint}", headers=headers, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"PrimeXBT API test failed: {response.text}")
            raise ValueError("Invalid API credentials or insufficient permissions")
        
        return response.json()
    
    def _store_api_credentials(
        self,
        user_id: str,
        form_data: ExchangeConnectionForm,
        account_info: Dict[str, Any]
    ):
        """Store API credentials securely in database."""
        db = self._get_db()
        try:
            # Check if credentials already exist
            existing = db.query(ExchangeCredential).filter_by(
                user_id=user_id,
                exchange=form_data.exchange
            ).first()
            
            if existing:
                # Update existing
                existing.api_key = self.mask_api_key(form_data.api_key)
                existing.api_key_encrypted = self.security.encrypt(form_data.api_key)
                existing.api_secret_encrypted = self.security.encrypt(form_data.api_secret.get_secret_value())
                if form_data.passphrase:
                    existing.passphrase_encrypted = self.security.encrypt(form_data.passphrase.get_secret_value())
                existing.testnet = form_data.testnet
                existing.updated_at = datetime.utcnow()
                existing.last_used_at = datetime.utcnow()
                existing.is_active = True
                credential = existing
            else:
                # Create new
                credential = ExchangeCredential(
                    user_id=user_id,
                    exchange=form_data.exchange,
                    api_key=self.mask_api_key(form_data.api_key),
                    api_key_encrypted=self.security.encrypt(form_data.api_key),
                    api_secret_encrypted=self.security.encrypt(form_data.api_secret.get_secret_value()),
                    passphrase_encrypted=self.security.encrypt(form_data.passphrase.get_secret_value()) if form_data.passphrase else None,
                    testnet=form_data.testnet,
                    created_at=datetime.utcnow(),
                    last_used_at=datetime.utcnow(),
                    is_active=True
                )
                db.add(credential)
            
            db.commit()
            logger.info(f"API credentials stored for user {user_id} on {form_data.exchange}")
            
        finally:
            db.close()
    
    # =================== General Methods ===================
    
    def get_user_exchanges(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all connected exchanges for a user."""
        db = self._get_db()
        try:
            credentials = db.query(ExchangeCredential).filter_by(
                user_id=user_id,
                is_active=True
            ).all()
            
            result = []
            for cred in credentials:
                result.append({
                    "id": cred.id,
                    "exchange": cred.exchange,
                    "api_key_masked": cred.api_key,
                    "testnet": cred.testnet,
                    "created_at": cred.created_at,
                    "last_used_at": cred.last_used_at,
                    "has_oauth": bool(cred.access_token_encrypted),
                    "has_api_key": bool(cred.api_key_encrypted),
                    "token_expires_at": cred.token_expires_at
                })
            
            return result
            
        finally:
            db.close()
    
    def disconnect_exchange(self, user_id: str, exchange: str) -> bool:
        """Disconnect an exchange (remove credentials)."""
        db = self._get_db()
        try:
            credential = db.query(ExchangeCredential).filter_by(
                user_id=user_id,
                exchange=exchange
            ).first()
            
            if not credential:
                return False
            
            # TODO: Revoke OAuth tokens if possible
            # For Binance/Bybit OAuth, call revocation endpoint
            
            db.delete(credential)
            db.commit()
            
            logger.info(f"Disconnected {exchange} for user {user_id}")
            return True
            
        finally:
            db.close()
    
    def get_exchange_credentials(self, user_id: str, exchange: str) -> Optional[Dict[str, Any]]:
        """Get decrypted credentials for making API calls."""
        db = self._get_db()
        try:
            credential = db.query(ExchangeCredential).filter_by(
                user_id=user_id,
                exchange=exchange,
                is_active=True
            ).first()
            
            if not credential:
                return None
            
            result = {
                "exchange": exchange,
                "testnet": credential.testnet
            }
            
            # Decrypt credentials
            if credential.api_key_encrypted:
                result["api_key"] = self.security.decrypt(credential.api_key_encrypted)
            
            if credential.api_secret_encrypted:
                result["api_secret"] = self.security.decrypt(credential.api_secret_encrypted)
            
            if credential.passphrase_encrypted:
                result["passphrase"] = self.security.decrypt(credential.passphrase_encrypted)
            
            if credential.access_token_encrypted:
                result["access_token"] = self.security.decrypt(credential.access_token_encrypted)
            
            if credential.refresh_token_encrypted:
                result["refresh_token"] = self.security.decrypt(credential.refresh_token_encrypted)
            
            result["token_expires_at"] = credential.token_expires_at
            
            # Update last used time
            credential.last_used_at = datetime.utcnow()
            db.commit()
            
            return result
            
        finally:
            db.close()


# Global instance
_exchange_manager: Optional[ExchangeManager] = None


def get_exchange_manager() -> ExchangeManager:
    """Get or create global ExchangeManager instance."""
    global _exchange_manager
    
    if _exchange_manager is None:
        _exchange_manager = ExchangeManager()
    
    return _exchange_manager
