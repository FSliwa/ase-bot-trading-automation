
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

async def close_test():
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
        # Close BTC position (Sell BTC with leverage)
        # To close a Long Margin position, we Sell with leverage.
        symbol = "BTC/USDT"
        amount = 0.00027 # From previous step
        leverage = 2
        
        print(f"🚀 Closing Margin Position: Sell {amount} BTC (2x lev)...")
        
        params = {'leverage': leverage}
        
        try:
            order = await exchange.create_market_sell_order(symbol, amount, params)
            print(f"✅ Position Closed! Order ID: {order['id']}")
            print(f"   Details: {order}")
        except Exception as e:
            print(f"❌ Failed to close position: {e}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(close_test())
