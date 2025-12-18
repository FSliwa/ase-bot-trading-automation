
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

# All users to check
USERS = [
    "4177e228-e38e-4a64-b34a-2005a959fcf2",  # Kraken User 1
    "e4f7f9e4-1664-4419-aaa2-592f12dc2f2a",  # Binance User
    "b812b608-3bdc-4afe-9dbd-9857e65a3bfe",  # Kraken User 3
]

async def check_user_balance(user_id: str, engine, security_manager):
    print(f"\n{'='*60}")
    print(f"🔍 User: {user_id[:8]}...")
    print(f"{'='*60}")
    
    # Fetch credentials
    with engine.connect() as conn:
        query = text("SELECT encrypted_api_key, encrypted_api_secret, exchange, is_testnet FROM api_keys WHERE user_id = :user_id AND is_active = true")
        result = conn.execute(query, {"user_id": user_id}).fetchone()
        
        if not result:
            print("   ❌ No API keys found")
            return
            
        api_key = security_manager.decrypt(result.encrypted_api_key)
        api_secret = security_manager.decrypt(result.encrypted_api_secret)
        exchange_name = result.exchange
        is_testnet = result.is_testnet
    
    print(f"   🏦 Exchange: {exchange_name} {'(testnet)' if is_testnet else '(live)'}")
    
    # Initialize adapter
    adapter = CCXTAdapter(
        api_key=api_key,
        api_secret=api_secret,
        exchange_name=exchange_name,
        testnet=is_testnet,
        futures=False  # Use spot for balance
    )
    
    try:
        # Fetch Full Balance
        balance = await adapter.exchange.fetch_balance()
        total_balance = balance.get('total', {})
        free_balance = balance.get('free', {})
        
        print("   💰 Portfolio Balances:")
        
        total_usd = 0.0
        assets_found = []
        
        for asset, amount in sorted(total_balance.items()):
            if amount > 0:
                free = free_balance.get(asset, 0)
                used = amount - free
                assets_found.append((asset, amount, free, used))
                print(f"      🔹 {asset}: {amount:.8f} (Free: {free:.8f}, Used: {used:.8f})")
        
        if not assets_found:
            print("      (No assets found)")
        
        # Try to get positions
        print("\n   📊 Open Positions:")
        try:
            positions = await adapter.get_positions()
            if positions:
                for pos in positions:
                    symbol = pos.get('symbol', 'N/A')
                    qty = pos.get('amount', pos.get('contracts', 0))
                    entry = pos.get('entryPrice', pos.get('entry_price', 0))
                    pnl = pos.get('unrealizedPnl', pos.get('unrealized_pnl', 0))
                    print(f"      📈 {symbol}: qty={qty} @ {entry} | PnL: {pnl}")
            else:
                print("      (No open positions)")
        except Exception as e:
            print(f"      ⚠️ Could not fetch positions: {e}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    finally:
        await adapter.close()

async def check_all_users():
    load_dotenv()
    
    # Database setup
    SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
    DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")
    if DATABASE_URL and "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"
    
    engine = create_engine(DATABASE_URL)
    security_manager = SecurityManager()
    
    print("\n" + "="*60)
    print("📊 ASE BOT - Portfolio Status for All Users")
    print("="*60)
    
    for user_id in USERS:
        await check_user_balance(user_id, engine, security_manager)
    
    print("\n" + "="*60)
    print("✅ Done checking all users")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(check_all_users())
