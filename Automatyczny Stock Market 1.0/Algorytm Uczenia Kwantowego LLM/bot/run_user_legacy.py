import asyncio
import sys
import os
import logging
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from bot.db import SessionLocal
from bot.models import APIKey, Profile
from bot.security import get_security_manager
from bot.auto_trader import AutomatedTradingBot
from bot.logging_setup import get_logger

logger = get_logger("run_user")

async def run_user_bot(user_id: str):
    """Run the bot for a specific user."""
    logger.info(f"Starting bot for user {user_id}")
    
    session = SessionLocal()
    try:
        # Get user profile to verify existence
        user = session.query(Profile).filter(Profile.user_id == user_id).first()
        if not user:
            logger.error(f"User {user_id} not found")
            return

        # Get active API key
        api_key_record = session.query(APIKey).filter(
            APIKey.user_id == user_id,
            APIKey.is_active == True
        ).first()
        
        if not api_key_record:
            logger.error(f"No active API keys found for user {user_id}")
            return
            
        logger.info(f"Found API key for exchange: {api_key_record.exchange}")
        
        # Decrypt credentials
        security = get_security_manager()
        
        try:
            decrypted_key = security.decrypt(api_key_record.encrypted_api_key)
            decrypted_secret = security.decrypt(api_key_record.encrypted_api_secret)
        except Exception as e:
            logger.error(f"Failed to decrypt credentials: {e}")
            return

        # Initialize bot with user credentials
        bot = AutomatedTradingBot(
            api_key=decrypted_key,
            api_secret=decrypted_secret,
            exchange_name=api_key_record.exchange,
            user_id=user_id
        )
        
        # Initialize and run
        await bot.initialize()
        await bot.run_forever()
        
    except Exception as e:
        logger.error(f"Error running bot for user {user_id}: {e}", exc_info=True)
    finally:
        session.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python bot/run_user.py <user_id>")
        sys.exit(1)
        
    user_id = sys.argv[1]
    
    try:
        asyncio.run(run_user_bot(user_id))
    except KeyboardInterrupt:
        print("Bot stopped by user")
