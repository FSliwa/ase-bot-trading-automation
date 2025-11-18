"""
Test Binance API connection with real credentials.
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env
env_path = Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM" / ".env"
load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM"))

from bot.db import SessionLocal
from bot.models import APIKey
from bot.security import get_security_manager
import ccxt

USER_ID = "3126f9fe-e724-4a33-bf4a-096804d56ece"

def test_binance_connection():
    """Test Binance API connection."""
    db = SessionLocal()
    security = get_security_manager()
    
    try:
        # Get API key
        api_key = db.query(APIKey).filter_by(
            user_id=USER_ID,
            exchange="binance",
            is_active=True
        ).first()
        
        if not api_key:
            print("❌ No API key found")
            return
        
        # Decrypt credentials
        api_key_str = security.decrypt(api_key.encrypted_api_key)
        api_secret_str = security.decrypt(api_key.encrypted_api_secret)
        
        print("🔧 Testing Binance connection...")
        print(f"   Testnet mode: {api_key.is_testnet}")
        
        # Create exchange instance
        exchange = ccxt.binance({
            'apiKey': api_key_str,
            'secret': api_secret_str,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot'  # spot trading
            }
        })
        
        # Test: Fetch account balance
        print("\n📊 Fetching account balance...")
        balance = exchange.fetch_balance()
        
        # Show non-zero balances
        total_balance = balance['total']
        non_zero = {k: v for k, v in total_balance.items() if v > 0}
        
        if non_zero:
            print("✅ Account balance:")
            for currency, amount in non_zero.items():
                print(f"   {currency}: {amount}")
        else:
            print("⚠️  No funds in account (all balances are 0)")
        
        # Test: Fetch market data
        print("\n📈 Fetching BTC/USDT ticker...")
        ticker = exchange.fetch_ticker('BTC/USDT')
        print(f"✅ BTC/USDT Price: ${ticker['last']:,.2f}")
        print(f"   24h High: ${ticker['high']:,.2f}")
        print(f"   24h Low: ${ticker['low']:,.2f}")
        print(f"   24h Volume: {ticker['baseVolume']:,.2f} BTC")
        
        # Test: Check trading permissions
        print("\n🔐 Checking API permissions...")
        account_info = exchange.fetch_balance()
        permissions = account_info.get('info', {}).get('permissions', [])
        
        if permissions:
            print(f"✅ API Permissions: {', '.join(permissions)}")
        else:
            print("⚠️  Could not fetch permissions")
        
        print("\n" + "="*50)
        print("✅ BINANCE CONNECTION SUCCESSFUL!")
        print("="*50)
        print("\n💡 You can now:")
        print("   1. Place manual trades through API")
        print("   2. Enable auto-trading in settings")
        print("   3. Monitor positions and P&L")
        
    except ccxt.AuthenticationError as e:
        print(f"\n❌ Authentication failed!")
        print(f"   Error: {e}")
        print(f"\n💡 Possible issues:")
        print(f"   - API key/secret incorrect")
        print(f"   - IP not whitelisted on Binance")
        print(f"   - API key permissions insufficient")
        
    except Exception as e:
        print(f"\n❌ Connection test failed!")
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        db.close()

if __name__ == "__main__":
    test_binance_connection()
