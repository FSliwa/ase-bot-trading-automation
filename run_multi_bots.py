#!/usr/bin/env python3
"""
Multi-user bot launcher - uruchamia boty dla wielu użytkowników równolegle.
Wszystkie logi są wyświetlane w jednym terminalu z prefixem user_id.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Lista użytkowników do uruchomienia
USER_IDS = [
    "4177e228-e38e-4a64-b34a-2005a959fcf2",
    "e4f7f9e4-1664-4419-aaa2-592f12dc2f2a",
    "b812b608-3bdc-4afe-9dbd-9857e65a3bfe",
    "1aa87e38-f100-49d1-85dc-292bc58e25f1",
    "43e88b0b-d34f-4795-8efa-5507f40426e8",
]

# Kolory do rozróżniania użytkowników
COLORS = [
    '\033[94m',  # Blue
    '\033[92m',  # Green
    '\033[93m',  # Yellow
    '\033[95m',  # Magenta
    '\033[96m',  # Cyan
]
RESET = '\033[0m'


class UserPrefixFormatter(logging.Formatter):
    """Custom formatter that adds user_id prefix and color."""
    
    def __init__(self, user_id: str, color: str):
        self.user_id_short = user_id[:8]
        self.color = color
        super().__init__(
            f'{color}[%(asctime)s][{self.user_id_short}]{RESET} %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )


async def run_bot_for_user(user_id: str, color: str, semaphore: asyncio.Semaphore):
    """Run a bot instance for a single user."""
    async with semaphore:
        print(f"{color}🚀 Starting bot for user {user_id[:8]}...{RESET}")
        
        try:
            from bot.auto_trader import AutomatedTradingBot
            
            # Create bot instance
            bot = AutomatedTradingBot(
                user_id=user_id,
                exchange_name=None,  # Will load from DB
                test_mode=False,
                futures=False,
                margin=True  # Enable margin for shorting
            )
            
            # Setup custom logger for this user
            bot_logger = logging.getLogger(f'bot.{user_id[:8]}')
            handler = logging.StreamHandler()
            handler.setFormatter(UserPrefixFormatter(user_id, color))
            bot_logger.handlers = [handler]
            bot_logger.setLevel(logging.INFO)
            
            # Initialize and run
            await bot.initialize()
            print(f"{color}✅ Bot initialized for user {user_id[:8]}{RESET}")
            
            # Run forever
            await bot.run_forever()
            
        except Exception as e:
            print(f"{color}❌ Bot error for user {user_id[:8]}: {e}{RESET}")
            import traceback
            traceback.print_exc()


async def main():
    """Main entry point - run all bots concurrently."""
    print("=" * 60)
    print("🤖 ASE Bot Multi-User Launcher")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"👥 Starting {len(USER_IDS)} bot instances...")
    print("=" * 60)
    
    # Create logs directory
    Path("logs").mkdir(exist_ok=True)
    
    # Limit concurrent initializations to avoid rate limiting
    semaphore = asyncio.Semaphore(3)
    
    # Create tasks for all users
    tasks = []
    for i, user_id in enumerate(USER_IDS):
        color = COLORS[i % len(COLORS)]
        task = asyncio.create_task(run_bot_for_user(user_id, color, semaphore))
        tasks.append(task)
        # Stagger starts to avoid rate limiting
        await asyncio.sleep(2)
    
    # Wait for all bots (they run forever)
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except KeyboardInterrupt:
        print("\n👋 Shutting down all bots...")
        for task in tasks:
            task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 All bots stopped by user")
