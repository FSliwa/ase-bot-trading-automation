
import asyncio
import sys
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import datetime

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from bot.security import SecurityManager
from bot.http.ccxt_adapter import CCXTAdapter

USERS = [
    "1aa87e38-f100-49d1-85dc-292bc58e25f1",
    "b812b608-3bdc-4afe-9dbd-9857e65a3bfe",
    "8260053f-b934-4581-b057-a9a4f62b126e"
]

async def monitor_group():
    load_dotenv()
    
    # Database setup
    SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
    DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")
    if "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"
    
    engine = create_engine(DATABASE_URL)
    security_manager = SecurityManager()
    
    print(f"🚀 Starting Continuous Group Monitor (Interval: 60s)...")
    
    while True:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n📊 --- GROUP MONITOR --- {timestamp}")
        
        for user_id in USERS:
            try:
                print(f"\n👤 User: {user_id}")
                
                # Fetch credentials
                with engine.connect() as conn:
                    query = text("SELECT encrypted_api_key, encrypted_api_secret, exchange, is_testnet FROM api_keys WHERE user_id = :user_id")
                    result = conn.execute(query, {"user_id": user_id}).fetchone()
                    
                    if not result:
                        print("   ❌ No API keys found")
                        continue
                        
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
                    # --- MARGIN SECTION ---
                    positions = await adapter.get_positions()
                    total_margin_used = 0.0
                    total_unrealized_pnl = 0.0
                    
                    if positions:
                        print("   📉 MARGIN POSITIONS:")
                        for p in positions:
                            # Estimate margin used for this position: (Quantity * Price) / Leverage
                            # We need current price. p.current_price might not be available in Position model depending on implementation.
                            # If not, we can approximate or fetch ticker. 
                            # Let's try to fetch ticker for accurate calculation.
                            try:
                                ticker = await adapter.exchange.fetch_ticker(p.symbol)
                                current_price = ticker['last']
                                position_value = p.quantity * current_price
                                margin_used = position_value / p.leverage
                                total_margin_used += margin_used
                                total_unrealized_pnl += p.unrealized_pnl
                                
                                print(f"      🔹 {p.symbol:<10} {p.side.upper():<4} {p.quantity:>10.4f} | Lev: {p.leverage:>2}x | PnL: {p.unrealized_pnl:>8.2f} | Margin: {margin_used:>8.2f}")
                            except Exception:
                                # Fallback if ticker fails
                                print(f"      🔹 {p.symbol:<10} {p.side.upper():<4} {p.quantity:>10.4f} | Lev: {p.leverage:>2}x | PnL: {p.unrealized_pnl:>8.2f}")
                        
                        print(f"      ----------------------------------------------------------------")
                        print(f"      📊 Total Margin PnL:  {total_unrealized_pnl:>8.2f} USDT (approx)")
                        print(f"      🔒 Total Margin Used: {total_margin_used:>8.2f} USDT (approx)")
                    else:
                        print("   📉 MARGIN POSITIONS: None")

                    # --- SPOT / BALANCE SECTION ---
                    # Fetch full balance to show all spot assets
                    full_balance = await adapter.exchange.fetch_balance()
                    total_balance = full_balance.get('total', {})
                    
                    # Filter for non-zero assets
                    spot_assets = {k: v for k, v in total_balance.items() if v > 0}
                    
                    print("\n   💰 SPOT WALLET & STATS:")
                    if spot_assets:
                        # Print significant assets first
                        for asset, amount in spot_assets.items():
                            if amount > 0.0001: # Filter dust
                                print(f"      💵 {asset:<5}: {amount:>12.4f}")
                    else:
                        print("      (Empty)")
                        
                    # Calculate approximate Equity (USDT + USD + USDC + PnL)
                    # This is a rough estimate.
                    usdt_bal = total_balance.get('USDT', 0.0)
                    usd_bal = total_balance.get('USD', 0.0)
                    usdc_bal = total_balance.get('USDC', 0.0)
                    
                    # Assuming 1:1 peg for simplicity in this view
                    stable_equity = usdt_bal + usd_bal + usdc_bal
                    total_equity = stable_equity + total_unrealized_pnl
                    free_margin = total_equity - total_margin_used
                    
                    print(f"\n   🧮 ACCOUNT SUMMARY (Est.):")
                    print(f"      💵 Stable Balance:    {stable_equity:>8.2f} (USDT/USD/USDC)")
                    print(f"      📈 Total Equity:      {total_equity:>8.2f}")
                    print(f"      🔓 Free Margin:       {free_margin:>8.2f}")
                    
                except Exception as e:
                    print(f"   ❌ Exchange Error: {e}")
                finally:
                    await adapter.close()
            
            except Exception as e:
                print(f"   ❌ System/DB Error for user {user_id}: {e}")
                # Continue to next user
                continue
        
        print("\n⏳ Waiting 60 seconds...")
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(monitor_group())
