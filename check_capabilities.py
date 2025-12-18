import sys
import os
import asyncio
import time
import ccxt.async_support as ccxt
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Add project root to path
sys.path.append(str(Path(__file__).parent))

load_dotenv()

from bot.security import SecurityManager

# User ID identified from database
USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"
EXCHANGE_NAME = "kraken"

# Get database URL
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")
if "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

engine = create_engine(DATABASE_URL)

def get_decrypted_keys(user_id, exchange):
    print(f"Fetching keys for user {user_id} on {exchange}...")
    with engine.connect() as conn:
        query = text("SELECT encrypted_api_key, encrypted_api_secret FROM api_keys WHERE user_id = :user_id AND exchange = :exchange")
        result = conn.execute(query, {"user_id": user_id, "exchange": exchange}).fetchone()
        
        if not result:
            raise ValueError(f"No keys found for user {user_id} on {exchange}")
            
        encrypted_key, encrypted_secret = result
        
        sm = SecurityManager()
        api_key = sm.decrypt(encrypted_key)
        api_secret = sm.decrypt(encrypted_secret)
        
        return api_key, api_secret

async def check_capabilities():
    exchange = None
    futures_exchange = None
    try:
        # 1. Get keys
        api_key, api_secret = get_decrypted_keys(USER_ID, EXCHANGE_NAME)
        print("Keys decrypted successfully.")
        
        # 2. Check Spot/Margin (Kraken)
        print(f"\nChecking {EXCHANGE_NAME} (Spot/Margin)...")
        exchange_class = getattr(ccxt, EXCHANGE_NAME)
        exchange = exchange_class({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {'adjustForTimeDifference': True}
        })
        exchange.nonce = lambda: int(time.time() * 1000000)
        
        try:
            # Check Balance (Basic Access)
            balance = await exchange.fetch_balance()
            print("✅ Basic Access (Spot): OK")
            
            # Check Margin Trading
            # Try to fetch margin balance or leverage info
            # Kraken returns 'trade' balance which includes margin info if available
            if 'trade' in balance:
                 print(f"   Margin Balance Info: Available")
                 print(f"   Trade Balance: {balance['trade']}")
            else:
                 # Try to create a dummy margin order (validate only) if possible, 
                 # but simpler is to check if we can fetch open orders (which we know we can).
                 # We will assume Margin is possible if we have trading permissions, 
                 # but we can check if 'margin' is in options or load markets.
                 pass

            # Check if markets have margin enabled
            await exchange.load_markets()
            margin_pairs = [s for s, m in exchange.markets.items() if m.get('margin')]
            if margin_pairs:
                print(f"✅ Margin Trading: Supported on {len(margin_pairs)} pairs (e.g., {margin_pairs[:3]})")
            else:
                print("❌ Margin Trading: Not supported or enabled on pairs.")
                
        except Exception as e:
            print(f"❌ Spot/Margin Check Failed: {e}")

        # 3. Check Futures (Kraken Futures)
        # Kraken often uses different keys for Futures, but sometimes they are linked.
        # We will try to use the same keys on 'krakenfutures'.
        print(f"\nChecking Kraken Futures (Perpetuals/Futures)...")
        try:
            futures_exchange = ccxt.krakenfutures({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
                'options': {'adjustForTimeDifference': True}
            })
            
            # Try to fetch balance on Futures
            f_balance = await futures_exchange.fetch_balance()
            print("✅ Futures/Perpetuals Access: OK")
            print(f"   Futures Balance: {f_balance.get('total', 'Unknown')}")
            
        except Exception as e:
            print(f"❌ Futures/Perpetuals Access: Failed ({e})")
            print("   (Note: Kraken Futures usually requires separate API keys or specific permissions)")

    except Exception as e:
        print(f"Error checking capabilities: {e}")
    finally:
        if exchange:
            await exchange.close()
        if futures_exchange:
            await futures_exchange.close()

if __name__ == "__main__":
    asyncio.run(check_capabilities())
