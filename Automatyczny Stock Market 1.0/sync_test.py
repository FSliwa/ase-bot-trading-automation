"""
Sync Kraken account data to database for webapp display.
Based on sync_binance_to_db.py
"""
import sys
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone
from decimal import Decimal

# Load .env from the correct location
script_dir = Path(__file__).parent.absolute()
env_path = script_dir / "Algorytm Uczenia Kwantowego LLM" / ".env"
print(f"Loading .env from: {env_path}")
load_dotenv(env_path)

# Verify ENCRYPTION_KEY is loaded
enc_key = os.getenv("ENCRYPTION_KEY")
if enc_key:
    print(f"✅ ENCRYPTION_KEY loaded: {enc_key[:20]}...")
else:
    print("❌ WARNING: ENCRYPTION_KEY not found in .env!")

sys.path.insert(0, str(script_dir / "Algorytm Uczenia Kwantowego LLM"))

from bot.db import SessionLocal, PortfolioSnapshot
from bot.models import APIKey, Portfolio, Trade, PortfolioPerformance
from bot.security import get_security_manager
import ccxt

USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

def sync_kraken_data():
    """Sync Kraken account data to database."""
    db = SessionLocal()
    security = get_security_manager()
    
    try:
        # 1. Get API credentials
        api_key = db.query(APIKey).filter_by(
            user_id=USER_ID,
            exchange="kraken",
            is_active=True
        ).first()
        
        if not api_key:
            print("❌ No API key found")
            return
        
        # Decrypt
        print(f"Decrypting key (prefix: {api_key.encrypted_api_key[:10]}...)...")
        api_key_str = security.decrypt(api_key.encrypted_api_key)
        api_secret_str = security.decrypt(api_key.encrypted_api_secret)
        
        print(f"Decrypted key prefix: {api_key_str[:5]}...")
        
        # 2. Connect to Kraken
        print("🔧 Connecting to Kraken...")
        exchange = ccxt.kraken({
            'apiKey': api_key_str,
            'secret': api_secret_str,
            'enableRateLimit': True,
        })
        
        # 3. Fetch account balance
        print("📊 Fetching balance...")
        balance = exchange.fetch_balance()
        print(f"Balance fetched successfully: {balance['total']}")
        
    except Exception as e:
        print(f"\n❌ Sync failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    sync_kraken_data()
