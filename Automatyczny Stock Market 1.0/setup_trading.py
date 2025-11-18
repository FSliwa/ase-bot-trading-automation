"""
Script to verify API key and create trading settings for filipsliwa.
"""
import sys
import uuid
from pathlib import Path
import os
from dotenv import load_dotenv

# Load .env from Algorytm directory
env_path = Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM" / ".env"
load_dotenv(env_path)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM"))

from bot.db import SessionLocal
from bot.models import APIKey, TradingSettings, Profile
from bot.security import get_security_manager

# User ID for filipsliwa
USER_ID = "3126f9fe-e724-4a33-bf4a-096804d56ece"

def verify_and_setup():
    """Verify API key exists and create trading settings."""
    db = SessionLocal()
    security = get_security_manager()
    
    try:
        # 1. Verify user profile exists
        profile = db.query(Profile).filter_by(user_id=USER_ID).first()
        if not profile:
            print(f"❌ User profile not found: {USER_ID}")
            return
        
        print(f"✅ User profile found: {profile.username}")
        
        # 2. Verify API key exists
        api_key = db.query(APIKey).filter_by(
            user_id=USER_ID,
            exchange="binance",
            is_active=True
        ).first()
        
        if not api_key:
            print(f"❌ No active Binance API key found")
            return
        
        print(f"✅ Binance API key found (ID: {api_key.id})")
        print(f"   Testnet: {api_key.is_testnet}")
        print(f"   Active: {api_key.is_active}")
        
        # Decrypt and display (masked)
        try:
            decrypted_key = security.decrypt(api_key.encrypted_api_key)
            decrypted_secret = security.decrypt(api_key.encrypted_api_secret)
            print(f"   API Key: {decrypted_key[:8]}...{decrypted_key[-8:]}")
            print(f"   Secret: {decrypted_secret[:8]}...{decrypted_secret[-8:]}")
        except Exception as e:
            print(f"   ⚠️  Could not decrypt: {e}")
        
        # 3. Check trading settings
        settings = db.query(TradingSettings).filter_by(user_id=USER_ID).first()
        
        if settings:
            print(f"\n✅ Trading settings already exist:")
            print(f"   ID: {settings.id}")
            print(f"   Exchange: {settings.exchange}")
            print(f"   Max Position: ${settings.max_position_size}")
            print(f"   Max Daily Loss: ${settings.max_daily_loss}")
            print(f"   Risk Level: {settings.risk_level}/5")
            print(f"   Trading Enabled: {settings.is_trading_enabled}")
        else:
            print(f"\n⚠️  No trading settings found. Creating default settings...")
            
            settings = TradingSettings(
                id=uuid.uuid4(),
                user_id=USER_ID,
                exchange="binance",
                max_position_size=1000.0,  # $1000 max per position
                max_daily_loss=100.0,       # $100 max daily loss
                risk_level=2,               # Conservative (1-5 scale)
                is_trading_enabled=False,   # Manual trading only
                preferred_pairs=["BTC/USDT", "ETH/USDT"]
            )
            
            db.add(settings)
            db.commit()
            
            print(f"✅ Trading settings created!")
            print(f"   Exchange: {settings.exchange}")
            print(f"   Max Position: ${settings.max_position_size}")
            print(f"   Max Daily Loss: ${settings.max_daily_loss}")
            print(f"   Risk Level: {settings.risk_level}/5")
            print(f"   Trading Enabled: {settings.is_trading_enabled}")
        
        print("\n" + "="*50)
        print("🚀 TRADING SETUP COMPLETE!")
        print("="*50)
        print(f"\n💡 Next steps:")
        print(f"   1. Test API connection with Binance")
        print(f"   2. Fetch account balance")
        print(f"   3. Start manual trading or enable auto-trading")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    verify_and_setup()
