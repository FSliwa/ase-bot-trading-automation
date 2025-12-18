"""
Fully Automated Trading Bot
Runs strategies automatically without user intervention

v2.0 - IMPROVED:
- Shortened signal window from 24h to 6h (fresher signals)
- Better signal deduplication (prefer newest per symbol)
- Rate limiting to prevent excessive trading
- Market intelligence for liquidity checks and sentiment
- Dynamic SL/TP based on volatility
"""

import asyncio
import os
import signal
import sys
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path

# Load environment variables FIRST before any other imports
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from bot.config import load_config
from bot.strategies import AutoTradingEngine, MomentumStrategy, MeanReversionStrategy, AIStrategy
from bot.risk_manager import RiskManager
from bot.db import DatabaseManager, init_db, extract_base_symbol
from bot.logging_setup import get_logger
from ccxt import AuthenticationError

from bot.analysis.technical_analysis import TechnicalAnalyzer
from bot.services.risk_manager import UserRiskSettings  # NEW: Import UserRiskSettings

# NEW v2.0: Import enhanced services for logic gap fixes
try:
    from bot.services.market_intelligence import get_market_intelligence, MarketRegime
    from bot.services.rate_limiter import get_rate_limiter, RateLimitConfig
    from bot.services.signal_deduplicator import get_signal_deduplicator
    ENHANCED_SERVICES_AVAILABLE = True
except ImportError as e:
    ENHANCED_SERVICES_AVAILABLE = False
    print(f"Warning: Enhanced services not available: {e}")

# NEW v3.0: Import core infrastructure modules for critical fixes
try:
    from bot.core import (
        SymbolNormalizer, normalize_symbol, to_exchange_format,
        TransactionManager, atomic_trade_operation,
        PositionLockManager, position_lock,
        DailyLossTracker,
        CorrelationManager,
        MarketRegimeSizer, RegimeIndicators, MarketRegime as CoreMarketRegime,
        SpreadAwarePnL, SpreadData, FeeStructure,
        ComponentRateLimiter,
        RetryHandler, with_retry
    )
    CORE_MODULES_AVAILABLE = True
except ImportError as e:
    CORE_MODULES_AVAILABLE = False
    print(f"Warning: Core modules not available: {e}")

# NEW v4.0: DCA Manager for Dollar Cost Averaging functionality
try:
    from bot.services.dca_manager import DCAManager, DCAConfig
    DCA_AVAILABLE = True
except ImportError as e:
    DCA_AVAILABLE = False
    print(f"Warning: DCA Manager not available: {e}")

logger = get_logger("auto_trader")


