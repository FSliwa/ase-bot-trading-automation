"""
Script to add Binance API key directly to database with encryption.
"""
import sys
import uuid
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM"))

from bot.security import get_security_manager
from bot.db import SessionLocal
from bot.models import APIKey
from datetime import datetime

# User ID for filipsliwa
USER_ID = "3126f9fe-e724-4a33-bf4a-096804d56ece"

# Binance API credentials
API_KEY = "Msr0cE4bwQNHQAip8utQ54D51EjuQTbH3NPyNLAZBoFDJ3FJgRNAYp1E9DbtXEla"
API_SECRET = "rjrTCVMqRhauRcSErJUxoX9YdQwlzIlKHLslcLkxxeJeZtKO6E2YxzlR74JsnZmH"

def add_api_key():
    """Add encrypted API key to database."""
    # Get security manager for encryption
    security = get_security_manager()
    
    # Encrypt credentials
    encrypted_api_key = security.encrypt(API_KEY)
    encrypted_api_secret = security.encrypt(API_SECRET)
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Check if key already exists
        existing = db.query(APIKey).filter_by(
            user_id=USER_ID,
            exchange="binance"
        ).first()
        
        if existing:
            print(f"✅ Binance API key already exists (ID: {existing.id})")
            print(f"   Updating credentials...")
            existing.encrypted_api_key = encrypted_api_key
            existing.encrypted_api_secret = encrypted_api_secret
            existing.is_active = True
            existing.is_testnet = False
            existing.updated_at = datetime.utcnow()
            db.commit()
            print(f"✅ Updated API key: {existing.id}")
        else:
            # Create new API key
            api_key = APIKey(
                id=uuid.uuid4(),
                user_id=USER_ID,
                exchange="binance",
                encrypted_api_key=encrypted_api_key,
                encrypted_api_secret=encrypted_api_secret,
                is_testnet=False,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            db.add(api_key)
            db.commit()
            
            print(f"✅ API key added successfully!")
            print(f"   ID: {api_key.id}")
            print(f"   Exchange: {api_key.exchange}")
            print(f"   Testnet: {api_key.is_testnet}")
            print(f"   Active: {api_key.is_active}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    add_api_key()
