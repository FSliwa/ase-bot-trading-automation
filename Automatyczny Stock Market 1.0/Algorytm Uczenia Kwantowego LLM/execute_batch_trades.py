
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from manual_buy import manual_buy

USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

TRADES = [
    {
        "symbol": "ETH/USDT",
        "usdt": 54,
        "tp": 2933.9,
        "sl": 2706.27
    },
    {
        "symbol": "SOL/USDT",
        "usdt": 24,
        "tp": 132.0,
        "sl": 121.56
    },
    {
        "symbol": "XRP/USDT",
        "usdt": 24,
        "tp": 2.15,
        "sl": 1.97
    }
]

async def run_batch():
    print(f"🚀 Starting Batch Execution for User {USER_ID}")
    print(f"ℹ️  Adapting to Kraken Spot Limits: Using 5x Leverage with 2x Margin to maintain Position Size.")
    print(f"📋 Total Trades: {len(TRADES)}")
    
    for i, trade in enumerate(TRADES, 1):
        print(f"\n--- Trade {i}/{len(TRADES)}: {trade['symbol']} ---")
        try:
            await manual_buy(
                symbol=trade['symbol'],
                usdt=trade['usdt'],
                tp=trade['tp'],
                sl=trade['sl'],
                leverage=5,
                user_id=USER_ID
            )
            print(f"✅ Trade {i} Completed")
        except Exception as e:
            print(f"❌ Trade {i} Failed: {e}")
        
        # Small delay between trades
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(run_batch())
