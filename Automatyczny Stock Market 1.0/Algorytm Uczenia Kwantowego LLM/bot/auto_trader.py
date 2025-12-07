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
from bot.strategies import AutoTradingEngine, MomentumStrategy, MeanReversionStrategy
from bot.strategies import AutoTradingEngine, MomentumStrategy, MeanReversionStrategy, AIStrategy
from bot.risk_manager import RiskManager
from bot.db import DatabaseManager, init_db
from bot.logging_setup import get_logger
from dotenv import load_dotenv
from ccxt import AuthenticationError

from bot.analysis.technical_analysis import TechnicalAnalyzer

logger = get_logger("auto_trader")

class AutomatedTradingBot:
    """Main automated trading system"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, 
                 exchange_name: Optional[str] = None, user_id: Optional[str] = None,
                 test_mode: bool = False, broker = None, exchange_adapter = None,
                 futures: bool = False):
        load_dotenv()
        self.config = load_config()
        self.running = False
        self.tasks = []
        self.user_id = user_id
        self.test_mode = test_mode
        self.injected_broker = broker
        self.injected_exchange = exchange_adapter
        self.futures = futures
        
        # Trading settings
        self.exchange_name = exchange_name or os.getenv("EXCHANGE_NAME", "binance")
        self.api_key = api_key or os.getenv("EXCHANGE_API_KEY")
        self.api_secret = api_secret or os.getenv("EXCHANGE_API_SECRET")
        self.testnet = os.getenv("USE_TESTNET", "true").lower() == "true"
        self.trading_interval = int(os.getenv("TRADING_INTERVAL_SECONDS", "3600"))
        self.enabled_strategies = os.getenv("ENABLED_STRATEGIES", "momentum,mean_reversion").split(",")
        self.trade_symbols = os.getenv("TRADE_SYMBOLS", "BTC/USDT,ETH/USDT").split(",")
        
        # Risk settings
        self.max_positions = int(os.getenv("MAX_POSITIONS", "5"))
        self.risk_per_trade = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
        self.daily_loss_limit = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "5.0"))
        
        # Initialize components
        self.exchange = None
        self.market_analyzer = None
        self.analysis_service = None
        self.risk_manager = RiskManager()
        self.trading_engine = None
        self.ai_strategy = None
        self.db_manager = None
        self.technical_analyzer = TechnicalAnalyzer()
        
    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing Automated Trading Bot...")
        
        # Initialize database
        init_db()
        self.db_manager = DatabaseManager()
        
        # Initialize exchange connection
        if self.injected_exchange:
            self.exchange = self.injected_exchange
            logger.info("Using injected exchange adapter")
        elif not self.test_mode and (not self.api_key or not self.api_secret):
            raise ValueError("EXCHANGE_API_KEY and EXCHANGE_API_SECRET must be set")
            
        if not self.exchange and not self.test_mode:
            from bot.http.ccxt_adapter import CCXTAdapter
            self.exchange = CCXTAdapter(
            exchange_name=self.exchange_name,
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=self.testnet,
            futures=self.futures
        )
        
        # Initialize AI analyzer and service
        # Initialize AI analyzer and service
        try:
            from bot.services.supabase_analysis_service import SupabaseAnalysisService
            
            self.analysis_service = SupabaseAnalysisService()
            logger.info("✅ Supabase AI Market Analysis Service initialized successfully")
        except Exception as e:
            logger.warning(f"AI analyzer initialization failed: {e}. Will trade without AI signals.")
        
        # Initialize trading engine
        if self.injected_broker:
            self.trading_engine = AutoTradingEngine(self.injected_broker, self.config)
            logger.info("Using injected broker for trading engine")
        else:
            from bot.broker.live_broker import LiveBroker  # We'll create this
            live_broker = LiveBroker(
                exchange_name=self.exchange_name,
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet
            )
            self.trading_engine = AutoTradingEngine(live_broker, self.config)
        
        # Add AI Strategy
        self.ai_strategy = AIStrategy(self.trade_symbols, self.config)
        self.trading_engine.add_strategy(self.ai_strategy)
        
        # Add other strategies if enabled
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
        logger.info(f"DEBUG: self.exchange type: {type(self.exchange)}")
        logger.info(f"DEBUG: self.broker type: {type(self.injected_broker) if self.injected_broker else 'None'}")
        
    async def get_market_data(self) -> Dict:
        """Fetch live market data"""
        market_data = {}
        
        for symbol in self.trade_symbols:
            try:
                # Use real ticker stats if available
                if hasattr(self.exchange, 'get_ticker_stats'):
                    stats = await self.exchange.get_ticker_stats(symbol)
                    if not stats:
                        continue
                        
                    from bot.strategies import MarketData
                    market_data[symbol] = MarketData(
                        symbol=symbol,
                        current_price=stats['last'],
                        high_24h=stats['high'],
                        low_24h=stats['low'],
                        volume_24h=stats['volume'],
                        change_24h_percent=stats['change_percent'],
                        timestamp=datetime.now()
                    )
                else:
                    # Fallback for legacy adapters
                    ticker = await self.exchange.get_market_price(symbol)
                    from bot.strategies import MarketData
                    market_data[symbol] = MarketData(
                        symbol=symbol,
                        current_price=ticker,
                        high_24h=ticker * 1.02,
                        low_24h=ticker * 0.98,
                        volume_24h=1000000,
                        change_24h_percent=0,
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
                
            # Check position count (Spot + Margin/Futures)
            logger.info(f"DEBUG: check_risk_limits self.exchange type: {type(self.exchange)}")
            spot_assets = await self.exchange.get_spot_balances()
            margin_positions = await self.exchange.get_positions()
            
            total_positions = len(spot_assets) + len(margin_positions)
            
            if total_positions >= self.max_positions:
                logger.info(f"Max positions reached ({total_positions}/{self.max_positions}). Spot: {len(spot_assets)}, Margin: {len(margin_positions)}")
                return False
                
            return True
            
        except AuthenticationError:
            raise
        except Exception as e:
            msg = str(e).lower()
            if "invalid api-key" in msg or "authentication" in msg or "code': -2008" in msg:
                raise AuthenticationError(f"Detected auth failure: {e}")
            logger.error(f"Risk check failed: {e}")
            return False
    
    async def execute_ai_analysis(self) -> Optional[Dict]:
        """Get AI trading recommendations using the new pipeline with dynamic symbol selection"""
        if not self.analysis_service:
            return None
            
        try:
            # 1. Dynamic Symbol Selection
            logger.info("🔍 Fetching top volume symbols for analysis...")
            if hasattr(self.exchange, 'get_top_volume_symbols'):
                dynamic_symbols = await self.exchange.get_top_volume_symbols(limit=5)
                if dynamic_symbols:
                    logger.info(f"✅ Selected top {len(dynamic_symbols)} symbols: {dynamic_symbols}")
                    self.trade_symbols = list(set(self.trade_symbols + dynamic_symbols))
            
            # 2. Fetch Market Data for ALL symbols
            logger.info(f"📊 Fetching market data for {len(self.trade_symbols)} symbols...")
            market_data_map = await self.get_market_data()
            
            valid_symbols = [s for s in self.trade_symbols if s in market_data_map]
            valid_market_data = {s: market_data_map[s] for s in valid_symbols}
            
            if not valid_symbols:
                logger.warning("No market data available for analysis")
                return None

            # 3. Enrich Data with Technical Analysis & Order Book
            enriched_data_dicts = {}
            
            for symbol, data in valid_market_data.items():
                # Basic Ticker Data
                symbol_data = {
                    "current_price": data.current_price,
                    "change_24h_percent": data.change_24h_percent,
                    "volume_24h": data.volume_24h,
                    "high_24h": data.high_24h,
                    "low_24h": data.low_24h
                }
                
                # Fetch & Analyze OHLCV
                if hasattr(self.exchange, 'fetch_ohlcv'):
                    ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
                    ta_indicators = self.technical_analyzer.analyze_ohlcv(ohlcv)
                    symbol_data['technical_indicators'] = ta_indicators
                    logger.info(f"Calculated TA for {symbol}: RSI={ta_indicators.get('rsi', 'N/A')}")
                
                # Fetch Order Book Depth
                if hasattr(self.exchange, 'get_order_book_depth'):
                    depth = await self.exchange.get_order_book_depth(symbol, limit=5)
                    symbol_data['order_book'] = depth
                
                enriched_data_dicts[symbol] = symbol_data

            # 4. Batch Analysis via Edge Function
            logger.info(f"🤖 Requesting AI analysis for {len(valid_symbols)} symbols...")
            analyses = await self.analysis_service.generate_signals_batch(valid_symbols, enriched_data_dicts)
            
            if not analyses:
                logger.info("No trading signals generated by AI")
                return None
                
            logger.info(f"✅ Received {len(analyses)} signals from AI")
            
            # Process and save signals
            for analysis in analyses:
                symbol = analysis['symbol']
                logger.info(f"AI Analysis for {symbol}: {analysis.get('action')} - {analysis.get('reasoning')}")
                
                # Save signal to DB
                try:
                    strength_val = analysis.get('confidence', 0.5)
                    
                    self.db_manager.save_signal(
                        symbol=symbol,
                        signal_type=analysis.get('action').lower(),
                        confidence=strength_val,
                        ai_analysis=analysis.get('reasoning'),
                        source="bot_v2_dynamic",
                        strength=str(strength_val)
                    )
                    logger.info(f"💾 Saved signal for {symbol} to DB")
                except Exception as e:
                    logger.error(f"Failed to save signal for {symbol}: {e}")
                
                last_analysis = analysis

            return analyses # Return list of analyses
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return None
    
    async def manage_capital(self) -> str:
        """
        Manage trading capital:
        1. Check USDT balance.
        2. Check USDC balance.
        3. Check FIAT balances and convert to USDC if needed.
        Returns the active quote currency (USDT or USDC).
        """
        if not self.exchange:
            return "USDT"

        # Check USDT
        usdt_balance = await self.exchange.get_specific_balance("USDT")
        if usdt_balance > 10:  # Minimum threshold
            logger.info(f"Using USDT as quote currency (Balance: {usdt_balance:.2f})")
            return "USDT"

        # Check USDC
        usdc_balance = await self.exchange.get_specific_balance("USDC")
        if usdc_balance > 10:
            logger.info(f"Using USDC as quote currency (Balance: {usdc_balance:.2f})")
            return "USDC"

        # Check FIAT and convert
        all_balances = await self.exchange.get_all_balances()
        fiat_currencies = ["USD", "EUR", "GBP", "PLN"]
        
        for currency, balance in all_balances.items():
            if currency in fiat_currencies and balance > 10:
                logger.info(f"Found FIAT capital: {balance:.2f} {currency}. Converting to USDC...")
                if await self.exchange.convert_currency(currency, "USDC", balance * 0.99): # 99% to cover fees
                    logger.info(f"Successfully converted {currency} to USDC")
                    return "USDC"
                else:
                    logger.error(f"Failed to convert {currency} to USDC")

        logger.warning("No sufficient trading capital found in USDT, USDC, or FIAT.")
        return "USDT" # Default fallback

    async def trading_cycle(self):
        """Main trading cycle"""
        logger.info("Starting trading cycle...")
        
        try:
            # Manage Capital & Select Quote Currency
            quote_currency = await self.manage_capital()
            
            # Update trade symbols based on quote currency
            current_symbols = []
            for symbol in self.trade_symbols:
                base = symbol.split('/')[0]
                current_symbols.append(f"{base}/{quote_currency}")
            
            # Update instance symbols if changed (careful with this in loop)
            # For now, we just use these symbols for this cycle
            active_symbols = current_symbols
            logger.info(f"Active trading symbols for this cycle: {active_symbols}")

            # Check risk limits
            if not await self.check_risk_limits():
                logger.info("Risk limits exceeded, skipping cycle")
                return
            
            # Get market data (using updated symbols)
            logger.info("Fetching market data...")
            # Temporarily update self.trade_symbols for get_market_data to work correctly
            original_symbols = self.trade_symbols
            self.trade_symbols = active_symbols
            
            market_data = await self.get_market_data()
            
            # Restore original symbols (or keep them updated? Let's keep them updated for consistency)
            # self.trade_symbols = original_symbols 
            
            if not market_data:
                logger.warning("No market data available")
                return
            
            logger.info(f"Market data fetched for {len(market_data)} symbols")
            
            # Update engine with real market data
            self.trading_engine.get_mock_market_data = lambda: market_data
            
            # Get AI analysis (optional enhancement)
            logger.info("Running AI market analysis...")
            ai_analysis = await self.execute_ai_analysis()
            if ai_analysis:
                logger.info("AI analysis completed successfully")
                # Update AI Strategy with new signals
                if self.ai_strategy:
                    self.ai_strategy.update_signals(ai_analysis)
            
            # Execute trading strategies
            logger.info("Executing trading strategies...")
            # Ensure strategies know about the new symbols
            for strategy in self.trading_engine.strategies:
                strategy.symbols = active_symbols
                
            signals = await self.trading_engine.run_cycle()
            
            if signals:
                logger.info(f"Generated {len(signals)} trading signals")
                for signal in signals:
                    logger.info(f"Signal: {signal.action} {signal.quantity} {signal.symbol} "
                              f"@ {signal.order_type} - {signal.reason}")
            else:
                logger.info("No trading signals generated this cycle")
                
            # Log account status
            try:
                account_info = await self.exchange.get_account_info()
                positions = await self.exchange.get_positions()
                logger.info(f"Account Balance: {account_info.total:.2f} USDT | Open Positions: {len(positions)}")
            except Exception as e:
                logger.warning(f"Could not fetch account info: {e}")
            
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
            except AuthenticationError as e:
                logger.critical(f"🛑 Authentication failed: {e}. Stopping bot for this user.")
                self.running = False
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
