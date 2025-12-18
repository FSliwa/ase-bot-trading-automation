import asyncio
import sys
import os
import logging
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass

# Add project root to path
# Project root is already in path when running from root
# sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Set test environment variables BEFORE importing bot modules
os.environ["SUPABASE_DB_URL"] = "sqlite:///:memory:"
os.environ["ALLOW_SQLITE_FALLBACK"] = "1"
os.environ["LOG_LEVEL"] = "INFO"
os.environ["EXCHANGE_NAME"] = "mock_exchange"

from bot.logging_setup import get_logger
from bot.auto_trader import AutomatedTradingBot
from bot.broker.enhanced_paper import EnhancedPaperBroker
from bot.db import init_db

logger = get_logger("run_test_mode")

@dataclass
class MockAccountInfo:
    total: float
    free: float
    used: float

class CompatiblePaperBroker(EnhancedPaperBroker):
    """EnhancedPaperBroker wrapper to match AutoTradingEngine expectations"""
    
    def place_order(self, *, side: str, symbol: str, order_type: str, quantity: float, 
                   market_price: Optional[float] = None, price: Optional[float] = None,
                   stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
                   leverage: Optional[float] = None, **kwargs):
        
        # AutoTradingEngine passes market_price, which EnhancedPaperBroker doesn't accept directly
        # It also passes kwargs that might not match exactly
        
        # Forward to EnhancedPaperBroker.place_order
        # Note: EnhancedPaperBroker.place_order signature:
        # (symbol, side, order_type, quantity, price=None, stop_price=None, ...)
        
        return super().place_order(
            symbol=symbol,
            side=side.upper(),
            order_type=order_type.upper(),
            quantity=quantity,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            leverage=leverage or 1.0
        )

    def get_positions(self):
        # AutoTradingEngine expects a dict of objects {symbol: PositionObj}
        # EnhancedPaperBroker.get_open_positions returns List[dict]
        
        raw_positions = self.get_open_positions()
        result = {}
        
        @dataclass
        class PositionObj:
            symbol: str
            quantity: float
            entry_price: float
            current_price: float
            unrealized_pnl: float
            side: str
            
        for p in raw_positions:
            result[p["symbol"]] = PositionObj(
                symbol=p["symbol"],
                quantity=p["quantity"],
                entry_price=p["entry_price"],
                current_price=p["current_price"],
                unrealized_pnl=p["unrealized_pnl"],
                side=p["side"]
            )
            
        return result

class MockExchangeAdapter:
    """Adapts CompatiblePaperBroker to the interface expected by AutomatedTradingBot.exchange"""
    
    def __init__(self, broker):
        self.broker = broker
        self.exchange_name = "mock_paper"

    async def get_account_info(self):
        info = self.broker.get_account_info()
        return MockAccountInfo(
            total=info["total_balance"],
            free=info["available_balance"],
            used=info["margin_used"]
        )

    async def get_positions(self):
        raw_positions = self.broker.get_open_positions()
        
        @dataclass
        class PositionObj:
            symbol: str
            quantity: float
            entry_price: float
            current_price: float
            unrealized_pnl: float
            side: str
            
        return [
            PositionObj(
                symbol=p["symbol"],
                quantity=p["quantity"],
                entry_price=p["entry_price"],
                current_price=p["current_price"],
                unrealized_pnl=p["unrealized_pnl"],
                side=p["side"]
            ) for p in raw_positions
        ]

    async def fetch_ticker(self, symbol: str):
        normalized_symbol = symbol.replace("/", "")
        data = self.broker.market_data.get(normalized_symbol)
        
        if not data:
            return {
                "symbol": symbol,
                "last": 50000.0,
                "bid": 49990.0,
                "ask": 50010.0,
                "percentage": 0.0
            }
            
        return {
            "symbol": symbol,
            "last": data.price,
            "bid": data.bid,
            "ask": data.ask,
            "percentage": 0.0
        }

    async def get_market_price(self, symbol: str) -> float:
        normalized_symbol = symbol.replace("/", "")
        data = self.broker.market_data.get(normalized_symbol)
        if not data:
            return 50000.0
        return data.price
        
    async def close(self):
        pass

async def main():
    """Run the bot in test mode."""
    logger.info("🚀 Starting Bot in TEST MODE")
    logger.info("Using in-memory database and paper trading broker")
    
    # Initialize DB (in-memory)
    init_db()
    
    # Create Broker and Adapter
    broker = CompatiblePaperBroker(initial_balance=100000.0)
    adapter = MockExchangeAdapter(broker)
    
    # Initialize bot
    bot = AutomatedTradingBot(
        test_mode=True,
        broker=broker,
        exchange_adapter=adapter,
        exchange_name="mock"
    )
    
    try:
        await bot.initialize()
        
        # Override get_market_data to ensure it returns data for symbols we want to trade
        # AutoTradingEngine.get_mock_market_data generates random data, which is fine.
        # But AutomatedTradingBot.get_market_data calls exchange.fetch_ticker.
        # We need to ensure MockExchangeAdapter.fetch_ticker returns valid data.
        # EnhancedPaperBroker has some initial data.
        
        logger.info("Bot initialized. Starting main loop...")
        await bot.run_forever()
        
    except KeyboardInterrupt:
        logger.info("Stopping bot...")
    except Exception as e:
        logger.error(f"Error running bot: {e}", exc_info=True)
    finally:
        await bot.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
