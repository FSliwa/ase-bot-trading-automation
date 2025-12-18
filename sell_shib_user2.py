
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

USER_ID = "b812b608-3bdc-4afe-9dbd-9857e65a3bfe"

async def sell_shib_user2():
    load_dotenv()
    
    # Database setup
    SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
    DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")
    if "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"
    
    engine = create_engine(DATABASE_URL)
    security_manager = SecurityManager()
    
    print(f"\n💸 Selling SHIB for User: {USER_ID}")
    
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
    
    # Initialize adapter (Spot Mode)
    adapter = CCXTAdapter(
        api_key=api_key,
        api_secret=api_secret,
        exchange_name=exchange_name,
        testnet=is_testnet,
        futures=False # Spot
    )
    
    try:
        # Fetch SHIB Balance
        balance = await adapter.exchange.fetch_balance()
        shib_balance = balance.get('total', {}).get('SHIB', 0.0)
        
        print(f"   🐶 SHIB Balance: {shib_balance}")
        
        if shib_balance > 1000: # Minimum threshold
            # Check available pairs
            markets = await adapter.exchange.load_markets()
            symbol = None
            
            if 'SHIB/USD' in markets:
                symbol = 'SHIB/USD'
            elif 'SHIB/USDT' in markets:
                symbol = 'SHIB/USDT'
            elif 'SHIB/EUR' in markets:
                symbol = 'SHIB/EUR'
            
            if symbol:
                print(f"   📉 Selling {shib_balance} {symbol} (Spot)...")
                order = await adapter.place_order(
                    symbol=symbol,
                    side='sell',
                    order_type='market',
                    quantity=shib_balance
                )
                print(f"   ✅ Sold SHIB! ID: {order.id}")
                
                # Verify new balance
                await asyncio.sleep(2)
                new_balance = await adapter.exchange.fetch_balance()
                quote = symbol.split('/')[1]
                new_quote_bal = new_balance.get('total', {}).get(quote, 0.0)
                print(f"   💰 New {quote} Balance: {new_quote_bal}")
            else:
                print("   ❌ No suitable SHIB pair found (USD/USDT/EUR)")
        else:
            print("   ⚠️ Balance too low to sell.")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    finally:
        await adapter.close()

if __name__ == "__main__":
    asyncio.run(sell_shib_user2())
