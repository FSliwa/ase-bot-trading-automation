
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

USER_ID = "b812b608-3bdc-4afe-9dbd-9857e65a3bfe"

async def check_user_balance():
    load_dotenv()
    
    # Database setup
    SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
    DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")
    if "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"
    
    engine = create_engine(DATABASE_URL)
    security_manager = SecurityManager()
    
    print(f"\n🔍 Checking balances for User: {USER_ID}")
    
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
        # Fetch Full Balance
        balance = await adapter.exchange.fetch_balance()
        total_balance = balance.get('total', {})
        
        print(f"   🏦 Exchange: {exchange_name}")
        print("   💰 Non-zero Balances:")
        
        found = False
        for asset, amount in total_balance.items():
            if amount > 0:
                print(f"      🔹 {asset}: {amount}")
                found = True
        
        if not found:
            print("      (No assets found)")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    finally:
        await adapter.close()

if __name__ == "__main__":
    asyncio.run(check_user_balance())
