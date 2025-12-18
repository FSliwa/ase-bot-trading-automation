
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

async def test_levels():
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
        # Check Balance
        balance = await exchange.fetch_balance()
        usdt = balance.get('free', {}).get('USDT', 0)
        print(f"💰 Available USDT: {usdt}")
        
        if usdt < 50:
            print("❌ Not enough USDT to test levels")
            return

        symbol = "BTC/USDT"
        amount_usdt = 12.0 # Small amount
        
        ticker = await exchange.fetch_ticker(symbol)
        price = ticker['last']
        
        # Test 5x
        leverage = 5
        quantity = amount_usdt * leverage / price
        print(f"\n🚀 Testing {leverage}x Leverage (Qty: {quantity:.6f})...")
        
        params = {'leverage': leverage}
        
        try:
            order = await exchange.create_market_buy_order(symbol, quantity, params)
            print(f"✅ 5x Order Placed! ID: {order['id']}")
            print(f"   Descr: {order['info']['descr']['order']}")
            
            # Close it immediately
            print("   Closing...")
            await exchange.create_market_sell_order(symbol, quantity, {'leverage': leverage})
            print("   Closed.")
            
        except Exception as e:
            print(f"❌ 5x Failed: {e}")
            
            # Try 4x
            leverage = 4
            quantity = amount_usdt * leverage / price
            print(f"\n🚀 Testing {leverage}x Leverage (Qty: {quantity:.6f})...")
            params = {'leverage': leverage}
            try:
                order = await exchange.create_market_buy_order(symbol, quantity, params)
                print(f"✅ 4x Order Placed! ID: {order['id']}")
                print(f"   Descr: {order['info']['descr']['order']}")
                print("   Closing...")
                await exchange.create_market_sell_order(symbol, quantity, {'leverage': leverage})
                print("   Closed.")
            except Exception as e2:
                print(f"❌ 4x Failed: {e2}")

                
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_levels())
