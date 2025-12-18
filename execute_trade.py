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

async def execute_trade():
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
        
        # Debug key
        print(f"API Key length: {len(api_key)}")
        print(f"API Key start: {api_key[:4]}...")
        print(f"API Secret length: {len(api_secret)}")
        
        # Check server time (public)
        try:
            server_time = await exchange.fetch_time()
            print(f"Server time: {server_time}")
        except Exception as e:
            print(f"Failed to fetch server time: {e}")

        # Try microseconds nonce (often used for HFT)
        exchange.nonce = lambda: int(time.time() * 1000000)
        print(f"Using microseconds nonce: {exchange.nonce()}")
        
        # Verify connection
        print("Fetching balance...")
        balance = await exchange.fetch_balance()
        total_usdt = balance['total'].get('USDT', 0)
        free_usdt = balance['free'].get('USDT', 0)
        print(f"Connection verified. Total Balance: {total_usdt} USDT, Free: {free_usdt} USDT")
        
        # 3. Execute Trade
        # Buy XRP with all USDT
        if free_usdt < 10:
             print(f"Warning: Low USDT balance ({free_usdt}). Trade might fail.")
        
        symbol = "XRP/USDT"
        print(f"Fetching ticker for {symbol}...")
        ticker = await exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        print(f"Current {symbol} price: {current_price}")
        
        # Calculate quantity
        amount_usdt = free_usdt * 0.99
        quantity = amount_usdt / current_price
        
        print(f"Placing BUY order for {quantity:.2f} XRP (~{amount_usdt:.2f} USDT)...")
        print(f"SL: 2.09, TP: 2.5")
        
        # Kraken supports 'stop_loss_price' and 'take_profit_price' in params?
        # Or we can use 'stopLoss' and 'takeProfit' params which CCXT unifies for some exchanges.
        # For Kraken, CCXT maps 'stopLoss' to 'stop-loss' order or conditional close?
        
        # Let's try passing params as CCXT expects
        params = {
            'stopLoss': {
                'triggerPrice': 2.09,
            },
            'takeProfit': {
                'triggerPrice': 2.5,
            }
        }
        
        order = await exchange.create_order(
            symbol=symbol,
            type='market',
            side='buy',
            amount=quantity,
            params=params
        )
        
        print(f"Order placed successfully: {order['id']}")
        print(f"Status: {order['status']}")
        print(f"Order info: {order}")
        
        print("Trade execution complete.")
        
    except Exception as e:
        print(f"Error executing trade: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if exchange:
            await exchange.close()

if __name__ == "__main__":
    asyncio.run(execute_trade())
