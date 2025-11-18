"""
Fully Automated Trading Bot
Runs strategies automatically without user intervention
"""

import asyncio
import os
import signal
import sys
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from bot.config import load_config
from bot.ai_analysis import MarketAnalyzer
from bot.strategies import AutoTradingEngine, MomentumStrategy, MeanReversionStrategy
from bot.http.ccxt_adapter import CCXTAdapter
from bot.risk_manager import RiskManager
from bot.db import DatabaseManager, init_db
from bot.logging_setup import get_logger
from dotenv import load_dotenv

logger = get_logger("auto_trader")


class AutomatedTradingBot:
    """Main automated trading system"""
    
    def __init__(self):
        load_dotenv()
        self.config = load_config()
        self.running = False
        self.tasks = []
        
        # Trading settings
        self.exchange_name = os.getenv("EXCHANGE_NAME", "binance")
        self.api_key = os.getenv("EXCHANGE_API_KEY")
        self.api_secret = os.getenv("EXCHANGE_API_SECRET")
        self.testnet = os.getenv("USE_TESTNET", "true").lower() == "true"
        self.trading_interval = int(os.getenv("TRADING_INTERVAL_SECONDS", "60"))
        self.enabled_strategies = os.getenv("ENABLED_STRATEGIES", "momentum,mean_reversion").split(",")
        self.trade_symbols = os.getenv("TRADE_SYMBOLS", "BTC/USDT,ETH/USDT").split(",")
        
        # Risk settings
        self.max_positions = int(os.getenv("MAX_POSITIONS", "3"))
        self.risk_per_trade = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
        self.daily_loss_limit = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "5.0"))
        
        # Initialize components
        self.exchange = None
        self.market_analyzer = None
        self.risk_manager = RiskManager()
        self.trading_engine = None
        
    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing Automated Trading Bot...")
        
        # Initialize database
        init_db()
        
        # Initialize exchange connection
        if not self.api_key or not self.api_secret:
            raise ValueError("EXCHANGE_API_KEY and EXCHANGE_API_SECRET must be set")
            
        self.exchange = CCXTAdapter(
            exchange_name=self.exchange_name,
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=self.testnet,
            futures=True
        )
        
        # Initialize AI analyzer
        try:
            self.market_analyzer = MarketAnalyzer()
        except Exception as e:
            logger.warning(f"AI analyzer initialization failed: {e}. Will trade without AI signals.")
        
        # Initialize trading engine
        from bot.broker.live_broker import LiveBroker  # We'll create this
        live_broker = LiveBroker(
            exchange_name=self.exchange_name,
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=self.testnet
        )
        self.trading_engine = AutoTradingEngine(live_broker, self.config)
        
        # Add strategies
        if "momentum" in self.enabled_strategies:
            self.trading_engine.add_strategy(
                MomentumStrategy(self.trade_symbols, self.config)
            )
        if "mean_reversion" in self.enabled_strategies:
            self.trading_engine.add_strategy(
                MeanReversionStrategy(self.trade_symbols, self.config)
            )
            
        # Activate trading engine
        self.trading_engine.active = True
        
        logger.info(f"Initialized with {len(self.enabled_strategies)} strategies on {self.exchange_name}")
        logger.info(f"Trading symbols: {self.trade_symbols}")
        logger.info(f"Testnet mode: {self.testnet}")
        
    async def get_market_data(self) -> Dict:
        """Fetch live market data"""
        market_data = {}
        
        for symbol in self.trade_symbols:
            try:
                ticker = await self.exchange.get_market_price(symbol)
                # Convert to our MarketData format
                from bot.strategies import MarketData
                market_data[symbol] = MarketData(
                    symbol=symbol,
                    current_price=ticker,
                    high_24h=ticker * 1.02,  # Simplified
                    low_24h=ticker * 0.98,
                    volume_24h=1000000,  # Would fetch real volume
                    change_24h_percent=0,  # Would calculate
                    timestamp=datetime.now()
                )
            except Exception as e:
                logger.error(f"Failed to fetch market data for {symbol}: {e}")
                
        return market_data
    
    async def check_risk_limits(self) -> bool:
        """Check if we're within risk limits"""
        try:
            account_info = await self.exchange.get_account_info()
            current_equity = account_info.total
            
            # Check circuit breakers
            breakers = self.risk_manager.check_circuit_breakers(current_equity)
            if breakers["should_halt_trading"]:
                logger.warning(f"Circuit breaker triggered: {breakers['breakers']}")
                return False
                
            # Check position count
            positions = await self.exchange.get_positions()
            if len(positions) >= self.max_positions:
                logger.info(f"Max positions reached ({self.max_positions})")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Risk check failed: {e}")
            return False
    
    async def execute_ai_analysis(self) -> Optional[Dict]:
        """Get AI trading recommendations"""
        if not self.market_analyzer:
            return None
            
        try:
            analysis = await self.market_analyzer.analyze_market({
                "notional": "10000",
                "max_leverage": str(self.config.max_leverage),
                "exchange": self.exchange_name
            })
            
            if "error" not in analysis:
                logger.info(f"AI Analysis: {analysis.get('top_pick', {}).get('symbol')} - "
                          f"{analysis.get('top_pick', {}).get('why')}")
                return analysis
            else:
                logger.error(f"AI analysis error: {analysis.get('error')}")
                return None
                
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return None
    
    async def trading_cycle(self):
        """Main trading cycle"""
        logger.info("Starting trading cycle...")
        
        try:
            # Check risk limits
            if not await self.check_risk_limits():
                logger.info("Risk limits exceeded, skipping cycle")
                return
            
            # Get market data
            market_data = await self.get_market_data()
            if not market_data:
                logger.warning("No market data available")
                return
            
            # Update engine with real market data
            self.trading_engine.get_mock_market_data = lambda: market_data
            
            # Get AI analysis (optional enhancement)
            ai_analysis = await self.execute_ai_analysis()
            
            # Execute trading strategies
            signals = self.trading_engine.run_cycle()
            
            if signals:
                logger.info(f"Executed {len(signals)} trades this cycle")
                for signal in signals:
                    logger.info(f"Trade: {signal.action} {signal.quantity} {signal.symbol} "
                              f"@ {signal.order_type} - {signal.reason}")
            else:
                logger.info("No trading signals generated")
                
            # Log account status
            account_info = await self.exchange.get_account_info()
            positions = await self.exchange.get_positions()
            logger.info(f"Account balance: {account_info.total:.2f} USDT, "
                       f"Open positions: {len(positions)}")
            
        except Exception as e:
            logger.error(f"Trading cycle error: {e}", exc_info=True)
    
    async def run_forever(self):
        """Run the bot forever"""
        self.running = True
        logger.info(f"Bot started - trading every {self.trading_interval} seconds")
        
        while self.running:
            try:
                await self.trading_cycle()
                await asyncio.sleep(self.trading_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retry
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down bot...")
        self.running = False
        
        # Close all positions if configured
        if os.getenv("CLOSE_ON_SHUTDOWN", "false").lower() == "true":
            try:
                positions = await self.exchange.get_positions()
                for pos in positions:
                    await self.exchange.close_position(pos.symbol)
                    logger.info(f"Closed position: {pos.symbol}")
            except Exception as e:
                logger.error(f"Error closing positions: {e}")
        
        # Close exchange connection
        if self.exchange:
            await self.exchange.close()
        
        logger.info("Bot shutdown complete")


async def main():
    """Main entry point"""
    bot = AutomatedTradingBot()
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
        asyncio.create_task(bot.shutdown())
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize
        await bot.initialize()
        
        # Run forever
        await bot.run_forever()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    # Create required directories
    Path("logs").mkdir(exist_ok=True)
    
    # Run the bot
    asyncio.run(main())
