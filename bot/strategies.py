from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .broker.paper import PaperBroker

logger = logging.getLogger(__name__)
from .config import AppConfig
from .parser import TradeIntent

# NEW v2.0: Import Market Intelligence for liquidity checks
try:
    from .services.market_intelligence import get_market_intelligence
    MARKET_INTELLIGENCE_AVAILABLE = True
except ImportError:
    MARKET_INTELLIGENCE_AVAILABLE = False

# FIX 2025-12-16: Import TransactionManager for atomic trade execution
try:
    from .core.transaction_manager import TransactionManager, TradeResult
    TRANSACTION_MANAGER_AVAILABLE = True
except ImportError:
    TRANSACTION_MANAGER_AVAILABLE = False
    logger.warning("TransactionManager not available - trades will use non-atomic execution")

# FIX 2025-12-16: Import Dead Letter Queue for failed signal persistence
try:
    from .services.dead_letter_queue import add_to_dlq, get_dead_letter_queue
    DLQ_AVAILABLE = True
except ImportError:
    DLQ_AVAILABLE = False
    add_to_dlq = None


# ========== P2-4 FIX: Trading Constants (previously hardcoded) ==========
class TradingConstants:
    """Centralized trading constants - eliminate magic numbers."""
    
    # Position sizing
    MAX_CONCURRENT_TRADES = 5              # Max trades per cycle
    DEFAULT_POSITION_PCT = 0.10            # 10% of capital per trade
    MAX_POSITION_PCT = 0.25                # Max 25% in single position
    MIN_POSITION_PCT = 0.02                # Min 2% position
    
    # Risk management
    DEFAULT_SL_PCT = 0.05                  # 5% stop loss
    DEFAULT_TP_PCT = 0.07                  # 7% take profit
    TRAILING_ACTIVATION_PCT = 0.02         # Activate trailing at 2% profit
    TRAILING_DISTANCE_PCT = 0.02           # 2% trailing distance
    
    # Signal filtering
    MAX_SIGNAL_AGE_SECONDS = 60            # Stale after 60s
    MIN_CONFIDENCE_THRESHOLD = 0.5         # Minimum signal confidence
    
    # Order validation
    DEFAULT_MIN_NOTIONAL_USD = 10.0        # Fallback min order size
    MIN_NOTIONAL_BY_EXCHANGE = {
        'binance': 5.0,
        'bybit': 1.0,
        'kraken': 5.0,
        'okx': 5.0,
        'kucoin': 1.0,
        'gate': 1.0,
        'mexc': 1.0,
        'bitget': 5.0,
    }
    
    # Memory management - P2-NEW-5
    MAX_TRADE_HISTORY_SIZE = 1000          # Max entries to prevent memory leak
    
    # Market filters
    MIN_VOLUME_24H_USD = 100000            # Min 24h volume
    MAX_SPREAD_PCT = 0.5                   # Max 0.5% spread
    
    # Order retry settings - P1-5 FIX
    ORDER_RETRY_COUNT = 3                  # Retry failed orders up to 3 times
    ORDER_RETRY_DELAY_SECONDS = 1.0        # Delay between retries


@dataclass
class Signal:
    """Trading signal from a strategy."""
    action: str  # "buy", "sell", "close", "hold"
    symbol: str
    quantity: float
    order_type: str  # "market", "limit"
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    leverage: Optional[float] = 10.0  # Default 10x, will be auto-adjusted by exchange
    reason: str = ""
    confidence: float = 0.5  # 0-1
    timestamp: Optional[datetime] = None  # P1-7: For signal age validation
    trading_mode: Optional[str] = "day_trading"  # NEW: Trading mode for Quick Exit
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class MarketData:
    """Simplified market data for strategies."""
    symbol: str
    current_price: float
    high_24h: float
    low_24h: float
    volume_24h: float
    change_24h_percent: float
    timestamp: datetime


class TradingStrategy(ABC):
    """Base class for all trading strategies."""
    
    # Default base prices for position size calculation fallback
    BASE_PRICES_USD = {
        'BTC': 100000, 'ETH': 4000, 'BNB': 700, 'SOL': 200, 
        'XRP': 2, 'ADA': 1, 'DOGE': 0.4, 'AVAX': 50,
        'DOT': 10, 'MATIC': 1, 'LINK': 20, 'LTC': 100
    }
    DEFAULT_POSITION_SIZE_USD = 50  # $50 fallback position size
    
    def __init__(self, name: str, symbols: List[str], config: AppConfig):
        self.name = name
        self.symbols = symbols
        self.config = config
        self.active = True
        # NEW: Risk manager and user settings injection
        self.risk_manager = None
        self.user_settings: Optional[Dict] = None
        
    def set_risk_manager(self, risk_manager) -> None:
        """Inject risk manager for dynamic position sizing."""
        self.risk_manager = risk_manager
        logger.debug(f"Strategy {self.name}: Risk manager injected")
    
    def set_user_settings(self, settings: Dict) -> None:
        """Inject user settings for position sizing."""
        self.user_settings = settings
        logger.debug(f"Strategy {self.name}: User settings injected: {settings}")
    
    async def calculate_position_size(
        self, 
        symbol: str, 
        current_price: float,
        stop_loss_price: float = None,
        signal_confidence: float = 0.5
    ) -> float:
        """
        Calculate position size using Risk Manager or fallback to user settings/default.
        
        Priority:
        1. Risk Manager (Kelly Criterion, ATR-based, volatility adjustment)
        2. User settings (max_position_size, risk_level)
        3. Default fallback ($50 position)
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            current_price: Current price of the asset
            stop_loss_price: Optional SL price for risk-based sizing
            signal_confidence: Signal confidence (0-1) for size scaling
            
        Returns:
            Position quantity in base asset
        """
        base_currency = symbol.split('/')[0] if '/' in symbol else symbol.replace('USDT', '').replace('USDC', '')
        
        # 1. Try Risk Manager (best option)
        if self.risk_manager:
            try:
                # Check if risk_manager has async calculate_position_size
                if hasattr(self.risk_manager, 'calculate_position_size'):
                    result = await self.risk_manager.calculate_position_size(
                        symbol=symbol,
                        entry_price=current_price,
                        stop_loss_price=stop_loss_price,
                        account_balance=None  # Risk Manager fetches from exchange
                    )
                    if hasattr(result, 'quantity') and result.quantity > 0:
                        logger.debug(f"Strategy {self.name}: Risk Manager sizing for {symbol}: {result.quantity:.6f}")
                        return result.quantity
            except Exception as e:
                logger.warning(f"Risk Manager sizing failed for {symbol}: {e}")
        
        # 2. Try User Settings
        if self.user_settings:
            try:
                max_pos_usd = self.user_settings.get('max_position_size', 100)
                risk_level = self.user_settings.get('risk_level', 3)
                
                # Scale by risk level (1-5): level 1 = 20%, level 5 = 100% of max
                risk_multiplier = risk_level / 5.0
                position_usd = max_pos_usd * risk_multiplier * signal_confidence
                
                # Calculate quantity
                if current_price and current_price > 0:
                    quantity = position_usd / current_price
                    logger.debug(
                        f"Strategy {self.name}: User settings sizing for {symbol}: "
                        f"${position_usd:.2f} / ${current_price:.2f} = {quantity:.6f}"
                    )
                    return quantity
            except Exception as e:
                logger.warning(f"User settings sizing failed for {symbol}: {e}")
        
        # 3. Fallback to default
        return self._get_default_quantity(symbol, current_price)
    
    def _get_default_quantity(self, symbol: str, current_price: float = None) -> float:
        """
        Default quantity based on base prices or hardcoded fallback.
        Returns ~$50 worth of the asset.
        """
        base_currency = symbol.split('/')[0] if '/' in symbol else symbol.replace('USDT', '').replace('USDC', '')
        
        # Use current price if available
        if current_price and current_price > 0:
            quantity = self.DEFAULT_POSITION_SIZE_USD / current_price
            logger.debug(f"Strategy {self.name}: Default sizing for {symbol}: ${self.DEFAULT_POSITION_SIZE_USD} / ${current_price:.2f} = {quantity:.6f}")
            return quantity
        
        # Fallback to estimated base prices
        estimated_price = self.BASE_PRICES_USD.get(base_currency, 100)
        quantity = self.DEFAULT_POSITION_SIZE_USD / estimated_price
        logger.debug(f"Strategy {self.name}: Estimated sizing for {symbol}: ${self.DEFAULT_POSITION_SIZE_USD} / ~${estimated_price} = {quantity:.6f}")
        return quantity
        
    @abstractmethod
    def analyze(self, market_data: Dict[str, MarketData], positions: Dict) -> List[Signal]:
        """Analyze market and return trading signals."""
        pass
        
    def validate_signal(self, signal: Signal) -> bool:
        """Enhanced signal validation.
        
        P1-NEW-3 FIX: Enhanced validation for price field.
        L9 FIX v3.0: Comprehensive signal validation including SL/TP/leverage checks.
        L4 FIX: Added signal age validation to reject stale signals.
        """
        # L4 FIX: Signal age validation - reject stale signals
        if signal.timestamp:
            signal_age_seconds = (datetime.now() - signal.timestamp).total_seconds()
            if signal_age_seconds > TradingConstants.MAX_SIGNAL_AGE_SECONDS:
                logger.warning(
                    f"Signal rejected: stale signal for {signal.symbol} | "
                    f"Age: {signal_age_seconds:.0f}s > max {TradingConstants.MAX_SIGNAL_AGE_SECONDS}s"
                )
                return False
        
        # Basic quantity check
        if signal.quantity <= 0:
            logger.warning(f"Signal rejected: quantity <= 0 ({signal.quantity})")
            return False
        
        # Order type specific validation    
        if signal.order_type == "limit":
            # Limit orders MUST have a valid price
            if signal.price is None or signal.price <= 0:
                logger.warning(f"Invalid limit order - price is None or <= 0: {signal.price}")
                return False
        
        # L9 FIX: Market order price validation (if provided)
        if signal.order_type == "market" and signal.price is not None:
            if signal.price <= 0:
                logger.warning(f"Invalid market order - provided price <= 0: {signal.price}")
                return False
        
        # L9 FIX: Stop Loss validation
        if signal.stop_loss is not None:
            if signal.stop_loss <= 0:
                logger.warning(f"Signal rejected: stop_loss <= 0 ({signal.stop_loss})")
                return False
            # Check SL direction vs action
            reference_price = signal.price if signal.price else getattr(signal, 'entry_price', None)
            if reference_price:
                if signal.action.lower() in ('buy', 'long'):
                    # For long: SL must be below entry
                    if signal.stop_loss >= reference_price:
                        logger.warning(
                            f"Signal rejected: stop_loss ({signal.stop_loss}) >= entry ({reference_price}) for LONG"
                        )
                        return False
                elif signal.action.lower() in ('sell', 'short'):
                    # For short: SL must be above entry
                    if signal.stop_loss <= reference_price:
                        logger.warning(
                            f"Signal rejected: stop_loss ({signal.stop_loss}) <= entry ({reference_price}) for SHORT"
                        )
                        return False
        
        # L9 FIX: Take Profit validation
        if signal.take_profit is not None:
            if signal.take_profit <= 0:
                logger.warning(f"Signal rejected: take_profit <= 0 ({signal.take_profit})")
                return False
            # Check TP direction vs action
            reference_price = signal.price if signal.price else getattr(signal, 'entry_price', None)
            if reference_price:
                if signal.action.lower() in ('buy', 'long'):
                    # For long: TP must be above entry
                    if signal.take_profit <= reference_price:
                        logger.warning(
                            f"Signal rejected: take_profit ({signal.take_profit}) <= entry ({reference_price}) for LONG"
                        )
                        return False
                elif signal.action.lower() in ('sell', 'short'):
                    # For short: TP must be below entry
                    if signal.take_profit >= reference_price:
                        logger.warning(
                            f"Signal rejected: take_profit ({signal.take_profit}) >= entry ({reference_price}) for SHORT"
                        )
                        return False
        
        # L9 FIX: Leverage validation
        if signal.leverage is not None:
            if signal.leverage < 1.0 or signal.leverage > 100.0:
                logger.warning(f"Signal rejected: leverage out of range 1-100 ({signal.leverage})")
                return False
        
        # L9 FIX: Confidence validation
        if hasattr(signal, 'confidence') and signal.confidence is not None:
            if signal.confidence < 0 or signal.confidence > 1:
                logger.warning(f"Signal rejected: confidence out of range 0-1 ({signal.confidence})")
                return False
        
        return True


