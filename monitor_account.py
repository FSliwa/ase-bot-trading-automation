
import asyncio
import sys
import os
import time
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from bot.security import SecurityManager
from bot.exchange_adapters.ccxt_adapter import CCXTAdapter

USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

async def monitor_account():
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
    
    print("🚀 Starting Account Monitor (Interval: 60s)...")
    print("Press Ctrl+C to stop.")
    
    try:
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"⏱️  Update: {now}")
            print("-" * 50)
            
            try:
                # 1. Positions
                print("📉 --- OPEN POSITIONS ---")
                positions = await adapter.get_positions()
                total_pnl = 0.0
                total_margin_used = 0.0
                
                if positions:
                    for pos in positions:
                        # Estimate margin used
                        entry_val = pos.quantity * pos.entry_price
                        
                        # Fetch current price for better estimation
                        ticker = await adapter.exchange.fetch_ticker(pos.symbol)
                        current_price = ticker['last']
                        current_val = pos.quantity * current_price
                        estimated_margin = current_val / pos.leverage if pos.leverage else 0
                        
                        print(f"   🔹 {pos.symbol:<10} {pos.side.upper():<4} {pos.quantity:<10} (Lev: {pos.leverage}x, PnL: {pos.unrealized_pnl:.2f}) | Margin: ~{estimated_margin:.2f} USDT")
                        total_pnl += float(pos.unrealized_pnl or 0)
                        total_margin_used += estimated_margin
                else:
                    print("   No open positions.")
                
                print(f"   📊 Total Unrealized PnL: {total_pnl:.2f} USDT")
                print(f"   🔒 Total Margin Used:    ~{total_margin_used:.2f} USDT")

                # 2. Balance
                print("\n💰 --- BALANCE ---")
                balance = await adapter.exchange.fetch_balance()
                total_equity = 0.0
                
                if 'total' in balance:
                    for currency, amount in balance['total'].items():
                        if amount > 0.0001: # Filter dust
                            free = balance.get('free', {}).get(currency, 0)
                            used = balance.get('used', {}).get(currency, 0)
                            print(f"   💵 {currency:<5}: Total={amount:.4f} (Free={free:.4f})")
                            
                            # Estimate equity (very rough, assuming USDT base)
                            if currency == 'USDT':
                                total_equity += amount
                            # Add other assets value if needed, but for now just showing balances
                
                print("-" * 50)
                print("Waiting 60s...")
                
            except Exception as e:
                print(f"❌ Error during update: {e}")
            
            await asyncio.sleep(60)
            
    except KeyboardInterrupt:
        print("\n🛑 Monitor stopped.")
    except Exception as e:
        print(f"❌ Fatal Error: {e}")
    finally:
        await adapter.close()

if __name__ == "__main__":
    try:
        asyncio.run(monitor_account())
    except KeyboardInterrupt:
        pass