class AutomatedTradingBot:
    """Main automated trading system"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, 
                 exchange_name: Optional[str] = None, user_id: Optional[str] = None,
                 test_mode: bool = False, broker = None, exchange_adapter = None,
                 futures: bool = False, margin: bool = False):
        load_dotenv()
        self.config = load_config()
        self.running = False
        self.tasks = []
        # Always convert user_id to string to avoid UUID slicing issues
        self.user_id = str(user_id) if user_id else None
        self.test_mode = test_mode
        self.injected_broker = broker
        self.injected_exchange = exchange_adapter
        self.futures = futures
        self.margin = margin  # NEW: Margin trading mode
        
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
        self.signal_validator = None  # Signal validation using historical data
        self.portfolio_manager = None  # Portfolio awareness for position sizing
        self.risk_manager_service = None  # NEW: Risk Manager for position sizing & trailing stop
        self.risk_manager = RiskManager()
        self.trading_engine = None
        self.ai_strategy = None
        self.db_manager = None
        self.technical_analyzer = TechnicalAnalyzer()
        
        # NEW v2.0: Enhanced services for logic gap fixes
        self.market_intelligence = None  # Liquidity check, sentiment, volatility-adjusted SL/TP
        self.rate_limiter = None         # Prevent excessive trading
        self.signal_deduplicator = None  # Better signal deduplication (prefer newest)
        
        # Real-time components
        self.ws_manager = None
        self.position_monitor = None
        self.started_at = None
        
        # NEW v3.0: Core infrastructure components
        self.symbol_normalizer = None      # Unified symbol format
        self.transaction_manager = None     # Atomic DB operations
        self.position_lock_manager = None   # Position mutex
        self.daily_loss_tracker = None      # Daily loss enforcement
        self.correlation_manager = None     # Correlation-based limiting
        self.regime_sizer = None            # Market regime position sizing
        self.spread_pnl = None              # Spread-aware P&L
        self.component_rate_limiter = None  # Per-component rate limiting
        self.retry_handler = None           # Retry logic for critical operations
        
    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing Automated Trading Bot...")
        self.started_at = datetime.now()
        
        # Initialize database
        init_db()
        self.db_manager = DatabaseManager()
        
        # Load API keys from database if user_id is provided
        if self.user_id and not self.api_key:
            logger.info(f"Loading API keys from database for user {self.user_id[:8]}...")
            await self._load_api_keys_from_db()
            logger.info(f"After loading: api_key={'SET' if self.api_key else 'NOT SET'}, exchange={self.exchange_name}")
        
        # Initialize exchange connection
        if self.injected_exchange:
            self.exchange = self.injected_exchange
            logger.info("Using injected exchange adapter")
        elif not self.test_mode and (not self.api_key or not self.api_secret):
            raise ValueError("EXCHANGE_API_KEY and EXCHANGE_API_SECRET must be set")
            
        if not self.exchange and not self.test_mode:
            from bot.exchange_adapters.ccxt_adapter import CCXTAdapter
            self.exchange = CCXTAdapter(
                exchange_name=self.exchange_name,
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet,
                futures=self.futures,
                margin=self.margin  # NEW: Pass margin mode
            )
        
        # Initialize Position Monitor for background SL/TP monitoring
        # with NEW features: Auto SL/TP, Partial TP, Time Exit
        if self.exchange:
            try:
                from bot.services.position_monitor import PositionMonitorService
                
                # FIX 2025-12-16: Properly load user's SL/TP from database
                # User's explicit SL/TP settings take priority over risk-based defaults
                user_sl_percent = None
                user_tp_percent = None
                
                # Try to get actual user settings from database
                if self.db_manager and self.user_id:
                    try:
                        with self.db_manager as db:
                            trading_settings = db.get_trading_settings(self.user_id)
                            if trading_settings:
                                # User explicitly set SL/TP in app → use those
                                if trading_settings.stop_loss_percentage:
                                    user_sl_percent = float(trading_settings.stop_loss_percentage)
                                    logger.info(f"📋 Using user's custom SL: {user_sl_percent}%")
                                if trading_settings.take_profit_percentage:
                                    user_tp_percent = float(trading_settings.take_profit_percentage)
                                    logger.info(f"📋 Using user's custom TP: {user_tp_percent}%")
                    except Exception as e:
                        logger.debug(f"Could not load user SL/TP from DB: {e}")
                
                # Fallback to risk-based calculation only if user didn't set explicit values
                user_settings = {
                    'sl_percent': user_sl_percent or (self.risk_per_trade * 100 * 2.5),  # Fallback: risk-based
                    'tp_percent': user_tp_percent or (self.risk_per_trade * 100 * 3.5),  # Fallback: risk-based
                    'max_hold_hours': 12.0  # Default max hold time
                }
                
                logger.info(f"📊 Position Monitor SL/TP: SL={user_settings['sl_percent']:.1f}% | TP={user_settings['tp_percent']:.1f}%")
                
                self.position_monitor = PositionMonitorService(
                    exchange_adapter=self.exchange,
                    check_interval=5.0,  # Check every 5 seconds
                    on_sl_triggered=self._on_sl_triggered,
                    on_tp_triggered=self._on_tp_triggered,
                    on_partial_tp_triggered=self._on_partial_tp_triggered,  # NEW
                    on_time_exit_triggered=self._on_time_exit_triggered,    # NEW
                    enable_trailing=True,
                    enable_dynamic_sl=True,
                    enable_partial_tp=True,    # NEW: Partial TP enabled
                    enable_time_exit=True,     # NEW: Time-based exit enabled
                    enable_auto_sl_tp=True,    # NEW: Auto-set SL/TP for unprotected positions
                    user_settings=user_settings,
                    default_user_id=self.user_id  # v4.3: Pass user_id for sync operations
                )
                
                # CRITICAL FIX: Set db_manager for reevaluation and liquidation logging
                if self.db_manager:
                    self.position_monitor.set_db_manager(self.db_manager)
                
                await self.position_monitor.start()
                logger.info(
                    f"✅ Position Monitor started (5s interval) | "
                    f"Auto SL/TP: ✅ | Partial TP: ✅ | Time Exit: ✅ (12h max)"
                )
                
                # Sync existing positions from database and exchange
                # This ensures positions from previous sessions are monitored
                try:
                    db_synced = await self.position_monitor.sync_from_database(self.db_manager)
                    ex_synced = await self.position_monitor.sync_from_exchange(self.db_manager)
                    if db_synced > 0 or ex_synced > 0:
                        logger.info(f"✅ Restored position monitoring: {db_synced} from DB, {ex_synced} from exchange")
                except Exception as sync_err:
                    logger.warning(f"Position sync failed (will monitor new positions only): {sync_err}")
                    
            except Exception as e:
                logger.warning(f"Position Monitor initialization failed: {e}")
        
        # Try to initialize WebSocket for real-time data (optional enhancement)
        try:
            from bot.realtime.websocket_manager import WebSocketManager
            self.ws_manager = WebSocketManager(
                exchange_name=self.exchange_name,
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet
            )
            if await self.ws_manager.connect():
                await self.ws_manager.subscribe_tickers(self.trade_symbols)
                logger.info("✅ WebSocket real-time data connected")
            else:
                logger.warning("WebSocket connection failed, using REST polling fallback")
                self.ws_manager = None
        except ImportError:
            logger.info("CCXT Pro not available, using REST polling for market data")
            self.ws_manager = None
        except Exception as e:
            logger.warning(f"WebSocket initialization failed: {e}. Using REST polling.")
            self.ws_manager = None
        
        # Initialize AI analyzer and service
        try:
            from bot.services.supabase_analysis_service import SupabaseAnalysisService
            
            self.analysis_service = SupabaseAnalysisService()
            logger.info("✅ Supabase AI Market Analysis Service initialized successfully")
        except Exception as e:
            logger.warning(f"AI analyzer initialization failed: {e}. Will trade without AI signals.")
        
        # Initialize Signal Validator (uses historical signals for consensus)
        # with ADAPTIVE CONFIDENCE THRESHOLD
        try:
            from bot.services.signal_validator import create_signal_validator
            
            self.signal_validator = create_signal_validator()
            logger.info("✅ Signal Validator initialized (adaptive confidence threshold)")
        except Exception as e:
            logger.warning(f"Signal Validator initialization failed: {e}. Signals will not be validated.")
            self.signal_validator = None
        
        # Initialize Portfolio Manager (portfolio-aware trading decisions)
        try:
            from bot.services.portfolio_manager import PortfolioManagerService
            
            self.portfolio_manager = PortfolioManagerService(
                exchange_adapter=self.exchange,
                custom_limits={
                    "max_single_position_pct": 25.0,
                    "max_category_exposure_pct": 40.0,
                    "max_meme_exposure_pct": 10.0,
                    "min_stable_reserve_pct": 10.0,
                }
            )
            logger.info("✅ Portfolio Manager initialized (portfolio-aware trading)")
        except Exception as e:
            logger.warning(f"Portfolio Manager initialization failed: {e}")
            self.portfolio_manager = None
        
        # Initialize Risk Manager (position sizing, trailing stop, dynamic SL/TP)
        try:
            from bot.services.risk_manager import (
                RiskManagerService, 
                RiskLevel, 
                TrailingStopConfig,
                DynamicSLTPConfig,
                KellyConfig
            )
            
            # Configure trailing stop
            trailing_config = TrailingStopConfig(
                enabled=True,
                activation_profit_percent=1.0,  # Activate after 1% profit
                trailing_distance_percent=2.0,   # Trail by 2%
                use_atr_distance=True,           # Use ATR for smarter trailing
                atr_multiplier=2.0               # 2x ATR trailing distance
            )
            
            # Configure dynamic SL/TP
            dynamic_sltp_config = DynamicSLTPConfig(
                enabled=True,
                use_atr=True,
                atr_multiplier_sl=2.0,   # SL at 2x ATR from entry
                atr_multiplier_tp=3.0,   # TP at 3x ATR (1:1.5 R:R)
                min_sl_percent=1.0,      # Minimum 1% SL
                max_sl_percent=5.0,      # Maximum 5% SL
                min_rr_ratio=1.5         # Minimum 1:1.5 Risk:Reward
            )
            
            # Configure Kelly Criterion
            # L7 FIX: Unified min_trades_required to 10 (was 20 here, 5 in risk_manager)
            # 10 trades provides balance between statistical significance and usability
            kelly_config = KellyConfig(
                enabled=True,
                fraction=0.25,           # Use 25% Kelly (safer)
                min_trades_required=10,  # L7 FIX: Unified to 10 trades for reliable stats
                fallback_risk_percent=1.0  # 1% risk if not enough data
            )
            
            # Load user-specific risk settings if user_id is available
            user_risk_settings = None
            if self.user_id:
                user_risk_settings = self._load_user_risk_settings()
            
            self.risk_manager_service = RiskManagerService(
                exchange_adapter=self.exchange,
                risk_level=RiskLevel.MODERATE,  # Default, may be overridden by user settings
                trailing_config=trailing_config,
                dynamic_sltp_config=dynamic_sltp_config,
                kelly_config=kelly_config,
                max_position_size_usd=1000.0,  # Default, may be overridden by user settings
                default_leverage=10.0,  # Default 10x leverage - will be auto-adjusted if not available
                user_settings=user_risk_settings  # NEW: User-specific settings
            )
            
            # Log with user settings info
            if user_risk_settings:
                logger.info(
                    "✅ Risk Manager initialized with USER SETTINGS | "
                    f"User: {self.user_id[:8]}... | "
                    f"Risk Level: {user_risk_settings.risk_level}/5 ({user_risk_settings.risk_per_trade_percent}% risk) | "
                    f"Max Position: ${user_risk_settings.max_position_size:.0f} | "
                    f"SL: {user_risk_settings.stop_loss_percentage}% | TP: {user_risk_settings.take_profit_percentage}% | "
                    f"Trailing: ✅ | Dynamic SL/TP: ✅ | Kelly: ✅ | Leverage: 10x"
                )
            else:
                logger.info(
                    "✅ Risk Manager initialized with DEFAULTS | "
                    f"Level: MODERATE (1% risk) | "
                    f"Trailing: ✅ | Dynamic SL/TP: ✅ | Kelly: ✅ | "
                    f"Default Leverage: 10x (auto-adjusted)"
                )
        except Exception as e:
            logger.warning(f"Risk Manager initialization failed: {e}")
            self.risk_manager_service = None
        
        # Connect Risk Manager to Position Monitor for trailing stops
        if self.position_monitor and self.risk_manager_service:
            self.position_monitor.set_risk_manager(self.risk_manager_service)
            logger.info("🔗 Connected Risk Manager to Position Monitor")
        
        # ========================================
        # NEW v2.0: Initialize Enhanced Services (Logic Gap Fixes)
        # ========================================
        if ENHANCED_SERVICES_AVAILABLE:
            try:
                # Market Intelligence - Liquidity check, sentiment, volatility SL/TP
                self.market_intelligence = get_market_intelligence(self.exchange)
                logger.info("✅ Market Intelligence initialized (liquidity check, sentiment, dynamic SL/TP)")
                
                # Rate Limiter - Prevent excessive trading
                rate_config = RateLimitConfig(
                    max_signals_per_cycle=3,      # Max 3 signals per bot cycle
                    max_trades_per_hour=5,        # Max 5 trades per hour
                    max_trades_per_day=15,        # Max 15 trades per day
                    symbol_cooldown_minutes=60,   # 1h cooldown per symbol
                    max_concurrent_positions=self.max_positions,
                    max_daily_loss_pct=self.daily_loss_limit,
                    pause_after_consecutive_losses=3  # Pause after 3 losses in a row
                )
                self.rate_limiter = get_rate_limiter(rate_config)
                logger.info(
                    f"✅ Rate Limiter initialized: {rate_config.max_signals_per_cycle}/cycle, "
                    f"{rate_config.max_trades_per_hour}/hour, {rate_config.max_trades_per_day}/day"
                )
                
                # Signal Deduplicator - Prefer newest signals per symbol
                self.signal_deduplicator = get_signal_deduplicator(
                    signal_window_hours=6.0,      # Shortened from 24h to 6h
                    stale_threshold_hours=2.0     # Consider signal stale after 2h
                )
                logger.info("✅ Signal Deduplicator initialized (6h window, prefer newest)")
                
            except Exception as e:
                logger.warning(f"Enhanced services initialization failed: {e}")
        else:
            logger.info("⚠️ Enhanced services not available - using legacy logic")
        
        # ========================================
        # NEW v3.0: Initialize Core Infrastructure Modules
        # ========================================
        if CORE_MODULES_AVAILABLE:
            try:
                # Symbol Normalizer - Unified symbol format
                self.symbol_normalizer = SymbolNormalizer()
                logger.info("✅ Symbol Normalizer initialized (unified format across all components)")
                
                # Transaction Manager - Atomic DB operations with retry
                from bot.db import get_session
                session = get_session()
                self.transaction_manager = TransactionManager(session)
                logger.info("✅ Transaction Manager initialized (atomic DB operations)")
                
                # Position Lock Manager - Mutex for position operations
                self.position_lock_manager = PositionLockManager()
                logger.info("✅ Position Lock Manager initialized (race condition prevention)")
                
                # Daily Loss Tracker - Enforce daily loss limit
                self.daily_loss_tracker = DailyLossTracker(
                    max_daily_loss_pct=self.daily_loss_limit,
                    max_consecutive_losses=5,
                    pause_duration_minutes=60
                )
                logger.info(f"✅ Daily Loss Tracker initialized (max {self.daily_loss_limit}% daily loss)")
                
                # Correlation Manager - Limit correlated exposure
                self.correlation_manager = CorrelationManager(
                    max_correlation_exposure=0.5,  # Max 50% in correlated assets
                    correlation_threshold=0.7      # Assets with >0.7 correlation
                )
                logger.info("✅ Correlation Manager initialized (exposure limiting)")
                
                # Market Regime Sizer - Dynamic position sizing
                self.regime_sizer = MarketRegimeSizer(
                    min_multiplier=0.1,
                    max_multiplier=2.0
                )
                logger.info("✅ Market Regime Sizer initialized (regime-based sizing)")
                
                # Spread-Aware P&L Calculator
                fee_structure = FeeStructure.binance_spot() if 'binance' in self.exchange_name.lower() else FeeStructure.kraken_spot()
                self.spread_pnl = SpreadAwarePnL(fee_structure)
                logger.info("✅ Spread-Aware P&L Calculator initialized")
                
                # Component Rate Limiter - Per-component limits
                self.component_rate_limiter = ComponentRateLimiter()
                logger.info("✅ Component Rate Limiter initialized (per-component limits)")
                
                # Retry Handler - Critical operation retry
                self.retry_handler = RetryHandler()
                logger.info("✅ Retry Handler initialized (exponential backoff + circuit breaker)")
                
            except Exception as e:
                logger.warning(f"Core modules initialization failed: {e}")
        else:
            logger.info("⚠️ Core modules not available - using legacy infrastructure")
        
        # ========================================
        # NEW v4.0: Initialize DCA Manager (Dollar Cost Averaging)
        # ========================================
        self.dca_manager = None
        self.dca_enabled = False
        
        if DCA_AVAILABLE and self.user_id:
            try:
                # P0-2 FIX (2025-12-15): DCAManager signature is (exchange_adapter, user_id, config)
                # Removed incorrect db_session parameter
                self.dca_manager = DCAManager(
                    exchange_adapter=self.exchange,
                    user_id=self.user_id
                    # config=None uses DCAConfig.default()
                )
                
                # Load user's DCA settings
                dca_settings = self.dca_manager.get_user_dca_settings()
                self.dca_enabled = dca_settings.get('dca_enabled', False) if dca_settings else False
                
                if self.dca_enabled:
                    logger.info(
                        f"✅ DCA Manager initialized (ENABLED) | "
                        f"Base: {dca_settings.get('base_order_percent', 40)}% | "
                        f"Safety Orders: {dca_settings.get('safety_order_count', 3)} | "
                        f"Price Deviation: {dca_settings.get('price_deviation_percent', 3)}%"
                    )
                else:
                    logger.info("✅ DCA Manager initialized (DISABLED - can be enabled in settings)")
                    
            except Exception as e:
                logger.warning(f"DCA Manager initialization failed: {e}")
                self.dca_manager = None
        else:
            if not DCA_AVAILABLE:
                logger.info("⚠️ DCA not available - module not imported")
            elif not self.user_id:
                logger.info("⚠️ DCA not available - no user_id set")
        
        # Initialize trading engine
        if self.injected_broker:
            self.trading_engine = AutoTradingEngine(
                self.injected_broker, 
                self.config,
                position_monitor=self.position_monitor,
                portfolio_manager=self.portfolio_manager,
                risk_manager=self.risk_manager_service,
                dca_manager=self.dca_manager  # NEW: Pass DCA Manager
            )
            logger.info("Using injected broker for trading engine")
        else:
            from bot.broker.live_broker import LiveBroker
            live_broker = LiveBroker(
                exchange_name=self.exchange_name,
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet,
                futures=self.futures,  # Pass futures flag
                margin=self.margin     # Pass margin flag
            )
            self.trading_engine = AutoTradingEngine(
                live_broker, 
                self.config, 
                db_manager=self.db_manager,
                user_id=self.user_id,
                symbols=self.trade_symbols,
                position_monitor=self.position_monitor,
                portfolio_manager=self.portfolio_manager,
                risk_manager=self.risk_manager_service,
                dca_manager=self.dca_manager  # NEW: Pass DCA Manager
            )
        
        # Add AI Strategy with shorting capability based on account type
        can_short = self.margin or self.futures
        self.ai_strategy = AIStrategy(self.trade_symbols, self.config, can_short=can_short)
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
        
        # Set symbols on trading engine
        self.trading_engine.set_symbols(self.trade_symbols)
            
        # Activate trading engine
        self.trading_engine.active = True
        
        logger.info(f"Initialized with {len(self.enabled_strategies)} strategies on {self.exchange_name}")
        logger.info(f"Default fallback symbols: {self.trade_symbols} (actual symbols from DB signals)")
        logger.info(f"Testnet mode: {self.testnet}")
        logger.info(f"WebSocket: {'enabled' if self.ws_manager else 'disabled (using REST)'}")
        logger.info(f"Position Monitor: {'enabled' if self.position_monitor else 'disabled'}")
        logger.info(f"Portfolio Manager: {'enabled' if self.portfolio_manager else 'disabled'}")
        logger.info(f"Risk Manager: {'enabled' if self.risk_manager_service else 'disabled'}")
        logger.info(f"DCA Manager: {'enabled' if self.dca_enabled else 'disabled'}")
        
        if self.risk_manager_service:
            status = self.risk_manager_service.get_status()
            logger.info(
                f"  └─ Risk Level: {status['risk_level']} | "
                f"Trailing: {'✅' if status['trailing_stop_enabled'] else '❌'} | "
                f"Dynamic SL/TP: {'✅' if status['dynamic_sltp_enabled'] else '❌'} | "
                f"Kelly: {'✅' if status['kelly_enabled'] else '❌'}"
            )
        
    async def get_market_data(self) -> Dict:
        """
        Fetch live market data.
        Uses WebSocket cache if available, falls back to REST API.
        """
        from bot.strategies import MarketData
        market_data = {}
        
        for symbol in self.trade_symbols:
            try:
                # PRIORITY 1: Use WebSocket data if available (fastest, <100ms)
                if self.ws_manager and self.ws_manager.is_connected():
                    tick = self.ws_manager.get_ticker(symbol)
                    if tick:
                        market_data[symbol] = MarketData(
                            symbol=symbol,
                            current_price=tick.last_price,
                            high_24h=tick.high_24h,
                            low_24h=tick.low_24h,
                            volume_24h=tick.volume_24h,
                            change_24h_percent=tick.change_24h_percent,
                            timestamp=tick.timestamp
                        )
                        continue
                
                # PRIORITY 2: REST API fallback
                if hasattr(self.exchange, 'get_ticker_stats'):
                    stats = await self.exchange.get_ticker_stats(symbol)
                    if not stats:
                        continue
                        
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
                    # Fallback: use CCXT fetch_ticker
                    ticker = await self.exchange.exchange.fetch_ticker(symbol)
                    market_data[symbol] = MarketData(
                        symbol=symbol,
                        current_price=ticker['last'],
                        high_24h=ticker.get('high', ticker['last'] * 1.02),
                        low_24h=ticker.get('low', ticker['last'] * 0.98),
                        volume_24h=ticker.get('quoteVolume', 0),
                        change_24h_percent=ticker.get('percentage', 0),
                        timestamp=datetime.now()
                    )
            except Exception as e:
                logger.error(f"Failed to fetch market data for {symbol}: {e}")
                
        return market_data
    
    async def check_risk_limits(self) -> bool:
        """
        Check if we're within risk limits.
        
        FIX 2025-12-16: Count positions based on account mode:
        - MARGIN mode: Only count margin positions (not spot assets)
        - SPOT mode: Only count spot positions (not margin)
        - Always ignore positions worth < $1 USD
        """
        try:
            account_info = await self.exchange.get_account_info()
            # Handle both Dict and object with .total attribute
            if isinstance(account_info, dict):
                current_equity = account_info.get('total', account_info.get('total_balance', 10000))
            else:
                current_equity = getattr(account_info, 'total', 10000)
            
            # Ensure we have a valid equity value
            if not current_equity or current_equity <= 0:
                logger.warning("Could not determine account equity, using default")
                current_equity = 10000  # Default for risk calculations
            
            # Check circuit breakers (wrapped in try-except to handle division errors)
            try:
                breakers = self.risk_manager.check_circuit_breakers(current_equity)
                if breakers["should_halt_trading"]:
                    logger.warning(f"Circuit breaker triggered: {breakers['breakers']}")
                    return False
            except ZeroDivisionError:
                logger.debug("Circuit breaker check failed (division by zero), skipping")
            except Exception as cb_err:
                logger.debug(f"Circuit breaker check failed: {cb_err}")
            
            # FIX 2025-12-16: Count positions based on account mode
            # Determine account mode from exchange adapter
            is_margin_mode = getattr(self.exchange, 'margin', False)
            is_futures_mode = getattr(self.exchange, 'futures', False)
            
            total_positions = 0
            mode_str = "SPOT"
            
            if is_margin_mode or is_futures_mode:
                # MARGIN/FUTURES mode: Only count margin/futures positions
                mode_str = "MARGIN" if is_margin_mode else "FUTURES"
                margin_positions = await self.exchange.get_positions()
                # Filter positions >= $1 value
                significant_positions = []
                for pos in margin_positions:
                    try:
                        pos_value = abs(float(getattr(pos, 'quantity', 0) or 0) * float(getattr(pos, 'entry_price', 0) or 0))
                        if pos_value >= 1.0:
                            significant_positions.append(pos)
                    except:
                        significant_positions.append(pos)  # Include if can't calculate
                total_positions = len(significant_positions)
                logger.debug(f"📊 {mode_str} mode: {total_positions} positions >= $1 (filtered from {len(margin_positions)})")
            else:
                # SPOT mode: Only count spot positions (get_spot_balances already filters < $1)
                mode_str = "SPOT"
                spot_assets = await self.exchange.get_spot_balances(min_value_usd=1.0)
                total_positions = len(spot_assets)
                logger.debug(f"📊 SPOT mode: {total_positions} positions >= $1")
            
            if total_positions >= self.max_positions:
                logger.info(f"Max positions reached ({total_positions}/{self.max_positions}) in {mode_str} mode")
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
    
    def get_user_tp_sl_settings(self) -> Dict[str, float]:
        """
        Fetch user's TP/SL percentage settings from database.
        Checks trading_settings first, then risk_management_settings as fallback.
        
        Returns:
            Dict with 'take_profit_pct' and 'stop_loss_pct' (as percentages, e.g., 3.0 for 3%)
        """
        default_settings = {'take_profit_pct': 3.0, 'stop_loss_pct': 5.0}
        
        if not self.user_id:
            logger.warning("No user_id set, using default TP/SL settings")
            return default_settings
        
        try:
            from bot.db import DatabaseManager
            from sqlalchemy import text
            
            with DatabaseManager.session_scope() as session:
                # Try trading_settings first
                result = session.execute(text("""
                    SELECT take_profit_percentage, stop_loss_percentage 
                    FROM trading_settings 
                    WHERE user_id = :user_id
                    LIMIT 1
                """), {'user_id': self.user_id})
                row = result.fetchone()
                
                if row and row[0] is not None and row[1] is not None:
                    settings = {
                        'take_profit_pct': float(row[0]),
                        'stop_loss_pct': float(row[1])
                    }
                    logger.info(f"📊 User TP/SL settings from trading_settings: TP={settings['take_profit_pct']}%, SL={settings['stop_loss_pct']}%")
                    return settings
                
                # Fallback to risk_management_settings
                result = session.execute(text("""
                    SELECT take_profit_percent, stop_loss_percent 
                    FROM risk_management_settings 
                    WHERE user_id = :user_id
                    LIMIT 1
                """), {'user_id': self.user_id})
                row = result.fetchone()
                
                if row and row[0] is not None and row[1] is not None:
                    settings = {
                        'take_profit_pct': float(row[0]),
                        'stop_loss_pct': float(row[1])
                    }
                    logger.info(f"📊 User TP/SL settings from risk_management_settings: TP={settings['take_profit_pct']}%, SL={settings['stop_loss_pct']}%")
                    return settings
                
                logger.info(f"📊 No TP/SL settings found for user {self.user_id}, using defaults: TP={default_settings['take_profit_pct']}%, SL={default_settings['stop_loss_pct']}%")
                return default_settings
                
        except Exception as e:
            logger.error(f"Failed to fetch user TP/SL settings: {e}")
            return default_settings
    
    def get_user_settings(self) -> Optional[Dict]:
        """
        Get user's trading settings including risk level.
        Used for AI portfolio evaluation.
        
        Returns:
            Dict with user settings or None if not found
        """
        try:
            from bot.db import DatabaseManager
            from sqlalchemy import text
            
            with DatabaseManager() as db:
                result = db.session.execute(text("""
                    SELECT risk_level, max_position_size, max_daily_loss, 
                           stop_loss_percentage, take_profit_percentage
                    FROM trading_settings 
                    WHERE user_id = :user_id
                    LIMIT 1
                """), {'user_id': self.user_id})
                row = result.fetchone()
                
                if row:
                    return {
                        'risk_level': int(row[0]) if row[0] else 3,
                        'max_position_size': float(row[1]) if row[1] else 1000.0,
                        'max_daily_loss': float(row[2]) if row[2] else 100.0,
                        'stop_loss_pct': float(row[3]) if row[3] else 5.0,
                        'take_profit_pct': float(row[4]) if row[4] else 3.0  # Default TP=3%
                    }
                
            return {'risk_level': 3, 'stop_loss_pct': 5.0, 'take_profit_pct': 3.0}  # Default moderate risk
            
        except Exception as e:
            logger.warning(f"Failed to fetch user settings: {e}")
            return {'risk_level': 3}

    def get_signals_from_database(self, quote_currency: str = "USDT", exchange_id: str = None) -> Optional[List[Dict]]:
        """
        Fetch active trading signals from the database (trading_signals table).
        Returns signals that have action BUY or SELL (not HOLD).
        
        Bot trades ONLY on symbols from trading_signals table!
        
        IMPORTANT: Signals with user_id=NULL are GLOBAL signals available for ALL users.
        They will be evaluated by AI to determine if suitable for this specific user.
        
        IMPROVED (v2.0):
        - Shortened signal window from 24h to 6h to avoid stale signals
        - Better deduplication: always prefer NEWEST signal per symbol
        - Sorted by created_at DESC so newest comes first
        
        P1-NEW-5: Added exchange_id filtering to skip symbols unavailable on user's exchange
        
        Args:
            quote_currency: Quote currency to use (USDT or USDC based on user's balance)
            exchange_id: Optional exchange ID to filter symbols (e.g., 'binance', 'kraken')
        """
        try:
            from bot.db import TradingSignal, DatabaseManager
            from datetime import timedelta
            from bot.db import _utcnow
            from sqlalchemy import or_
            
            # IMPROVED: Shortened from 24h to 6h for fresher signals
            # Old: 24 hours caught stale signals in fast markets
            # New: 6 hours balances freshness with availability
            SIGNAL_WINDOW_HOURS = 6  # Configurable signal freshness window
            cutoff = _utcnow() - timedelta(hours=SIGNAL_WINDOW_HOURS)
            
            # Use fresh DatabaseManager context
            with DatabaseManager() as db:
                # Fetch signals for THIS USER or GLOBAL signals (user_id=NULL)
                # Global signals (NULL) are shared across all users
                # Note: user_id is UUID type, so we only check for NULL (not empty string)
                # TRUSTED signal sources - 2025-12-15: Restricted to ONLY COUNCIL V2.0 and TITAN V3
                # Removed: 'ai-scheduler', 'ai-trading-signals', 'titan_v2', 'manual'
                TRUSTED_SOURCES = ['titan_v3', 'COUNCIL_V2.0_FALLBACK']
                
                buy_sell_signals = (
                    db.session.query(TradingSignal)
                    .filter(TradingSignal.is_active == True)
                    .filter(TradingSignal.created_at > cutoff)
                    .filter(TradingSignal.signal_type.in_(['buy', 'sell', 'BUY', 'SELL']))
                    .filter(TradingSignal.source.in_(TRUSTED_SOURCES))  # FIX: Only trusted sources
                    .filter(
                        or_(
                            TradingSignal.user_id == self.user_id,  # User-specific signals
                            TradingSignal.user_id == None           # Global signals (NULL)
                        )
                    )
                    .order_by(TradingSignal.created_at.desc())
                    .all()
                )
                
                # If no BUY/SELL, also consider HOLD signals (for monitoring)
                if not buy_sell_signals:
                    logger.info("📊 No BUY/SELL signals, checking HOLD signals for monitoring...")
                    hold_signals = (
                        db.session.query(TradingSignal)
                        .filter(TradingSignal.is_active == True)
                        .filter(TradingSignal.created_at > cutoff)
                        .filter(TradingSignal.source.in_(TRUSTED_SOURCES))  # FIX: Only trusted sources
                        .filter(
                            or_(
                                TradingSignal.user_id == self.user_id,
                                TradingSignal.user_id == None
                            )
                        )
                        .order_by(TradingSignal.created_at.desc())
                        .limit(10)  # Limit to top 10 most recent
                        .all()
                    )
                    signals = hold_signals
                else:
                    signals = buy_sell_signals
                
                if not signals:
                    logger.info(f"📊 No active signals found in trading_signals table (last {SIGNAL_WINDOW_HOURS}h)")
                    logger.info(f"   Searched trusted sources: {TRUSTED_SOURCES}")
                    return None
                
                # Log signal sources breakdown
                user_specific = sum(1 for s in signals if s.user_id == self.user_id)
                global_signals = len(signals) - user_specific
                
                # Count by source for diagnostics
                source_counts = {}
                for s in signals:
                    src = s.source or 'unknown'
                    source_counts[src] = source_counts.get(src, 0) + 1
                
                logger.info(f"📊 Found {len(signals)} signals from TRUSTED sources: {source_counts}")
                logger.info(f"   ({user_specific} user-specific, {global_signals} global)")
                logger.info(f"   Trusted sources filter: {TRUSTED_SOURCES}")
                
                # IMPROVED: Convert to dict format, keeping only NEWEST signal per symbol
                # Old logic: "seen_symbols" would skip newer signals if old was seen first
                # New logic: Group by symbol, keep only the most recent one (already sorted DESC)
                result = []
                seen_symbols = {}  # Changed to dict: symbol -> signal (keeps newest)
                
                for sig in signals:
                    # Parse symbol from database
                    raw_symbol = sig.symbol.strip()
                    
                    # Normalize symbol format (e.g., "BTC" -> "BTC/USDT", "BTCUSDT" -> "BTC/USDT")
                    if '/' in raw_symbol:
                        base = raw_symbol.split('/')[0]
                    elif raw_symbol.endswith('USDT'):
                        base = raw_symbol.replace('USDT', '')
                    elif raw_symbol.endswith('USDC'):
                        base = raw_symbol.replace('USDC', '')
                    else:
                        base = raw_symbol
                    
                    # Build final symbol with user's quote currency
                    target_symbol = f"{base}/{quote_currency}"
                    
                    # IMPROVED: Since signals are sorted by created_at DESC,
                    # the first signal for each symbol is the newest
                    # Old: if target_symbol in seen_symbols: continue (skipped newer!)
                    # New: Only keep first occurrence (which is newest due to DESC sort)
                    if target_symbol in seen_symbols:
                        # Log that we're skipping an OLDER duplicate
                        old_time = sig.created_at.strftime('%H:%M') if sig.created_at else '?'
                        logger.debug(f"  Skipping older {target_symbol} signal from {old_time}")
                        continue
                    
                    # Mark if this is a global signal
                    is_global = sig.user_id is None or sig.user_id == ''
                    
                    signal_dict = {
                        'symbol': target_symbol,
                        'action': sig.signal_type.upper(),
                        'confidence': float(sig.confidence_score or 0) / 100.0,  # Convert 0-100 to 0-1
                        'reasoning': sig.ai_analysis or sig.reasoning or 'Signal from trading_signals table',
                        'stop_loss': float(sig.stop_loss) if sig.stop_loss else None,
                        'take_profit': float(sig.take_profit) if sig.take_profit else None,
                        'entry_price': float(sig.entry_price) if sig.entry_price else None,
                        'source': f"db:{sig.source or 'trading_signals'}",
                        'signal_id': str(sig.id),
                        'timeframe': sig.timeframe,
                        'expected_profit': float(sig.expected_profit_percentage) if sig.expected_profit_percentage else None,
                        'is_global_signal': is_global,  # NEW: Mark global signals for AI evaluation
                        'original_user_id': str(sig.user_id) if sig.user_id else None,
                        'created_at': sig.created_at.isoformat() if sig.created_at else None  # IMPROVED: Include timestamp
                    }
                    
                    # Track seen symbols and add to results
                    seen_symbols[target_symbol] = signal_dict
                    result.append(signal_dict)
                
                # P1-NEW-5 FIX: Filter signals by exchange compatibility
                # Validate that symbols are available on user's exchange
                if exchange_id:
                    filtered_result = []
                    for signal_dict in result:
                        # Basic symbol validation - some exchanges don't support certain pairs
                        symbol = signal_dict['symbol']
                        
                        # Known exchange-specific restrictions
                        exchange_restrictions = {
                            'kraken': ['LUNA/', 'UST/', 'FTT/', 'USTC/'],  # Delisted/restricted tokens (USTC blocked for PL)
                            'binance': [],  # Binance has most pairs
                            'coinbase': ['DOGE/', 'SHIB/'],  # Limited meme coins (may change)
                        }
                        
                        restrictions = exchange_restrictions.get(exchange_id.lower(), [])
                        is_restricted = any(symbol.startswith(r) for r in restrictions)
                        
                        if is_restricted:
                            logger.info(f"⏭️ Skipping {symbol} - not available on {exchange_id}")
                            continue
                        
                        filtered_result.append(signal_dict)
                    
                    if len(filtered_result) < len(result):
                        logger.info(
                            f"📊 Filtered signals: {len(result)} → {len(filtered_result)} "
                            f"(removed {len(result) - len(filtered_result)} incompatible with {exchange_id})"
                        )
                    result = filtered_result
                
                symbols_list = [r['symbol'] for r in result]
                logger.info(f"📊 Found {len(result)} active signals from trading_signals: {symbols_list}")
                return result if result else None
                
        except Exception as e:
            logger.error(f"Failed to fetch signals from database: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def execute_ai_analysis(self, existing_market_data: Dict = None) -> Optional[Dict]:
        """
        Get AI trading recommendations - PRIMARY SOURCE: trading_signals table.
        
        Bot trades ONLY on symbols from trading_signals table!
        If no signals in DB, fallback to Edge Function AI analysis.
        
        Args:
            existing_market_data: Optional pre-fetched market data to avoid duplicate API calls
        """
        if not self.analysis_service:
            return None
            
        try:
            # Determine quote currency based on user's balance
            quote_currency = "USDT"  # Default
            try:
                balances = await self.exchange.get_all_balances()
                if balances:
                    # Handle both formats: Dict[str, float] and Dict[str, Dict]
                    usdc_val = balances.get('USDC', 0)
                    usdt_val = balances.get('USDT', 0)
                    usdc_balance = usdc_val if isinstance(usdc_val, (int, float)) else usdc_val.get('free', 0) or 0
                    usdt_balance = usdt_val if isinstance(usdt_val, (int, float)) else usdt_val.get('free', 0) or 0
                    if usdc_balance > usdt_balance:
                        quote_currency = "USDC"
                    logger.info(f"💰 Using {quote_currency} as quote currency (USDC: {usdc_balance}, USDT: {usdt_balance})")
            except Exception as e:
                logger.warning(f"Could not determine quote currency: {e}")
            
            # ========================================
            # 1. PRIMARY: Get signals from trading_signals table
            # Bot trades ONLY on symbols from this table!
            # ========================================
            logger.info("📊 Checking trading_signals table for active BUY/SELL signals...")
            
            # P1-NEW-5: Pass exchange_id for filtering
            current_exchange_id = self.exchange.exchange.id if hasattr(self.exchange, 'exchange') else None
            db_signals = self.get_signals_from_database(
                quote_currency=quote_currency,
                exchange_id=current_exchange_id
            )
            
            # FIX: Check if signals are actionable (not just HOLD with 0% confidence)
            # titan_v3 often returns HOLD with 0% confidence when AUDIT fails
            actionable_signals = []
            if db_signals:
                for sig in db_signals:
                    action = sig.get('action', 'hold').upper()
                    confidence = sig.get('confidence', 0)
                    # Consider signal actionable if: BUY/SELL OR (HOLD with confidence > 0)
                    if action in ['BUY', 'SELL']:
                        actionable_signals.append(sig)
                    elif action == 'HOLD' and confidence > 0.1:  # HOLD with >10% confidence = monitor
                        actionable_signals.append(sig)
                
                if not actionable_signals and db_signals:
                    logger.warning(f"⚠️ Found {len(db_signals)} signals but ALL are HOLD/0% confidence - treating as no signals for FALLBACK")
            
            if actionable_signals:
                db_signals = actionable_signals
                # Extract symbols from database signals
                signal_symbols = list(set([sig['symbol'] for sig in db_signals]))
                logger.info(f"✅ Found {len(db_signals)} signals for {len(signal_symbols)} symbols: {signal_symbols}")
                
                # Update trade_symbols to ONLY use symbols from trading_signals
                self.trade_symbols = signal_symbols
                
                # Fetch market data ONLY for signal symbols
                logger.info(f"📈 Fetching market data for signal symbols: {signal_symbols}")
                market_data_map = {}
                for symbol in signal_symbols:
                    try:
                        data = await self.exchange.get_ticker(symbol)
                        if data:
                            market_data_map[symbol] = data
                    except Exception as e:
                        logger.warning(f"Could not fetch ticker for {symbol}: {e}")
                
                # Get user's TP/SL settings for auto-calculation
                user_tp_sl = self.get_user_tp_sl_settings()
                tp_pct = user_tp_sl['take_profit_pct']
                sl_pct = user_tp_sl['stop_loss_pct']
                
                # ========================================
                # NEW v2.0: Get market sentiment for dynamic SL/TP
                # ========================================
                market_regime = None
                if hasattr(self, 'market_intelligence') and self.market_intelligence:
                    try:
                        sentiment = await self.market_intelligence.get_market_sentiment()
                        market_regime = sentiment.regime
                        logger.debug(f"Market regime for SL/TP adjustment: {market_regime.value}")
                    except Exception as e:
                        logger.debug(f"Could not get market sentiment: {e}")
                
                # Enrich signals with current market data and auto-calculate TP/SL if missing
                for sig in db_signals:
                    symbol = sig['symbol']
                    action = sig.get('action', '').upper()
                    
                    if symbol in market_data_map:
                        ticker_data = market_data_map[symbol]
                        # Handle both dict and object formats
                        if isinstance(ticker_data, dict):
                            current_price = ticker_data.get('last') or ticker_data.get('current_price')
                        else:
                            current_price = getattr(ticker_data, 'current_price', getattr(ticker_data, 'last', None))
                        
                        sig['current_price'] = current_price
                        sig['market_data'] = ticker_data
                        
                        # ========================================
                        # NEW v2.0: VOLATILITY-ADJUSTED SL/TP 
                        # Instead of fixed 5%/7%, adjusts based on:
                        # 1. Asset type (BTC vs memecoins)
                        # 2. Market regime (bull/bear/crisis)
                        # ========================================
                        if action in ('BUY', 'SELL') and current_price and current_price > 0:
                            # Try to get volatility-adjusted SL/TP from Market Intelligence
                            dynamic_sl_pct = sl_pct
                            dynamic_tp_pct = tp_pct
                            
                            if hasattr(self, 'market_intelligence') and self.market_intelligence and market_regime:
                                try:
                                    vol_profile = self.market_intelligence.get_volatility_adjusted_sl_tp(
                                        symbol=symbol,
                                        market_regime=market_regime
                                    )
                                    dynamic_sl_pct = vol_profile.suggested_sl_pct
                                    dynamic_tp_pct = vol_profile.suggested_tp_pct
                                    
                                    logger.info(
                                        f"📊 Volatility-adjusted SL/TP for {symbol}: "
                                        f"SL={dynamic_sl_pct}% (was {sl_pct}%), "
                                        f"TP={dynamic_tp_pct}% (was {tp_pct}%) | "
                                        f"Regime: {market_regime.value}"
                                    )
                                except Exception as e:
                                    logger.debug(f"Using default SL/TP (volatility calc failed: {e})")
                            
                            # Calculate TP if missing
                            if sig.get('take_profit') is None:
                                if action == 'BUY':
                                    # For BUY: TP is above current price
                                    sig['take_profit'] = round(current_price * (1 + dynamic_tp_pct / 100), 8)
                                else:  # SELL (short)
                                    # For SELL: TP is below current price
                                    sig['take_profit'] = round(current_price * (1 - dynamic_tp_pct / 100), 8)
                                logger.info(f"📊 Auto-calculated TP for {symbol} {action}: {sig['take_profit']} ({dynamic_tp_pct}% from {current_price})")
                            
                            # Calculate SL if missing
                            if sig.get('stop_loss') is None:
                                if action == 'BUY':
                                    # For BUY: SL is below current price
                                    sig['stop_loss'] = round(current_price * (1 - dynamic_sl_pct / 100), 8)
                                else:  # SELL (short)
                                    # For SELL: SL is above current price
                                    sig['stop_loss'] = round(current_price * (1 + dynamic_sl_pct / 100), 8)
                                logger.info(f"📊 Auto-calculated SL for {symbol} {action}: {sig['stop_loss']} ({dynamic_sl_pct}% from {current_price})")
                            
                            # Set entry_price if missing
                            if sig.get('entry_price') is None:
                                sig['entry_price'] = current_price
                
                analyses = db_signals
                logger.info(f"✅ Using {len(analyses)} signals from trading_signals table")
                
                # ========================================
                # AI PORTFOLIO EVALUATION for GLOBAL signals (user_id=NULL)
                # ========================================
                global_signals = [s for s in analyses if s.get('is_global_signal', False)]
                if global_signals:
                    logger.info(f"🤖 AI evaluating {len(global_signals)} GLOBAL signals for user {self.user_id[:8]}...")
                    try:
                        from bot.services.ai_portfolio_evaluator import get_ai_portfolio_evaluator
                        
                        evaluator = get_ai_portfolio_evaluator()
                        
                        # Get current portfolio state
                        portfolio_state = await evaluator.get_portfolio_state(
                            user_id=self.user_id,
                            exchange_adapter=self.exchange,
                            user_settings=self.get_user_settings()
                        )
                        
                        logger.info(
                            f"📊 Portfolio State: ${portfolio_state.total_balance_usd:.2f} total, "
                            f"${portfolio_state.available_balance_usd:.2f} available, "
                            f"{portfolio_state.position_count} positions, "
                            f"{portfolio_state.margin_level_percent:.0f}% margin level"
                        )
                        
                        # Evaluate each global signal
                        evaluated_signals = []
                        for sig in analyses:
                            if sig.get('is_global_signal', False):
                                evaluation = await evaluator.evaluate_signal_for_user(
                                    signal=sig,
                                    portfolio_state=portfolio_state
                                )
                                
                                if evaluation.should_execute:
                                    # Adjust signal based on AI recommendation
                                    sig['confidence'] = sig.get('confidence', 0.5) * evaluation.position_size_multiplier
                                    sig['ai_portfolio_eval'] = {
                                        'multiplier': evaluation.position_size_multiplier,
                                        'risk': evaluation.risk_assessment,
                                        'reasons': evaluation.reasons,
                                        'warnings': evaluation.warnings
                                    }
                                    logger.info(
                                        f"✅ GLOBAL signal {sig['symbol']} {sig['action']} APPROVED for user | "
                                        f"Size multiplier: {evaluation.position_size_multiplier:.0%} | "
                                        f"Risk: {evaluation.risk_assessment}"
                                    )
                                    evaluated_signals.append(sig)
                                else:
                                    logger.info(
                                        f"❌ GLOBAL signal {sig['symbol']} {sig['action']} REJECTED for user | "
                                        f"Reasons: {evaluation.reasons}"
                                    )
                            else:
                                # User-specific signals pass through without AI eval
                                evaluated_signals.append(sig)
                        
                        analyses = evaluated_signals
                        logger.info(f"📊 After AI evaluation: {len(analyses)} signals remain")
                        
                    except Exception as e:
                        logger.warning(f"AI Portfolio evaluation failed (using all signals): {e}")
                        import traceback
                        traceback.print_exc()
                
            else:
                # ========================================
                # 2. FALLBACK: No actionable signals in DB - use AI Edge Function (COUNCIL V2.0 FALLBACK)
                # ========================================
                logger.info("📊 No actionable signals in trading_signals table - falling back to COUNCIL V2.0 Edge Function...")
                logger.info("   (titan_v3 signals were HOLD/0% confidence or no signals at all)")
                
                # Dynamic Symbol Selection for AI fallback
                if hasattr(self.exchange, 'get_top_volume_symbols'):
                    dynamic_symbols = await self.exchange.get_top_volume_symbols(limit=5)
                    if dynamic_symbols:
                        logger.info(f"✅ Selected top {len(dynamic_symbols)} symbols for AI: {dynamic_symbols}")
                        self.trade_symbols = list(set(self.trade_symbols + dynamic_symbols))
                
                # Fetch Market Data
                if existing_market_data:
                    logger.info(f"📊 Using {len(existing_market_data)} pre-fetched market data symbols")
                    market_data_map = existing_market_data
                else:
                    logger.info(f"📊 Fetching market data for {len(self.trade_symbols)} symbols...")
                    market_data_map = await self.get_market_data()
                
                valid_symbols = [s for s in self.trade_symbols if s in market_data_map]
                valid_market_data = {s: market_data_map[s] for s in valid_symbols}
                
                if not valid_symbols:
                    logger.warning("No market data available for analysis")
                    return None

                # Enrich Data with Technical Analysis
                enriched_data_dicts = {}
                for symbol, data in valid_market_data.items():
                    # Handle both dict and object formats for market data
                    if isinstance(data, dict):
                        symbol_data = {
                            "current_price": data.get('last') or data.get('current_price'),
                            "change_24h_percent": data.get('percentage') or data.get('change_24h_percent', 0),
                            "volume_24h": data.get('quoteVolume') or data.get('volume_24h', 0),
                            "high_24h": data.get('high') or data.get('high_24h'),
                            "low_24h": data.get('low') or data.get('low_24h')
                        }
                    else:
                        symbol_data = {
                            "current_price": getattr(data, 'current_price', None),
                            "change_24h_percent": getattr(data, 'change_24h_percent', 0),
                            "volume_24h": getattr(data, 'volume_24h', 0),
                            "high_24h": getattr(data, 'high_24h', None),
                            "low_24h": getattr(data, 'low_24h', None)
                        }
                    
                    if hasattr(self.exchange, 'fetch_ohlcv'):
                        ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
                        ta_indicators = self.technical_analyzer.analyze_ohlcv(ohlcv)
                        symbol_data['technical_indicators'] = ta_indicators
                    
                    enriched_data_dicts[symbol] = symbol_data

                # Request AI analysis from Edge Function
                logger.info(f"🤖 Requesting AI analysis for {len(valid_symbols)} symbols...")
                analyses = await self.analysis_service.generate_signals_batch(valid_symbols, enriched_data_dicts)
            
            if not analyses:
                logger.info("No trading signals from DB or AI")
                # FIX 2025-12-14: Log why no signals were generated
                logger.info("   📊 Possible reasons:")
                logger.info("   1. titan_v3 returned HOLD/0% confidence (FALLBACK triggered)")
                logger.info("   2. COUNCIL V2.0 Edge Function returned empty signals[]")
                logger.info("   3. Market conditions: Fear & Greed index indicates caution")
                logger.info("   ➡️ Built-in strategies (Momentum/MeanReversion) will be used as last fallback")
                return None
                
            logger.info(f"✅ Processing {len(analyses)} signals")
            
            # Process, validate and save signals
            validated_analyses = []
            
            for analysis in analyses:
                symbol = analysis['symbol']
                action = analysis.get('action', 'hold').upper()
                confidence = analysis.get('confidence', 0.5)
                
                logger.info(f"AI Analysis for {symbol}: {action} - {analysis.get('reasoning')}")
                
                # VALIDATION: Check against historical signals (immutable operation)
                if self.signal_validator:
                    validation = self.signal_validator.validate_signal(analysis, symbol)
                    
                    logger.info(
                        f"📊 Signal Validation for {symbol}: "
                        f"execute={validation.should_execute}, "
                        f"consensus={validation.consensus_score:.2f}, "
                        f"reasons={validation.reasons}"
                    )
                    
                    # Skip duplicate signals
                    if self.signal_validator.is_duplicate_signal(symbol, action):
                        logger.info(f"⏭️ Skipping duplicate signal for {symbol} {action}")
                        continue
                    
                    # Update analysis with adjusted confidence
                    analysis = {
                        **analysis,  # Create NEW dict (immutability)
                        'confidence': validation.confidence_adjusted,
                        'should_execute': validation.should_execute,
                        'consensus_score': validation.consensus_score,
                        'validation_reasons': validation.reasons
                    }
                else:
                    # No validator - allow all signals
                    analysis = {
                        **analysis,
                        'should_execute': action != 'HOLD',
                        'consensus_score': 0.5,
                        'validation_reasons': ('No validator configured',)
                    }
                
                # Save signal to DB (only NEW signals - skip if already from DB)
                # FIX 2025-12-13: Don't re-save signals that came from DB (prevents duplicates)
                signal_source = analysis.get('source', '')
                is_from_db = signal_source.startswith('db:') or analysis.get('signal_id')
                
                if is_from_db:
                    logger.debug(f"⏭️ Skipping DB save for {symbol} - already in DB (source: {signal_source})")
                else:
                    # Only save NEW signals (from Edge Function fallback)
                    try:
                        strength_val = analysis.get('confidence', 0.5)
                        
                        # Extract TP/SL from analysis
                        take_profit_val = analysis.get('take_profit')
                        stop_loss_val = analysis.get('stop_loss')
                        entry_price_val = analysis.get('entry_price') or analysis.get('price')
                        
                        # Also check 'targets' array for TP
                        if not take_profit_val:
                            targets = analysis.get('targets', [])
                            if targets and targets[0]:
                                take_profit_val = targets[0]
                        
                        # Use session_scope for proper DB transaction
                        from bot.db import DatabaseManager
                        with DatabaseManager.session_scope() as session:
                            from bot.db import TradingSignal
                            from datetime import datetime, timedelta
                            import uuid as uuid_lib
                            
                            # Save only base symbol (BTC, ETH, SOL) - quote currency added locally when reading
                            base_symbol = extract_base_symbol(symbol)
                            
                            # FIX: Check if similar signal exists in last 6 hours (dedup)
                            cutoff = datetime.utcnow() - timedelta(hours=6)
                            existing = session.query(TradingSignal).filter(
                                TradingSignal.user_id == self.user_id,
                                TradingSignal.symbol == base_symbol,
                                TradingSignal.signal_type == action.lower(),
                                TradingSignal.created_at > cutoff
                            ).first()
                            
                            if existing:
                                logger.info(f"⏭️ Signal for {base_symbol} {action} already exists (from {existing.created_at.strftime('%H:%M')})")
                            else:
                                # FIX: Always generate proper COUNCIL v3.0 format reasoning
                                # Don't use original reasoning if it's test/placeholder data
                                original_reasoning = analysis.get('reasoning', '')
                                
                                # Check if reasoning needs regeneration
                                needs_regen = (
                                    not original_reasoning or 
                                    original_reasoning.lower().startswith('test') or 
                                    len(original_reasoning) < 20 or
                                    'Test signal' in original_reasoning or
                                    'test' in original_reasoning.lower()[:30]  # First 30 chars
                                )
                                
                                if needs_regen:
                                    # Generate proper COUNCIL v3.0 format reasoning
                                    sentiment = analysis.get('marketSentiment', 'neutral').upper()
                                    conf = int(strength_val * 100) if strength_val <= 1 else int(strength_val)
                                    
                                    # Build detailed reasoning with available data
                                    details = []
                                    if analysis.get('technical_score'):
                                        details.append(f"Technical: {analysis.get('technical_score')}")
                                    if analysis.get('sentiment_score'):
                                        details.append(f"Sentiment: {analysis.get('sentiment_score')}")
                                    if analysis.get('risk_score'):
                                        details.append(f"Risk: {analysis.get('risk_score')}")
                                    if not details:
                                        details.append(f"Market: {sentiment}")
                                    
                                    reasoning = (
                                        f"[COUNCIL v3.0] {action} {base_symbol} | "
                                        f"Confidence: {conf}% | "
                                        f"{', '.join(details)} | "
                                        f"Entry: ${entry_price_val or 'market'} | "
                                        f"TP: ${take_profit_val} | SL: ${stop_loss_val}"
                                    )
                                else:
                                    reasoning = original_reasoning
                                
                                signal = TradingSignal(
                                    id=str(uuid_lib.uuid4()),
                                    user_id=self.user_id,
                                    symbol=base_symbol,
                                    signal_type=action.lower(),
                                    confidence_score=int(float(strength_val) * 100) if float(strength_val) <= 1 else int(float(strength_val)),
                                    ai_analysis=reasoning,
                                    source="COUNCIL_V2.0_FALLBACK",  # Fallback when no titan_v3 signals in DB
                                    strength=float(strength_val),
                                    is_active=True,
                                    status="pending",
                                    take_profit=float(take_profit_val) if take_profit_val else None,
                                    stop_loss=float(stop_loss_val) if stop_loss_val else None,
                                    entry_price=float(entry_price_val) if entry_price_val else None,
                                )
                                session.add(signal)
                                logger.info(f"💾 Saved NEW signal for {base_symbol} to DB (TP={take_profit_val}, SL={stop_loss_val})")
                    except Exception as e:
                        import traceback
                        logger.error(f"Failed to save signal for {symbol}: {e}\n{traceback.format_exc()}")
                
                # Only add to validated list if should execute
                if analysis.get('should_execute', False):
                    validated_analyses.append(analysis)
                else:
                    logger.info(f"⏭️ Signal for {symbol} skipped: {analysis.get('validation_reasons')}")

            logger.info(f"✅ {len(validated_analyses)}/{len(analyses)} signals passed validation")
            return validated_analyses if validated_analyses else None
            
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
        """Main trading cycle - IMPROVED v3.0 with core infrastructure modules"""
        logger.info("Starting trading cycle...")
        
        try:
            # ========================================
            # NEW v4.0: DCA Safety Order Check (FIRST!)
            # ========================================
            if self.dca_manager and self.dca_enabled:
                try:
                    executed_safety_orders = await self.dca_manager.check_and_execute_safety_orders()
                    if executed_safety_orders > 0:
                        logger.info(f"💰 DCA: Executed {executed_safety_orders} safety order(s)")
                except Exception as dca_err:
                    logger.error(f"DCA safety order check failed: {dca_err}")
            
            # ========================================
            # NEW v3.0: Daily Loss Tracker - Pre-trade Check
            # ========================================
            if CORE_MODULES_AVAILABLE and self.daily_loss_tracker and self.user_id:
                if not self.daily_loss_tracker.can_open_new_trade(self.user_id):
                    status = self.daily_loss_tracker.get_status(self.user_id)
                    logger.warning(
                        f"🚫 Daily loss limit reached! "
                        f"Daily P&L: ${status.get('daily_pnl', 0):.2f} ({status.get('daily_pnl_pct', 0):.2f}%) | "
                        f"Consecutive losses: {status.get('consecutive_losses', 0)} | "
                        f"Is paused: {status.get('is_paused', False)}"
                    )
                    return
            
            # ========================================
            # NEW v2.0: Rate Limiter - Start of Cycle
            # ========================================
            if self.rate_limiter and self.user_id:
                self.rate_limiter.start_cycle(self.user_id)
                metrics = self.rate_limiter.get_metrics(self.user_id)
                logger.info(
                    f"📊 Rate Limiter: {metrics['trades_today']}/{metrics['max_trades_per_day']} today, "
                    f"{metrics['trades_this_hour']}/{metrics['max_trades_per_hour']} this hour, "
                    f"positions: {metrics['current_positions']}"
                )
            
            # ========================================
            # NEW v2.0: Market Intelligence - Kill Switch Check
            # ========================================
            if self.market_intelligence:
                should_kill, kill_reason = await self.market_intelligence.should_kill_switch()
                if should_kill:
                    logger.critical(f"🚨 KILL SWITCH ACTIVATED: {kill_reason}")
                    logger.critical("Skipping trading cycle due to extreme market conditions")
                    return
                
                # Log market sentiment
                sentiment = await self.market_intelligence.get_market_sentiment()
                logger.info(
                    f"📈 Market Sentiment: Fear & Greed = {sentiment.fear_greed_index} ({sentiment.fear_greed_label}) | "
                    f"Regime: {sentiment.regime.value} | "
                    f"Safe to trade: {'✅' if sentiment.is_safe_to_trade else '⚠️'}"
                )
                if sentiment.warnings:
                    for warning in sentiment.warnings:
                        logger.warning(f"  {warning}")
            
            # Manage Capital & Select Quote Currency
            quote_currency = await self.manage_capital()
            
            # ========================================
            # FIRST: Get symbols from trading_signals table!
            # ========================================
            logger.info("📊 Checking trading_signals table for active signals...")
            
            # P1-NEW-5: Pass exchange_id for filtering
            current_exchange_id = self.exchange.exchange.id if hasattr(self.exchange, 'exchange') else None
            db_signals = self.get_signals_from_database(
                quote_currency=quote_currency,
                exchange_id=current_exchange_id
            )
            
            # ========================================
            # NEW v2.0: Signal Deduplicator - Prefer newest signals
            # ========================================
            if db_signals and self.signal_deduplicator and self.user_id:
                dedup_result = self.signal_deduplicator.deduplicate_signals(
                    user_id=self.user_id,
                    signals=db_signals
                )
                db_signals = dedup_result.unique_signals
                if dedup_result.duplicates_removed > 0 or dedup_result.stale_removed > 0:
                    logger.info(
                        f"🔍 Deduplication: {dedup_result.duplicates_removed} duplicates removed, "
                        f"{dedup_result.stale_removed} stale removed, "
                        f"{dedup_result.upgraded_signals} upgraded | "
                        f"{len(db_signals)} signals remaining"
                    )
            
            if db_signals:
                # Use ONLY symbols from trading_signals
                signal_symbols = list(set([sig['symbol'] for sig in db_signals]))
                logger.info(f"✅ Found {len(db_signals)} signals for {len(signal_symbols)} symbols from DB: {signal_symbols}")
                active_symbols = signal_symbols
            else:
                # Fallback: use default symbols if no signals in DB
                logger.warning("⚠️ No signals in trading_signals table, using default symbols")
                active_symbols = []
                for symbol in self.trade_symbols:
                    base = symbol.split('/')[0]
                    active_symbols.append(f"{base}/{quote_currency}")
            
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
            
            # ========== UPDATE VOLATILITY MODE for Signal Validator ==========
            if self.signal_validator and self.risk_manager_service:
                try:
                    vol_profile = await self.risk_manager_service.get_volatility_profile("BTC/USDT")
                    if vol_profile:
                        if vol_profile.is_high_volatility:
                            self.signal_validator.set_volatility_mode('high')
                        elif vol_profile.is_low_volatility:
                            self.signal_validator.set_volatility_mode('low')
                        else:
                            self.signal_validator.set_volatility_mode('normal')
                except Exception as ve:
                    logger.debug(f"Could not update volatility mode: {ve}")
            
            # Update engine with real market data
            self.trading_engine.get_mock_market_data = lambda: market_data
            
            # Get AI analysis (pass existing market data to avoid duplicate fetch)
            logger.info("Running AI market analysis...")
            ai_analysis = await self.execute_ai_analysis(existing_market_data=market_data)
            if ai_analysis:
                logger.info(f"✅ AI analysis completed - {len(ai_analysis)} actionable signals")
                # Update AI Strategy with new signals
                if self.ai_strategy:
                    self.ai_strategy.update_signals(ai_analysis)
            else:
                # FALLBACK: Use built-in strategies when no AI signals
                logger.info("⚠️ No AI signals - using built-in strategies (Momentum/MeanReversion)")
            
            # Execute trading strategies
            logger.info("Executing trading strategies...")
            # Ensure strategies know about the new symbols
            for strategy in self.trading_engine.strategies:
                strategy.symbols = active_symbols
            
            # Also update the trading engine's symbols
            self.trading_engine.symbols = active_symbols
                
            # Pass market_data to avoid duplicate API calls
            signals = await self.trading_engine.run_cycle(external_market_data=market_data)
            
            # ========================================
            # NEW v3.0: Filter signals with core modules
            # ========================================
            if signals and CORE_MODULES_AVAILABLE:
                filtered_signals = []
                
                for signal in signals:
                    symbol = signal.symbol
                    action = signal.action
                    
                    # ========================================
                    # NEW v3.1: PRE-TRADE RISK CHECK (VaR, Multi-TF, Session, Sharpe)
                    # ========================================
                    if self.risk_manager_service:
                        try:
                            # Get portfolio value for VaR calculation
                            portfolio_value = 0
                            try:
                                balance = await self.exchange.get_all_balances()
                                portfolio_value = sum(v for v in balance.values() if isinstance(v, (int, float)))
                            except:
                                portfolio_value = 10000  # Fallback
                            
                            # Estimate position size
                            position_size = signal.quantity * signal.price if hasattr(signal, 'price') and signal.price else 100
                            signal_direction = 'long' if action.lower() == 'buy' else 'short'
                            
                            # Run comprehensive pre-trade check
                            risk_check = await self.risk_manager_service.pre_trade_risk_check(
                                symbol=symbol,
                                signal_direction=signal_direction,
                                position_size_usd=position_size,
                                portfolio_value=portfolio_value,
                                user_id=self.user_id
                            )
                            
                            if not risk_check['can_trade']:
                                logger.warning(
                                    f"🚫 Signal {action} {symbol} blocked by pre-trade risk check: "
                                    f"{', '.join(risk_check['blockers'])}"
                                )
                                continue
                            
                            # Apply size adjustment from risk check
                            if risk_check['size_multiplier'] < 1.0:
                                original_qty = signal.quantity
                                signal.quantity = signal.quantity * risk_check['size_multiplier']
                                logger.info(
                                    f"📉 Position size adjusted by risk check: "
                                    f"{original_qty:.4f} → {signal.quantity:.4f} "
                                    f"(mult: {risk_check['size_multiplier']:.2f})"
                                )
                            
                            # Log warnings
                            for warning in risk_check.get('warnings', []):
                                logger.warning(f"⚠️ Risk warning for {symbol}: {warning}")
                                
                        except Exception as risk_err:
                            logger.warning(f"Pre-trade risk check failed (proceeding): {risk_err}")
                    
                    # 1. Check correlation limit
                    if self.correlation_manager:
                        can_add, reason = self.correlation_manager.check_correlation_limit(
                            symbol=symbol,
                            side='long' if action.lower() == 'buy' else 'short',
                            proposed_value_usd=signal.quantity * signal.price if hasattr(signal, 'price') else 100
                        )
                        if not can_add:
                            logger.warning(f"🚫 Signal {action} {symbol} blocked by correlation manager: {reason}")
                            continue
                    
                    # 2. Apply regime-based position sizing
                    if self.regime_sizer and self.market_intelligence:
                        try:
                            sentiment = await self.market_intelligence.get_market_sentiment()
                            indicators = RegimeIndicators(
                                volatility_percentile=sentiment.volatility_percentile if hasattr(sentiment, 'volatility_percentile') else 50,
                                trend_direction=1 if sentiment.fear_greed_index > 50 else -1,
                                trend_strength=abs(sentiment.fear_greed_index - 50) * 2,
                                fear_greed_index=sentiment.fear_greed_index,
                                correlation_with_btc=0.8,  # Default high for alts
                                volume_percentile=50
                            )
                            size_mult = self.regime_sizer.get_size_multiplier(
                                indicators=indicators,
                                signal_direction='long' if action.lower() == 'buy' else 'short'
                            )
                            
                            # Adjust signal quantity
                            original_qty = signal.quantity
                            signal.quantity = signal.quantity * size_mult.final_multiplier
                            
                            if size_mult.final_multiplier < 0.8:
                                logger.info(
                                    f"📉 Position size reduced for {symbol}: "
                                    f"{original_qty:.4f} → {signal.quantity:.4f} "
                                    f"(multiplier: {size_mult.final_multiplier:.2f})"
                                )
                        except Exception as e:
                            logger.debug(f"Regime sizing failed for {symbol}: {e}")
                    
                    # 3. Normalize symbol format
                    if self.symbol_normalizer:
                        normalized = self.symbol_normalizer.normalize(symbol)
                        signal.symbol = normalized.internal
                    
                    filtered_signals.append(signal)
                
                signals = filtered_signals
                logger.info(f"✅ After core module filtering: {len(signals)} signals remain")
            
            if signals:
                logger.info(f"Generated {len(signals)} trading signals")
                for signal in signals:
                    logger.info(f"Signal: {signal.action} {signal.quantity} {signal.symbol} "
                              f"@ {signal.order_type} - {signal.reason}")
            else:
                logger.info("No trading signals generated this cycle")
                
            # Log account status - check USDC and USDT
            try:
                balance = await self.exchange.get_all_balances()
                positions = await self.exchange.get_positions()
                
                # Get balance in preferred quote currency
                usdc_balance = balance.get('USDC', 0) if isinstance(balance, dict) else 0
                usdt_balance = balance.get('USDT', 0) if isinstance(balance, dict) else 0
                total_balance = usdc_balance + usdt_balance
                
                quote_currency = "USDC" if usdc_balance > usdt_balance else "USDT"
                display_balance = usdc_balance if usdc_balance > usdt_balance else usdt_balance
                
                logger.info(f"Account Balance: {display_balance:.2f} {quote_currency} | Open Positions: {len(positions)}")
            except Exception as e:
                logger.warning(f"Could not fetch account info: {e}")
            
        except Exception as e:
            logger.error(f"Trading cycle error: {e}", exc_info=True)
    
    async def _calculate_adaptive_interval(self) -> int:
        """
        Calculate adaptive trading interval based on market conditions.
        Returns interval in seconds.
        
        Rules:
        - High volatility: 60-120s (more frequent checks)
        - Open positions: 180-300s (moderate monitoring)
        - Normal conditions: 600-900s (relaxed)
        - No signals/quiet market: 1800s (very relaxed)
        """
        base_interval = 300  # 5 minutes default
        
        try:
            # Check if we have open positions
            positions = await self.exchange.get_positions() if self.exchange else []
            has_positions = len(positions) > 0
            
            # Check volatility (if risk_manager available)
            is_high_volatility = False
            if self.risk_manager_service:
                try:
                    # Get volatility for BTC as market proxy
                    volatility_data = await self.risk_manager_service.get_volatility_assessment("BTC/USDT")
                    if volatility_data and volatility_data.get('is_high_volatility'):
                        is_high_volatility = True
                except:
                    pass
            
            # Determine interval based on conditions
            if is_high_volatility:
                interval = 60  # 1 minute during high volatility
                reason = "high volatility"
            elif has_positions:
                interval = 180  # 3 minutes with open positions
                reason = f"{len(positions)} open positions"
            else:
                interval = 600  # 10 minutes when idle
                reason = "no positions, normal conditions"
            
            # Log if interval changed significantly
            if abs(interval - self.trading_interval) > 60:
                logger.info(f"📊 Adaptive interval: {interval}s ({reason})")
            
            return interval
            
        except Exception as e:
            logger.debug(f"Adaptive interval calculation failed: {e}")
            return base_interval
    
    async def _log_upcoming_economic_events(self):
        """Log upcoming economic events at bot startup."""
        try:
            from bot.services.economic_calendar import get_economic_calendar
            
            calendar = get_economic_calendar()
            events = calendar.get_high_impact_events_this_week()
            
            if events:
                logger.info("📅 HIGH-IMPACT ECONOMIC EVENTS THIS WEEK:")
                for event in events[:5]:  # Show max 5 events
                    logger.info(f"   🔴 {event.name}: {event.datetime_utc.strftime('%Y-%m-%d %H:%M UTC')}")
                
                # Check for imminent events (next 60 min)
                from bot.services.economic_calendar import get_upcoming_economic_event
                imminent = await get_upcoming_economic_event(minutes_ahead=60)
                if imminent:
                    name, minutes = imminent
                    logger.warning(f"⚠️ IMMINENT EVENT: {name} in {minutes:.0f} minutes!")
            else:
                logger.info("📅 No high-impact economic events this week")
                
        except Exception as e:
            logger.debug(f"Could not load economic calendar: {e}")
    
    async def run_forever(self):
        """Run the bot forever with ADAPTIVE INTERVAL"""
        self.running = True
        logger.info(f"Bot started - initial interval: {self.trading_interval} seconds (adaptive enabled)")
        
        # Log upcoming economic events at startup
        await self._log_upcoming_economic_events()
        
        while self.running:
            try:
                await self.trading_cycle()
                
                # Calculate adaptive interval for next cycle
                adaptive_interval = await self._calculate_adaptive_interval()
                
                logger.info(f"💤 Next cycle in {adaptive_interval}s...")
                await asyncio.sleep(adaptive_interval)
                
            except asyncio.CancelledError:
                break
            except AuthenticationError as e:
                logger.critical(f"🛑 Authentication failed: {e}. Stopping bot for this user.")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retry
    
    async def _on_sl_triggered(self, position, price: float):
        """Callback when stop loss is triggered by Position Monitor."""
        logger.warning(f"🛑 SL triggered for {position.symbol} @ {price}")
        
        # Calculate P&L for daily loss tracking
        pnl = 0.0
        if position.side == 'long':
            pnl = (price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - price) * position.quantity
        
        # NEW v3.0: Record loss in Daily Loss Tracker
        if CORE_MODULES_AVAILABLE and self.daily_loss_tracker and self.user_id:
            self.daily_loss_tracker.record_trade(
                user_id=self.user_id,
                pnl=pnl,
                is_win=False  # SL = loss
            )
            logger.info(f"📊 Recorded SL loss: ${pnl:.2f} for daily tracking")
        
        # NEW v3.0: Update correlation manager (remove closed position)
        if CORE_MODULES_AVAILABLE and self.correlation_manager:
            self.correlation_manager.remove_position(position.symbol)
        
        # Save to database - GAP-2 FIX: Include SL/TP/leverage/entry/exit
        if self.db_manager:
            try:
                with self.db_manager as db:
                    db.save_trade(
                        user_id=self.user_id,
                        symbol=position.symbol,
                        trade_type="sell",  # SL = closing a long position = sell
                        price=price,
                        amount=position.quantity,
                        pnl=pnl,  # GAP-2 FIX: Include calculated PnL
                        source="position_monitor",  # GAP-2 FIX: More specific source
                        emotion="🛑 Stop loss triggered automatically",
                        exchange=self.exchange_name,
                        # GAP-2 FIX: Include SL/TP/leverage data for analytics
                        stop_loss=position.stop_loss,
                        take_profit=position.take_profit,
                        entry_price=position.entry_price,
                        exit_price=price,
                        leverage=getattr(position, 'leverage', 1.0)
                    )
            except Exception as e:
                logger.error(f"Failed to save SL trigger to DB: {e}")
    
    async def _on_tp_triggered(self, position, price: float):
        """Callback when take profit is triggered by Position Monitor."""
        logger.info(f"✅ TP triggered for {position.symbol} @ {price}")
        
        # Calculate P&L
        pnl = 0.0
        if position.side == 'long':
            pnl = (price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - price) * position.quantity
        
        # NEW v3.0: Record win in Daily Loss Tracker
        if CORE_MODULES_AVAILABLE and self.daily_loss_tracker and self.user_id:
            self.daily_loss_tracker.record_trade(
                user_id=self.user_id,
                pnl=pnl,
                is_win=True  # TP = win
            )
            logger.info(f"📊 Recorded TP profit: ${pnl:.2f} for daily tracking")
        
        # NEW v3.0: Update correlation manager (remove closed position)
        if CORE_MODULES_AVAILABLE and self.correlation_manager:
            self.correlation_manager.remove_position(position.symbol)
        
        # Save to database - GAP-2 FIX: Include SL/TP/leverage/entry/exit
        if self.db_manager:
            try:
                with self.db_manager as db:
                    db.save_trade(
                        user_id=self.user_id,
                        symbol=position.symbol,
                        trade_type="sell",  # TP = closing a long position = sell
                        price=price,
                        amount=position.quantity,
                        pnl=pnl,  # GAP-2 FIX: Include calculated PnL
                        source="position_monitor",  # GAP-2 FIX: More specific source
                        emotion="✅ Take profit triggered automatically",
                        exchange=self.exchange_name,
                        # GAP-2 FIX: Include SL/TP/leverage data for analytics
                        stop_loss=position.stop_loss,
                        take_profit=position.take_profit,
                        entry_price=position.entry_price,
                        exit_price=price,
                        leverage=getattr(position, 'leverage', 1.0)
                    )
            except Exception as e:
                logger.error(f"Failed to save TP trigger to DB: {e}")
    
    async def _on_partial_tp_triggered(self, position, price: float, quantity: float, level_index: int):
        """Callback when partial take profit is triggered by Position Monitor."""
        logger.info(f"🎯 Partial TP (Level {level_index + 1}) triggered for {position.symbol} @ {price} | Qty: {quantity}")
        
        # Calculate partial PnL
        pnl = 0.0
        if position.side == 'long':
            pnl = (price - position.entry_price) * quantity
        else:
            pnl = (position.entry_price - price) * quantity
        
        # Save to database - GAP-2 FIX: Include SL/TP/leverage/entry/exit
        if self.db_manager:
            try:
                with self.db_manager as db:
                    db.save_trade(
                        user_id=self.user_id,
                        symbol=position.symbol,
                        trade_type="sell",  # Partial TP = partial sell
                        price=price,
                        amount=quantity,
                        pnl=pnl,  # GAP-2 FIX: Include partial PnL
                        source="position_monitor",  # GAP-2 FIX: More specific source
                        emotion=f"🎯 Partial take profit level {level_index + 1}",
                        exchange=self.exchange_name,
                        # GAP-2 FIX: Include SL/TP/leverage data
                        stop_loss=position.stop_loss,
                        take_profit=position.take_profit,
                        entry_price=position.entry_price,
                        exit_price=price,
                        leverage=getattr(position, 'leverage', 1.0)
                    )
            except Exception as e:
                logger.error(f"Failed to save Partial TP trigger to DB: {e}")
    
    async def _on_time_exit_triggered(self, position, price: float):
        """Callback when time-based exit is triggered by Position Monitor."""
        # Calculate P&L
        pnl = 0.0
        if position.side == 'long':
            pnl = (price - position.entry_price) * position.quantity
            pnl_percent = ((price - position.entry_price) / position.entry_price) * 100
        else:
            pnl = (position.entry_price - price) * position.quantity
            pnl_percent = ((position.entry_price - price) / position.entry_price) * 100
        
        logger.warning(
            f"⏰ Time Exit triggered for {position.symbol} @ {price} | "
            f"P&L: {pnl_percent:+.2f}%"
        )
        
        # Save to database - GAP-2 FIX: Include SL/TP/leverage/entry/exit
        if self.db_manager:
            try:
                with self.db_manager as db:
                    db.save_trade(
                        user_id=self.user_id,
                        symbol=position.symbol,
                        trade_type="sell",  # Time exit = closing position = sell
                        price=price,
                        amount=position.quantity,
                        pnl=pnl,  # GAP-2 FIX: Include PnL
                        source="position_monitor",  # GAP-2 FIX: More specific source
                        emotion=f"⏰ Time exit | P&L: {pnl_percent:+.2f}%",
                        exchange=self.exchange_name,
                        # GAP-2 FIX: Include SL/TP/leverage data
                        stop_loss=position.stop_loss,
                        take_profit=position.take_profit,
                        entry_price=position.entry_price,
                        exit_price=price,
                        leverage=getattr(position, 'leverage', 1.0)
                    )
            except Exception as e:
                logger.error(f"Failed to save Time Exit to DB: {e}")
    
    async def _load_api_keys_from_db(self):
        """
        Load API keys from database for the current user_id.
        Uses the api_keys table with encrypted credentials.
        """
        if not self.user_id:
            logger.warning("No user_id provided, cannot load API keys from database")
            return
        
        try:
            from sqlalchemy import create_engine, text
            from bot.security import SecurityManager
            
            DATABASE_URL = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
            logger.debug(f"🔍 DATABASE_URL: {DATABASE_URL[:40] if DATABASE_URL else 'NOT SET'}...")
            
            if not DATABASE_URL:
                logger.error("No DATABASE_URL configured for loading API keys")
                return
            
            if "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
                DATABASE_URL += "?sslmode=require"
            
            engine = create_engine(DATABASE_URL)
            
            # FIX 2025-12-14: Load ENCRYPTION_KEY from environment
            encryption_key = os.getenv("ENCRYPTION_KEY")
            security_manager = SecurityManager(encryption_key)
            
            logger.info(f"🔍 Querying api_keys for user_id={self.user_id}")
            
            with engine.connect() as conn:
                # FIX 2025-12-14: Only filter by exchange if explicitly provided via CLI (--exchange)
                # Don't use default EXCHANGE_NAME from .env as filter when loading from DB
                cli_exchange_filter = self.exchange_name if self.exchange_name and os.getenv("EXCHANGE_NAME") != self.exchange_name else None
                
                if cli_exchange_filter:
                    logger.info(f"   Using CLI exchange filter: {cli_exchange_filter}")
                    query = text("""
                        SELECT encrypted_api_key, encrypted_api_secret, exchange, is_testnet 
                        FROM api_keys 
                        WHERE user_id = :user_id AND exchange = :exchange AND is_active = true
                        ORDER BY created_at ASC
                        LIMIT 1
                    """)
                    result = conn.execute(query, {"user_id": self.user_id, "exchange": cli_exchange_filter}).fetchone()
                else:
                    logger.info(f"   No exchange filter, querying first active key for user")
                    query = text("""
                        SELECT encrypted_api_key, encrypted_api_secret, exchange, is_testnet 
                        FROM api_keys 
                        WHERE user_id = :user_id AND is_active = true
                        ORDER BY created_at ASC
                        LIMIT 1
                    """)
                    result = conn.execute(query, {"user_id": self.user_id}).fetchone()
                
                logger.info(f"   Query result: {'FOUND' if result else 'NOT FOUND'}")
                
                if result:
                    self.api_key = security_manager.decrypt(result.encrypted_api_key)
                    self.api_secret = security_manager.decrypt(result.encrypted_api_secret)
                    self.exchange_name = result.exchange
                    self.testnet = result.is_testnet if result.is_testnet is not None else False
                    
                    # Set futures/margin mode based on exchange and CLI args
                    if self.exchange_name in ['kraken']:
                        self.futures = True  # Kraken uses futures for margin
                    elif self.exchange_name == 'binance':
                        # Binance: Respect --margin flag from CLI, otherwise use SPOT
                        self.futures = False  # No futures for Binance
                        if self.margin:
                            logger.info(f"📊 Binance: Using MARGIN mode (--margin flag enabled)")
                        else:
                            logger.info(f"📊 Binance: Using SPOT mode (futures disabled)")
                    
                    logger.info(f"✅ Loaded API keys for user {self.user_id[:8]}... | Exchange: {self.exchange_name} | Testnet: {self.testnet}")
                    
                    # ========================================
                    # NEW v2.5: Validate API keys after loading
                    # ========================================
                    await self._validate_api_keys()
                    
                else:
                    logger.error(f"No API keys found in database for user {self.user_id}")
                    
        except Exception as e:
            logger.error(f"Failed to load API keys from database: {e}")
    
    async def _validate_api_keys(self):
        """
        NEW v2.5: Validate API keys by testing connection to exchange.
        
        Catches invalid/expired/revoked API keys BEFORE starting the trading loop.
        """
        if not self.api_key or not self.api_secret:
            logger.warning("Cannot validate API keys - keys not loaded")
            return
        
        try:
            from bot.exchange_adapters.ccxt_adapter import CCXTAdapter
            
            logger.info(f"🔑 Validating API keys for {self.exchange_name}...")
            
            # Create temporary adapter for validation
            test_adapter = CCXTAdapter(
                exchange_name=self.exchange_name,
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet,
                futures=self.futures,
                margin=self.margin
            )
            
            try:
                # Try to fetch balance - this will fail if keys are invalid
                # Use internal exchange object to get proper error
                if hasattr(test_adapter, 'exchange'):
                    balance_raw = await test_adapter.exchange.fetch_balance()
                    balance = {k: v for k, v in balance_raw['total'].items() if v > 0}
                else:
                    balance = await test_adapter.get_all_balances()
                
                if balance:
                    total_balance = sum(balance.values()) if isinstance(balance, dict) else 0
                    logger.info(
                        f"✅ API keys VALID for {self.exchange_name} | "
                        f"User: {self.user_id[:8]}... | "
                        f"Balance: {len(balance)} currencies (total: {total_balance:.2f})"
                    )
                else:
                    logger.info(f"✅ API keys VALID for {self.exchange_name} (empty balance)")
                    
            except AuthenticationError as auth_err:
                error_msg = str(auth_err).lower()
                
                # Check specific error types
                if "invalid api-key" in error_msg or "invalid api key" in error_msg:
                    logger.error(
                        f"❌ INVALID API KEY for {self.exchange_name} | User: {self.user_id[:8]}... | "
                        f"The API key does not exist or is incorrectly formatted."
                    )
                elif "signature" in error_msg:
                    logger.error(
                        f"❌ INVALID API SECRET for {self.exchange_name} | User: {self.user_id[:8]}... | "
                        f"The API secret is incorrect or has been changed."
                    )
                elif "permission" in error_msg or "restrict" in error_msg:
                    logger.error(
                        f"❌ API KEY PERMISSION ERROR for {self.exchange_name} | User: {self.user_id[:8]}... | "
                        f"The API key may not have trading permissions enabled."
                    )
                elif "expired" in error_msg:
                    logger.error(
                        f"❌ API KEY EXPIRED for {self.exchange_name} | User: {self.user_id[:8]}... | "
                        f"The API key has expired and needs to be renewed."
                    )
                else:
                    logger.error(
                        f"❌ API KEY AUTHENTICATION FAILED for {self.exchange_name} | "
                        f"User: {self.user_id[:8]}... | Error: {auth_err}"
                    )
                
                # Clear invalid keys to prevent trading attempts
                self.api_key = None
                self.api_secret = None
                raise ValueError(f"Invalid API keys for {self.exchange_name}: {auth_err}")
            
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check if it's an API key error disguised as ExchangeError
                if "invalid api-key" in error_msg or "code\":-2015" in error_msg or "-2008" in error_msg:
                    logger.error(
                        f"❌ INVALID API KEY for {self.exchange_name} | User: {self.user_id[:8]}... | "
                        f"API key invalid or restricted. Error: {e}"
                    )
                    self.api_key = None
                    self.api_secret = None
                    raise ValueError(f"Invalid API keys for {self.exchange_name}: {e}")
                elif "permission" in error_msg or "ip" in error_msg:
                    logger.error(
                        f"❌ API KEY IP/PERMISSION ERROR for {self.exchange_name} | User: {self.user_id[:8]}... | "
                        f"API key may be IP restricted or missing permissions. Error: {e}"
                    )
                    self.api_key = None
                    self.api_secret = None
                    raise ValueError(f"API key restricted for {self.exchange_name}: {e}")
                else:
                    # Network errors etc - don't clear keys, might be temporary
                    logger.warning(
                        f"⚠️ Could not validate API keys (may be temporary): {e}"
                    )
            finally:
                await test_adapter.close()
                
        except ImportError:
            logger.warning("Could not import CCXTAdapter for key validation")
        except ValueError:
            # Re-raise ValueError (invalid keys) to stop bot
            raise
        except Exception as e:
            logger.warning(f"API key validation error (non-fatal): {e}")
    
    def _load_user_risk_settings(self) -> Optional['UserRiskSettings']:
        """
        Load user-specific risk settings from TradingSettings table using SQLAlchemy.
        
        Returns:
            UserRiskSettings object or None if no settings found
        """
        if not self.user_id:
            logger.debug("No user_id available, cannot load user risk settings")
            return None
        
        try:
            from bot.db import DatabaseManager
            from sqlalchemy import text
            
            with DatabaseManager.session_scope() as session:
                # Query trading_settings table directly via raw SQL for flexibility
                result = session.execute(
                    text("""
                        SELECT 
                            risk_level,
                            max_position_size,
                            max_daily_loss,
                            stop_loss_percentage,
                            take_profit_percentage
                        FROM trading_settings 
                        WHERE user_id = :user_id
                        LIMIT 1
                    """),
                    {"user_id": self.user_id}
                ).fetchone()
                
                if result:
                    # Create TradingSettings-like object from result
                    class SettingsProxy:
                        def __init__(self, row):
                            self.risk_level = row[0] or 3
                            self.max_position_size = float(row[1] or 1000)
                            self.max_daily_loss = float(row[2] or 100)
                            self.stop_loss_percentage = float(row[3] or 5.0)
                            self.take_profit_percentage = float(row[4] or 3.0)  # Default TP=3%
                    
                    settings_proxy = SettingsProxy(result)
                    user_settings = UserRiskSettings.from_trading_settings(settings_proxy, self.user_id)
                    
                    logger.info(
                        f"📋 Loaded user risk settings for {self.user_id[:8]}... | "
                        f"Risk Level: {user_settings.risk_level}/5 | "
                        f"Risk Per Trade: {user_settings.risk_per_trade_percent}% | "
                        f"Max Position: ${user_settings.max_position_size:.0f} | "
                        f"SL: {user_settings.stop_loss_percentage}% | TP: {user_settings.take_profit_percentage}%"
                    )
                    
                    return user_settings
                else:
                    logger.info(f"No trading settings found for user {self.user_id[:8]}..., using defaults")
                    return None
                
        except Exception as e:
            logger.warning(f"Failed to load user risk settings: {e}")
            return None
    
    async def shutdown(self):
        """
        Graceful shutdown with complete resource cleanup.
        
        L2 FIX: Added cleanup for:
        - EconomicCalendarService (aiohttp session)
        - Risk Manager service
        - Database manager
        - Any orphaned aiohttp sessions
        """
        logger.info("Shutting down bot...")
        self.running = False
        
        # Stop position monitor
        if self.position_monitor:
            await self.position_monitor.stop()
            logger.info("Position monitor stopped")
        
        # Disconnect WebSocket
        if self.ws_manager:
            await self.ws_manager.disconnect()
            logger.info("WebSocket disconnected")
        
        # L2 FIX: Close Economic Calendar Service (aiohttp session)
        if hasattr(self, 'economic_calendar') and self.economic_calendar:
            try:
                await self.economic_calendar.close()
                logger.info("Economic calendar service closed")
            except Exception as e:
                logger.warning(f"Error closing economic calendar: {e}")
        
        # L2 FIX: Close Risk Manager if it has cleanup methods
        if hasattr(self, 'risk_manager_service') and self.risk_manager_service:
            try:
                if hasattr(self.risk_manager_service, 'close'):
                    await self.risk_manager_service.close()
                    logger.info("Risk manager service closed")
            except Exception as e:
                logger.warning(f"Error closing risk manager: {e}")
        
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
        
        # L2 FIX: Close any remaining aiohttp sessions from this module
        try:
            import gc
            import aiohttp
            for obj in gc.get_objects():
                if isinstance(obj, aiohttp.ClientSession) and not obj.closed:
                    try:
                        await obj.close()
                    except Exception:
                        pass  # Best effort cleanup
        except Exception as e:
            logger.debug(f"Error during aiohttp session cleanup: {e}")
        
        logger.info("Bot shutdown complete")


async def main():
    """Main entry point"""
    import argparse
    parser = argparse.ArgumentParser(description='ASE Trading Bot')
    parser.add_argument('--user-id', type=str, help='User ID to load API keys from database')
    parser.add_argument('--exchange', type=str, help='Exchange name (e.g., binance, kraken)')
    parser.add_argument('--test-mode', action='store_true', help='Run in test mode (no real trades)')
    parser.add_argument('--futures', action='store_true', help='Enable futures trading')
    parser.add_argument('--margin', action='store_true', help='Enable margin trading (for Binance without Futures)')
    args = parser.parse_args()
    
    logger.info(f"Starting bot with user_id={args.user_id}, exchange={args.exchange}, test_mode={args.test_mode}, margin={args.margin}")
    
    bot = AutomatedTradingBot(
        user_id=args.user_id,
        exchange_name=args.exchange,
        test_mode=args.test_mode,
        futures=args.futures,
        margin=args.margin
    )
    
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
