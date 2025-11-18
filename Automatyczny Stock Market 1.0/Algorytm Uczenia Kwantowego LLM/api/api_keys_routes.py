"""
API Keys Management Routes
Endpoints for users to manage their exchange API keys
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
import uuid

from bot.database import DatabaseManager
from bot.models import APIKey
from bot.security import get_security_manager
from .auth_routes import verify_token

api_keys_router = APIRouter(prefix="/api/keys", tags=["API Keys"])


class AddAPIKeyRequest(BaseModel):
    exchange: str  # binance, bybit, okx, etc.
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None
    is_testnet: bool = False


class APIKeyResponse(BaseModel):
    id: str
    exchange: str
    is_active: bool
    is_testnet: bool
    created_at: datetime
    # Note: We don't return the actual keys for security


@api_keys_router.post("/", response_model=APIKeyResponse)
async def add_api_key(
    request: AddAPIKeyRequest,
    token_data: dict = Depends(verify_token)
):
    """
    Add a new exchange API key for the authenticated user.
    Keys are encrypted before storage.
    """
    user_id = token_data.get("sub")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    
    # Get security manager
    security = get_security_manager()
    
    # Encrypt credentials
    encrypted_key = security.encrypt(request.api_key)
    encrypted_secret = security.encrypt(request.api_secret)
    encrypted_passphrase = security.encrypt(request.passphrase) if request.passphrase else None
    
    # Store in database
    with DatabaseManager() as db:
        # Check if user already has a key for this exchange
        existing_key = db.session.query(APIKey).filter(
            APIKey.user_id == user_id,
            APIKey.exchange == request.exchange,
            APIKey.is_testnet == request.is_testnet
        ).first()
        
        if existing_key:
            # Update existing key
            existing_key.encrypted_api_key = encrypted_key
            existing_key.encrypted_api_secret = encrypted_secret
            existing_key.passphrase = encrypted_passphrase
            existing_key.is_active = True
            existing_key.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            
            return APIKeyResponse(
                id=str(existing_key.id),
                exchange=existing_key.exchange,
                is_active=existing_key.is_active,
                is_testnet=existing_key.is_testnet,
                created_at=existing_key.created_at
            )
        else:
            # Create new key
            new_key = APIKey(
                id=uuid.uuid4(),
                user_id=uuid.UUID(user_id),
                exchange=request.exchange,
                encrypted_api_key=encrypted_key,
                encrypted_api_secret=encrypted_secret,
                passphrase=encrypted_passphrase,
                is_testnet=request.is_testnet,
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            
            db.session.add(new_key)
            db.session.commit()
            db.session.refresh(new_key)
            
            return APIKeyResponse(
                id=str(new_key.id),
                exchange=new_key.exchange,
                is_active=new_key.is_active,
                is_testnet=new_key.is_testnet,
                created_at=new_key.created_at
            )


@api_keys_router.get("/", response_model=List[APIKeyResponse])
async def list_api_keys(token_data: dict = Depends(verify_token)):
    """
    List all API keys for the authenticated user.
    """
    user_id = token_data.get("sub")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    
    with DatabaseManager() as db:
        keys = db.session.query(APIKey).filter(
            APIKey.user_id == user_id
        ).all()
        
        return [
            APIKeyResponse(
                id=str(key.id),
                exchange=key.exchange,
                is_active=key.is_active,
                is_testnet=key.is_testnet,
                created_at=key.created_at
            )
            for key in keys
        ]


@api_keys_router.delete("/{key_id}")
async def delete_api_key(
    key_id: str,
    token_data: dict = Depends(verify_token)
):
    """
    Delete an API key. User can only delete their own keys.
    """
    user_id = token_data.get("sub")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    
    with DatabaseManager() as db:
        key = db.session.query(APIKey).filter(
            APIKey.id == uuid.UUID(key_id),
            APIKey.user_id == user_id
        ).first()
        
        if not key:
            raise HTTPException(status_code=404, detail="API key not found")
        
        db.session.delete(key)
        db.session.commit()
        
        return {"message": "API key deleted successfully"}


@api_keys_router.patch("/{key_id}/toggle")
async def toggle_api_key(
    key_id: str,
    token_data: dict = Depends(verify_token)
):
    """
    Activate or deactivate an API key.
    """
    user_id = token_data.get("sub")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    
    with DatabaseManager() as db:
        key = db.session.query(APIKey).filter(
            APIKey.id == uuid.UUID(key_id),
            APIKey.user_id == user_id
        ).first()
        
        if not key:
            raise HTTPException(status_code=404, detail="API key not found")
        
        key.is_active = not key.is_active
        key.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        
        return {
            "message": f"API key {'activated' if key.is_active else 'deactivated'}",
            "is_active": key.is_active
        }
