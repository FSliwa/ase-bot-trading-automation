import asyncio
import logging
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from bot.security import SecurityManager
from bot.auto_trader import AutomatedTradingBot
from bot.logging_setup import get_logger

# Setup logging
logger = get_logger("multi_user_runner")

load_dotenv()

# ============================================================================
# ALLOWED USERS - Bot will only run for these users
# ============================================================================
ALLOWED_USER_IDS = [
    # "b812b608-3bdc-4afe-9dbd-9857e65a3bfe",  # User 1 - DISABLED
    "4177e228-e38e-4a64-b34a-2005a959fcf2",  # User 2 - ACTIVE
]
# ============================================================================

# Database setup
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")

if not DATABASE_URL:
    logger.error("DATABASE_URL not set")
    sys.exit(1)

if "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

engine = create_engine(DATABASE_URL)
security_manager = SecurityManager()

async def run_bot_for_user(user_id: str, api_key_encrypted: str, api_secret_encrypted: str, exchange: str, testnet: bool):
    """Run a single bot instance for a user."""
    try:
        logger.info(f"🚀 Starting bot for user {user_id} on {exchange}...")
        
        # Decrypt keys
        api_key = security_manager.decrypt(api_key_encrypted)
        api_secret = security_manager.decrypt(api_secret_encrypted)
        
        if not api_key or not api_secret:
            logger.error(f"❌ Failed to decrypt keys for user {user_id}")
            return

        # Initialize bot
        bot = AutomatedTradingBot(
            api_key=api_key,
            api_secret=api_secret,
            exchange_name=exchange,
            user_id=user_id,
            test_mode=False # We want real trading (or testnet if configured in key)
        )
        
        # Override testnet setting based on key config
        bot.testnet = testnet
        
        await bot.initialize()
        await bot.run_forever()
        
    except Exception as e:
        logger.error(f"❌ Error running bot for user {user_id}: {e}")

async def main():
    logger.info("🔄 Fetching users and API keys from database...")
    logger.info(f"📋 Allowed users: {ALLOWED_USER_IDS}")
    
    bots = []
    
    with engine.connect() as conn:
        # Fetch all valid API keys
        query = text("""
            SELECT user_id, encrypted_api_key, encrypted_api_secret, exchange, is_testnet 
            FROM api_keys 
            WHERE encrypted_api_key IS NOT NULL AND encrypted_api_secret IS NOT NULL
        """)
        result = conn.execute(query)
        
        for row in result:
            user_id = str(row.user_id)
            
            # Filter: Only run for allowed users
            if user_id not in ALLOWED_USER_IDS:
                logger.debug(f"⏭️ Skipping user {user_id} (not in allowed list)")
                continue
            
            logger.info(f"✅ Found allowed user: {user_id} on {row.exchange}")
            
            # Create and schedule task immediately
            task = asyncio.create_task(
                run_bot_for_user(
                    user_id=user_id,
                    api_key_encrypted=row.encrypted_api_key,
                    api_secret_encrypted=row.encrypted_api_secret,
                    exchange=row.exchange,
                    testnet=row.is_testnet
                )
            )
            bots.append(task)
            
            # Stagger start to prevent spikes
            await asyncio.sleep(1.0)
            
    if not bots:
        logger.warning("⚠️ No users found with valid API keys.")
        return

    logger.info(f"✅ Launched {len(bots)} bots.")
    
    # Wait for all bots
    await asyncio.gather(*bots)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Multi-user runner stopped by user.")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
