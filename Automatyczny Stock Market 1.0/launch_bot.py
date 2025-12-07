#!/usr/bin/env python3
"""
Launcher script for the Automated Trading Bot.
Handles user context injection and credential management.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("launcher")

def setup_environment(user_id: str):
    """
    Setup environment variables for the specific user.
    Prioritizes:
    1. Database credentials (if reachable)
    2. Local user-specific .env file (.env.user.<user_id>)
    3. Manual input (interactive mode)
    """
    
    # 1. Try to load base .env
    base_env = Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM" / ".env"
    if base_env.exists():
        logger.info(f"Loading base config from {base_env}")
        load_dotenv(base_env)
    
    # 2. Try to connect to DB and fetch credentials
    try:
        # Add project root to path for imports
        sys.path.insert(0, str(Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM"))
        from bot.db import SessionLocal
        from bot.models import APIKey, TradingSettings
        from bot.security import get_security_manager
        
        logger.info("Attempting to fetch credentials from database...")
        db = SessionLocal()
        security = get_security_manager()
        
        api_key = db.query(APIKey).filter_by(user_id=user_id, is_active=True).first()
        
        if api_key:
            logger.info("✅ Found API key in database")
            decrypted_key = security.decrypt(api_key.encrypted_api_key)
            decrypted_secret = security.decrypt(api_key.encrypted_api_secret)
            
            os.environ["EXCHANGE_API_KEY"] = decrypted_key
            os.environ["EXCHANGE_API_SECRET"] = decrypted_secret
            os.environ["EXCHANGE_NAME"] = api_key.exchange
            os.environ["USE_TESTNET"] = str(api_key.is_testnet).lower()
            
            # Fetch settings
            settings = db.query(TradingSettings).filter_by(user_id=user_id).first()
            if settings:
                if settings.max_position_size:
                    os.environ["MAX_POSITION_SIZE"] = str(settings.max_position_size)
                if settings.max_daily_loss:
                    os.environ["MAX_DAILY_LOSS"] = str(settings.max_daily_loss)
            
            return True
            
    except Exception as e:
        logger.warning(f"⚠️  Could not fetch from DB: {e}")
        logger.warning("Falling back to local configuration...")

    # 3. Fallback: Check for local user env file
    user_env_path = Path(__file__).parent / f".env.user.{user_id}"
    if user_env_path.exists():
        logger.info(f"Loading user config from {user_env_path}")
        load_dotenv(user_env_path)
        
        if os.getenv("EXCHANGE_API_KEY") and os.getenv("EXCHANGE_API_SECRET"):
            return True
            
    return False

def main():
    parser = argparse.ArgumentParser(description="Launch Trading Bot for User")
    parser.add_argument("--user-id", required=True, help="UUID of the user")
    args = parser.parse_args()
    
    logger.info(f"🚀 Initializing bot for user: {args.user_id}")
    
    if not setup_environment(args.user_id):
        logger.error("❌ Could not find valid credentials!")
        logger.error(f"Please create a file named .env.user.{args.user_id} with:")
        logger.error("EXCHANGE_API_KEY=your_key")
        logger.error("EXCHANGE_API_SECRET=your_secret")
        sys.exit(1)
        
    logger.info("✅ Environment configured successfully")
    
    # Launch the bot
    try:
        # We need to be in the inner directory for imports to work correctly
        # or adjust sys.path further. Let's adjust sys.path.
        project_root = Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM"
        sys.path.insert(0, str(project_root))
        
        # Import here to avoid early failures if env vars aren't set
        from bot.auto_trader import main as run_bot
        import asyncio
        
        logger.info("Starting Auto Trader...")
        asyncio.run(run_bot())
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