class MomentumStrategy(TradingStrategy):
    """Simple momentum strategy - buy on uptrend, sell on downtrend."""
    
    # FIX 2025-12-16: Increased threshold from 1% to 2.5% - crypto is too volatile for 1%
    def __init__(self, symbols: List[str], config: AppConfig, threshold: float = 2.5):
        super().__init__("Momentum", symbols, config)
        self.threshold = threshold  # % change threshold (increased from 1.0 to 2.5 for crypto volatility)
        # Volume confirmation threshold (20% above average)
        self.volume_confirmation_ratio = 1.2
        
    def analyze(self, market_data: Dict[str, MarketData], positions: Dict) -> List[Signal]:
        """Synchronous analyze - uses default quantity. For dynamic sizing, use analyze_async."""
        signals = []
        
        for symbol in self.symbols:
            if symbol not in market_data:
                continue
                
            data = market_data[symbol]
            has_position = symbol in positions
            
            # Calculate confidence based on momentum strength
            confidence = min(0.5 + (data.change_24h_percent / 10), 0.9)
            stop_loss = data.current_price * 0.97  # 3% stop loss
            
            # FIX 2025-12-16: Volume confirmation - skip if volume is below average
            volume_confirmed = True
            if hasattr(data, 'volume_24h') and hasattr(data, 'avg_volume'):
                if data.avg_volume and data.avg_volume > 0:
                    volume_ratio = data.volume_24h / data.avg_volume
                    volume_confirmed = volume_ratio >= self.volume_confirmation_ratio
                    if not volume_confirmed:
                        logger.debug(f"Momentum {symbol}: Volume too low ({volume_ratio:.2f}x avg), skipping")
            
            # Buy signal: positive momentum above threshold + volume confirmation
            if data.change_24h_percent > self.threshold and not has_position and volume_confirmed:
                # P2-1 FIX: Dynamic position sizing (sync fallback)
                quantity = self._get_default_quantity(symbol, data.current_price)
                
                signal = Signal(
                    action="buy",
                    symbol=symbol,
                    quantity=quantity,  # CHANGED: was hardcoded 0.01
                    order_type="market",
                    stop_loss=stop_loss,
                    take_profit=data.current_price * 1.05,  # 5% take profit
                    leverage=10.0,  # Default 10x, will be auto-adjusted by exchange
                    reason=f"Momentum up {data.change_24h_percent:.1f}%",
                    confidence=confidence
                )
                signals.append(signal)
                
            # Sell signal: negative momentum below threshold
            elif data.change_24h_percent < -self.threshold and has_position:
                signal = Signal(
                    action="close",
                    symbol=symbol,
                    quantity=positions[symbol].quantity,
                    order_type="market",
                    reason=f"Momentum down {data.change_24h_percent:.1f}%",
                    confidence=min(0.5 + (abs(data.change_24h_percent) / 10), 0.9)
                )
                signals.append(signal)
                
        return [s for s in signals if self.validate_signal(s)]
    
    async def analyze_async(self, market_data: Dict[str, MarketData], positions: Dict) -> List[Signal]:
        """Async analyze with full Risk Manager integration for dynamic position sizing."""
        signals = []
        
        for symbol in self.symbols:
            if symbol not in market_data:
                continue
                
            data = market_data[symbol]
            has_position = symbol in positions
            
            # Calculate confidence based on momentum strength
            confidence = min(0.5 + (data.change_24h_percent / 10), 0.9)
            stop_loss = data.current_price * 0.97  # 3% stop loss
            
            # FIX 2025-12-16: Volume confirmation - skip if volume is below average
            volume_confirmed = True
            if hasattr(data, 'volume_24h') and hasattr(data, 'avg_volume'):
                if data.avg_volume and data.avg_volume > 0:
                    volume_ratio = data.volume_24h / data.avg_volume
                    volume_confirmed = volume_ratio >= self.volume_confirmation_ratio
                    if not volume_confirmed:
                        logger.debug(f"Momentum {symbol}: Volume too low ({volume_ratio:.2f}x avg), skipping")
            
            # Buy signal: positive momentum above threshold + volume confirmation
            if data.change_24h_percent > self.threshold and not has_position and volume_confirmed:
                # P2-1 FIX: Dynamic position sizing with Risk Manager
                quantity = await self.calculate_position_size(
                    symbol=symbol,
                    current_price=data.current_price,
                    stop_loss_price=stop_loss,
                    signal_confidence=confidence
                )
                
                signal = Signal(
                    action="buy",
                    symbol=symbol,
                    quantity=quantity,
                    order_type="market",
                    stop_loss=stop_loss,
                    take_profit=data.current_price * 1.05,
                    leverage=10.0,
                    reason=f"Momentum up {data.change_24h_percent:.1f}%",
                    confidence=confidence
                )
                signals.append(signal)
                
            # Sell signal: negative momentum below threshold
            elif data.change_24h_percent < -self.threshold and has_position:
                signal = Signal(
                    action="close",
                    symbol=symbol,
                    quantity=positions[symbol].quantity,
                    order_type="market",
                    reason=f"Momentum down {data.change_24h_percent:.1f}%",
                    confidence=min(0.5 + (abs(data.change_24h_percent) / 10), 0.9)
                )
                signals.append(signal)
                
        return [s for s in signals if self.validate_signal(s)]


class MeanReversionStrategy(TradingStrategy):
    """Mean reversion - buy oversold, sell overbought."""
    
    # FIX 2025-12-16: Increased band_width from 2% to 4% to avoid false signals in crypto volatility
    def __init__(self, symbols: list[str], config: AppConfig, band_width: float = 0.04):
        super().__init__("MeanReversion", symbols, config)
        self.band_width = band_width  # 4% bands (was 2% - too narrow for crypto)
        
    async def analyze(self, market_data: Dict[str, MarketData], positions: Dict) -> List[Signal]:
        """Analyze market data for mean reversion opportunities with dynamic position sizing."""
        signals = []
        
        for symbol in self.symbols:
            if symbol not in market_data:
                continue
                
            data = market_data[symbol]
            has_position = symbol in positions
            
            # Calculate simple bands
            mid_price = (data.high_24h + data.low_24h) / 2
            lower_band = mid_price * (1 - self.band_width)
            upper_band = mid_price * (1 + self.band_width)
            
            # Buy at lower band
            if data.current_price <= lower_band and not has_position:
                # Calculate stop loss and take profit
                stop_loss = data.current_price * 0.98  # 2% stop loss default
                take_profit = mid_price  # Target mid price
                
                # Use risk manager for SL/TP if available
                if self.risk_manager:
                    try:
                        risk_params = self.risk_manager.calculate_position_risk(
                            symbol=symbol,
                            entry_price=data.current_price,
                            side="long"
                        )
                        if risk_params:
                            stop_loss = risk_params.get('stop_loss', stop_loss)
                            take_profit = risk_params.get('take_profit', take_profit)
                    except Exception:
                        pass  # Use defaults
                
                # Dynamic position sizing
                quantity = await self.calculate_position_size(
                    symbol=symbol,
                    current_price=data.current_price,
                    stop_loss_price=stop_loss
                )
                
                signal = Signal(
                    action="buy",
                    symbol=symbol,
                    quantity=quantity,
                    order_type="limit",
                    price=data.current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    leverage=10.0,  # Default 10x, will be auto-adjusted by exchange
                    reason=f"Oversold at lower band",
                    confidence=0.6
                )
                signals.append(signal)
                
            # Sell at upper band
            elif data.current_price >= upper_band and has_position:
                signal = Signal(
                    action="close",
                    symbol=symbol,
                    quantity=positions[symbol].quantity,
                    order_type="market",
                    reason=f"Overbought at upper band",
                    confidence=0.6
                )
                signals.append(signal)
                
        return [s for s in signals if self.validate_signal(s)]


