
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

async def check_positions():
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
        print("\n📉 --- OPEN POSITIONS (fetch_positions) ---")
        try:
            # Try to fetch positions (works for some exchanges/modes)
            positions = await exchange.fetch_positions()
            if positions:
                for pos in positions:
                    print(f"   🔹 {pos['symbol']} {pos['side']} {pos['contracts']} (Entry: {pos['entryPrice']}, PnL: {pos['unrealizedPnl']})")
            else:
                print("   No positions returned by fetch_positions().")
        except Exception as e:
            print(f"   ⚠️ fetch_positions failed: {e}")

        # For Kraken Spot Margin, positions might not be in fetch_positions.
        # We can check 'trade balance' or specific private endpoints if needed.
        # But let's check balance 'used' or negative values.
        
        print("\n💰 --- BALANCE CHECK (Margin signs) ---")
        balance = await exchange.fetch_balance()
        if 'total' in balance:
            for currency, amount in balance['total'].items():
                if amount != 0: # Show even negative
                    print(f"   {currency}: {amount}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(check_positions())
