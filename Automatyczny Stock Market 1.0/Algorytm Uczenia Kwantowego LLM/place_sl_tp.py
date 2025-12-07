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

# Trade Parameters
SYMBOL = "XRP/USDT"
AMOUNT = 130.51771539
STOP_LOSS_PRICE = 2.09
TAKE_PROFIT_PRICE = 2.5

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

async def place_sl_tp():
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
        
        # 3. Place Orders
        print(f"\nPlacing orders for {AMOUNT} {SYMBOL}...")
        print(f"SL: {STOP_LOSS_PRICE}, TP: {TAKE_PROFIT_PRICE}")
        
        # Note: Placing two separate sell orders for the full amount might fail if funds are locked.
        # We will try to place SL first (priority).
        
        # --- STOP LOSS ---
        print(f"1. Placing Stop Loss at {STOP_LOSS_PRICE}...")
        try:
            # For Kraken stop-loss, 'price' is the stop price.
            # CCXT unified API usually maps 'price' to the limit price for limit orders,
            # but for 'stop-loss' market orders, it might expect 'price' to be the trigger.
            # However, Kraken API uses 'price' as the stop price for stop-loss orders.
            # The error 'Invalid arguments:price' suggests we might be sending it wrongly or it conflicts.
            # Let's try passing 'price' as None and putting the trigger in params['price'] or params['stopPrice'].
            
            # Attempt 2: Use specific params for Kraken
            # Kraken 'stop-loss' is a market order triggered at a price.
            # CCXT: create_order(symbol, 'stop-loss', 'sell', amount, price, params)
            # If we pass price, CCXT might be sending it as 'price' (which is correct for Kraken stop price).
            # But maybe it needs to be explicit.
            
            sl_order = await exchange.create_order(
                symbol=SYMBOL,
                type='stop-loss',
                side='sell',
                amount=AMOUNT,
                price=STOP_LOSS_PRICE, 
                params={} 
            )
            print(f"✅ Stop Loss placed: {sl_order['id']}")
        except Exception as e:
            print(f"❌ Failed to place Stop Loss (Attempt 1): {e}")
            try:
                # Attempt 3: Try 'market' type with params
                print("   -> Retrying as 'market' with stopLossPrice...")
                sl_order = await exchange.create_order(
                    symbol=SYMBOL,
                    type='market',
                    side='sell',
                    amount=AMOUNT,
                    params={'stopLossPrice': STOP_LOSS_PRICE}
                )
                print(f"   ✅ Stop Loss placed (as market w/ stop): {sl_order['id']}")
            except Exception as e2:
                 print(f"   ❌ Failed to place Stop Loss (Attempt 2): {e2}")

            
        # --- TAKE PROFIT ---
        print(f"2. Placing Take Profit at {TAKE_PROFIT_PRICE}...")
        try:
            tp_order = await exchange.create_order(
                symbol=SYMBOL,
                type='take-profit',
                side='sell',
                amount=AMOUNT,
                price=TAKE_PROFIT_PRICE,
                params={}
            )
            print(f"✅ Take Profit placed: {tp_order['id']}")
        except Exception as e:
            print(f"❌ Failed to place Take Profit (Attempt 1): {e}")
            try:
                # Attempt 3: Try 'market' type with takeProfitPrice
                print("   -> Retrying as 'market' with takeProfitPrice...")
                tp_order = await exchange.create_order(
                    symbol=SYMBOL,
                    type='market',
                    side='sell',
                    amount=AMOUNT,
                    params={'takeProfitPrice': TAKE_PROFIT_PRICE}
                )
                print(f"   ✅ Take Profit placed (as market w/ tp): {tp_order['id']}")
            except Exception as e2:
                 print(f"   ❌ Failed to place Take Profit (Attempt 2): {e2}")
                 if "insufficient funds" in str(e2).lower():
                    print("  -> Note: This is expected if the Stop Loss order already locked the funds. OCO is required for both.")

        print("\nDone.")
            
    except Exception as e:
        print(f"Error placing orders: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if exchange:
            await exchange.close()

if __name__ == "__main__":
    asyncio.run(place_sl_tp())
