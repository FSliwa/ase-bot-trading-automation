
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

async def force_sell():
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
        # 1. Cancel All Orders
        print("🚫 Cancelling all open orders...")
        try:
            await exchange.cancel_all_orders()
            print("   ✅ Orders cancelled.")
        except Exception as e:
            print(f"   ⚠️ Failed to cancel orders: {e}")

        # 2. Fetch Balance
        print("💰 Fetching balances...")
        balance = await exchange.fetch_balance()
        
        assets_to_check = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'PEPE']
        
        for asset in assets_to_check:
            amount = balance.get('free', {}).get(asset, 0)
            print(f"\n--- Checking {asset} ---")
            
            if amount > 0:
                print(f"   Found {amount} {asset}. Selling to USDT...")
                symbol = f"{asset}/USDT"
                
                try:
                    # Check if market exists
                    markets = await exchange.load_markets()
                    if symbol not in markets:
                        print(f"   ❌ Market {symbol} does not exist. Trying USD...")
                        symbol = f"{asset}/USD"
                        if symbol not in markets:
                            print(f"   ❌ Market {symbol} does not exist either. Skipping.")
                            continue

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
    asyncio.run(force_sell())
