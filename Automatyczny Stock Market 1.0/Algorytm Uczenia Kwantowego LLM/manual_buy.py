
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

logger = get_logger("manual_buy")
load_dotenv()

DEFAULT_USER_ID = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

async def manual_buy(symbol: str, amount: float = 0, pct: float = 0, usdt: float = 0, tp: float = 0, sl: float = 0, leverage: int = 10, user_id: str = DEFAULT_USER_ID):
    """Execute a manual BUY order."""
    
    # ... (existing setup code) ...
    
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
    exchange_name = "binance" # Default
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
        
        # Calculate Quantity
        quantity = amount
        price = 0.0
        
        # Fetch current price
        ticker = await bot.exchange.exchange.fetch_ticker(symbol)
        price = ticker['last']
        logger.info(f"💲 Current Price of {symbol}: {price}")

        if pct > 0:
            # Infer quote currency from symbol (e.g. XRP/USDC -> USDC)
            quote_currency = symbol.split('/')[1] if '/' in symbol else 'USDT'
            
            # Fetch Balance
            balance = await bot.exchange.get_specific_balance(quote_currency)
            logger.info(f"💰 Available {quote_currency}: {balance}")
            
            # Calculate Margin Amount (Cost)
            margin_amount = balance * (pct / 100.0)
            
            # Calculate Position Value
            position_value = margin_amount * leverage
            
            # Calculate Quantity
            quantity = position_value / price
            logger.info(f"🧮 Calculated Quantity from %: {quantity:.6f} (Margin: {margin_amount:.2f} USDT, Pos Value: {position_value:.2f} USDT)")
            
        elif usdt > 0:
            # Calculate from fixed USDT margin
            margin_amount = usdt
            position_value = margin_amount * leverage
            quantity = position_value / price
            logger.info(f"🧮 Calculated Quantity from USDT: {quantity:.6f} (Margin: {margin_amount:.2f} USDT, Pos Value: {position_value:.2f} USDT)")
        
        if quantity <= 0:
            logger.error("❌ Invalid quantity")
            return

        # Execute Order
        logger.info(f"💸 Placing BUY order: {quantity:.6f} {symbol} ({leverage}x Leverage)...")
        if tp > 0: logger.info(f"   TP: {tp}")
        if sl > 0: logger.info(f"   SL: {sl}")
        
        order = await bot.exchange.place_order(
            symbol=symbol,
            side='buy',
            order_type='market',
            quantity=quantity,
            leverage=leverage,
            take_profit=tp if tp > 0 else None,
            stop_loss=sl if sl > 0 else None
        )
        
        logger.info(f"✅ Order Placed Successfully! ID: {order.id}")
        logger.info(f"Details: {order}")
        
    except Exception as e:
        logger.error(f"❌ Failed to place order: {e}")
    finally:
        if bot.exchange:
            await bot.exchange.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual BUY Order")
    parser.add_argument("--symbol", type=str, required=True, help="Trading symbol (e.g., BTC/USDT)")
    parser.add_argument("--amount", type=float, default=0, help="Amount to buy (quantity)")
    parser.add_argument("--pct", type=float, default=0, help="Percentage of USDT balance to use as margin")
    parser.add_argument("--usdt", type=float, default=0, help="USDT amount to use as margin")
    parser.add_argument("--tp", type=float, default=0, help="Take Profit Price")
    parser.add_argument("--sl", type=float, default=0, help="Stop Loss Price")
    parser.add_argument("--leverage", type=int, default=10, help="Leverage (default: 10)")
    parser.add_argument("--user_id", type=str, default=DEFAULT_USER_ID, help="User ID")
    
    args = parser.parse_args()
    
    if args.amount == 0 and args.pct == 0 and args.usdt == 0:
        print("❌ Error: Must specify either --amount, --pct, or --usdt")
        sys.exit(1)
    
    asyncio.run(manual_buy(args.symbol, args.amount, args.pct, args.usdt, args.tp, args.sl, args.leverage, args.user_id))
