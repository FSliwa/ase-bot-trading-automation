import sys
from pathlib import Path
import os
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM"))

# Load .env from Algorytm directory
env_path = Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM" / ".env"
load_dotenv(env_path)

from bot.db import SessionLocal
from bot.models import APIKey, TradingSettings, Profile
from bot.security import get_security_manager

USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

def check_user():
    db = SessionLocal()
    security = get_security_manager()
    
    try:
        print(f"Checking user: {USER_ID}")
        
        # 1. Check Profile
        profile = db.query(Profile).filter_by(user_id=USER_ID).first()
        if not profile:
            print("❌ User profile not found!")
            return
        print(f"✅ User profile found: {profile.username} ({profile.email})")
        
        # 2. Check API Keys
        api_keys = db.query(APIKey).filter_by(user_id=USER_ID, is_active=True).all()
        if not api_keys:
            print("❌ No active API keys found!")
        else:
            print(f"✅ Found {len(api_keys)} active API keys:")
            for key in api_keys:
                print(f"   - Exchange: {key.exchange}, Testnet: {key.is_testnet}")
                try:
                    decrypted_key = security.decrypt(key.encrypted_api_key)
                    decrypted_secret = security.decrypt(key.encrypted_api_secret)
                    print(f"     Key: {decrypted_key[:4]}...{decrypted_key[-4:]}")
                    print(f"     Secret: {decrypted_secret[:4]}...{decrypted_secret[-4:]}")
                except Exception as e:
                    print(f"     ⚠️ Decryption failed: {e}")

        # 3. Check Trading Settings
        settings = db.query(TradingSettings).filter_by(user_id=USER_ID).first()
        if not settings:
            print("⚠️ No trading settings found.")
        else:
            print("✅ Trading settings found:")
            print(f"   - Enabled: {settings.is_trading_enabled}")
            print(f"   - Exchange: {settings.exchange}")
            print(f"   - Strategy: {settings.strategy_config}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_user()
