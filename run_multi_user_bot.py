#!/usr/bin/env python3
"""
Multi-user trading bot runner.
Runs bots for multiple users concurrently.
"""

import asyncio
import logging
import sys
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Users to run bots for
USERS = [
    '4177e228-e38e-4a64-b34a-2005a959fcf2',
    'e4f7f9e4-1664-4419-aaa2-592f12dc2f2a',
    'b812b608-3bdc-4afe-9dbd-9857e65a3bfe',
    '1aa87e38-f100-49d1-85dc-292bc58e25f1',
    '43e88b0b-d34f-4795-8efa-5507f40426e8',
]


async def run_bot_for_user(user_id: str):
    """Run bot for a single user."""
    from bot.auto_trader import AutomatedTradingBot
    
    try:
        logger.info(f"🚀 Starting bot for user {user_id[:8]}...")
        bot = AutomatedTradingBot(user_id=user_id)
        await bot.initialize()
        logger.info(f"✅ Bot initialized for {user_id[:8]}")
        await bot.run_forever()  # Fixed: was run() but method is run_forever()
    except Exception as e:
        logger.error(f"❌ Bot for {user_id[:8]} failed: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main entry point."""
    logger.info("="*60)
    logger.info("🤖 ASE-BOT Multi-User Trading System")
    logger.info("="*60)
    logger.info(f"Starting bots for {len(USERS)} users...")
    
    # Run all bots concurrently
    tasks = [run_bot_for_user(user_id) for user_id in USERS]
    
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down bots...")
    except Exception as e:
        logger.error(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
