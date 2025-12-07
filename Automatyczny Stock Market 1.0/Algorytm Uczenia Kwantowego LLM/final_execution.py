
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from manual_buy import manual_buy
from manual_sell import manual_sell

USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

async def run_final_execution():
    print("🚀 Starting Final Execution...")

    # 1. Sell Spot Dust
    # Amounts from previous sync:
    # SOL: 0.39410421
    # ETH: 0.01773258
    # BTC: 0.00058187
    
    dust_assets = [
        {"symbol": "SOL/USDT", "amount": 0.3941}, # Rounding down slightly to be safe
        {"symbol": "ETH/USDT", "amount": 0.0177},
        {"symbol": "BTC/USDT", "amount": 0.00058}
    ]

    print("\n🧹 Selling Spot Dust...")
    for asset in dust_assets:
        print(f"   Selling {asset['amount']} {asset['symbol']} (Spot)...")
        try:
            await manual_sell(
                symbol=asset['symbol'],
                amount=asset['amount'],
                leverage=1, # Explicitly Spot
                user_id=USER_ID
            )
            print(f"   ✅ Sold {asset['symbol']}")
        except Exception as e:
            print(f"   ❌ Failed to sell {asset['symbol']}: {e}")
        await asyncio.sleep(2)

    # 2. Buy BTC Margin
    print("\n🐂 Buying BTC Margin...")
    # TP: 89 925 664 -> 89925.664
    # SL: 82 941 147 -> 82941.147
    
    try:
        await manual_buy(
            symbol="BTC/USDT",
            usdt=54,
            tp=89925.664,
            sl=82941.147,
            leverage=10,
            user_id=USER_ID
        )
        print("   ✅ BTC Margin Buy Completed")
    except Exception as e:
        print(f"   ❌ BTC Margin Buy Failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_final_execution())
