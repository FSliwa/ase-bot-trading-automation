import sys
import os
import asyncio
import time
import ccxt.async_support as ccxt
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from datetime import datetime

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

async def analyze_orders():
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
        
        # Use microseconds nonce
        exchange.nonce = lambda: int(time.time() * 1000000)
        
        # 3. Fetch Open Orders
        print("Fetching open orders...")
        orders = await exchange.fetch_open_orders()
        
        print("\n" + "="*80)
        print(f"OPEN ORDERS ANALYSIS FOR USER: {USER_ID}")
        print("="*80)
        
        if not orders:
            print("No open orders found.")
        else:
            print(f"{'ID':<20} | {'SYMBOL':<10} | {'TYPE':<10} | {'SIDE':<5} | {'AMOUNT':<10} | {'PRICE':<10} | {'STOP PRICE':<10} | {'STATUS'}")
            print("-" * 100)
            for order in orders:
                oid = order['id']
                symbol = order['symbol']
                otype = order['type']
                side = order['side']
                amount = order['amount']
                price = order.get('price') or 'Market'
                stop_price = order.get('stopPrice') or order.get('triggerPrice') or '-'
                status = order['status']
                print(f"{oid:<20} | {symbol:<10} | {otype:<10} | {side:<5} | {amount:<10} | {str(price):<10} | {str(stop_price):<10} | {status}")

        # 4. Fetch Closed Orders to verify main trade
        print("\n" + "="*80)
        print("RECENT CLOSED ORDERS (Last 5)")
        print("="*80)
        try:
            closed_orders = await exchange.fetch_closed_orders(limit=5)
            if not closed_orders:
                print("No closed orders found.")
            else:
                print(f"{'ID':<20} | {'SYMBOL':<10} | {'TYPE':<10} | {'SIDE':<5} | {'AMOUNT':<10} | {'PRICE':<10} | {'STATUS'}")
                print("-" * 100)
                for order in closed_orders:
                    oid = order['id']
                    symbol = order['symbol']
                    otype = order['type']
                    side = order['side']
                    amount = order['amount']
                    price = order.get('average') or order.get('price') or '-'
                    status = order['status']
                    print(f"{oid:<20} | {symbol:<10} | {otype:<10} | {side:<5} | {amount:<10} | {str(price):<10} | {status}")
                    
                    # Check if this is our main trade and if it has related orders
                    if oid == 'OPXVQZ-MXBDR-FFHHOF':
                        print(f"  -> Found target order {oid}. Checking info...")
                        print(f"  -> Info: {order.get('info')}")
        except Exception as e:
            print(f"Error fetching closed orders: {e}")

        print("="*80 + "\n")
            
    except Exception as e:
        print(f"Error analyzing orders: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if exchange:
            await exchange.close()

if __name__ == "__main__":
    asyncio.run(analyze_orders())
