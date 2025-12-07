
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from manual_buy import manual_buy

USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

async def execute_btc_analysis():
    print("🚀 Executing BTC Analysis Trade (850 USDT)...")

    trade = {
        "symbol": "BTC/USDT",
        "usdt": 850,
        "leverage": 5,
        "tp": 97773.15,
        "sl": 86807.76
    }

    print(f"\n🐂 Buying {trade['symbol']} (Margin {trade['leverage']}x)...")
    print(f"   Amount: {trade['usdt']} USDT")
    print(f"   TP: {trade['tp']}")
    print(f"   SL: {trade['sl']}")
    
    try:
        await manual_buy(
            symbol=trade['symbol'],
            usdt=trade['usdt'],
            tp=trade['tp'],
            sl=trade['sl'],
            leverage=trade['leverage'],
            user_id=USER_ID
        )
        print(f"   ✅ Trade Executed: {trade['symbol']}")
    except Exception as e:
        print(f"   ❌ Failed to execute {trade['symbol']}: {e}")

if __name__ == "__main__":
    asyncio.run(execute_btc_analysis())
