
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

async def diagnose():
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
        # 1. Check Spot Balance & Portfolio Value
        print("\n💰 --- SPOT BALANCE CHECK ---")
        balance = await exchange.fetch_balance()
        total_usdt_value = 0.0
        
        if 'total' in balance:
            print("\n📊 --- ASSET BREAKDOWN ---")
            for currency, amount in balance['total'].items():
                if amount > 0:
                    free = balance.get('free', {}).get(currency, 0)
                    used = balance.get('used', {}).get(currency, 0)
                    print(f"   🔹 {currency}: Total={amount} (Free={free}, Used={used})")
                    
                    # Estimate USDT value
                    if currency == 'USDT':
                        total_usdt_value += amount
                    elif currency != 'USD' and currency != 'USDG':
                        try:
                            ticker = await exchange.fetch_ticker(f"{currency}/USDT")
                            val = amount * ticker['last']
                            total_usdt_value += val
                            print(f"      (≈ {val:.2f} USDT)")
                        except:
                            pass
        
        print(f"\n💵 Estimated Total Spot Portfolio Value: ~{total_usdt_value:.2f} USDT")

        # 2. Check Futures Balance (using same keys)
        print("\n🔮 --- FUTURES BALANCE CHECK ---")
        try:
            exchange_futures = ccxt.krakenfutures({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
            })
            futures_balance = await exchange_futures.fetch_balance()
            print("✅ Connected to Kraken Futures!")
            if 'total' in futures_balance:
                 for currency, amount in futures_balance['total'].items():
                    if amount > 0:
                        print(f"   {currency}: {amount}")
            else:
                print("   No positive balance found on Futures.")
            await exchange_futures.close()
        except Exception as e:
            print(f"❌ Could not connect to Kraken Futures with these keys: {e}")

        # 3. Check Open Orders
        print("\n📜 --- OPEN ORDERS CHECK ---")
        open_orders = await exchange.fetch_open_orders()
        if open_orders:
            print(f"⚠️ Found {len(open_orders)} open orders!")
            for order in open_orders:
                print(f"   - {order['symbol']} {order['side']} {order['amount']} (Filled: {order['filled']})")
        else:
            print("✅ No open orders blocking funds.")
            
    except Exception as e:
        print(f"❌ Error during diagnosis: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    # Redirect stdout to file
    with open("diagnosis.txt", "w") as f:
        sys.stdout = f
        asyncio.run(diagnose())
