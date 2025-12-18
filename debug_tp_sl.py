
import asyncio
import sys
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import json

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from bot.security import SecurityManager
from bot.exchange_adapters.ccxt_adapter import CCXTAdapter

USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

async def debug_tp_sl():
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
        is_testnet = result.is_testnet
    
    # Initialize adapter
    adapter = CCXTAdapter(
        api_key=api_key,
        api_secret=api_secret,
        exchange_name=exchange_name,
        testnet=is_testnet,
        futures=True
    )
    
    try:
        # 1. Place a small order with TP/SL
        symbol = "XRP/USDT"
        amount = 10 # Small amount
        leverage = 5
        
        # Get current price
        ticker = await adapter.exchange.fetch_ticker(symbol)
        price = ticker['last']
        print(f"Current {symbol} price: {price}")
        
        tp = price * 1.05
        sl = price * 0.95
        
        print(f"🚀 Placing Test Order: {amount} {symbol} (Lev: {leverage})")
        print(f"   TP: {tp}")
        print(f"   SL: {sl}")
        
        order = await adapter.place_order(
            symbol=symbol,
            side='buy',
            order_type='market',
            quantity=amount,
            leverage=leverage,
            take_profit=tp,
            stop_loss=sl
        )
        
        print(f"✅ Order Placed! ID: {order.id}")
        
        # 1b. Place Separate Stop Loss Order
        print(f"🚀 Placing Separate Stop Loss Order (Attempt 3)...")
        # Try create_market_sell_order with stopPrice
        # Note: For Kraken, we might need to specify 'ordertype': 'stop-loss' in params explicitly?
        # Or CCXT handles it if we pass 'stopPrice'?
        # Actually, create_market_sell_order creates a market order. 
        # To make it a stop-loss, we need to change type or params.
        # Let's try create_order with type='stop-loss' again but passing price correctly.
        # Maybe the issue was leverage?
        
        # Let's try create_order but with type='stop-loss' and price=sl
        # And ensure leverage is passed.
        # Maybe 'price' argument in create_order IS the stop price for stop-loss orders?
        # The error 'Invalid arguments:price' suggests it received something it didn't like.
        # Maybe it received both price and price2?
        
        # Let's try using the raw params that worked for the main order but as a separate order?
        # No, main order used 'stopLoss' param which attaches to main.
        
        # Let's try this:
        sl_order = await adapter.exchange.create_order(
            symbol=symbol,
            type='stop-loss',
            side='sell',
            amount=amount,
            price=sl, 
            params={'leverage': leverage}
        )
        print(f"✅ SL Order Placed! ID: {sl_order['id']}")
        
        # 2. Check Open Orders
        print("\n📋 --- OPEN ORDERS ---")
        open_orders = await adapter.exchange.fetch_open_orders()
        print(f"Found {len(open_orders)} open orders.")
        for o in open_orders:
            print(f"   ID: {o['id']} Type: {o['type']} Side: {o['side']} Status: {o['status']}")
            print(f"   Info: {json.dumps(o['info'], indent=2)}")

        # 3. Check Closed Orders
        print("\n🔒 --- CLOSED ORDERS ---")
        closed_orders = await adapter.exchange.fetch_closed_orders(limit=5)
        print(f"Found {len(closed_orders)} closed orders (last 5).")
        for o in closed_orders:
            print(f"   ID: {o['id']} Type: {o['type']} Side: {o['side']} Status: {o['status']}")
            if o['id'] == order.id:
                print(f"   >>> TARGET ORDER INFO: {json.dumps(o['info'], indent=2)}")
        
        # 4. Try fetching with 'trigger' param
        print("\n🔍 --- TRIGGER ORDERS? ---")
        try:
            # Kraken might need this to show conditional orders?
            trigger_orders = await adapter.exchange.fetch_open_orders(params={'trigger': 'any'})
            print(f"Found {len(trigger_orders)} trigger orders.")
            for o in trigger_orders:
                print(f"   ID: {o['id']} Type: {o['type']} Info: {json.dumps(o['info'], indent=2)}")
        except Exception as e:
            print(f"   Fetch trigger orders failed: {e}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await adapter.close()

if __name__ == "__main__":
    asyncio.run(debug_tp_sl())
