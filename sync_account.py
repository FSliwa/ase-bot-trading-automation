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
from bot.db import DatabaseManager

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

async def sync_account():
    exchange = None
    try:
        # 1. Get keys
        api_key, api_secret = get_decrypted_keys(USER_ID, EXCHANGE_NAME)
        print("Keys decrypted successfully.")
        
        # 2. Connect to exchange
        print(f"Connecting to {EXCHANGE_NAME}...")
        
        exchange_class = getattr(ccxt, EXCHANGE_NAME)
        exchange = exchange_class({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
            }
        })
        
        # Use microseconds nonce as it worked before
        exchange.nonce = lambda: int(time.time() * 1000000)
        
        # 3. Fetch Balance
        print("Fetching balance...")
        balance = await exchange.fetch_balance()
        
        total_usdt_value = 0.0
        print("\n" + "="*50)
        print(f"ACCOUNT STATE FOR USER: {USER_ID}")
        print("="*50)
        print(f"{'ASSET':<10} | {'FREE':<15} | {'USED':<15} | {'TOTAL':<15} | {'VALUE (USDT)'}")
        print("-" * 80)
        
        # Calculate total value and print details
        # We need prices for non-USDT assets to calculate total value
        # For simplicity, we will fetch ticker for non-USDT assets if possible, or just estimate
        
        for currency, amount in balance['total'].items():
            if amount > 0:
                free = balance['free'].get(currency, 0.0)
                used = balance['used'].get(currency, 0.0)
                
                # Estimate value in USDT
                value_usdt = 0.0
                if currency in ['USDT', 'USD']:
                    value_usdt = amount
                else:
                    try:
                        # Try to get price
                        symbol = f"{currency}/USDT"
                        if currency == 'XRP': # We know we have XRP
                             ticker = await exchange.fetch_ticker(symbol)
                             price = ticker['last']
                             value_usdt = amount * price
                    except Exception:
                        pass # Ignore if price fetch fails
                
                total_usdt_value += value_usdt
                
                print(f"{currency:<10} | {free:<15.8f} | {used:<15.8f} | {amount:<15.8f} | {value_usdt:.2f}")
        
        print("-" * 80)
        print(f"TOTAL ESTIMATED VALUE: {total_usdt_value:.2f} USDT")
        print("="*50 + "\n")
        
        # 4. Update Database
        print("Updating database...")
        with DatabaseManager() as db:
            # Record portfolio snapshot
            snapshot = db.record_portfolio_snapshot(
                user_id=USER_ID,
                total_balance=total_usdt_value,
                available_balance=balance['free'].get('USDT', 0.0), # Assuming USDT is main
                margin_used=0.0, # Spot only for now
                unrealized_pnl=0.0,
                metadata={
                    "exchange": EXCHANGE_NAME,
                    "raw_balance": balance['total']
                }
            )
            print(f"Portfolio snapshot recorded with ID: {snapshot.id}")
            
    except Exception as e:
        print(f"Error syncing account: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if exchange:
            await exchange.close()

if __name__ == "__main__":
    asyncio.run(sync_account())
