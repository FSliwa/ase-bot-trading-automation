
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from manual_buy import manual_buy

USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

async def execute_analysis_trades():
    print("🚀 Executing Analysis Trades...")

    trades = [
        {
            "symbol": "ADA/USDT",
            "usdt": 250,
            "leverage": 5,
            "tp": 0.4676,
            "sl": 0.4152
        },
        {
            "symbol": "SOL/USDT",
            "usdt": 250,
            "leverage": 5,
            # Calculated from 138.94 reference price with 7% TP and 5% SL
            "tp": 148.66, 
            "sl": 131.99
        }
    ]

    for trade in trades:
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
            # Fallback for ADA/USD if USDT fails (common on Kraken)
            if "ADA" in trade['symbol'] and "USDT" in trade['symbol']:
                 print("   ⚠️ Retrying ADA with ADA/USD pair...")
                 try:
                    await manual_buy(
                        symbol="ADA/USD",
                        usdt=trade['usdt'],
                        tp=trade['tp'],
                        sl=trade['sl'],
                        leverage=trade['leverage'],
                        user_id=USER_ID
                    )
                    print(f"   ✅ Trade Executed: ADA/USD")
                 except Exception as e2:
                     print(f"   ❌ Failed to execute ADA/USD: {e2}")

        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(execute_analysis_trades())
