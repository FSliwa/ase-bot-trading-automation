
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from manual_buy import manual_buy

USERS = [
    "1aa87e38-f100-49d1-85dc-292bc58e25f1",
    "b812b608-3bdc-4afe-9dbd-9857e65a3bfe",
    "8260053f-b934-4581-b057-a9a4f62b126e"
]

async def execute_group_trade():
    print("🚀 Executing Group Trade (XRP/USDC, 15% Capital, 10x Leverage)...")

    for user_id in USERS:
        print(f"\n👤 Processing User: {user_id}")
        try:
            await manual_buy(
                symbol="XRP/USDC",
                pct=15,
                leverage=10,
                user_id=user_id
            )
            print(f"   ✅ Trade Executed for {user_id}")
        except Exception as e:
            print(f"   ❌ Failed for {user_id}: {e}")
        
        await asyncio.sleep(2) # Delay between users

if __name__ == "__main__":
    asyncio.run(execute_group_trade())
