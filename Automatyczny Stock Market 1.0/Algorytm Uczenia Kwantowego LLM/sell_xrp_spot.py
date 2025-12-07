
import asyncio
import sys
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from bot.security import SecurityManager
from bot.auto_trader import AutomatedTradingBot
from bot.logging_setup import get_logger

logger = get_logger("sell_xrp_spot")
USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

async def sell_xrp_spot():
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

    # Initialize Bot with futures=False for Pure Spot
    print(f"🚀 Initializing bot on {exchange_name} (Spot Mode)...")
    bot = AutomatedTradingBot(
        api_key=api_key,
        api_secret=api_secret,
        exchange_name=exchange_name,
        user_id=USER_ID,
        test_mode=False,
        futures=False # Pure Spot
    )
    bot.testnet = is_testnet
    
    try:
        await bot.initialize()
        
        # Fetch Balance
        print("💰 Fetching XRP Balance...")
        balance = await bot.exchange.exchange.fetch_balance()
        xrp_balance = balance.get('total', {}).get('XRP', 0.0)
        
        print(f"   XRP Balance: {xrp_balance}")
        
        if xrp_balance > 0.1: # Minimum threshold
            print(f"\n💸 Selling {xrp_balance} XRP/USDT (Spot)...")
            try:
                # place_order is a method of CCXTAdapter, so bot.exchange.place_order is correct
                order = await bot.exchange.place_order(
                    symbol='XRP/USDT',
                    side='sell',
                    order_type='market',
                    quantity=xrp_balance
                )
                print(f"✅ Sold XRP! ID: {order.id}")
            except Exception as e:
                print(f"❌ Failed to sell XRP: {e}")
        else:
            print("   ⚠️ Balance too low to sell.")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if bot.exchange:
            await bot.exchange.close()

if __name__ == "__main__":
    asyncio.run(sell_xrp_spot())
