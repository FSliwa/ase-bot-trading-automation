
import asyncio
import argparse
import sys
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from bot.security import SecurityManager
from bot.auto_trader import AutomatedTradingBot
from bot.logging_setup import get_logger

logger = get_logger("manual_sell")
load_dotenv()

DEFAULT_USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

async def manual_sell(symbol: str, amount: float, leverage: int = 10, user_id: str = DEFAULT_USER_ID):
    """Execute a manual SELL order."""
    
    # Database setup
    SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
    DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")
    
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set")
        return

    if "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"

    engine = create_engine(DATABASE_URL)
    security_manager = SecurityManager()
    
    # Fetch credentials
    logger.info(f"🔍 Fetching credentials for user {user_id}...")
    
    api_key = None
    api_secret = None
    exchange_name = "binance"
    testnet = False
    
    with engine.connect() as conn:
        query = text("""
            SELECT encrypted_api_key, encrypted_api_secret, exchange, is_testnet 
            FROM api_keys 
            WHERE user_id = :user_id
        """)
        result = conn.execute(query, {"user_id": user_id}).fetchone()
        
        if not result:
            logger.error(f"❌ No API keys found for user {user_id}")
            return
            
        api_key = security_manager.decrypt(result.encrypted_api_key)
        api_secret = security_manager.decrypt(result.encrypted_api_secret)
        exchange_name = result.exchange
        testnet = result.is_testnet

    if not api_key or not api_secret:
        logger.error("❌ Failed to decrypt API keys")
        return

    # Initialize Bot
    logger.info(f"🚀 Initializing bot on {exchange_name} (Testnet: {testnet}) with {leverage}x Margin...")
    bot = AutomatedTradingBot(
        api_key=api_key,
        api_secret=api_secret,
        exchange_name=exchange_name,
        user_id=user_id,
        test_mode=False,
        futures=True
    )
    bot.testnet = testnet
    
    try:
        await bot.initialize()
        
        # Execute Order
        logger.info(f"💸 Placing SELL order: {amount} {symbol} ({leverage}x Leverage)...")
        order = await bot.exchange.place_order(
            symbol=symbol,
            side='sell',
            order_type='market',
            quantity=amount,
            leverage=leverage
        )
        
        logger.info(f"✅ Order Placed Successfully! ID: {order.id}")
        logger.info(f"Details: {order}")
        
    except Exception as e:
        logger.error(f"❌ Failed to place order: {e}")
    finally:
        if bot.exchange:
            await bot.exchange.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual SELL Order")
    parser.add_argument("--symbol", type=str, required=True, help="Trading symbol (e.g., BTC/USDT)")
    parser.add_argument("--amount", type=float, required=True, help="Amount to sell")
    parser.add_argument("--leverage", type=int, default=10, help="Leverage (default: 10)")
    parser.add_argument("--user_id", type=str, default=DEFAULT_USER_ID, help="User ID")
    
    args = parser.parse_args()
    
    asyncio.run(manual_sell(args.symbol, args.amount, args.leverage, args.user_id))
