#!/usr/bin/env python3
"""Run bot for a single user by user_id."""

import asyncio
import logging
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from bot.security import get_security_manager
from bot.auto_trader import AutomatedTradingBot
from bot.logging_setup import get_logger

# Setup logging
logger = get_logger("single_user_runner")

load_dotenv()

# Database setup
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")

if not DATABASE_URL:
    logger.error("DATABASE_URL not set")
    sys.exit(1)

if "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

engine = create_engine(DATABASE_URL)

# Use global security manager (handles missing ENCRYPTION_KEY gracefully)
security_manager = get_security_manager()


async def run_bot_for_user(user_id: str):
    """Run a single bot instance for a user."""
    try:
        logger.info(f"🔍 Looking up API keys for user {user_id}...")
        
        with engine.connect() as conn:
            # FIX 2025-12-16: Added account_type to query
            query = text("""
                SELECT user_id, encrypted_api_key, encrypted_api_secret, exchange, is_testnet, account_type 
                FROM api_keys 
                WHERE user_id = :user_id
                  AND encrypted_api_key IS NOT NULL 
                  AND encrypted_api_secret IS NOT NULL
                LIMIT 1
            """)
            result = conn.execute(query, {"user_id": user_id})
            row = result.fetchone()
            
            if not row:
                logger.error(f"❌ No API keys found for user {user_id}")
                return
            
            user_id, api_key_encrypted, api_secret_encrypted, exchange, testnet, account_type = row
        
        # FIX 2025-12-16: Determine margin/futures mode from account_type
        # Default: Binance = spot, Kraken = margin (for leverage trading)
        account_type = (account_type or '').lower()
        
        # Determine trading mode
        is_margin = account_type == 'margin'
        is_futures = account_type == 'futures'
        
        # Log account mode
        mode_str = "MARGIN" if is_margin else ("FUTURES" if is_futures else "SPOT")
        logger.info(f"🚀 Starting bot for user {user_id}")
        logger.info(f"   Exchange: {exchange} | Account Type from DB: '{account_type}' → Trading Mode: {mode_str}")
        logger.info(f"   margin={is_margin}, futures={is_futures}, testnet={testnet}")
        
        # Decrypt keys
        api_key = security_manager.decrypt(api_key_encrypted)
        api_secret = security_manager.decrypt(api_secret_encrypted)
        
        if not api_key or not api_secret:
            logger.error(f"❌ Failed to decrypt keys for user {user_id}")
            return

        # Initialize bot with correct trading mode
        bot = AutomatedTradingBot(
            api_key=api_key,
            api_secret=api_secret,
            exchange_name=exchange,
            user_id=user_id,
            test_mode=False,
            margin=is_margin,      # FIX: Pass margin mode from DB
            futures=is_futures     # FIX: Pass futures mode from DB
        )
        
        # Override testnet setting based on key config
        bot.testnet = testnet if testnet is not None else False
        
        await bot.initialize()
        await bot.run_forever()
        
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Error running bot for user {user_id}: {e}")
        import traceback
        traceback.print_exc()


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_single_user.py <user_id>")
        print("Example: python run_single_user.py b812b608-3bdc-4afe-9dbd-9857e65a3bfe")
        sys.exit(1)
    
    user_id = sys.argv[1]
    logger.info(f"🤖 Starting bot for user: {user_id}")
    
    asyncio.run(run_bot_for_user(user_id))


if __name__ == "__main__":
    main()
