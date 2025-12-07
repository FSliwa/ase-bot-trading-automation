
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from manual_sell import manual_sell

USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

async def close_positions():
    print("🚀 Closing Margin Positions...")

    positions_to_close = [
        {"symbol": "BTC/USDT", "amount": 0.01278944, "leverage": 10},
        {"symbol": "BNB/USD", "amount": 0.29088, "leverage": 3},
        {"symbol": "SOL/USDT", "amount": 0.94562647, "leverage": 5},
        {"symbol": "ETH/USDT", "amount": 0.09589294, "leverage": 5}
    ]

    for pos in positions_to_close:
        print(f"\n📉 Closing {pos['symbol']} ({pos['amount']}) Lev: {pos['leverage']}x...")
        try:
            await manual_sell(
                symbol=pos['symbol'],
                amount=pos['amount'],
                leverage=pos['leverage'],
                user_id=USER_ID
            )
            print(f"   ✅ Closed {pos['symbol']}")
        except Exception as e:
            print(f"   ❌ Failed to close {pos['symbol']}: {e}")
        
        # Small delay to avoid rate limits
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(close_positions())
