
import asyncio
import sys
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import ccxt.async_support as ccxt

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from bot.security import SecurityManager

USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"
ASSETS_TO_SELL = ['BTC', 'ETH', 'BNB', 'SOL']

async def sell_assets():
    load_dotenv()
    
    # Database setup
    SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
    DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")
    if "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"
    
    engine = create_engine(DATABASE_URL)
    security_manager = SecurityManager()
    
    # Fetch credentials
    print(f"🔍 Fetching credentials for user {USER_ID}...")
    with engine.connect() as conn:
        query = text("SELECT encrypted_api_key, encrypted_api_secret, exchange, is_testnet FROM api_keys WHERE user_id = :user_id")
        result = conn.execute(query, {"user_id": USER_ID}).fetchone()
        
        if not result:
            print("❌ No API keys found")
            return
            
        api_key = security_manager.decrypt(result.encrypted_api_key)
        api_secret = security_manager.decrypt(result.encrypted_api_secret)
        exchange_name = result.exchange
    
    print(f"🔌 Connecting to {exchange_name}...")
    exchange_class = getattr(ccxt, exchange_name)
    import time
    exchange = exchange_class({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'adjustForTimeDifference': True,
        },
        'nonce': lambda: int(time.time() * 1000000)
    })
    
    try:
        # 1. Fetch Balance
        print("💰 Fetching balances...")
        balance = await exchange.fetch_balance()
        
        for asset in ASSETS_TO_SELL:
            amount = balance.get('free', {}).get(asset, 0)
            print(f"\n--- Checking {asset} ---")
            
            if amount > 0:
                print(f"   Found {amount} {asset}. Selling...")
                symbol = f"{asset}/USDT"
                
                try:
                    # Check minimum order size if possible, but for now just try to sell
                    order = await exchange.create_market_sell_order(symbol, amount)
                    print(f"   ✅ SOLD {amount} {asset}! Order ID: {order['id']}")
                except Exception as e:
                    print(f"   ❌ Failed to sell {asset}: {e}")
            else:
                print(f"   No free {asset} to sell.")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(sell_assets())
