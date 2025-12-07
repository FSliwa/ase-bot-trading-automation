
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

async def test_margin():
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
        # 1. Check Balance
        print("💰 Fetching balances...")
        balance = await exchange.fetch_balance()
        usdt = balance.get('free', {}).get('USDT', 0)
        print(f"   Available USDT: {usdt}")
        
        if usdt < 10:
            print("❌ Not enough USDT to test (need > 10)")
            return

        # 2. Place Margin Buy Order (2x Leverage)
        symbol = "BTC/USDT"
        amount_usdt = 12.0 # Small amount
        leverage = 2
        
        ticker = await exchange.fetch_ticker(symbol)
        price = ticker['last']
        quantity = amount_usdt * leverage / price
        
        print(f"🚀 Placing Margin BUY for {quantity:.6f} BTC (~{amount_usdt} USDT margin, 2x lev)...")
        
        params = {'leverage': leverage}
        
        try:
            order = await exchange.create_market_buy_order(symbol, quantity, params)
            print(f"✅ Order Placed! ID: {order['id']}")
            print(f"   Details: {order}")
            
            # 3. Check if it's a position
            # Kraken Spot Margin positions are not always in fetch_positions in standard CCXT?
            # But we can check balance. If we used margin, we should have borrowed funds?
            # Actually, for Long BTC/USDT, we borrow USDT.
            # So USDT balance should decrease by margin amount? Or total USDT becomes negative?
            # Let's check balance again.
            
            await asyncio.sleep(2)
            new_balance = await exchange.fetch_balance()
            new_usdt = new_balance.get('free', {}).get('USDT', 0)
            print(f"   New USDT Balance: {new_usdt}")
            print(f"   Change: {new_usdt - usdt}")
            
        except Exception as e:
            print(f"❌ Failed to place order: {e}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_margin())
