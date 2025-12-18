
import asyncio
import sys
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from bot.security import SecurityManager
from bot.exchange_adapters.ccxt_adapter import CCXTAdapter

USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"
SYMBOL = "LINK/USDT"

async def close_link_user1():
    load_dotenv()
    
    # Database setup
    SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
    DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")
    if "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"
    
    engine = create_engine(DATABASE_URL)
    security_manager = SecurityManager()
    
    print(f"\n📉 Closing {SYMBOL} for User: {USER_ID}")
    
    # Fetch credentials
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
        # Fetch Positions
        positions = await adapter.get_positions()
        target_position = None
        
        for p in positions:
            if p.symbol == SYMBOL:
                target_position = p
                break
        
        if target_position:
            qty = target_position.quantity
            print(f"   🎯 Found Position: {qty} {SYMBOL}")
            
            if qty > 0:
                print(f"   💸 Closing Position (Selling {qty} {SYMBOL})...")
                order = await adapter.place_order(
                    symbol=SYMBOL,
                    side='sell',
                    order_type='market',
                    quantity=qty,
                    leverage=int(target_position.leverage)
                )
                print(f"   ✅ Position Closed! Order ID: {order.id}")
            else:
                print("   ⚠️ Position quantity is 0 or negative.")
        else:
            print(f"   ❌ No open position found for {SYMBOL}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    finally:
        await adapter.close()

if __name__ == "__main__":
    asyncio.run(close_link_user1())
