
import asyncio
import sys
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from bot.security import SecurityManager
from bot.http.ccxt_adapter import CCXTAdapter

USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

async def check_orders():
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
        print("\n📋 --- OPEN ORDERS (Pending TP/SL/Limit) ---")
        orders = await adapter.exchange.fetch_open_orders()
        
        if orders:
            for order in orders:
                # Format timestamp
                dt = order['datetime']
                
                # Extract details
                symbol = order['symbol']
                side = order['side'].upper()
                type_ = order['type'].upper()
                amount = order['amount']
                price = order['price']
                status = order['status']
                info = order.get('info', {})
                
                # Kraken specific info for TP/SL might be in 'price2' or 'stopPrice' depending on structure
                # But fetch_open_orders usually normalizes it.
                
                print(f"   🔸 [{dt}] {symbol} {side} {type_}")
                print(f"       ID: {order['id']}")
                print(f"       Amount: {amount}")
                print(f"       Price: {price}")
                if 'stopPrice' in order and order['stopPrice']:
                    print(f"       Stop Price: {order['stopPrice']}")
                print(f"       Status: {status}")
                print("-" * 30)
        else:
            print("   No open orders found.")

    except Exception as e:
        print(f"❌ Error fetching orders: {e}")
    finally:
        await adapter.close()

if __name__ == "__main__":
    asyncio.run(check_orders())
