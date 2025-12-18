# Core modules for trading bot
"""
Core module for trading bot infrastructure.

Contains:
- Symbol normalization
- Transaction management with retry logic
- Position locking (mutex)
- Rate limiting (per-component)
- Daily loss tracking
- Correlation management
- Spread-aware P&L calculations
- Market regime position sizing
"""

from .symbol_normalizer import SymbolNormalizer, normalize_symbol, to_exchange_format
from .transaction_manager import TransactionManager, atomic_trade_operation
from .position_lock import PositionLockManager, position_lock
from .rate_limiter_v2 import ComponentRateLimiter, RateLimitExceeded
from .daily_loss_tracker import DailyLossTracker
from .correlation_manager import CorrelationManager
from .spread_calculator import (
    SpreadAwarePnL, 
    SpreadData, 
    FeeStructure, 
    PnLResult,
    get_spread_aware_pnl
)
from .market_regime_sizer import (
    MarketRegimeSizer,
    MarketRegimeDetector,
    MarketRegime,
    TrendStrength,
    RegimeIndicators,
    PositionSizeMultiplier,
    get_regime_sizer
)
from .retry_handler import RetryHandler, with_retry
from .db_timeout import (
    DBTimeoutError,
    db_operation_with_timeout,
    db_timeout,
    with_db_timeout,
    async_db_timeout,
    safe_db_query,
    shutdown_timeout_executor,
    DEFAULT_DB_TIMEOUT,
    DEFAULT_DB_TIMEOUT_SHORT
)

__all__ = [
    # Symbol Normalizer
    'SymbolNormalizer',
    'normalize_symbol', 
    'to_exchange_format',
    
    # Transaction Manager
    'TransactionManager',
    'atomic_trade_operation',
    
    # Position Locks
    'PositionLockManager',
    'position_lock',
    
    # Rate Limiting
    'ComponentRateLimiter',
    'RateLimitExceeded',
    
    # Daily Loss Tracking
    'DailyLossTracker',
    
    # Correlation Management
    'CorrelationManager',
    
    # Spread-Aware P&L
    'SpreadAwarePnL',
    'SpreadData',
    'FeeStructure',
    'PnLResult',
    'get_spread_aware_pnl',
    
    # Market Regime Sizing
    'MarketRegimeSizer',
    'MarketRegimeDetector',
    'MarketRegime',
    'TrendStrength',
    'RegimeIndicators',
    'PositionSizeMultiplier',
    'get_regime_sizer',
    
    # Retry Handler
    'RetryHandler',
    'with_retry',
    
    # DB Timeout
    'DBTimeoutError',
    'db_operation_with_timeout',
    'db_timeout',
    'with_db_timeout',
    'async_db_timeout',
    'safe_db_query',
    'shutdown_timeout_executor',
    'DEFAULT_DB_TIMEOUT',
    'DEFAULT_DB_TIMEOUT_SHORT',
]