class GridTradingStrategy(TradingStrategy):
    """Grid trading - place orders at regular intervals."""
    
    def __init__(self, symbols: list[str], config: AppConfig, grid_size: float = 0.01, levels: int = 5):
        super().__init__("GridTrading", symbols, config)
        self.grid_size = grid_size  # 1% between levels
        self.levels = levels
        self.grids: Dict[str, List[float]] = {}
        
    async def analyze(self, market_data: Dict[str, MarketData], positions: Dict) -> List[Signal]:
        """Analyze market data for grid trading with dynamic position sizing."""
        signals = []
        
        for symbol in self.symbols:
            if symbol not in market_data:
                continue
                
            data = market_data[symbol]
            
            # Initialize grid if needed
            if symbol not in self.grids:
                self.grids[symbol] = self._create_grid(data.current_price)
                
            # Check each grid level
            for i, level in enumerate(self.grids[symbol]):
                # Buy below current price
                if level < data.current_price * 0.99:
                    stop_loss = level * 0.98  # 2% stop loss
                    
                    # Dynamic position sizing - smaller for grid (divide by levels)
                    base_quantity = await self.calculate_position_size(
                        symbol=symbol,
                        current_price=level,
                        stop_loss_price=stop_loss
                    )
                    # Grid uses smaller positions (divided by number of levels)
                    quantity = base_quantity / self.levels if base_quantity else self._get_default_quantity(symbol) / self.levels
                    
                    signal = Signal(
                        action="buy",
                        symbol=symbol,
                        quantity=quantity,
                        order_type="limit",
                        price=level,
                        stop_loss=stop_loss,
                        leverage=10.0,  # Default 10x, will be auto-adjusted by exchange
                        reason=f"Grid buy level {i+1}",
                        confidence=0.5
                    )
                    signals.append(signal)
                    
        return [s for s in signals if self.validate_signal(s)][:3]  # Limit orders per cycle
        
    def _create_grid(self, current_price: float) -> list[float]:
        """Create grid levels around current price."""
        levels = []
        for i in range(1, self.levels + 1):
            levels.append(current_price * (1 - self.grid_size * i))
            levels.append(current_price * (1 + self.grid_size * i))
        return sorted(levels)


class AIStrategy(TradingStrategy):
    """Strategy that executes signals from AI analysis."""
    
    # FIX 2025-12-16: Action normalization for various LLM response formats
    ACTION_ALIASES = {
        # BUY actions
        'buy': 'buy',
        'long': 'buy',
        'enter': 'buy',
        'enter_long': 'buy',
        'open_long': 'buy',
        'bullish': 'buy',
        'accumulate': 'buy',
        'strong_buy': 'buy',
        'strong buy': 'buy',
        # SELL actions
        'sell': 'sell',
        'short': 'sell',
        'enter_short': 'sell',
        'open_short': 'sell',
        'bearish': 'sell',
        'strong_sell': 'sell',
        'strong sell': 'sell',
        # CLOSE actions
        'close': 'close',
        'exit': 'close',
        'close_position': 'close',
        'take_profit': 'close',
        'stop_loss': 'close',
        # HOLD actions
        'hold': 'hold',
        'wait': 'hold',
        'neutral': 'hold',
        'observe': 'hold',
        'no_action': 'hold',
        'no action': 'hold',
    }
    
    def __init__(self, symbols: list[str], config: AppConfig, can_short: bool = False):
        super().__init__("AIStrategy", symbols, config)
        self.latest_signals: Dict[str, Dict] = {}
        self.can_short = can_short  # Flag to enable shorting for margin/futures accounts
    
    def _normalize_action(self, raw_action: str) -> str:
        """Normalize AI action to standard format (buy/sell/close/hold).
        
        FIX 2025-12-16: Handle various LLM response formats like:
        - 'STRONG BUY' -> 'buy'
        - 'enter_long' -> 'buy'
        - 'short' -> 'sell'
        - 'exit' -> 'close'
        """
        if not raw_action:
            return 'hold'
        
        # Clean and lowercase
        action = raw_action.lower().strip()
        
        # Direct lookup
        if action in self.ACTION_ALIASES:
            return self.ACTION_ALIASES[action]
        
        # Fuzzy match - check if any alias is contained in the action
        for alias, normalized in self.ACTION_ALIASES.items():
            if alias in action:
                return normalized
        
        # Default to hold for unknown actions
        logger.warning(f"AIStrategy: Unknown action '{raw_action}', defaulting to 'hold'")
        return 'hold'
        
    def update_signals(self, ai_analyses: List[Dict]):
        """Update the latest AI signals."""
        self.latest_signals.clear()
        if not ai_analyses:
            return
            
        for analysis in ai_analyses:
            symbol = analysis.get('symbol')
            if symbol:
                self.latest_signals[symbol] = analysis
                # Debug log for TP/SL - check both 'take_profit' (DB) and 'targets' (AI)
                tp = analysis.get('take_profit') or (analysis.get('targets', [None])[0] if analysis.get('targets') else None)
                sl = analysis.get('stop_loss')
                logger.debug(f"AIStrategy: {symbol} - TP={tp}, SL={sl}")
                
    async def analyze(self, market_data: Dict[str, MarketData], positions: Dict) -> List[Signal]:
        """Analyze AI signals and generate trading signals with dynamic position sizing."""
        signals = []
        
        # CRITICAL FIX: Iterate over symbols from latest_signals, not just self.symbols
        # This ensures we process signals from DB even if they're not in the default symbol list
        symbols_to_check = set(self.symbols) | set(self.latest_signals.keys())
        
        for symbol in symbols_to_check:
            # Skip if no AI analysis for this symbol
            if symbol not in self.latest_signals:
                continue
                
            analysis = self.latest_signals[symbol]
            # FIX 2025-12-16: Use normalized action to handle various LLM formats
            raw_action = analysis.get('action', 'hold')
            action = self._normalize_action(raw_action)
            
            # Skip HOLD signals
            if action == 'hold':
                continue
                
            has_position = symbol in positions
            
            # Map AI action to Signal action
            # FIX 2025-12-16: Added 'close' as direct action type
            signal_action = None
            if action == 'buy' and not has_position:
                signal_action = 'buy'
            elif action == 'close' and has_position:
                # Direct close action from AI (e.g., "exit", "close_position")
                signal_action = 'close'
            elif action == 'sell':
                if has_position:
                    signal_action = 'close'  # Close existing long position
                elif self.can_short:
                    signal_action = 'sell'   # Open short position (margin/futures only)
                    logger.debug(f"AIStrategy: Opening SHORT for {symbol} (can_short={self.can_short})")
            
            if signal_action:
                # Use confidence to determine quantity or leverage if desired
                confidence = float(analysis.get('confidence', 0.5))
                
                # Get stop loss and take profit from AI analysis
                stop_loss_price = analysis.get('stop_loss')
                take_profit_price = analysis.get('take_profit')
                
                # Try to get targets if no direct take_profit
                if not take_profit_price:
                    targets = analysis.get('targets', [])
                    if targets and targets[0]:
                        take_profit_price = float(targets[0])
                
                # Convert to float if present
                if stop_loss_price:
                    stop_loss_price = float(stop_loss_price)
                if take_profit_price:
                    take_profit_price = float(take_profit_price)
                
                # Get current price for position sizing
                current_price = None
                if symbol in market_data:
                    current_price = market_data[symbol].current_price
                
                # Dynamic position sizing based on risk
                if current_price and stop_loss_price:
                    quantity = await self.calculate_position_size(
                        symbol=symbol,
                        current_price=current_price,
                        stop_loss_price=stop_loss_price
                    )
                else:
                    # Fallback to default quantity
                    quantity = self._get_default_quantity(symbol)
                
                signal = Signal(
                    action=signal_action,
                    symbol=symbol,
                    quantity=quantity,
                    order_type="market",
                    leverage=10.0,  # Default 10x, will be auto-adjusted by exchange
                    reason=f"AI Signal: {analysis.get('reasoning', 'No reasoning')}",
                    confidence=confidence
                )
                
                # Add take profit and stop loss
                if take_profit_price:
                    signal.take_profit = take_profit_price
                if stop_loss_price:
                    signal.stop_loss = stop_loss_price
                
                # Debug log for created signal
                logger.debug(f"AIStrategy Signal: {symbol} {signal_action} - TP={signal.take_profit}, SL={signal.stop_loss}, Qty={quantity}")
                    
                signals.append(signal)
                
        return [s for s in signals if self.validate_signal(s)]


