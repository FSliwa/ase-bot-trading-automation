import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from bot.security import SecurityManager
from bot.http.ccxt_adapter import CCXTAdapter
from bot.logging_setup import get_logger

# Setup logging
logger = get_logger("balance_syncer")

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
security_manager = SecurityManager()

async def sync_user_balance(user_id: str):
    """Sync and display balance for a specific user."""
    logger.info(f"🔄 Syncing balance for user {user_id}...")
    
    api_key_encrypted = None
    api_secret_encrypted = None
    exchange_name = None
    is_testnet = False
    
    with engine.connect() as conn:
        # Fetch API keys for the user
        query = text("""
            SELECT encrypted_api_key, encrypted_api_secret, exchange, is_testnet 
            FROM api_keys 
            WHERE user_id = :user_id
        """)
        result = conn.execute(query, {"user_id": user_id}).fetchone()
        
        if not result:
            logger.error(f"❌ No API keys found for user {user_id}")
            return

        api_key_encrypted = result.encrypted_api_key
        api_secret_encrypted = result.encrypted_api_secret
        exchange_name = result.exchange
        is_testnet = result.is_testnet

    # Decrypt keys
    api_key = security_manager.decrypt(api_key_encrypted)
    api_secret = security_manager.decrypt(api_secret_encrypted)
    
    if not api_key or not api_secret:
        logger.error(f"❌ Failed to decrypt keys for user {user_id}")
        return

    logger.info(f"🔑 Keys decrypted for {exchange_name} (Testnet: {is_testnet})")

    # Initialize adapter with Futures support
    adapter = CCXTAdapter(
        api_key=api_key,
        api_secret=api_secret,
        exchange_name=exchange_name,
        testnet=is_testnet,
        futures=True
    )
    
    # Force Futures for Binance Mainnet/Testnet if not handled by adapter
    if exchange_name == 'binance':
        adapter.exchange.options['defaultType'] = 'future'
        # Reload markets to ensure futures markets are loaded
        await adapter.exchange.load_markets()

    from sqlalchemy.orm import sessionmaker
    from bot.db import Position
    
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # --- 1. Sync Positions ---
        logger.info("📉 Fetching open positions from exchange...")
        exchange_positions = await adapter.get_positions()
        logger.info(f"   Found {len(exchange_positions)} open positions.")
        
        # Get DB positions
        db_positions = session.query(Position).filter(
            Position.user_id == user_id,
            Position.status == "OPEN"
        ).all()
        
        db_pos_map = {p.symbol: p for p in db_positions}
        exch_pos_map = {p.symbol: p for p in exchange_positions}
        
        # Update or Create
        for symbol, exch_pos in exch_pos_map.items():
            if symbol in db_pos_map:
                # Update existing
                db_pos = db_pos_map[symbol]
                db_pos.quantity = exch_pos.quantity
                db_pos.entry_price = exch_pos.entry_price
                db_pos.current_price = exch_pos.current_price # Note: CCXTAdapter might not set current_price in get_positions, check implementation
                db_pos.unrealized_pnl = exch_pos.unrealized_pnl
                db_pos.leverage = exch_pos.leverage
                db_pos.updated_at = datetime.utcnow()
                logger.info(f"   UPDATED {symbol}: PnL={exch_pos.unrealized_pnl}")
            else:
                # Create new
                new_pos = Position(
                    user_id=user_id,
                    symbol=exch_pos.symbol,
                    side=exch_pos.side,
                    quantity=exch_pos.quantity,
                    entry_price=exch_pos.entry_price,
                    leverage=exch_pos.leverage,
                    unrealized_pnl=exch_pos.unrealized_pnl,
                    status="OPEN",
                    strategy="manual_sync"
                )
                session.add(new_pos)
                logger.info(f"   CREATED {symbol}")
        
        # Close missing
        for symbol, db_pos in db_pos_map.items():
            if symbol not in exch_pos_map:
                db_pos.status = "CLOSED"
                db_pos.exit_time = datetime.utcnow()
                db_pos.updated_at = datetime.utcnow()
                logger.info(f"   CLOSED {symbol} (not found on exchange)")
        
        session.commit()
        logger.info("✅ Positions synchronized.")

        # --- 2. Sync Balance ---
        # Fetch full balance directly from exchange instance to get all assets
        full_balance = await adapter.exchange.fetch_balance()
        
        logger.info(f"💰 Balance for user {user_id}:")
        
        # 'total' key usually contains the total amount of each asset
        if 'total' in full_balance:
            for currency, amount in full_balance['total'].items():
                if amount > 0:
                    free = full_balance.get('free', {}).get(currency, 0)
                    used = full_balance.get('used', {}).get(currency, 0)
                    logger.info(f"   {currency}: Total={amount:.8f} | Free={free:.8f} | Used={used:.8f}")
        else:
            # Fallback for exchanges with different structure
            logger.info(f"   Raw Balance: {full_balance}")
        
    except Exception as e:
        logger.error(f"❌ Error syncing data: {e}")
        session.rollback()
    finally:
        session.close()
        await adapter.close()

if __name__ == "__main__":
    # Default user ID from request
    TARGET_USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"
    
    # Allow overriding via command line arg
    if len(sys.argv) > 1:
        TARGET_USER_ID = sys.argv[1]

    try:
        asyncio.run(sync_user_balance(TARGET_USER_ID))
    except KeyboardInterrupt:
        logger.info("🛑 Stopped by user.")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
