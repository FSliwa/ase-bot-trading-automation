#!/usr/bin/env python3
"""
Multi-User Trading Bot Runner
Runs bots for multiple users with different configurations
"""
import asyncio
import logging
import sys
from datetime import datetime

# Setup logging to show in terminal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("multi_bot")

# User configurations - 5 users (updated 2025-12-15)
USERS = [
    {
        "user_id": "4177e228-e38e-4a64-b34a-2005a959fcf2",
        "name": "Kraken Futures User 1",
        "exchange": "kraken",
        "futures": True,
        "margin": False
    },
    {
        "user_id": "e4f7f9e4-1664-4419-aaa2-592f12dc2f2a",
        "name": "Binance MARGIN User",
        "exchange": "binance",
        "futures": False,
        "margin": True
    },
    {
        "user_id": "b812b608-3bdc-4afe-9dbd-9857e65a3bfe",
        "name": "Kraken Futures User 2",
        "exchange": "kraken",
        "futures": True,
        "margin": False
    },
    {
        "user_id": "1aa87e38-f100-49d1-85dc-292bc58e25f1",
        "name": "Kraken Futures User 3",
        "exchange": "kraken",
        "futures": True,
        "margin": False
    },
    {
        "user_id": "43e88b0b-d34f-4795-8efa-5507f40426e8",
        "name": "Binance SPOT User",
        "exchange": "binance",
        "futures": False,
        "margin": False
    }
]

async def run_bot_for_user(user_config: dict):
    """Run trading bot for a specific user."""
    from bot.auto_trader import AutomatedTradingBot
    
    user_id = user_config["user_id"]
    exchange = user_config.get("exchange", "binance")
    logger.info(f"🚀 Starting bot for user: {user_id[:8]}... ({user_config['name']}) on {exchange.upper()}")
    
    try:
        bot = AutomatedTradingBot(
            user_id=user_id,
            exchange_name=exchange,
            futures=user_config.get("futures", False),
            margin=user_config.get("margin", False)
        )
        
        await bot.initialize()
        logger.info(f"✅ Bot initialized for {user_id[:8]}... | Exchange: {bot.exchange_name} | Margin: {user_config.get('margin', False)}")
        
        # Run trading cycles
        cycle_count = 0
        while True:
            cycle_count += 1
            logger.info(f"📈 [{user_id[:8]}] Starting trading cycle #{cycle_count}")
            
            try:
                await bot.trading_cycle()
            except Exception as e:
                logger.error(f"❌ [{user_id[:8]}] Cycle error: {e}")
            
            # Wait 5 minutes between cycles
            logger.info(f"⏳ [{user_id[:8]}] Next cycle in 300s...")
            await asyncio.sleep(300)
            
    except Exception as e:
        logger.error(f"❌ Bot failed for {user_id[:8]}: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Run bots for all users concurrently."""
    logger.info("=" * 60)
    logger.info("🤖 ASE BOT - Multi-User Trading System")
    logger.info(f"📅 Started at: {datetime.now()}")
    logger.info(f"👥 Users: {len(USERS)}")
    logger.info("=" * 60)
    
    # Create tasks for all users
    tasks = [run_bot_for_user(user) for user in USERS]
    
    # Run all bots concurrently
    await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bots stopped by user")
