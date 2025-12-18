
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from manual_buy import manual_buy

# User 2: b812b608... (Has USD -> BTC/USD)
# User 3: 8260053f... (Has USDC -> BTC/USDC)

TRADES = [
    {
        "user_id": "b812b608-3bdc-4afe-9dbd-9857e65a3bfe",
        "symbol": "BTC/USD",
        "pct": 15,
        "leverage": 10
    },
    {
        "user_id": "8260053f-b934-4581-b057-a9a4f62b126e",
        "symbol": "BTC/USDC",
        "pct": 15,
        "leverage": 10
    }
]

async def execute_btc_group():
    print("🚀 Executing BTC Group Trade (15% Capital, 10x Leverage)...")

    for trade in TRADES:
        user_id = trade["user_id"]
        symbol = trade["symbol"]
        print(f"\n👤 Processing User: {user_id} ({symbol})")
        try:
            await manual_buy(
                symbol=symbol,
                pct=trade["pct"],
                leverage=trade["leverage"],
                user_id=user_id
            )
            print(f"   ✅ Trade Executed for {user_id}")
        except Exception as e:
            print(f"   ❌ Failed for {user_id}: {e}")
        
        await asyncio.sleep(2) # Delay between users

if __name__ == "__main__":
    asyncio.run(execute_btc_group())