class AutoTradingEngine:
    """Automatic trading engine that runs strategies."""
    
    def __init__(
        self, 
        broker: PaperBroker, 
        config: AppConfig, 
        db_manager=None, 
        user_id: str = None, 
        symbols: List[str] = None, 
        position_monitor=None, 
        portfolio_manager=None,
        risk_manager=None,  # Risk Manager integration
        dca_manager=None    # NEW: DCA Manager integration
    ):
        self.broker = broker
        self.config = config
        self.strategies: List[TradingStrategy] = []
        self.active = False
        self.last_run = datetime.now()
        self.trade_history: List[Tuple[datetime, Signal]] = []
        self.db_manager = db_manager
        self.user_id = user_id
        self.symbols = symbols or ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
        self.position_monitor = position_monitor  # For background SL/TP monitoring
        self.portfolio_manager = portfolio_manager  # For portfolio-aware decisions
        self.risk_manager = risk_manager  # For position sizing & dynamic SL/TP
        self.dca_manager = dca_manager  # NEW: For DCA (Dollar Cost Averaging)
        
        # FIX 2025-12-16: Initialize TransactionManager for atomic trade execution
        self.transaction_manager = None
        if TRANSACTION_MANAGER_AVAILABLE and db_manager:
            try:
                self.transaction_manager = TransactionManager(db_manager)
                logger.info("✅ TransactionManager initialized for atomic trade execution")
            except Exception as e:
                logger.warning(f"TransactionManager initialization failed: {e} - using non-atomic execution")
        
        # Connect Risk Manager to Position Monitor if both exist
        if self.position_monitor and self.risk_manager:
            self.position_monitor.set_risk_manager(self.risk_manager)
        
        # Real-time data cache (updated by WebSocket or polling)
        self._market_data_cache: Dict[str, MarketData] = {}
        self._cache_expiry_seconds = 60  # Cache valid for 60 seconds
    
    def set_portfolio_manager(self, portfolio_manager) -> None:
        """Set the portfolio manager for portfolio-aware trading."""
        self.portfolio_manager = portfolio_manager
    
    def set_risk_manager(self, risk_manager) -> None:
        """Set the risk manager for position sizing and dynamic SL/TP."""
        self.risk_manager = risk_manager
        if self.position_monitor:
            self.position_monitor.set_risk_manager(risk_manager)
    
    def set_dca_manager(self, dca_manager) -> None:
        """Set the DCA manager for Dollar Cost Averaging."""
        self.dca_manager = dca_manager
        
    def add_strategy(self, strategy: TradingStrategy) -> None:
        """Add a strategy to the engine and inject dependencies."""
        # Inject risk_manager for dynamic position sizing
        if self.risk_manager and hasattr(strategy, 'risk_manager'):
            strategy.risk_manager = self.risk_manager
        
        # Inject user_settings if available from config
        if hasattr(strategy, 'user_settings') and self.config:
            # Try to get user-specific settings from database
            if self.db_manager and self.user_id:
                try:
                    with self.db_manager as db:
                        user_settings = db.get_user_settings(self.user_id)
                        if user_settings:
                            strategy.user_settings = user_settings
                except Exception as e:
                    logger.warning(f"Failed to load user settings for strategy: {e}")
        
        self.strategies.append(strategy)
        logger.debug(f"Added strategy {strategy.name} with risk_manager={strategy.risk_manager is not None}")
        
    def remove_strategy(self, name: str) -> None:
        """Remove a strategy by name."""
        self.strategies = [s for s in self.strategies if s.name != name]
    
    def set_symbols(self, symbols: List[str]) -> None:
        """Set the symbols to trade."""
        self.symbols = symbols
        
    def update_market_data_cache(self, symbol: str, data: MarketData) -> None:
        """Update the market data cache (called by WebSocket manager)."""
        self._market_data_cache[symbol] = data
    
    async def fetch_real_market_data(self) -> Dict[str, MarketData]:
        """Fetch real market data from broker/exchange."""
        market_data = {}
        
        # Check if we have a LiveBroker with CCXT client
        if hasattr(self.broker, 'client'):
            for symbol in self.symbols:
                try:
                    # Fetch ticker data from exchange
                    if hasattr(self.broker.client, 'get_ticker_stats'):
                        stats = await self.broker.client.get_ticker_stats(symbol)
                        if stats:
                            market_data[symbol] = MarketData(
                                symbol=symbol,
                                current_price=stats.get('last', 0),
                                high_24h=stats.get('high', 0),
                                low_24h=stats.get('low', 0),
                                volume_24h=stats.get('volume', 0),
                                change_24h_percent=stats.get('change_percent', 0),
                                timestamp=datetime.now()
                            )
                    else:
                        # Fallback: use CCXT fetch_ticker directly
                        ticker = await self.broker.client.exchange.fetch_ticker(symbol)
                        if ticker:
                            market_data[symbol] = MarketData(
                                symbol=symbol,
                                current_price=ticker.get('last', 0),
                                high_24h=ticker.get('high', 0),
                                low_24h=ticker.get('low', 0),
                                volume_24h=ticker.get('quoteVolume', ticker.get('baseVolume', 0)),
                                change_24h_percent=ticker.get('percentage', 0),
                                timestamp=datetime.now()
                            )
                except Exception as e:
                    logger.error(f"Failed to fetch market data for {symbol}: {e}")
                    # Use cached data if available
                    if symbol in self._market_data_cache:
                        market_data[symbol] = self._market_data_cache[symbol]
        else:
            # PaperBroker - use cached data or mock for testing only
            logger.warning("Using PaperBroker - returning mock data for testing")
            return self.get_mock_market_data()
        
        # Update cache
        for symbol, data in market_data.items():
            self._market_data_cache[symbol] = data
            
        return market_data
        
    def get_mock_market_data(self) -> Dict[str, MarketData]:
        """Generate mock market data for testing only."""
        # WARNING: This should only be used in test mode!
        symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
        market_data = {}
        
        for symbol in symbols:
            base_price = {
                "BTC/USDT": 60000,
                "ETH/USDT": 3000,
                "BNB/USDT": 400
            }.get(symbol, 100)
            
            # Simulate price movements
            change = random.uniform(-5, 5)
            current = base_price * (1 + change / 100)
            
            market_data[symbol] = MarketData(
                symbol=symbol,
                current_price=current,
                high_24h=current * 1.02,
                low_24h=current * 0.98,
                volume_24h=random.uniform(1000000, 10000000),
                change_24h_percent=change,
                timestamp=datetime.now()
            )
            
        return market_data

    def _save_trade_to_db(self, signal: Signal, price: float, trade_type: str) -> None:
        """Save executed trade to database with full SL/TP/leverage data."""
        if not self.db_manager:
            logger.warning("No db_manager configured, trade not saved to DB")
            return
        
        # P0 FIX: user_id is required for save_trade()
        if not self.user_id:
            logger.warning("No user_id configured, trade not saved to DB")
            return
            
        try:
            # Normalize trade_type to lowercase for ENUM compatibility
            # Map: BUY -> buy, SELL -> sell, CLOSE -> close, etc.
            normalized_type = trade_type.lower()
            
            # P1-NEW-3 FIX: Extract SL/TP/leverage from signal for complete trade tracking
            stop_loss = getattr(signal, 'stop_loss', None)
            take_profit = getattr(signal, 'take_profit', None)
            leverage = getattr(signal, 'leverage', None)
            
            with self.db_manager as db:
                db.save_trade(
                    user_id=self.user_id,  # P0 FIX: Add required user_id
                    symbol=signal.symbol,
                    trade_type=normalized_type,
                    price=price,
                    amount=signal.quantity,
                    source="bot",
                    emotion=signal.reason[:100] if signal.reason else None,
                    # P1-NEW-3 FIX: Pass SL/TP/leverage to save_trade()
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    leverage=leverage,
                    entry_price=price  # Entry price = execution price for new trades
                )
            logger.info(
                f"💾 Trade saved to DB: {normalized_type} {signal.symbol} @ {price} | "
                f"SL={stop_loss} TP={take_profit} Lev={leverage}x"
            )
        except Exception as e:
            logger.error(f"Failed to save trade to DB: {e}")

    def _save_position_to_db(self, signal: Signal, entry_price: float, side: str) -> None:
        """
        🔴 CRITICAL FIX: Save new position to positions table as OPEN.
        
        This is essential for:
        1. Position Monitor sync_from_database() to restore SL/TP after bot restart
        2. Position tracking and analytics
        3. Liquidation monitoring
        
        Args:
            signal: Trading signal with symbol, quantity, SL/TP, leverage
            entry_price: Entry price of the position
            side: 'long' or 'short'
        """
        if not self.db_manager:
            logger.warning("No db_manager configured, position not saved to DB")
            return
        
        if not self.user_id:
            logger.warning("No user_id configured, position not saved to DB")
            return
            
        try:
            leverage = getattr(signal, 'leverage', 1.0) or 1.0
            
            with self.db_manager as db:
                position = db.create_position(
                    symbol=signal.symbol,
                    side=side,  # 'long' or 'short'
                    quantity=signal.quantity,
                    entry_price=entry_price,
                    leverage=leverage,
                    user_id=self.user_id,
                    strategy="ai_bot",  # Mark source
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )
                
            logger.info(
                f"💾 Position saved to DB: {side.upper()} {signal.symbol} | "
                f"Entry: {entry_price:.4f} | Qty: {signal.quantity:.6f} | "
                f"SL: {signal.stop_loss} | TP: {signal.take_profit} | Lev: {leverage}x"
            )
        except Exception as e:
            logger.error(f"Failed to save position to DB: {e}", exc_info=True)
    
    # FIX 2025-12-16: Atomic trade execution wrapper
    async def _execute_atomic_trade(
        self,
        signal: Signal,
        current_price: float,
        side: str = "buy"
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Execute trade with atomic transaction (order + position created together).
        
        If TransactionManager is available, ensures order and position are created
        atomically - either both succeed or both fail with rollback.
        
        Returns:
            Tuple[success: bool, result: Optional[Dict]]
        """
        if not self.transaction_manager:
            # Fallback to non-atomic execution
            return await self._execute_non_atomic_trade(signal, current_price, side)
        
        # FIX: Extract base asset and try alternative quote currencies
        base_asset = signal.symbol.split('/')[0] if '/' in signal.symbol else signal.symbol
        original_quote = signal.symbol.split('/')[1] if '/' in signal.symbol else 'USDT'
        
        quote_currencies = [original_quote]
        if original_quote == 'USDT':
            quote_currencies.extend(['USDC', 'EUR', 'USD'])
        elif original_quote == 'USDC':
            quote_currencies.extend(['USDT', 'EUR', 'USD'])
            
        last_error = None
        
        for quote in quote_currencies:
            try_symbol = f"{base_asset}/{quote}"
            
            try:
                # Prepare order data
                order_data = {
                    'user_id': self.user_id,
                    'strategy': signal.strategy_name if hasattr(signal, 'strategy_name') else 'AI_SIGNAL',
                    'symbol': try_symbol, # Use try_symbol
                    'side': side.upper(),
                    'order_type': signal.order_type,
                    'quantity': signal.quantity,
                    'price': signal.price or current_price,
                    'stop_price': signal.stop_loss,
                    'leverage': signal.leverage or 1.0,
                }
                
                # Prepare position data
                position_data = {
                    'user_id': self.user_id,
                    'strategy': order_data['strategy'],
                    'symbol': try_symbol, # Use try_symbol
                    'side': 'long' if side.lower() == 'buy' else 'short',
                    'quantity': signal.quantity,
                    'entry_price': current_price,
                    'leverage': signal.leverage or 1.0,
                    'stop_loss': signal.stop_loss,
                    'take_profit': signal.take_profit,
                    'margin_used': (signal.quantity * current_price) / (signal.leverage or 1.0),
                }
                
                # Define exchange callback (will be called inside atomic transaction)
                async def exchange_order_callback(order_data_inner):
                    result = await self.broker.place_order(
                        side=side,
                        symbol=try_symbol, # Use try_symbol
                        order_type=signal.order_type,
                        quantity=signal.quantity,
                        market_price=current_price,
                        price=signal.price,
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit,
                        leverage=signal.leverage
                    )
                    if isinstance(result, dict) and not result.get('success', True):
                        return {'success': False, 'error': result.get('error', 'Unknown')}
                    return {'success': True, 'order_id': result.get('order_id') if isinstance(result, dict) else None}
                
                # Execute atomic trade (sync wrapper for async callback)
                # Note: TransactionManager is sync, so we run exchange call separately
                # and wrap DB operations in transaction
                
                # Step 1: Execute on exchange first
                exchange_result = await exchange_order_callback(order_data)
                if not exchange_result.get('success', False):
                    error_msg = exchange_result.get('error', 'Unknown')
                    
                    # Check for permission error
                    if 'not permitted' in str(error_msg).lower() or '-2010' in str(error_msg) or 'invalid permissions' in str(error_msg).lower():
                        logger.warning(f"⚠️ {try_symbol} not permitted, trying alternative...")
                        last_error = error_msg
                        continue # Try next quote
                        
                    logger.error(f"❌ Exchange order failed: {error_msg}")
                    return False, exchange_result
                
                # Step 2: Atomic DB operations (order + position)
                trade_result = self.transaction_manager.atomic_create_order_and_position(
                    order_data=order_data,
                    position_data=position_data,
                    on_exchange_success=None  # Already executed above
                )
                
                if trade_result.success:
                    logger.info(
                        f"✅ Atomic trade completed: {try_symbol} | "
                        f"Order={trade_result.order_id} | Position={trade_result.position_id}"
                    )
                    return True, {
                        'success': True,
                        'order_id': trade_result.order_id,
                        'position_id': trade_result.position_id,
                        'exchange_order_id': exchange_result.get('order_id')
                    }
                else:
                    logger.error(f"❌ Atomic DB operation failed: {trade_result.error}")
                    # Note: Exchange order already placed, manual reconciliation may be needed
                    return False, {'success': False, 'error': trade_result.error}
                    
            except Exception as e:
                logger.error(f"Atomic trade execution error: {e}")
                last_error = e
                continue
                
        return False, {'success': False, 'error': str(last_error)}
    
    async def _execute_non_atomic_trade(
        self,
        signal: Signal,
        current_price: float,
        side: str = "buy"
    ) -> Tuple[bool, Optional[Dict]]:
        """Fallback non-atomic trade execution (original logic)."""
        
        # FIX: Extract base asset and try alternative quote currencies
        base_asset = signal.symbol.split('/')[0] if '/' in signal.symbol else signal.symbol
        original_quote = signal.symbol.split('/')[1] if '/' in signal.symbol else 'USDT'
        
        quote_currencies = [original_quote]
        if original_quote == 'USDT':
            quote_currencies.extend(['USDC', 'EUR', 'USD'])
        elif original_quote == 'USDC':
            quote_currencies.extend(['USDT', 'EUR', 'USD'])
            
        last_error = None
        
        for quote in quote_currencies:
            try_symbol = f"{base_asset}/{quote}"
            
            for retry_attempt in range(TradingConstants.ORDER_RETRY_COUNT):
                try:
                    result = await self.broker.place_order(
                        side=side,
                        symbol=try_symbol, # Use try_symbol
                        order_type=signal.order_type,
                        quantity=signal.quantity,
                        market_price=current_price,
                        price=signal.price,
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit,
                        leverage=signal.leverage
                    )
                    if isinstance(result, dict) and not result.get('success', True):
                        error_msg = result.get('error', 'Unknown')
                        
                        # Check for permission error
                        if 'not permitted' in str(error_msg).lower() or '-2010' in str(error_msg) or 'invalid permissions' in str(error_msg).lower():
                            logger.warning(f"⚠️ {try_symbol} not permitted, trying alternative...")
                            last_error = error_msg
                            break # Break retry loop, try next quote
                        
                        if retry_attempt < TradingConstants.ORDER_RETRY_COUNT - 1:
                            await asyncio.sleep(TradingConstants.ORDER_RETRY_DELAY_SECONDS)
                            continue
                        
                        # Final failure for this symbol
                        last_error = error_msg
                        break # Break retry loop, try next quote
                        
                    # Success!
                    if try_symbol != signal.symbol:
                        logger.info(f"✅ Trade executed using alternative symbol: {try_symbol}")
                    return True, result
                    
                except Exception as order_err:
                    error_str = str(order_err).lower()
                    if 'not permitted' in error_str or '-2010' in error_str or 'invalid permissions' in error_str:
                        logger.warning(f"⚠️ {try_symbol} not permitted, trying alternative...")
                        last_error = order_err
                        break # Break retry loop, try next quote
                        
                    if retry_attempt < TradingConstants.ORDER_RETRY_COUNT - 1:
                        await asyncio.sleep(TradingConstants.ORDER_RETRY_DELAY_SECONDS)
                        continue
                    
                    last_error = order_err
        
        # FIX 2025-12-16: Add to DLQ on max retries exceeded
        self._add_to_dead_letter_queue(signal, side, str(last_error) if last_error else 'All quote currencies failed')
        return False, {'success': False, 'error': str(last_error)}
    
    def _add_to_dead_letter_queue(self, signal: Signal, side: str, error: str):
        """Add failed signal to Dead Letter Queue for later retry."""
        if not DLQ_AVAILABLE or add_to_dlq is None:
            logger.warning(f"DLQ not available - signal {signal.symbol} lost: {error}")
            return
        
        try:
            signal_data = {
                'symbol': signal.symbol,
                'action': signal.action,
                'quantity': signal.quantity,
                'price': signal.price,
                'stop_loss': signal.stop_loss,
                'take_profit': signal.take_profit,
                'leverage': signal.leverage,
                'order_type': signal.order_type,
                'confidence': signal.confidence,
                'side': side,
            }
            
            entry_id = add_to_dlq(
                signal_type=side,
                signal_data=signal_data,
                error=error,
                user_id=self.user_id,
                symbol=signal.symbol
            )
            logger.warning(f"📥 Failed signal added to DLQ: {entry_id[:8]} | {signal.symbol}")
        except Exception as e:
            logger.error(f"Failed to add signal to DLQ: {e}")
        
    async def run_cycle(self, external_market_data: Dict[str, MarketData] = None) -> List[Signal]:
        """Run one trading cycle - analyze and execute signals.
        
        Args:
            external_market_data: Optional pre-fetched market data to avoid duplicate API calls
        """
        if not self.active:
            return []
            
        executed_signals = []
        
        # Use external market data if provided, otherwise fetch fresh data
        if external_market_data:
            market_data = external_market_data
            logger.info(f"📊 Using pre-fetched market data for {len(market_data)} symbols")
        else:
            # CRITICAL FIX: Use real market data instead of mock
            market_data = await self.fetch_real_market_data()
            
            if not market_data:
                logger.warning("No market data available, skipping cycle")
                return []
            
            logger.info(f"📊 Fetched real market data for {len(market_data)} symbols")
        
        # Handle async vs sync broker and normalize positions to Dict
        if hasattr(self.broker, 'client'):
            positions_list = await self.broker.get_positions()
            # Convert List to Dict for strategy compatibility
            positions = {pos.symbol: pos for pos in positions_list} if positions_list else {}
        else:
            positions = self.broker.get_positions()
        
        # Portfolio Analysis (if available)
        portfolio_analysis = None
        if self.portfolio_manager:
            try:
                portfolio_analysis = await self.portfolio_manager.analyze_portfolio()
                logger.info(
                    f"📊 Portfolio: ${portfolio_analysis.total_value_usd:.2f} | "
                    f"Positions: {len(portfolio_analysis.positions)} | "
                    f"Diversification: {portfolio_analysis.diversification_score:.1f}%"
                )
                
                # Log any portfolio recommendations
                if portfolio_analysis.recommendations:
                    for rec in portfolio_analysis.recommendations[:3]:  # Top 3 recommendations
                        logger.info(f"📋 Portfolio Recommendation: {rec}")
            except Exception as e:
                logger.warning(f"Portfolio analysis failed: {e}")
        
        # Collect signals from all strategies (now supports async analyze)
        all_signals = []
        for strategy in self.strategies:
            if strategy.active:
                try:
                    # Support both async and sync strategies
                    if asyncio.iscoroutinefunction(strategy.analyze):
                        signals = await strategy.analyze(market_data, positions)
                    else:
                        signals = strategy.analyze(market_data, positions)
                    all_signals.extend(signals)
                except Exception as e:
                    logger.error(f"Strategy {strategy.name} analyze failed: {e}")
                
        # Sort by confidence and execute top signals
        all_signals.sort(key=lambda s: s.confidence, reverse=True)
        
        # P1-7 FIX: Filter out stale signals (older than MAX_SIGNAL_AGE_SECONDS)
        fresh_signals = []
        now = datetime.now()
        for signal in all_signals:
            if hasattr(signal, 'timestamp') and signal.timestamp:
                signal_age = (now - signal.timestamp).total_seconds()
                if signal_age > TradingConstants.MAX_SIGNAL_AGE_SECONDS:
                    logger.warning(
                        f"⏰ Skipping stale signal for {signal.symbol} - "
                        f"age: {signal_age:.1f}s > max: {TradingConstants.MAX_SIGNAL_AGE_SECONDS}s"
                    )
                    continue
            fresh_signals.append(signal)
        
        all_signals = fresh_signals
        
        for signal in all_signals[:TradingConstants.MAX_CONCURRENT_TRADES]:  # P2-4: Use constant
            try:
                # Skip if symbol not in market_data
                if signal.symbol not in market_data:
                    logger.warning(f"Symbol {signal.symbol} not in market_data, skipping")
                    continue
                
                # ===== PORTFOLIO AWARENESS CHECK =====
                if self.portfolio_manager:
                    try:
                        trade_decision = await self.portfolio_manager.evaluate_trade(
                            symbol=signal.symbol,
                            action=signal.action,
                            proposed_size_usd=signal.quantity * market_data[signal.symbol].current_price,
                            confidence=signal.confidence
                        )
                        
                        # Log portfolio decision
                        logger.info(
                            f"📊 Portfolio Decision for {signal.symbol}: "
                            f"{trade_decision.recommended_action.upper()} | "
                            f"execute={trade_decision.should_execute} | "
                            f"size_multiplier={trade_decision.position_size_multiplier:.2f}"
                        )
                        for reason in trade_decision.reasons:
                            logger.info(f"   └─ {reason}")
                        
                        # Skip if portfolio manager says no
                        if not trade_decision.should_execute:
                            logger.info(f"⏭️ Skipping {signal.symbol} - blocked by portfolio rules")
                            continue
                        
                        # Adjust position size based on portfolio context
                        if trade_decision.position_size_multiplier != 1.0:
                            original_qty = signal.quantity
                            signal.quantity *= trade_decision.position_size_multiplier
                            logger.info(
                                f"📐 Adjusted quantity for {signal.symbol}: "
                                f"{original_qty:.4f} → {signal.quantity:.4f} "
                                f"(×{trade_decision.position_size_multiplier:.2f})"
                            )
                    except Exception as pm_err:
                        logger.warning(f"Portfolio check failed for {signal.symbol}: {pm_err}")
                
                current_price = market_data[signal.symbol].current_price
                
                # P1-NEW-3 FIX: Ensure signal.price has a value for calculations
                # For market orders, use current_price if signal.price is None
                if signal.price is None or signal.price <= 0:
                    if signal.order_type == "market":
                        signal.price = current_price
                        logger.debug(f"📊 Using current price {current_price} for market order {signal.symbol}")
                    else:
                        # Limit order without price - should have been caught by validate_signal
                        logger.error(f"❌ Limit order {signal.symbol} has no price, skipping")
                        continue
                
                # ===== RISK MANAGER - POSITION SIZING & DYNAMIC SL/TP =====
                if self.risk_manager and signal.action in ['buy', 'sell']:
                    try:
                        # Calculate optimal position size
                        capital = await self._get_available_capital()
                        
                        # P0 FIX: Block trading if capital is 0 (unable to determine)
                        if capital <= 0:
                            logger.error(
                                f"🚫 TRADING BLOCKED for {signal.symbol}: "
                                f"Unable to determine available capital (capital={capital})"
                            )
                            continue
                        
                        # P0 FIX: Minimum capital requirement
                        MIN_TRADING_CAPITAL = 10.0  # $10 minimum to trade
                        if capital < MIN_TRADING_CAPITAL:
                            logger.warning(
                                f"⏭️ Skipping {signal.symbol} - "
                                f"Insufficient capital: ${capital:.2f} < ${MIN_TRADING_CAPITAL:.2f}"
                            )
                            continue
                        
                        size_result = await self.risk_manager.calculate_optimal_position_size(
                            symbol=signal.symbol,
                            capital=capital,
                            current_price=current_price,
                            confidence=signal.confidence,
                            user_id=self.user_id
                        )
                        
                        # NEW v2.5: Check if position was rejected (below exchange minimum)
                        if size_result.quantity <= 0:
                            rejection_reason = size_result.details.get('rejection_reason', 'Position size too small')
                            logger.warning(
                                f"⏭️ Skipping {signal.symbol} - Risk Manager rejected: {rejection_reason}"
                            )
                            continue
                        
                        if size_result.quantity > 0:
                            original_qty = signal.quantity
                            signal.quantity = size_result.quantity
                            
                            logger.info(
                                f"🛡️ Risk-Adjusted Position Size for {signal.symbol}: "
                                f"{original_qty:.4f} → {signal.quantity:.4f} | "
                                f"Method: {size_result.method_used} | "
                                f"Size: ${size_result.size_usd:.2f} | "
                                f"Capital: ${capital:.2f}"
                            )
                        
                        # Calculate dynamic SL/TP based on ATR
                        # L13 FIX: Pass user_id for user-specific SL/TP settings
                        new_sl, new_tp = await self.risk_manager.calculate_dynamic_sl_tp(
                            symbol=signal.symbol,
                            side='long' if signal.action == 'buy' else 'short',
                            entry_price=current_price,
                            signal_sl=signal.stop_loss,
                            signal_tp=signal.take_profit,
                            user_id=getattr(self, 'user_id', None)  # L13 FIX
                        )
                        
                        # Update signal with dynamic SL/TP (only if better than signal's)
                        if signal.action == 'buy':  # long
                            if new_sl and (signal.stop_loss is None or new_sl > signal.stop_loss):
                                logger.info(
                                    f"🎯 Dynamic SL for {signal.symbol}: "
                                    f"{signal.stop_loss} → {new_sl:.4f}"
                                )
                                signal.stop_loss = new_sl
                            if new_tp and (signal.take_profit is None or new_tp > signal.take_profit):
                                logger.info(
                                    f"🎯 Dynamic TP for {signal.symbol}: "
                                    f"{signal.take_profit} → {new_tp:.4f}"
                                )
                                signal.take_profit = new_tp
                        else:  # short
                            if new_sl and (signal.stop_loss is None or new_sl < signal.stop_loss):
                                signal.stop_loss = new_sl
                            if new_tp and (signal.take_profit is None or new_tp < signal.take_profit):
                                signal.take_profit = new_tp
                                
                    except Exception as rm_err:
                        logger.warning(f"Risk Manager adjustment failed for {signal.symbol}: {rm_err}")
                
                if signal.action == "buy":
                    # ===== NEW v2.0: LIQUIDITY CHECK =====
                    if MARKET_INTELLIGENCE_AVAILABLE and hasattr(self.broker, 'client'):
                        try:
                            mi = get_market_intelligence(self.broker.client)
                            order_value_usd = signal.quantity * current_price
                            liquidity = await mi.check_liquidity(signal.symbol, order_value_usd)
                            
                            if not liquidity.is_liquid:
                                logger.warning(
                                    f"❌ LIQUIDITY CHECK FAILED for {signal.symbol}: "
                                    f"spread={liquidity.bid_ask_spread_pct:.2f}%, "
                                    f"depth=${liquidity.order_book_depth_usd:,.0f}, "
                                    f"slippage={liquidity.estimated_slippage_pct:.2f}%"
                                )
                                for w in liquidity.warnings:
                                    logger.warning(f"  └─ {w}")
                                logger.warning(f"⏭️ Skipping {signal.symbol} - insufficient liquidity")
                                continue
                            else:
                                logger.info(
                                    f"✅ Liquidity OK for {signal.symbol}: "
                                    f"spread={liquidity.bid_ask_spread_pct:.2f}%, "
                                    f"slippage={liquidity.estimated_slippage_pct:.2f}%, "
                                    f"max_safe=${liquidity.max_safe_order_usd:,.0f}"
                                )
                        except Exception as liq_err:
                            logger.debug(f"Liquidity check error: {liq_err}")
                            # Continue with trade if liquidity check fails
                    
                    # ===== NEW v2.1: MARGIN CHECK BEFORE ORDER =====
                    if hasattr(self.broker, 'client'):
                        try:
                            leverage = signal.leverage or 1
                            margin_check = await self.broker.client.check_can_open_position(
                                signal.symbol, signal.quantity, current_price, leverage
                            )
                            if not margin_check.get('can_open', True):
                                logger.warning(
                                    f"❌ MARGIN CHECK FAILED for {signal.symbol}: {margin_check.get('reason')}"
                                )
                                suggestion = margin_check.get('suggestion', '')
                                if suggestion:
                                    logger.info(f"   💡 Suggestion: {suggestion}")
                                # Try to reduce position size to fit available margin
                                available_margin = margin_check.get('available_margin', 0)
                                if available_margin > 10:
                                    max_size_usd = available_margin * leverage * 0.8  # Use 80% of available
                                    new_quantity = max_size_usd / current_price
                                    if new_quantity >= 0.0001:  # Minimum tradeable amount
                                        logger.info(
                                            f"📊 Adjusting position size: {signal.quantity:.6f} → {new_quantity:.6f} "
                                            f"to fit available margin (${available_margin:.2f})"
                                        )
                                        signal.quantity = new_quantity
                                    else:
                                        logger.warning(f"⏭️ Skipping {signal.symbol} - insufficient margin even for minimum order")
                                        continue
                                else:
                                    logger.warning(f"⏭️ Skipping {signal.symbol} - insufficient margin")
                                    continue
                            else:
                                logger.info(
                                    f"✅ Margin OK for {signal.symbol}: "
                                    f"available=${margin_check.get('available_margin', 0):.2f}, "
                                    f"required=${margin_check.get('required_margin', 0):.2f}"
                                )
                        except Exception as margin_err:
                            logger.debug(f"Margin check error: {margin_err}")
                            # Continue with trade if margin check fails
                    
                    # ===== P0-6 FIX: VALIDATE MIN_NOTIONAL BEFORE ORDER =====
                    min_notional = await self._get_min_notional(signal.symbol)
                    order_value = signal.quantity * current_price
                    if order_value < min_notional:
                        logger.warning(
                            f"⏭️ Skipping {signal.symbol} - Order value ${order_value:.2f} "
                            f"below exchange minimum ${min_notional:.2f}"
                        )
                        continue
                    
                    # Check if it's LiveBroker (async) or PaperBroker (sync)
                    # ===== P0-5 FIX: ATOMIC ORDER + MONITOR REGISTRATION =====
                    order_success = False
                    order_result = None
                    
                    # ===== NEW v4.0: DCA MODE CHECK =====
                    # If DCA is enabled and we have DCA manager, use DCA execution
                    use_dca = False
                    if self.dca_manager:
                        try:
                            dca_settings = self.dca_manager.get_user_dca_settings()
                            use_dca = dca_settings.get('dca_enabled', False) if dca_settings else False
                        except Exception as dca_err:
                            logger.debug(f"DCA settings check failed: {dca_err}")
                    
                    if use_dca and self.dca_manager:
                        # ===== DCA EXECUTION =====
                        logger.info(f"💰 Using DCA mode for {signal.symbol}")
                        try:
                            # Prepare signal dict for DCA manager
                            signal_dict = {
                                'symbol': signal.symbol,
                                'action': signal.action,
                                'quantity': signal.quantity,
                                'price': current_price,
                                'stop_loss': signal.stop_loss,
                                'take_profit': signal.take_profit,
                                'leverage': getattr(signal, 'leverage', 1.0),
                                'confidence': signal.confidence,
                                'reason': signal.reason
                            }
                            
                            # Load DCA config from settings
                            dca_settings = self.dca_manager.get_user_dca_settings()
                            from bot.services.dca_manager import DCAConfig
                            dca_config = DCAConfig(
                                base_order_percent=dca_settings.get('base_order_percent', 40.0),
                                safety_order_count=dca_settings.get('safety_order_count', 3),
                                price_deviation_percent=dca_settings.get('price_deviation_percent', 3.0),
                                safety_order_scale=dca_settings.get('safety_order_scale', 1.0),
                                take_profit_percent=dca_settings.get('take_profit_percent', 5.0),
                                stop_loss_percent=dca_settings.get('stop_loss_percent', 10.0)
                            )
                            
                            # Open DCA position (base order + safety orders)
                            dca_position = await self.dca_manager.open_dca_position(
                                signal=signal_dict,
                                config=dca_config
                            )
                            
                            if dca_position:
                                order_success = True
                                logger.info(
                                    f"✅ DCA Position opened: {signal.symbol} | "
                                    f"Base: ${dca_position.total_invested:.2f} | "
                                    f"Safety Orders: {dca_config.safety_order_count} pending"
                                )
                            else:
                                logger.error(f"❌ DCA position creation failed for {signal.symbol}")
                                continue
                                
                        except Exception as dca_err:
                            logger.error(f"DCA execution failed for {signal.symbol}: {dca_err}")
                            # Fallback to normal order
                            use_dca = False
                    
                    # ===== NORMAL (non-DCA) EXECUTION =====
                    if not use_dca:
                        if hasattr(self.broker, 'client'):
                            # DEBUG: Log before calling broker
                            logger.debug(f"About to call broker.place_order for {signal.symbol} - SL={signal.stop_loss}, TP={signal.take_profit}")
                            # LiveBroker - run async method with RETRY logic (P1-5 FIX)
                            for retry_attempt in range(TradingConstants.ORDER_RETRY_COUNT):
                                try:
                                    result = await self.broker.place_order(
                                        side="buy",
                                        symbol=signal.symbol,
                                        order_type=signal.order_type,
                                        quantity=signal.quantity,
                                        market_price=current_price,
                                        price=signal.price,
                                        stop_loss=signal.stop_loss,
                                        take_profit=signal.take_profit,
                                        leverage=signal.leverage
                                    )
                                    # Check if order was successful
                                    if isinstance(result, dict) and not result.get('success', True):
                                        logger.error(f"Order failed (attempt {retry_attempt+1}/{TradingConstants.ORDER_RETRY_COUNT}): {result.get('error')}")
                                        if retry_attempt < TradingConstants.ORDER_RETRY_COUNT - 1:
                                            await asyncio.sleep(TradingConstants.ORDER_RETRY_DELAY_SECONDS)
                                            continue
                                        continue  # Skip to next signal after all retries
                                    order_success = True
                                    order_result = result
                                    break  # Success - exit retry loop
                                except Exception as order_err:
                                    logger.error(f"Order execution failed (attempt {retry_attempt+1}/{TradingConstants.ORDER_RETRY_COUNT}) for {signal.symbol}: {order_err}")
                                    if retry_attempt < TradingConstants.ORDER_RETRY_COUNT - 1:
                                        await asyncio.sleep(TradingConstants.ORDER_RETRY_DELAY_SECONDS)
                                        continue
                                    continue  # Skip to next signal after all retries
                        else:
                            # PaperBroker - sync method
                            try:
                                self.broker.place_order(
                                    side="buy",
                                    symbol=signal.symbol,
                                    order_type=signal.order_type,
                                    quantity=signal.quantity,
                                    market_price=current_price,
                                    price=signal.price,
                                    stop_loss=signal.stop_loss,
                                    take_profit=signal.take_profit,
                                    leverage=signal.leverage
                                )
                                order_success = True
                            except Exception as order_err:
                                logger.error(f"Order execution failed for {signal.symbol}: {order_err}")
                                continue
                    
                    # Only proceed with post-order actions if order was successful
                    if order_success:
                        executed_signals.append(signal)
                        
                        # P2-NEW-5 FIX: Limit trade_history size to prevent memory leak
                        self.trade_history.append((datetime.now(), signal))
                        if len(self.trade_history) > TradingConstants.MAX_TRADE_HISTORY_SIZE:
                            # Remove oldest 10% to avoid frequent resizing
                            remove_count = TradingConstants.MAX_TRADE_HISTORY_SIZE // 10
                            self.trade_history = self.trade_history[remove_count:]
                            logger.debug(f"🧹 Trimmed trade_history, removed {remove_count} oldest entries")
                        
                        logger.info(f"✅ Executed BUY: {signal.symbol} qty={signal.quantity} SL={signal.stop_loss} TP={signal.take_profit}")
                        
                        # Save trade to database (trades table - history)
                        self._save_trade_to_db(signal, current_price, "BUY")
                        
                        # 🔴 CRITICAL FIX: Save position to positions table as OPEN
                        # This enables Position Monitor to restore SL/TP after bot restart
                        try:
                            self._save_position_to_db(signal, current_price, "long")
                        except Exception as pos_err:
                            logger.error(f"❌ Failed to save position to DB: {pos_err}")
                        
                        # P0-5 FIX: Register with Position Monitor - CRITICAL for SL/TP protection
                        # If this fails, log error but don't rollback order (position exists on exchange)
                        try:
                            self._register_position_monitor(signal, current_price, "long")
                        except Exception as monitor_err:
                            logger.error(
                                f"🚨 CRITICAL: Position {signal.symbol} opened but NOT registered with monitor! "
                                f"Manual SL/TP management required. Error: {monitor_err}"
                            )
                            # TODO: Consider adding to a "orphaned positions" list for manual review
                
                elif signal.action == "sell":
                    # ===== NEW v2.0: LIQUIDITY CHECK FOR SELL =====
                    if MARKET_INTELLIGENCE_AVAILABLE and hasattr(self.broker, 'client'):
                        try:
                            mi = get_market_intelligence(self.broker.client)
                            order_value_usd = signal.quantity * current_price
                            liquidity = await mi.check_liquidity(signal.symbol, order_value_usd)
                            
                            if not liquidity.is_liquid:
                                logger.warning(
                                    f"❌ LIQUIDITY CHECK FAILED for {signal.symbol} (SELL): "
                                    f"spread={liquidity.bid_ask_spread_pct:.2f}%, "
                                    f"slippage={liquidity.estimated_slippage_pct:.2f}%"
                                )
                                for w in liquidity.warnings:
                                    logger.warning(f"  └─ {w}")
                                logger.warning(f"⏭️ Skipping {signal.symbol} - insufficient liquidity")
                                continue
                        except Exception as liq_err:
                            logger.debug(f"Liquidity check error (sell): {liq_err}")
                    
                    # ===== P0-6 FIX: VALIDATE MIN_NOTIONAL BEFORE ORDER =====
                    min_notional = await self._get_min_notional(signal.symbol)
                    order_value = signal.quantity * current_price
                    if order_value < min_notional:
                        logger.warning(
                            f"⏭️ Skipping {signal.symbol} SELL - Order value ${order_value:.2f} "
                            f"below exchange minimum ${min_notional:.2f}"
                        )
                        continue
                    
                    # ===== P0-5 FIX: ATOMIC ORDER + MONITOR REGISTRATION =====
                    order_success = False
                    
                    # Handle short selling
                    if hasattr(self.broker, 'client'):
                        try:
                            result = await self.broker.place_order(
                                side="sell",
                                symbol=signal.symbol,
                                order_type=signal.order_type,
                                quantity=signal.quantity,
                                market_price=current_price,
                                price=signal.price,
                                stop_loss=signal.stop_loss,
                                take_profit=signal.take_profit,
                                leverage=signal.leverage
                            )
                            if isinstance(result, dict) and not result.get('success', True):
                                logger.error(f"Order failed: {result.get('error')}")
                                continue
                            order_success = True
                        except Exception as order_err:
                            logger.error(f"SELL order execution failed for {signal.symbol}: {order_err}")
                            continue
                    else:
                        try:
                            self.broker.place_order(
                                side="sell",
                                symbol=signal.symbol,
                                order_type=signal.order_type,
                                quantity=signal.quantity,
                                market_price=current_price,
                                price=signal.price,
                                stop_loss=signal.stop_loss,
                                take_profit=signal.take_profit,
                                leverage=signal.leverage
                            )
                            order_success = True
                        except Exception as order_err:
                            logger.error(f"SELL order execution failed for {signal.symbol}: {order_err}")
                            continue
                    
                    # Only proceed with post-order actions if order was successful
                    if order_success:
                        executed_signals.append(signal)
                        
                        # P2-NEW-5 FIX: Limit trade_history size to prevent memory leak
                        self.trade_history.append((datetime.now(), signal))
                        if len(self.trade_history) > TradingConstants.MAX_TRADE_HISTORY_SIZE:
                            remove_count = TradingConstants.MAX_TRADE_HISTORY_SIZE // 10
                            self.trade_history = self.trade_history[remove_count:]
                            logger.debug(f"🧹 Trimmed trade_history, removed {remove_count} oldest entries")
                        
                        logger.info(f"✅ Executed SELL: {signal.symbol} qty={signal.quantity}")
                        
                        # Save trade to database (trades table - history)
                        self._save_trade_to_db(signal, current_price, "SELL")
                        
                        # 🔴 CRITICAL FIX: Save position to positions table as OPEN
                        # This enables Position Monitor to restore SL/TP after bot restart
                        try:
                            self._save_position_to_db(signal, current_price, "short")
                        except Exception as pos_err:
                            logger.error(f"❌ Failed to save SHORT position to DB: {pos_err}")
                        
                        # P0-5 FIX: Register with Position Monitor - CRITICAL for SL/TP protection
                        try:
                            self._register_position_monitor(signal, current_price, "short")
                        except Exception as monitor_err:
                            logger.error(
                                f"🚨 CRITICAL: SHORT Position {signal.symbol} opened but NOT registered with monitor! "
                                f"Manual SL/TP management required. Error: {monitor_err}"
                            )
                    
                elif signal.action == "close":
                    if hasattr(self.broker, 'client'):
                        success = await self.broker.close_position(symbol=signal.symbol)
                        if not success:
                            logger.error(f"Failed to close position: {signal.symbol}")
                            continue
                    else:
                        self.broker.close_position(symbol=signal.symbol)
                    executed_signals.append(signal)
                    
                    # P2-NEW-5 FIX: Limit trade_history size to prevent memory leak
                    self.trade_history.append((datetime.now(), signal))
                    if len(self.trade_history) > TradingConstants.MAX_TRADE_HISTORY_SIZE:
                        remove_count = TradingConstants.MAX_TRADE_HISTORY_SIZE // 10
                        self.trade_history = self.trade_history[remove_count:]
                    
                    logger.info(f"✅ Closed position: {signal.symbol}")
                    
                    # Save close trade to database
                    self._save_trade_to_db(signal, current_price, "CLOSE")
                    
                    # Remove from Position Monitor
                    self._unregister_position_monitor(signal.symbol)
                    
            except Exception as e:
                logger.error(f"Failed to execute signal {signal.action} {signal.symbol}: {e}")
                
        self.last_run = datetime.now()
        return executed_signals
    
    async def _get_available_capital(self) -> float:
        """Get available capital for position sizing.
        
        Enhanced v2.6: Better balance detection for multiple exchange types.
        """
        try:
            if hasattr(self.broker, 'client'):
                # LiveBroker - get real balance from exchange
                balance = await self.broker.get_balance()
                
                if balance:
                    logger.info(f"💰 Balance response keys: {list(balance.keys())}")
                    
                    # Check if it's our LiveBroker format with total_balance/available_balance
                    if 'available_balance' in balance:
                        capital = float(balance.get('available_balance', 0))
                        if capital > 1:
                            logger.info(f"💰 Using available_balance: ${capital:.2f}")
                            return capital
                        # Try total_balance as fallback
                        capital = float(balance.get('total_balance', 0))
                        if capital > 1:
                            logger.info(f"💰 Using total_balance: ${capital:.2f}")
                            return capital
                    
                    # If currencies dict is present, search there
                    currencies = balance.get('currencies', {})
                    if currencies:
                        logger.debug(f"💰 Currencies: {list(currencies.keys())[:15]}")
                        # P1-5 FIX: Extended quote currency list for all exchanges
                        # Kraken uses Z prefix (ZUSD, ZEUR), some use lowercase
                        quote_currencies = [
                            'USDT', 'USD', 'USDC', 'EUR', 'BUSD',  # Standard
                            'ZUSD', 'ZEUR', 'XXBT',  # Kraken format
                            'usdt', 'usd', 'usdc', 'eur',  # lowercase variants
                        ]
                        for currency in quote_currencies:
                            if currency in currencies:
                                val = currencies[currency]
                                # Handle both dict and float formats
                                if isinstance(val, dict):
                                    capital = float(val.get('free', val.get('available', 0)))
                                else:
                                    capital = float(val) if val else 0
                                if capital > 1:
                                    logger.info(f"💰 Found {currency}: ${capital:.2f}")
                                    return capital
                    
                    # P1-5 FIX: Extended quote currency search with multiple formats
                    # Check common quote currencies directly in balance (case-insensitive)
                    quote_currencies = [
                        'USDT', 'USD', 'USDC', 'EUR', 'BUSD',  # Standard
                        'ZUSD', 'ZEUR',  # Kraken
                        'UST',  # Some exchanges
                    ]
                    
                    # First pass: exact match for dict with 'free' key
                    for currency in quote_currencies:
                        if currency in balance and isinstance(balance[currency], dict):
                            capital = float(balance[currency].get('free', 0))
                            if capital > 1:
                                logger.info(f"💰 Found capital: {currency}=${capital:.2f}")
                                return capital
                    
                    # Second pass: case-insensitive match
                    balance_upper = {k.upper(): v for k, v in balance.items()}
                    for currency in quote_currencies:
                        if currency in balance_upper:
                            val = balance_upper[currency]
                            if isinstance(val, dict):
                                capital = float(val.get('free', 0))
                            else:
                                capital = float(val) if val else 0
                            if capital > 1:
                                logger.info(f"💰 Found capital (case-insensitive): {currency}=${capital:.2f}")
                                return capital
                
                logger.warning(f"💰 No suitable quote currency found in balance, using fallback")
            
            # Fallback: try from database or config
            if self.db_manager:
                try:
                    from bot.db import PortfolioSnapshot
                    with self.db_manager as db:
                        snapshot = (
                            db.session.query(PortfolioSnapshot)
                            .filter(PortfolioSnapshot.user_id == self.user_id)
                            .order_by(PortfolioSnapshot.timestamp.desc())
                            .first()
                        )
                        if snapshot and float(snapshot.available_balance) > 1:
                            logger.info(f"💰 Using capital from DB snapshot: ${float(snapshot.available_balance):.2f}")
                            return float(snapshot.available_balance)
                except Exception as db_err:
                    logger.debug(f"DB snapshot lookup failed: {db_err}")
            
            # CRITICAL FIX: Instead of hardcoded fallback, raise error or return 0
            # Trading with fake capital can cause real financial losses
            logger.error("💰 CRITICAL: Unable to determine available capital - trading blocked!")
            return 0.0  # Return 0 to block trading
            
        except Exception as e:
            logger.error(f"CRITICAL: Failed to get available capital: {e}")
            # Return 0 to block trading instead of fake $1000
            return 0.0
    
    async def _get_min_notional(self, symbol: str) -> float:
        """
        Get minimum order value (notional) for a symbol from exchange.
        
        P0-6 FIX: Validates orders meet exchange minimum requirements.
        
        Returns:
            Minimum order value in USD. Defaults to $5 if unable to fetch.
        """
        try:
            if hasattr(self.broker, 'client') and hasattr(self.broker.client, 'exchange'):
                exchange = self.broker.client.exchange
                
                # Try to get from exchange markets info
                if hasattr(exchange, 'markets') and exchange.markets:
                    market = exchange.markets.get(symbol)
                    if market:
                        # Try different possible keys for min notional
                        limits = market.get('limits', {})
                        cost_limits = limits.get('cost', {})
                        min_cost = cost_limits.get('min')
                        
                        if min_cost and min_cost > 0:
                            logger.debug(f"📊 Min notional for {symbol}: ${min_cost}")
                            return float(min_cost)
                        
                        # Some exchanges use 'minNotional' in info
                        info = market.get('info', {})
                        min_notional = info.get('minNotional') or info.get('min_notional')
                        if min_notional:
                            logger.debug(f"📊 Min notional for {symbol} (from info): ${min_notional}")
                            return float(min_notional)
                
                # P2-4: Fallback to centralized exchange-specific defaults
                exchange_id = getattr(exchange, 'id', '').lower()
                if exchange_id in TradingConstants.MIN_NOTIONAL_BY_EXCHANGE:
                    return TradingConstants.MIN_NOTIONAL_BY_EXCHANGE[exchange_id]
        
        except Exception as e:
            logger.debug(f"Could not fetch min_notional for {symbol}: {e}")
        
        # P2-4: Safe default from constants
        return TradingConstants.DEFAULT_MIN_NOTIONAL_USD
    
    def _register_position_monitor(self, signal: Signal, entry_price: float, side: str) -> None:
        """Register a new position with the Position Monitor for background SL/TP tracking."""
        if not self.position_monitor:
            return
            
        try:
            # Enable trailing stop for profitable trades
            trailing_enabled = True  # Enable by default
            
            # Default values for all features
            enable_quick_exit = False
            quick_exit_profit_pct = 0.5
            quick_exit_time_minutes = 30.0
            max_hold_hours = 12.0  # Default
            # v1.2: New feature defaults
            enable_break_even = True
            break_even_trigger_pct = 1.0
            break_even_buffer_pct = 0.1
            enable_momentum_scalp = False
            momentum_scalp_pct = 50.0
            momentum_scalp_minutes = 60
            enable_news_protection = False
            news_close_minutes_before = 30
            
            try:
                from bot.trading_config.trading_modes import get_mode
                mode_name = getattr(signal, 'trading_mode', 'day_trading') or 'day_trading'
                mode = get_mode(mode_name)
                if mode:
                    enable_quick_exit = mode.enable_quick_exit
                    quick_exit_profit_pct = mode.quick_exit_profit_pct
                    quick_exit_time_minutes = mode.quick_exit_time_minutes
                    max_hold_hours = mode.max_hold_hours
                    # v1.2: New features from trading mode
                    enable_break_even = mode.enable_break_even
                    break_even_trigger_pct = mode.break_even_trigger_pct
                    break_even_buffer_pct = mode.break_even_buffer_pct
                    enable_momentum_scalp = mode.enable_momentum_scalp
                    momentum_scalp_pct = mode.momentum_scalp_pct
                    momentum_scalp_minutes = mode.momentum_scalp_minutes
                    enable_news_protection = mode.enable_news_protection
                    news_close_minutes_before = mode.news_close_minutes_before
                    
                    logger.info(
                        f"🎯 Trading Mode: {mode_name} | "
                        f"QuickExit={enable_quick_exit} | BreakEven={enable_break_even} | "
                        f"MomentumScalp={enable_momentum_scalp} | NewsProtect={enable_news_protection}"
                    )
            except ImportError:
                logger.debug("Trading modes config not available, using defaults")
            
            self.position_monitor.add_position(
                symbol=signal.symbol,
                side=side,
                entry_price=entry_price,
                quantity=signal.quantity,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                user_id=self.user_id,
                trailing_enabled=trailing_enabled,
                dynamic_sl_enabled=True,  # Enable dynamic SL/TP adjustment
                max_hold_hours=max_hold_hours,
                # Quick Exit settings
                enable_quick_exit=enable_quick_exit,
                quick_exit_profit_pct=quick_exit_profit_pct,
                quick_exit_time_minutes=quick_exit_time_minutes,
                # v1.2: Smart Break-Even
                enable_break_even=enable_break_even,
                break_even_trigger_pct=break_even_trigger_pct,
                break_even_buffer_pct=break_even_buffer_pct,
                # v1.2: Momentum Scalper
                enable_momentum_scalp=enable_momentum_scalp,
                momentum_scalp_pct=momentum_scalp_pct,
                momentum_scalp_minutes=momentum_scalp_minutes,
                # v1.2: News Protection
                enable_news_protection=enable_news_protection,
                news_close_minutes_before=news_close_minutes_before
            )
            
            # Build feature flags for logging
            features = []
            if enable_quick_exit:
                features.append("QuickExit⚡")
            if enable_break_even:
                features.append("BreakEven🛡️")
            if enable_momentum_scalp:
                features.append("MomentumScalp🚀")
            if enable_news_protection:
                features.append("NewsProtect📰")
            features_str = " | ".join(features) if features else "Standard"
            
            logger.info(
                f"📍 Registered {signal.symbol} with Position Monitor | "
                f"SL={signal.stop_loss} TP={signal.take_profit} | "
                f"Features: {features_str}"
            )
        except Exception as e:
            logger.warning(f"Failed to register with Position Monitor: {e}")
    
    def _unregister_position_monitor(self, symbol: str) -> None:
        """Remove a position from the Position Monitor."""
        if not self.position_monitor:
            return
            
        try:
            self.position_monitor.remove_position(symbol, user_id=self.user_id)
        except Exception as e:
            logger.warning(f"Failed to unregister from Position Monitor: {e}")
        
    def get_status(self) -> Dict:
        """Get engine status."""
        return {
            "active": self.active,
            "strategies": [s.name for s in self.strategies],
            "last_run": self.last_run.isoformat(),
            "trade_count": len(self.trade_history),
            "position_monitor_active": bool(self.position_monitor),
            "risk_manager_active": bool(self.risk_manager)
        }
