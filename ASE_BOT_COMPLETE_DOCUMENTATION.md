# ASE BOT v4.2 - Complete Technical Documentation

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [System Architecture Overview](#system-architecture-overview)
3. [Core Components Deep Dive](#core-components-deep-dive)
4. [Exchange Adapter Layer](#exchange-adapter-layer)
5. [Position Monitoring System](#position-monitoring-system)
6. [Risk Management Framework](#risk-management-framework)
7. [AI Signal Processing](#ai-signal-processing)
8. [Database Layer](#database-layer)
9. [Monitoring & Diagnostics](#monitoring--diagnostics)
10. [Configuration Reference](#configuration-reference)
11. [Recent Changes & Fixes](#recent-changes--fixes)
12. [Known Issues & Roadmap](#known-issues--roadmap)

---

## Executive Summary

ASE BOT is an advanced automated cryptocurrency trading system designed for multi-user, multi-exchange trading operations. The system leverages AI-powered market analysis, sophisticated risk management, and real-time position monitoring to execute trades autonomously.

### Key Capabilities
- **Multi-Exchange Support**: Binance, Kraken, Bybit, OKX, KuCoin, Gate.io, MEXC, Bitget
- **Trading Modes**: SPOT, MARGIN, and FUTURES trading
- **AI-Powered Signals**: Integration with Supabase Edge Functions for market analysis
- **Advanced Risk Management**: Kelly Criterion, ATR-based sizing, trailing stops
- **Real-Time Monitoring**: Position monitoring every 5 seconds with SL/TP automation
- **Liquidation Protection**: Automatic position closure at critical risk levels
- **Multi-User Architecture**: Simultaneous operation for multiple user accounts

### Version History
- v1.0: Basic automated trading with SL/TP
- v2.0: Enhanced services (rate limiting, signal deduplication, market intelligence)
- v3.0: Core infrastructure (symbol normalization, transaction management, position locking)
- v4.0: Liquidation monitoring and auto-close functionality
- v4.1: Hybrid RAM + Supabase persistence for position data
- v4.2: Account type detection from database, improved position counting

---

## System Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ASE BOT SYSTEM                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐  │
│  │  run_single   │    │  run_multi    │    │   monitor     │  │
│  │   _user.py    │    │   _bots.py    │    │   _group.py   │  │
│  └───────┬───────┘    └───────┬───────┘    └───────┬───────┘  │
│          │                    │                    │           │
│          └────────────────────┼────────────────────┘           │
│                               ▼                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              AutomatedTradingBot (auto_trader.py)        │   │
│  │  - Initialize components                                  │   │
│  │  - Load API keys from database                           │   │
│  │  - Trading loop execution                                │   │
│  │  - Signal processing & trade execution                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                               │                                 │
│          ┌────────────────────┼────────────────────┐           │
│          ▼                    ▼                    ▼           │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐  │
│  │   Exchange    │    │   Position    │    │     Risk      │  │
│  │   Adapter     │    │   Monitor     │    │   Manager     │  │
│  │  (CCXT)       │    │   Service     │    │   Service     │  │
│  └───────────────┘    └───────────────┘    └───────────────┘  │
│          │                    │                    │           │
│          ▼                    ▼                    ▼           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Services Layer                        │   │
│  │  - SupabaseAnalysisService (AI signals)                 │   │
│  │  - SignalValidator (adaptive confidence)                │   │
│  │  - PortfolioManager (exposure limits)                   │   │
│  │  - MarketIntelligence (liquidity, sentiment)            │   │
│  │  - RateLimiter (trade frequency control)                │   │
│  │  - DCAManager (dollar cost averaging)                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                               │                                 │
│          ┌────────────────────┼────────────────────┐           │
│          ▼                    ▼                    ▼           │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐  │
│  │   Supabase    │    │   SQLite      │    │   Exchange    │  │
│  │   (Cloud DB)  │    │   (Local DB)  │    │   APIs        │  │
│  └───────────────┘    └───────────────┘    └───────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Signal Acquisition**: AI signals fetched from Supabase Edge Function
2. **Signal Validation**: Signals validated against historical data and confidence thresholds
3. **Risk Assessment**: Position sizing calculated based on account balance and risk settings
4. **Portfolio Check**: Exposure limits verified before trade execution
5. **Trade Execution**: Order placed through CCXT adapter
6. **Position Monitoring**: Continuous SL/TP monitoring in background
7. **Trade Closure**: Automatic or triggered position closure with P&L logging

---

## Core Components Deep Dive

### 3.1 AutomatedTradingBot (`bot/auto_trader.py`)

The central orchestrator of the entire trading system. This class manages the lifecycle of all trading operations for a single user.

#### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | str | None | Exchange API key (loaded from DB if not provided) |
| `api_secret` | str | None | Exchange API secret |
| `exchange_name` | str | "binance" | Target exchange identifier |
| `user_id` | str | None | User UUID for multi-user operation |
| `test_mode` | bool | False | Enable paper trading mode |
| `futures` | bool | False | Enable futures trading mode |
| `margin` | bool | False | Enable margin trading mode |

#### Initialization Sequence

```python
async def initialize(self):
    """
    Complete initialization sequence:
    
    1. Load environment configuration
    2. Initialize database connections (SQLite + Supabase)
    3. Load API keys from database for user_id
    4. Create exchange adapter (CCXTAdapter)
    5. Start Position Monitor Service
    6. Initialize WebSocket connection (optional)
    7. Initialize AI Analysis Service
    8. Initialize Signal Validator
    9. Initialize Portfolio Manager
    10. Initialize Risk Manager Service
    11. Initialize Enhanced Services (v2.0)
        - Market Intelligence
        - Rate Limiter
        - Signal Deduplicator
    12. Initialize Core Infrastructure (v3.0)
        - Symbol Normalizer
        - Transaction Manager
        - Position Lock Manager
        - Daily Loss Tracker
        - Correlation Manager
        - Market Regime Sizer
        - Spread-Aware P&L Calculator
        - Retry Handler
    13. Initialize DCA Manager (v4.0)
    """
```

#### Main Trading Loop

The bot operates in a continuous loop with configurable intervals:

```python
async def run(self):
    """
    Main trading loop execution:
    
    1. Fetch fresh AI signals from Supabase Edge Function
    2. Filter signals by freshness (< 6 hours old)
    3. Deduplicate signals (prefer newest per symbol)
    4. Validate each signal through SignalValidator
    5. Check rate limits before processing
    6. For each valid signal:
       a. Check position limits
       b. Check portfolio exposure
       c. Calculate position size via Risk Manager
       d. Execute trade through Exchange Adapter
       e. Register position with Position Monitor
    7. Sleep for trading_interval (default: 3600 seconds)
    8. Repeat
    """
```

#### Key Methods

| Method | Description |
|--------|-------------|
| `initialize()` | Full component initialization |
| `run()` | Main trading loop |
| `_load_api_keys_from_db()` | Load encrypted API keys from Supabase |
| `_load_user_risk_settings()` | Load user's risk preferences |
| `check_risk_limits()` | Verify position count against limits |
| `_execute_trade()` | Execute a trade based on signal |
| `_on_sl_triggered()` | Callback for stop loss events |
| `_on_tp_triggered()` | Callback for take profit events |
| `_on_partial_tp_triggered()` | Callback for partial take profit |
| `_on_time_exit_triggered()` | Callback for time-based exit |
| `shutdown()` | Graceful shutdown of all components |

#### Position Counting Logic (FIX 2025-12-16)

The bot now correctly counts positions based on account mode:

```python
async def check_risk_limits(self):
    """
    Mode-aware position counting:
    
    SPOT Mode:
    - Count only spot balances with value > $10
    - Exclude LD* tokens (Binance Launchpad)
    - Exclude stablecoins (USDT, USDC, etc.)
    - Exclude fiat currencies (USD, EUR, etc.)
    
    MARGIN/FUTURES Mode:
    - Count only margin/futures positions
    - Ignore spot holdings entirely
    
    This prevents false "Max positions reached" errors
    that occurred when mixing spot and margin counts.
    """
```

---

## Exchange Adapter Layer

### 4.1 CCXTAdapter (`bot/exchange_adapters/ccxt_adapter.py`)

A universal asynchronous adapter wrapping the CCXT library for multi-exchange support.

#### Supported Exchanges

| Exchange | Identifier | SPOT | MARGIN | FUTURES |
|----------|------------|------|--------|---------|
| Binance | `binance` | ✅ | ✅ | ✅ |
| Kraken | `kraken` | ✅ | ✅ | ❌ |
| Bybit | `bybit` | ✅ | ✅ | ✅ |
| OKX | `okx` | ✅ | ✅ | ✅ |
| KuCoin | `kucoin` | ✅ | ✅ | ✅ |
| Gate.io | `gateio` | ✅ | ✅ | ✅ |
| MEXC | `mexc` | ✅ | ✅ | ✅ |
| Bitget | `bitget` | ✅ | ✅ | ✅ |

#### Constructor

```python
def __init__(
    self, 
    exchange_name: str,      # Exchange identifier
    api_key: str,            # API key
    api_secret: str,         # API secret
    testnet: bool = False,   # Use testnet endpoint
    futures: bool = True,    # Enable futures mode
    margin: bool = False     # Enable margin mode
):
```

#### Core Methods

##### Balance & Position Retrieval

```python
async def get_balance() -> Dict[str, AccountInfo]:
    """
    Fetch account balance for all assets.
    
    Returns:
        Dictionary mapping asset symbols to AccountInfo objects
        containing free, used, and total amounts.
    
    Behavior varies by mode:
    - SPOT: Returns spot wallet balances
    - MARGIN: Returns margin account balances
    - FUTURES: Returns futures wallet balances
    """

async def get_spot_balances(min_value_usd: float = 10.0) -> List[Dict]:
    """
    Get spot balances with value filtering.
    
    FIX 2025-12-16: Enhanced filtering:
    - Excludes LD* tokens (Binance Launchpad staking)
    - Excludes BETH, BFUSD (wrapped/staked tokens)
    - Excludes stablecoins: USDT, USDC, USD, DAI, BUSD, USDG
    - Excludes fiat: EUR, PLN, GBP, CHF
    - Minimum value threshold: $10 (prevents dust counting)
    
    Returns:
        List of asset dictionaries with symbol, amount, and value_usd
    """

async def get_positions() -> List[Position]:
    """
    Fetch open margin/futures positions.
    
    Returns:
        List of Position objects containing:
        - symbol: Trading pair
        - side: 'long' or 'short'
        - quantity: Position size
        - entry_price: Average entry price
        - unrealized_pnl: Current P&L
        - leverage: Position leverage
    """
```

##### Order Execution

```python
async def place_order(
    symbol: str,
    side: str,           # 'buy' or 'sell'
    amount: float,       # Order quantity
    order_type: str,     # 'market', 'limit', 'stop'
    price: float = None, # Required for limit orders
    params: dict = None  # Exchange-specific parameters
) -> Order:
    """
    Place an order on the exchange.
    
    Features:
    - Automatic symbol normalization
    - Rate limit handling with exponential backoff
    - Retry logic for transient failures
    - Order validation before submission
    
    Returns:
        Order object with execution details
    """

async def close_position(
    symbol: str,
    side: str,
    amount: float = None  # None = close entire position
) -> bool:
    """
    Close an open position.
    
    For SPOT:
    - Executes market sell order for the asset
    
    For MARGIN/FUTURES:
    - Places opposite order to close position
    - Handles leverage unwinding
    
    Returns:
        True if position closed successfully
    """
```

##### Market Data

```python
async def get_ticker(symbol: str) -> Dict:
    """
    Get current ticker data for a symbol.
    
    Returns:
        Dictionary containing:
        - last: Last traded price
        - bid: Current best bid
        - ask: Current best ask
        - volume: 24h volume
        - change: 24h price change %
    """

async def get_ohlcv(
    symbol: str,
    timeframe: str = '1h',
    limit: int = 100
) -> List[List]:
    """
    Fetch OHLCV candlestick data.
    
    Used for:
    - Technical analysis (RSI, MACD, etc.)
    - ATR calculation for dynamic SL/TP
    - Market regime detection
    
    Returns:
        List of [timestamp, open, high, low, close, volume]
    """
```

##### Symbol Validation

```python
async def validate_symbol(symbol: str) -> Tuple[bool, Optional[str]]:
    """
    Validate if a symbol is tradeable on this exchange.
    
    Performs:
    1. Load exchange markets if not cached
    2. Direct symbol match check
    3. Normalized symbol match (BTC/USDT variations)
    4. Common transformation attempts
    
    Returns:
        Tuple of (is_valid, error_message)
    """
```

#### Error Handling & Retry Logic

```python
# Retry configuration
MAX_RETRIES = 5
RETRY_DELAY = 1.0  # Base delay (exponential backoff)
REQUEST_TIMEOUT = 30000  # 30 seconds
RATE_LIMIT_WAIT = 60  # Wait time when rate limited

# Automatic retry for:
# - Network timeouts
# - Rate limit errors (429)
# - Temporary exchange errors
# - Connection reset errors
```

---

## Position Monitoring System

### 5.1 PositionMonitorService (`bot/services/position_monitor.py`)

A comprehensive real-time position monitoring system running as a background service.

#### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  PositionMonitorService                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │  Monitor Loop   │  │  Persistence    │                   │
│  │  (5s interval)  │  │  Loop (5s)      │                   │
│  └────────┬────────┘  └────────┬────────┘                   │
│           │                    │                             │
│           ▼                    ▼                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              MonitoredPosition Registry              │    │
│  │         (In-Memory HashMap + Supabase Sync)         │    │
│  └─────────────────────────────────────────────────────┘    │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                Position Checks                       │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │    │
│  │  │   SL    │ │   TP    │ │ Partial │ │  Time   │   │    │
│  │  │  Check  │ │  Check  │ │   TP    │ │  Exit   │   │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │    │
│  │  │Trailing │ │ Break   │ │Momentum │ │  News   │   │    │
│  │  │  Stop   │ │  Even   │ │ Scalp   │ │ Protect │   │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │    │
│  │  ┌─────────┐ ┌─────────┐                           │    │
│  │  │  Quick  │ │ Liquid- │                           │    │
│  │  │  Exit   │ │  ation  │                           │    │
│  │  └─────────┘ └─────────┘                           │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### MonitoredPosition Data Structure

```python
@dataclass
class MonitoredPosition:
    """
    Complete position tracking data structure.
    """
    # Core identification
    symbol: str                    # Trading pair (e.g., "BTC/USDT")
    side: str                      # "long" or "short"
    
    # Position details
    entry_price: float             # Average entry price
    quantity: float                # Position size
    leverage: float = 1.0          # Position leverage
    
    # Stop Loss / Take Profit
    stop_loss: float = None        # SL price level
    take_profit: float = None      # TP price level
    original_stop_loss: float      # Initial SL (before trailing)
    
    # Trailing stop tracking
    trailing_enabled: bool = True
    trailing_distance_pct: float = 2.0
    highest_price: float = None    # For long positions
    lowest_price: float = None     # For short positions
    trailing_activated: bool = False
    
    # Dynamic SL/TP
    dynamic_sl_enabled: bool = True
    leverage_aware_sl_tp: bool = True
    
    # Time-based exit
    max_hold_hours: float = 12.0   # Maximum hold time
    opened_at: datetime = None     # Position open timestamp
    
    # Quick exit (scalping)
    quick_exit_enabled: bool = False
    quick_exit_profit_pct: float = 0.5
    quick_exit_time_minutes: int = 5
    
    # Break-even protection
    break_even_enabled: bool = True
    break_even_trigger_pct: float = 1.5
    break_even_offset_pct: float = 0.1
    break_even_activated: bool = False
    
    # Momentum scalper
    momentum_scalp_enabled: bool = False
    momentum_exit_rsi_threshold: float = 70.0
    
    # News protection
    news_protection_enabled: bool = True
    news_exit_minutes_before: int = 15
    
    # Partial take profit
    partial_tp_executed: List[str] = []  # Levels already executed
    original_quantity: float = None
    
    # Liquidation monitoring (v4.0)
    liquidation_price: float = None
    liquidation_risk_level: str = "safe"
    liquidation_warnings_sent: int = 0
    auto_close_attempted: bool = False
    
    # Manual position flag (v4.2)
    is_manual_position: bool = False
    
    # Metadata
    user_id: str = None
    source: str = "bot"            # "bot", "manual", "sync"
    notes: str = None              # Special handling notes
```

#### Stop Loss / Take Profit Logic

##### Basic SL/TP Check

```python
async def _check_all_positions(self):
    """
    Main position checking routine (runs every 5 seconds).
    
    For each monitored position:
    1. Fetch current price from exchange
    2. Check Stop Loss trigger
    3. Check Take Profit trigger
    4. Apply trailing stop adjustments
    5. Check partial TP levels
    6. Check time-based exit
    7. Check quick exit (scalping)
    8. Check break-even trigger
    9. Check momentum scalp exit
    10. Check news protection exit
    11. Check liquidation risk (v4.0)
    """
```

##### Stop Loss Trigger Logic

```python
def _is_sl_triggered(position: MonitoredPosition, price: float) -> bool:
    """
    Determine if stop loss should trigger.
    
    For LONG positions:
        Trigger if: current_price <= stop_loss
    
    For SHORT positions:
        Trigger if: current_price >= stop_loss
    
    Special handling:
    - Leverage-aware SL considers liquidation distance
    - Manual positions may have SL-only monitoring
    """
```

##### Take Profit Trigger Logic

```python
def _is_tp_triggered(position: MonitoredPosition, price: float) -> bool:
    """
    Determine if take profit should trigger.
    
    For LONG positions:
        Trigger if: current_price >= take_profit
    
    For SHORT positions:
        Trigger if: current_price <= take_profit
    """
```

#### Trailing Stop Implementation

```python
async def _apply_trailing_stop(
    self, 
    key: str, 
    position: MonitoredPosition, 
    current_price: float
):
    """
    Dynamic trailing stop implementation.
    
    Activation Conditions:
    - Position must be in profit
    - Profit must exceed activation threshold (default: 1%)
    
    Trailing Behavior:
    For LONG positions:
        1. Track highest_price seen since entry
        2. If price makes new high, update highest_price
        3. Calculate new SL = highest_price * (1 - trailing_distance_pct)
        4. Only move SL up, never down
    
    For SHORT positions:
        1. Track lowest_price seen since entry
        2. If price makes new low, update lowest_price
        3. Calculate new SL = lowest_price * (1 + trailing_distance_pct)
        4. Only move SL down, never up
    
    ATR-Based Trailing (if enabled):
        - Fetch ATR for symbol
        - trailing_distance = ATR * atr_multiplier
        - More volatile = wider trailing distance
    """
```

#### Partial Take Profit System

```python
async def _check_partial_tp(
    self, 
    key: str, 
    position: MonitoredPosition, 
    current_price: float
):
    """
    Multi-level partial take profit system.
    
    Default Levels:
    - Level 1: Close 30% at 1.5% profit
    - Level 2: Close 50% at 2.5% profit (of remaining)
    - Level 3: Close remaining at full TP
    
    After Each Partial Close:
    - Update position quantity
    - Move SL to break-even (or better)
    - Record level as executed
    
    Benefits:
    - Lock in profits progressively
    - Reduce risk while letting winners run
    - Automatic risk management
    """
```

#### Time-Based Exit

```python
async def _check_time_exit(
    self, 
    key: str, 
    position: MonitoredPosition, 
    current_price: float
):
    """
    Automatic exit after maximum hold time.
    
    Default: 12 hours maximum hold
    
    Logic:
    1. Calculate time_held = now - opened_at
    2. If time_held > max_hold_hours:
       a. If in profit: Close at market
       b. If in loss: Close at market (cut losses)
    
    Configurable per position based on strategy.
    """
```

#### Liquidation Monitoring (v4.0)

```python
async def _check_liquidation_risk_all(self):
    """
    Monitor all positions for liquidation risk.
    
    Risk Levels:
    - SAFE: > 20% distance to liquidation
    - WARNING: 15-20% distance (send alert)
    - HIGH: 10-15% distance (send urgent alert)
    - CRITICAL: 5-10% distance (prepare for auto-close)
    - EXTREME: < 5% distance (auto-close if enabled)
    
    Auto-Close Threshold: 3.5% (configurable)
    
    Actions:
    1. Calculate liquidation price for each position
    2. Calculate distance to liquidation
    3. Determine risk level
    4. Send alerts at WARNING and above
    5. Execute auto-close at EXTREME level
    """

def calculate_liquidation_price(
    self,
    entry_price: float,
    leverage: float,
    side: str,
    maintenance_margin_rate: float = 0.004  # 0.4%
) -> float:
    """
    Calculate theoretical liquidation price.
    
    For LONG:
        liq_price = entry_price * (1 - 1/leverage + maintenance_margin_rate)
    
    For SHORT:
        liq_price = entry_price * (1 + 1/leverage - maintenance_margin_rate)
    
    Note: Actual liquidation may vary by exchange.
    """
```

#### Hybrid Persistence (v4.1)

```python
async def _sync_to_supabase(self, force: bool = False) -> bool:
    """
    Synchronize in-memory positions to Supabase.
    
    Strategy:
    - Primary storage: In-memory (fast access)
    - Backup storage: Supabase (persistence across restarts)
    - Sync interval: 5 seconds (or on significant changes)
    
    On Startup:
    1. Load positions from Supabase
    2. Sync with exchange to detect new positions
    3. Reconcile ghost positions (in DB but not on exchange)
    
    On Position Change:
    1. Update in-memory immediately
    2. Mark as dirty
    3. Sync to Supabase in next persistence loop
    """
```

---

## Risk Management Framework

### 6.1 RiskManagerService (`bot/services/risk_manager.py`)

Comprehensive risk management including position sizing, dynamic SL/TP, and trailing stops.

#### Risk Level Definitions

```python
class RiskLevel(Enum):
    CONSERVATIVE = "conservative"  # 0.5% risk per trade
    MODERATE = "moderate"          # 1.0% risk per trade
    AGGRESSIVE = "aggressive"      # 2.0% risk per trade

# User Risk Level (1-5 scale from database)
# Level 1: 0.25% risk
# Level 2: 0.50% risk
# Level 3: 1.00% risk (default)
# Level 4: 1.50% risk
# Level 5: 2.00% risk
```

#### Position Sizing Algorithms

##### Fixed Fractional

```python
def calculate_position_size_fixed(
    self,
    account_balance: float,
    risk_percent: float,
    entry_price: float,
    stop_loss: float
) -> float:
    """
    Fixed fractional position sizing.
    
    Formula:
        risk_amount = account_balance * (risk_percent / 100)
        price_risk = abs(entry_price - stop_loss) / entry_price
        position_size = risk_amount / (entry_price * price_risk)
    
    Example:
        Balance: $10,000
        Risk: 1%
        Entry: $50,000
        SL: $49,000 (2% below)
        
        Risk amount = $100
        Position size = $100 / ($50,000 * 0.02) = 0.1 BTC
    """
```

##### Kelly Criterion

```python
def calculate_kelly_position_size(
    self,
    win_rate: float,        # Historical win rate (0-1)
    avg_win: float,         # Average winning trade
    avg_loss: float,        # Average losing trade
    account_balance: float
) -> float:
    """
    Kelly Criterion optimal position sizing.
    
    Formula:
        W = win_rate
        R = avg_win / abs(avg_loss)  # Win/Loss ratio
        Kelly% = W - (1-W)/R
    
    Safety Adjustment:
        - Use fractional Kelly (25% of full Kelly)
        - Minimum 10 trades required for reliable stats
        - Fallback to fixed 1% if insufficient data
    
    Benefits:
        - Mathematically optimal growth rate
        - Automatic adjustment based on performance
        - Prevents over-betting
    """
```

##### Volatility-Based Sizing

```python
def calculate_volatility_adjusted_size(
    self,
    base_size: float,
    symbol: str,
    timeframe: str = '1h'
) -> float:
    """
    Adjust position size based on volatility.
    
    Method:
    1. Calculate ATR (Average True Range) for symbol
    2. Calculate normalized volatility
    3. Adjust size inversely to volatility
    
    High volatility = Smaller position
    Low volatility = Larger position
    
    This prevents outsized losses during volatile periods.
    """
```

#### Dynamic SL/TP Configuration

```python
@dataclass
class DynamicSLTPConfig:
    enabled: bool = True
    use_atr: bool = True
    atr_multiplier_sl: float = 2.0   # SL at 2x ATR
    atr_multiplier_tp: float = 3.0   # TP at 3x ATR
    min_sl_percent: float = 1.0      # Minimum 1% SL
    max_sl_percent: float = 5.0      # Maximum 5% SL
    min_rr_ratio: float = 1.5        # Minimum Risk:Reward

def calculate_dynamic_sl_tp(
    self,
    symbol: str,
    entry_price: float,
    side: str,
    leverage: float = 1.0
) -> Tuple[float, float]:
    """
    Calculate ATR-based stop loss and take profit.
    
    Process:
    1. Fetch recent OHLCV data (14 periods)
    2. Calculate ATR
    3. SL distance = ATR * sl_multiplier
    4. TP distance = ATR * tp_multiplier
    5. Adjust for leverage (tighter stops at higher leverage)
    6. Apply min/max constraints
    7. Ensure minimum R:R ratio
    
    For LONG:
        SL = entry_price - sl_distance
        TP = entry_price + tp_distance
    
    For SHORT:
        SL = entry_price + sl_distance
        TP = entry_price - tp_distance
    """
```

#### Trailing Stop Configuration

```python
@dataclass
class TrailingStopConfig:
    enabled: bool = True
    activation_profit_percent: float = 1.0  # Activate at 1% profit
    trailing_distance_percent: float = 2.0  # Trail by 2%
    use_atr_distance: bool = True           # Use ATR for distance
    atr_multiplier: float = 2.0             # 2x ATR trailing distance

def calculate_trailing_stop(
    self,
    position: MonitoredPosition,
    current_price: float,
    atr: float = None
) -> Optional[float]:
    """
    Calculate new trailing stop level.
    
    Returns new SL if it should be updated, None otherwise.
    """
```

---

## AI Signal Processing

### 7.1 SupabaseAnalysisService (`bot/services/supabase_analysis_service.py`)

Integration with Supabase Edge Functions for AI-powered market analysis.

#### Signal Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Bot       │────▶│  Supabase   │────▶│  OpenAI     │
│  Request    │     │  Edge Fn    │     │  GPT-4      │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Market     │
                    │  Analysis   │
                    │  Response   │
                    └─────────────┘
```

#### Edge Function Endpoint

```python
SUPABASE_URL = os.getenv("SUPABASE_URL")
EDGE_FUNCTION_URL = f"{SUPABASE_URL}/functions/v1/market-analysis"
REQUEST_TIMEOUT = 300  # 5 minutes

async def get_fresh_signals(
    self,
    symbols: List[str] = None,
    max_age_hours: float = 6.0
) -> List[Dict]:
    """
    Fetch fresh AI signals from Edge Function.
    
    Request:
        POST /functions/v1/market-analysis
        Headers: Authorization: Bearer <SERVICE_KEY>
        Body: {"symbols": [...], "analyze_all": true}
    
    Response:
        {
            "signals": [
                {
                    "symbol": "BTC/USDT",
                    "action": "buy",
                    "confidence": 0.85,
                    "combined_score": 0.42,
                    "entry_price": 42000,
                    "stop_loss": 40000,
                    "take_profit": 46000,
                    "analysis": "Strong bullish momentum...",
                    "timestamp": "2025-12-17T00:00:00Z"
                },
                ...
            ]
        }
    
    Filtering:
        - Only signals with combined_score >= 0.35
        - Only signals less than 6 hours old
        - Prefer newest signal per symbol
    """
```

### 7.2 SignalValidator (`bot/services/signal_validator.py`)

Validates AI signals against historical data and market conditions.

```python
class SignalValidator:
    """
    Adaptive signal validation system.
    
    Validation Checks:
    1. Confidence threshold (adaptive based on market regime)
    2. Consensus with recent signals (same direction)
    3. Technical confirmation (RSI, MACD alignment)
    4. Volume confirmation
    5. Spread check (ensure tradeable liquidity)
    
    Adaptive Confidence:
    - Trending market: Lower threshold (0.30)
    - Ranging market: Higher threshold (0.40)
    - Volatile market: Highest threshold (0.50)
    """
    
    def validate_signal(
        self,
        signal: Dict,
        market_regime: str = "normal"
    ) -> Tuple[bool, str]:
        """
        Validate a signal for trading.
        
        Returns:
            Tuple of (is_valid, rejection_reason)
        """
```

---

## Database Layer

### 8.1 Database Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Database Architecture                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────┐    ┌───────────────────────┐    │
│  │      Supabase         │    │       SQLite          │    │
│  │   (Cloud PostgreSQL)  │    │     (Local Cache)     │    │
│  └───────────┬───────────┘    └───────────┬───────────┘    │
│              │                            │                 │
│              ▼                            ▼                 │
│  ┌───────────────────────────────────────────────────────┐ │
│  │                     Tables                             │ │
│  │                                                        │ │
│  │  api_keys            - Exchange API credentials        │ │
│  │  trading_settings    - User risk preferences           │ │
│  │  positions           - Position history                │ │
│  │  trades              - Trade execution log             │ │
│  │  monitored_positions - Active position monitoring      │ │
│  │  signals             - AI signal history               │ │
│  │  users               - User accounts                   │ │
│  │                                                        │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 Key Tables

#### api_keys Table

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    exchange exchange_type NOT NULL,  -- 'binance', 'kraken', etc.
    encrypted_api_key TEXT NOT NULL,
    encrypted_api_secret TEXT NOT NULL,
    passphrase TEXT,                   -- For exchanges requiring it
    is_testnet BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    account_type TEXT DEFAULT 'spot',  -- 'spot', 'margin', 'futures'
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
```

#### trades Table (Primary P&L Source)

```sql
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    exchange exchange_type NOT NULL,
    symbol TEXT NOT NULL,
    trade_type trade_type NOT NULL,    -- 'buy', 'sell'
    amount NUMERIC NOT NULL,
    price NUMERIC NOT NULL,
    entry_price NUMERIC,
    exit_price NUMERIC,
    pnl NUMERIC,                       -- Realized P&L
    fee NUMERIC,
    fee_currency TEXT,
    status trade_status DEFAULT 'pending',
    leverage NUMERIC DEFAULT 1.0,
    stop_loss NUMERIC,
    take_profit NUMERIC,
    emotion TEXT,                      -- Exit reason (SL, TP, etc.)
    source VARCHAR(50),                -- 'bot', 'manual', 'position_monitor'
    executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

#### monitored_positions Table

```sql
CREATE TABLE monitored_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    position_key TEXT NOT NULL,        -- Unique identifier
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,                -- 'long', 'short'
    entry_price FLOAT NOT NULL,
    quantity FLOAT NOT NULL,
    stop_loss FLOAT,
    take_profit FLOAT,
    original_stop_loss FLOAT,
    leverage FLOAT DEFAULT 1.0,
    trailing_enabled BOOLEAN DEFAULT true,
    trailing_distance_pct FLOAT DEFAULT 2.0,
    highest_price FLOAT,
    lowest_price FLOAT,
    trailing_activated BOOLEAN DEFAULT false,
    dynamic_sl_enabled BOOLEAN DEFAULT true,
    max_hold_hours FLOAT DEFAULT 12.0,
    partial_tp_executed JSONB DEFAULT '[]',
    original_quantity FLOAT,
    liquidation_price FLOAT,
    liquidation_risk_level TEXT DEFAULT 'safe',
    is_active BOOLEAN DEFAULT true,
    opened_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_sync TIMESTAMPTZ DEFAULT now()
);
```

---

## Monitoring & Diagnostics

### 9.1 Monitor Group (`monitor_group.py`)

Dashboard for monitoring all users and their trading activity.

#### Display Information

```
======================================================================
📊 --- ALL USERS MONITOR --- 2025-12-17 01:00:00
======================================================================

👤 User: 2dc2d6d0-1aba-4689-8217-0206d7ebee62
   📊 Found 5 completed trades in DB

   📉 SPOT ASSETS:
      🔹 BTC: 0.0012 ($50.00)
      🔹 ETH: 0.025 ($80.00)

   💰 WALLET (SPOT):
      💵 USDT:      26.72
      💵 USDC:      10.00

   🧮 ACCOUNT SUMMARY (Est.):
      💵 Stable Balance:      36.72 (USDT/USD/USDC)
      📈 Total Equity:       166.72
      🔓 Free Margin:        166.72

   📅 MONTHLY P&L (Last 30 days):
      🟢 Realized P&L:      +12.34 USDT
      📊 Closed Trades:          5
      ✅ Winning:               3 (60.0%)
      ❌ Losing:                2
      📈 Avg Win:           +8.50
      📉 Avg Loss:          -4.00
      🏆 Best Trade:       +15.00
      💀 Worst Trade:       -6.00

   📜 RECENT CLOSED TRADES:
      1. ETH/USDT SELL +0.02 (SL triggered)
      2. BTC/USDT SELL +5.50 (TP reached)
      ...
```

### 9.2 Logging System

```python
# Log levels and formatting
import logging

logger = get_logger("auto_trader")

# Log format
# [12/17/25 00:16:02] INFO     Message here                    module.py:123

# Key log messages:
# 🚀 Starting bot for user {user_id}
# 📊 Found {n} fresh signals
# ✅ Trade executed: {symbol} {side}
# 🛑 Stop loss triggered: {symbol}
# 🎯 Take profit triggered: {symbol}
# ⚠️ Warning: {message}
# ❌ Error: {message}
```

---

## Configuration Reference

### 10.1 Environment Variables

```bash
# Exchange Configuration
EXCHANGE_NAME=binance              # Exchange identifier
EXCHANGE_API_KEY=your_api_key      # API key (if not using DB)
EXCHANGE_API_SECRET=your_secret    # API secret
USE_TESTNET=false                  # Use testnet endpoints

# Database Configuration
DATABASE_URL=sqlite:///trading.db  # Local SQLite
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJhbG...             # Anon key
SUPABASE_SERVICE_KEY=eyJhbG...     # Service role key (bypasses RLS)

# Trading Parameters
TRADING_INTERVAL_SECONDS=3600      # Bot cycle interval
MAX_POSITIONS=5                    # Maximum concurrent positions
RISK_PER_TRADE_PCT=1.0            # Risk per trade (%)
DAILY_LOSS_LIMIT_PCT=5.0          # Daily loss limit (%)
TRADE_SYMBOLS=BTC/USDT,ETH/USDT   # Symbols to trade

# AI Configuration
OPENAI_API_KEY=sk-...             # OpenAI API key
REQUEST_TIMEOUT=300               # Edge function timeout

# Encryption
ENCRYPTION_KEY=your_32_byte_key   # Fernet encryption key
```

### 10.2 Trading Settings Defaults

```python
DEFAULT_SETTINGS = {
    # Position sizing
    "max_position_size": 1000.0,     # USD
    "risk_per_trade": 1.0,           # %
    
    # Stop Loss / Take Profit
    "stop_loss_percentage": 5.0,     # %
    "take_profit_percentage": 3.0,   # %
    
    # Trailing stop
    "trailing_enabled": True,
    "trailing_activation": 1.0,      # % profit to activate
    "trailing_distance": 2.0,        # %
    
    # Time limits
    "max_hold_hours": 12.0,
    
    # Partial TP
    "partial_tp_enabled": True,
    "partial_tp_levels": [
        {"profit_pct": 1.5, "close_pct": 30},
        {"profit_pct": 2.5, "close_pct": 50},
        {"profit_pct": 100, "close_pct": 100}  # Full TP
    ],
    
    # Liquidation protection
    "liquidation_warning_pct": 15.0,
    "liquidation_auto_close_pct": 3.5
}
```

---

## Recent Changes & Fixes

### 11.1 Session Changes (2025-12-16/17)

#### FIX: Position Counting Logic (`auto_trader.py`)

**Problem**: Bot counted SPOT + MARGIN positions together, causing false "Max positions reached (10/5)" errors.

**Solution**: Mode-aware position counting:
- SPOT mode: Count only spot balances (excluding LD* tokens)
- MARGIN mode: Count only margin positions

```python
# FIX 2025-12-16: Count positions based on account mode
if self.margin or self.futures:
    # MARGIN/FUTURES mode: Only count margin/futures positions
    margin_positions = await self.exchange.get_positions()
    total_positions = len(margin_positions)
else:
    # SPOT mode: Only count spot positions (excluding dust/airdrops)
    spot_assets = await self.exchange.get_spot_balances(min_value_usd=10.0)
    total_positions = len(spot_assets)
```

#### FIX: LD* Token Exclusion (`ccxt_adapter.py`)

**Problem**: Binance Launchpad tokens (LD*) were counted as positions.

**Solution**: Filter out LD*, BETH, BFUSD prefixes:

```python
LAUNCHPAD_PREFIXES = ('LD', 'BETH', 'BFUSD')
EXCLUDED_ASSETS = {'USDT', 'USDC', 'USD', 'DAI', 'BUSD', 'EUR', 'PLN', 'GBP', 'CHF', 'USDG'}

# Skip LD* tokens
if any(asset.startswith(prefix) for prefix in LAUNCHPAD_PREFIXES):
    continue
```

#### FIX: Account Type Reading (`run_single_user.py`)

**Problem**: Bot wasn't reading `account_type` from database.

**Solution**: Added account_type to SQL query:

```python
# FIX 2025-12-16: Added account_type to query
query = text("""
    SELECT user_id, encrypted_api_key, encrypted_api_secret, 
           exchange, is_testnet, account_type 
    FROM api_keys WHERE user_id = :user_id
""")

# Determine trading mode
account_type = (account_type or '').lower()
is_margin = account_type == 'margin'
is_futures = account_type == 'futures'
```

#### FIX: P&L Data Source (`monitor_group.py`)

**Problem**: `positions` table had `user_id = NULL` for closed positions.

**Solution**: Use `trades` table as primary P&L source:

```python
# FIX 2025-12-17: trades table is the PRIMARY source for closed trades
response = supabase.table("trades").select(
    "symbol, trade_type, amount, price, entry_price, exit_price, pnl, status, emotion, created_at"
).eq("user_id", user_id).eq("status", "completed").order("created_at", desc=True).limit(200).execute()
```

---

## Known Issues & Roadmap

### 12.1 Known Issues

| Issue | Severity | Description | Workaround |
|-------|----------|-------------|------------|
| `positions.user_id = NULL` | Medium | Closed positions missing user_id | Use `trades` table for P&L |
| `positions.realized_pnl = 0` | Low | P&L not saved to positions table | Calculate from entry/exit prices |
| Edge Function 504 | Medium | Timeout on large analyses | Fallback to DB signals |
| Rate Limiting | Low | Occasional exchange rate limits | Exponential backoff implemented |

### 12.2 Future Roadmap

#### Short Term
- [ ] Fix `user_id` population in `positions` table on close
- [ ] Save `realized_pnl` when closing positions
- [ ] Add position `exit_time` tracking

#### Medium Term
- [ ] Web dashboard for position monitoring
- [ ] Push notifications for SL/TP triggers
- [ ] Multi-strategy support per user
- [ ] Backtesting framework

#### Long Term
- [ ] Machine learning model training
- [ ] Social trading / copy trading
- [ ] Advanced portfolio optimization
- [ ] Multi-exchange arbitrage

---

## Appendix

### A. File Structure

```
Algorytm Uczenia Kwantowego LLM/
├── bot/
│   ├── __init__.py
│   ├── auto_trader.py           # Main trading bot
│   ├── config.py                # Configuration loading
│   ├── db.py                    # Database manager
│   ├── risk_manager.py          # Basic risk management
│   ├── strategies.py            # Trading strategies
│   ├── core/
│   │   ├── symbol_normalizer.py
│   │   ├── transaction_manager.py
│   │   ├── position_lock.py
│   │   ├── daily_loss_tracker.py
│   │   ├── correlation_manager.py
│   │   ├── market_regime_sizer.py
│   │   ├── spread_calculator.py
│   │   ├── rate_limiter_v2.py
│   │   └── retry_handler.py
│   ├── services/
│   │   ├── position_monitor.py  # Position monitoring (4000+ lines)
│   │   ├── risk_manager.py      # Advanced risk management
│   │   ├── portfolio_manager.py
│   │   ├── market_intelligence.py
│   │   ├── signal_validator.py
│   │   ├── rate_limiter.py
│   │   ├── dca_manager.py
│   │   ├── alert_service.py
│   │   ├── supabase_analysis_service.py
│   │   └── economic_calendar.py
│   └── exchange_adapters/
│       ├── ccxt_adapter.py      # CCXT exchange adapter
│       └── example_implementation.py
├── run_single_user.py           # Single user bot runner
├── run_multi_bots.py            # Multi-user bot runner
├── monitor_group.py             # Monitoring dashboard
├── start_all_bots.sh            # Shell script to start bots
├── start_monitor.sh             # Shell script to start monitor
├── .env                         # Environment configuration
└── requirements.txt             # Python dependencies
```

### B. Quick Commands

```bash
# Start all 6 bots
./start_all_bots.sh

# Start monitor dashboard
./start_monitor.sh

# View bot logs
tail -f logs/bot_*.log

# View specific user bot log
tail -f logs/bot_2dc2d6d0.log

# Check running processes
ps aux | grep -E "run_single_user|monitor_group"

# Kill all bots
pkill -f "run_single_user.py|monitor_group.py"
```

### C. Support & Contact

- **Repository**: github.com/FSliwa/ase-bot
- **Documentation**: This file
- **Last Updated**: 2025-12-17

---

*This documentation was generated based on source code analysis of ASE BOT v4.2*
