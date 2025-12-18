"""
Risk Manager Service - Advanced risk management for trading positions.

Features:
1. Dynamic SL/TP - adjusts based on ATR/volatility
2. Trailing Stop - moves SL to lock in profits
3. Kelly Criterion - optimal position sizing based on win rate
4. Volatility-based sizing - adjusts size based on instrument volatility
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level categories."""
    CONSERVATIVE = "conservative"  # 0.5% risk per trade
    MODERATE = "moderate"          # 1% risk per trade
    AGGRESSIVE = "aggressive"      # 2% risk per trade


@dataclass
class UserRiskSettings:
    """
    User-specific risk settings from TradingSettings table.
    Maps to the Supabase trading_settings table.
    """
    user_id: str
    risk_level: int = 3  # 1-5 scale from database
    max_position_size: float = 1000.0  # Max position size in USD
    max_daily_loss: float = 100.0  # Max daily loss in USD
    stop_loss_percentage: float = 5.0  # Default SL % (changed from 5.0)
    take_profit_percentage: float = 3.0  # Default TP % (changed from 10.0)
    
    @property
    def risk_level_enum(self) -> RiskLevel:
        """Convert numeric risk level (1-5) to RiskLevel enum."""
        if self.risk_level <= 2:
            return RiskLevel.CONSERVATIVE
        elif self.risk_level >= 4:
            return RiskLevel.AGGRESSIVE
        else:
            return RiskLevel.MODERATE
    
    @property
    def risk_per_trade_percent(self) -> float:
        """
        Calculate risk per trade based on user's risk level (1-5).
        Level 1: 0.25%
        Level 2: 0.5%
        Level 3: 1.0%
        Level 4: 1.5%
        Level 5: 2.0%
        """
        risk_map = {
            1: 0.25,
            2: 0.5,
            3: 1.0,
            4: 1.5,
            5: 2.0
        }
        return risk_map.get(self.risk_level, 1.0)
    
    @classmethod
    def from_trading_settings(cls, settings, user_id: str = None) -> 'UserRiskSettings':
        """
        Create UserRiskSettings from TradingSettings model.
        Handles both SQLAlchemy model, dict input, and proxy objects.
        
        Args:
            settings: TradingSettings model, dict, or any object with attributes
            user_id: Optional user_id override (used when settings doesn't have user_id)
        """
        # Determine user_id
        uid = user_id
        if not uid:
            if hasattr(settings, 'user_id'):
                uid = str(settings.user_id)
            elif isinstance(settings, dict):
                uid = str(settings.get('user_id', ''))
            else:
                uid = ''
        
        if hasattr(settings, 'risk_level'):
            # Object with attributes (SQLAlchemy model or proxy object)
            return cls(
                user_id=uid,
                risk_level=int(settings.risk_level or 3),
                max_position_size=float(settings.max_position_size or 1000),
                max_daily_loss=float(settings.max_daily_loss or 100),
                stop_loss_percentage=float(settings.stop_loss_percentage or 5.0),
                take_profit_percentage=float(settings.take_profit_percentage or 3.0)  # Default TP=3%
            )
        elif isinstance(settings, dict):
            # Dictionary
            return cls(
                user_id=uid,
                risk_level=int(settings.get('risk_level', 3)),
                max_position_size=float(settings.get('max_position_size', 1000)),
                max_daily_loss=float(settings.get('max_daily_loss', 100)),
                stop_loss_percentage=float(settings.get('stop_loss_percentage', 5.0)),
                take_profit_percentage=float(settings.get('take_profit_percentage', 3.0))  # Default TP=3%
            )
        else:
            raise ValueError(f"Unknown settings type: {type(settings)}")


@dataclass
class ATRData:
    """Average True Range data for a symbol."""
    symbol: str
    atr_value: float
    atr_percent: float  # ATR as % of price
    period: int = 14
    calculated_at: datetime = field(default_factory=datetime.now)


@dataclass
class VolatilityProfile:
    """Volatility profile for position sizing."""
    symbol: str
    volatility_24h: float  # 24h volatility %
    volatility_7d: float   # 7d volatility %
    atr: ATRData
    risk_multiplier: float  # 1.0 = normal, <1 = reduce size, >1 = increase size
    
    @property
    def is_high_volatility(self) -> bool:
        return self.volatility_24h > 5.0 or self.atr.atr_percent > 3.0
    
    @property
    def is_low_volatility(self) -> bool:
        return self.volatility_24h < 2.0 and self.atr.atr_percent < 1.5


@dataclass
class TrailingStopConfig:
    """Configuration for trailing stop."""
    enabled: bool = True
    activation_profit_percent: float = 2.0  # FIXED: Activate after 2% profit (was 1%)
    trailing_distance_percent: float = 1.5  # FIXED: Trail by 1.5% (was 2%)
    step_size_percent: float = 0.5           # Move SL in 0.5% steps
    use_atr_distance: bool = True            # Use ATR for distance if available
    atr_multiplier: float = 2.0              # Trail at 2x ATR
    # NEW: Tiered trailing based on profit level
    tiered_trailing_enabled: bool = True
    tiers: Dict = None  # Will be set in __post_init__
    
    def __post_init__(self):
        """Initialize tiered trailing config."""
        if self.tiers is None:
            # profit_percent: trailing_distance_percent
            # More profit = tighter trailing to lock in gains
            self.tiers = {
                2.0: 1.5,   # At 2% profit, trail at 1.5%
                5.0: 1.0,   # At 5% profit, trail at 1.0%
                10.0: 0.75, # At 10% profit, trail at 0.75%
                20.0: 0.5,  # At 20% profit, trail at 0.5%
            }


@dataclass
class DynamicSLTPConfig:
    """Configuration for dynamic SL/TP."""
    enabled: bool = True
    use_atr: bool = True
    atr_multiplier_sl: float = 2.0   # SL at 2x ATR
    atr_multiplier_tp: float = 3.0   # TP at 3x ATR
    min_sl_percent: float = 1.0      # Minimum 1% SL
    max_sl_percent: float = 5.0      # Maximum 5% SL
    min_rr_ratio: float = 1.5        # Minimum Risk:Reward ratio


@dataclass
class KellyConfig:
    """Configuration for Kelly Criterion sizing."""
    enabled: bool = True
    fraction: float = 0.25           # Use 25% Kelly (fractional Kelly)
    min_trades_required: int = 10    # L7 FIX: Unified to 10 (was 5 here, 20 in auto_trader)
    fallback_risk_percent: float = 1.0  # Fallback if not enough data
    # NEW: Progressive Kelly - increases Kelly fraction as more data collected
    progressive_enabled: bool = True
    min_fraction: float = 0.1        # Start at 10% Kelly with few trades
    max_fraction: float = 0.35       # Max 35% Kelly with many trades
    full_kelly_trades: int = 50      # Full Kelly fraction after 50 trades


@dataclass
class PositionSizeResult:
    """Result of position size calculation."""
    quantity: float
    size_usd: float
    risk_amount: float
    method_used: str
    details: Dict = field(default_factory=dict)


@dataclass
class SLTPAdjustment:
    """Result of SL/TP adjustment calculation."""
    symbol: str
    old_stop_loss: Optional[float]
    new_stop_loss: Optional[float]
    old_take_profit: Optional[float]
    new_take_profit: Optional[float]
    reason: str
    should_update: bool


class RiskManagerService:
    """
    Comprehensive risk management service.
    
    Integrates with:
    - PositionMonitorService (for trailing stop updates)
    - PortfolioManagerService (for position sizing context)
    - AutoTradingEngine (for new trade sizing)
    - UserRiskSettings (for user-specific risk preferences)
    """
    
    # Default target leverage - will be reduced if exchange doesn't support
    DEFAULT_LEVERAGE = 10
    
    def __init__(
        self,
        exchange_adapter=None,
        risk_level: RiskLevel = RiskLevel.MODERATE,
        trailing_config: TrailingStopConfig = None,
        dynamic_sltp_config: DynamicSLTPConfig = None,
        kelly_config: KellyConfig = None,
        max_position_size_usd: float = 1000.0,
        default_leverage: float = 10.0,  # Default to 10x
        user_settings: UserRiskSettings = None  # NEW: User-specific settings
    ):
        self.exchange = exchange_adapter
        self.risk_level = risk_level
        self.trailing_config = trailing_config or TrailingStopConfig()
        self.dynamic_sltp_config = dynamic_sltp_config or DynamicSLTPConfig()
        self.kelly_config = kelly_config or KellyConfig()
        self.max_position_size_usd = max_position_size_usd
        self.default_leverage = default_leverage
        
        # User-specific risk settings
        self._user_settings: Dict[str, UserRiskSettings] = {}
        if user_settings:
            self._user_settings[user_settings.user_id] = user_settings
            # Apply user settings to default values
            self.max_position_size_usd = user_settings.max_position_size
            self.risk_level = user_settings.risk_level_enum
        
        # Cache for ATR and volatility data
        self._atr_cache: Dict[str, ATRData] = {}
        self._volatility_cache: Dict[str, VolatilityProfile] = {}
        self._cache_ttl = timedelta(minutes=15)
        
        # Trading statistics for Kelly
        self._trading_stats: Dict[str, Dict] = {}
        
        # Risk per trade based on level (fallback if no user settings)
        self._risk_per_trade = {
            RiskLevel.CONSERVATIVE: 0.005,  # 0.5%
            RiskLevel.MODERATE: 0.01,        # 1%
            RiskLevel.AGGRESSIVE: 0.02       # 2%
        }
        
        logger.info(
            f"🛡️ RiskManager initialized | Level: {risk_level.value} | "
            f"Max Position: ${max_position_size_usd:.0f} | "
            f"Trailing: {self.trailing_config.enabled} | "
            f"Dynamic SL/TP: {self.dynamic_sltp_config.enabled} | "
            f"Kelly: {self.kelly_config.enabled}"
        )
    
    # ========================================================================
    # USER SETTINGS MANAGEMENT
    # ========================================================================
    
    def set_user_settings(self, settings: UserRiskSettings) -> None:
        """
        Set or update risk settings for a specific user.
        This allows per-user position sizing configuration.
        """
        self._user_settings[settings.user_id] = settings
        logger.info(
            f"👤 User risk settings updated: {settings.user_id} | "
            f"Risk Level: {settings.risk_level}/5 ({settings.risk_per_trade_percent}% per trade) | "
            f"Max Position: ${settings.max_position_size:.0f} | "
            f"SL: {settings.stop_loss_percentage}% | TP: {settings.take_profit_percentage}%"
        )
    
    def get_user_settings(self, user_id: str) -> Optional[UserRiskSettings]:
        """Get risk settings for a specific user."""
        return self._user_settings.get(user_id)
    
    def load_user_settings_from_db(self, user_id: str) -> Optional[UserRiskSettings]:
        """
        Load user settings from database (TradingSettings table).
        Returns None if user not found.
        """
        try:
            from bot.models_legacy import TradingSettings, db
            
            with db.session_scope() as session:
                settings = (
                    session.query(TradingSettings)
                    .filter(TradingSettings.user_id == user_id)
                    .first()
                )
                
                if settings:
                    user_settings = UserRiskSettings.from_trading_settings(settings)
                    self._user_settings[user_id] = user_settings
                    logger.info(f"📥 Loaded user settings from DB for: {user_id}")
                    return user_settings
                    
        except Exception as e:
            logger.warning(f"Could not load user settings from DB: {e}")
        
        return None
    
    def get_risk_per_trade(self, user_id: Optional[str] = None) -> float:
        """
        Get risk per trade percentage for a user.
        Uses user-specific settings if available, otherwise falls back to default.
        
        Returns:
            Risk percentage as decimal (e.g., 0.01 for 1%)
        """
        if user_id and user_id in self._user_settings:
            return self._user_settings[user_id].risk_per_trade_percent / 100
        return self._risk_per_trade[self.risk_level]
    
    def get_max_position_size(self, user_id: Optional[str] = None) -> float:
        """
        Get max position size for a user in USD.
        Uses user-specific settings if available.
        """
        if user_id and user_id in self._user_settings:
            return self._user_settings[user_id].max_position_size
        return self.max_position_size_usd
    
    def get_default_sl_tp(self, user_id: Optional[str] = None) -> Tuple[float, float]:
        """
        Get default stop loss and take profit percentages for a user.
        
        Returns:
            Tuple of (stop_loss_percent, take_profit_percent)
        """
        if user_id and user_id in self._user_settings:
            settings = self._user_settings[user_id]
            return (settings.stop_loss_percentage, settings.take_profit_percentage)
        # Default values: SL=5%, TP=3%
        return (5.0, 3.0)
    
    # ========================================================================
    # ATR & VOLATILITY CALCULATION
    # ========================================================================
    
    async def calculate_atr(
        self,
        symbol: str,
        period: int = 14,
        timeframe: str = '1h'
    ) -> Optional[ATRData]:
        """
        Calculate Average True Range for a symbol.
        
        ATR = Moving Average of True Range
        True Range = max(high-low, |high-prev_close|, |low-prev_close|)
        """
        # Check cache
        cache_key = f"{symbol}_{period}"
        if cache_key in self._atr_cache:
            cached = self._atr_cache[cache_key]
            if datetime.now() - cached.calculated_at < self._cache_ttl:
                return cached
        
        try:
            if not self.exchange:
                logger.warning("No exchange adapter - cannot calculate ATR")
                return None
            
            # Fetch OHLCV data
            ohlcv = await self._fetch_ohlcv(symbol, timeframe, limit=period + 10)
            
            if not ohlcv or len(ohlcv) < period + 1:
                logger.warning(f"Insufficient OHLCV data for ATR: {symbol}")
                return None
            
            # Calculate True Range for each candle
            true_ranges = []
            for i in range(1, len(ohlcv)):
                high = ohlcv[i][2]
                low = ohlcv[i][3]
                prev_close = ohlcv[i-1][4]
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)
            
            # Calculate ATR (Simple Moving Average of TR)
            if len(true_ranges) >= period:
                atr_value = sum(true_ranges[-period:]) / period
            else:
                atr_value = sum(true_ranges) / len(true_ranges)
            
            # Get current price for percentage calculation
            current_price = ohlcv[-1][4]  # Last close
            atr_percent = (atr_value / current_price) * 100 if current_price > 0 else 0
            
            atr_data = ATRData(
                symbol=symbol,
                atr_value=atr_value,
                atr_percent=atr_percent,
                period=period
            )
            
            # Cache result
            self._atr_cache[cache_key] = atr_data
            
            logger.debug(
                f"📊 ATR({period}) for {symbol}: {atr_value:.4f} ({atr_percent:.2f}%)"
            )
            
            return atr_data
            
        except Exception as e:
            logger.error(f"Failed to calculate ATR for {symbol}: {e}")
            return None
    
    async def get_volatility_profile(self, symbol: str) -> Optional[VolatilityProfile]:
        """Get comprehensive volatility profile for a symbol."""
        # Check cache
        if symbol in self._volatility_cache:
            cached = self._volatility_cache[symbol]
            if datetime.now() - cached.atr.calculated_at < self._cache_ttl:
                return cached
        
        try:
            # Get ATR
            atr = await self.calculate_atr(symbol)
            if not atr:
                return None
            
            # Get 24h stats from ticker
            volatility_24h = 0.0
            volatility_7d = 0.0
            
            if self.exchange:
                try:
                    ticker = await self._fetch_ticker(symbol)
                    if ticker:
                        # Use percentage change as volatility proxy
                        volatility_24h = abs(ticker.get('percentage', 0) or 0)
                        
                        # Estimate 7d from 24h (rough approximation)
                        volatility_7d = volatility_24h * 2.5  # Rough estimate
                except Exception:
                    pass
            
            # Calculate risk multiplier
            # High volatility = lower multiplier (smaller position)
            # Low volatility = higher multiplier (larger position)
            if atr.atr_percent > 4.0:
                risk_multiplier = 0.5  # Very high volatility - halve position
            elif atr.atr_percent > 3.0:
                risk_multiplier = 0.7
            elif atr.atr_percent > 2.0:
                risk_multiplier = 0.85
            elif atr.atr_percent < 1.0:
                risk_multiplier = 1.2  # Low volatility - can size up slightly
            else:
                risk_multiplier = 1.0  # Normal
            
            profile = VolatilityProfile(
                symbol=symbol,
                volatility_24h=volatility_24h,
                volatility_7d=volatility_7d,
                atr=atr,
                risk_multiplier=risk_multiplier
            )
            
            # Cache
            self._volatility_cache[symbol] = profile
            
            logger.debug(
                f"📊 Volatility Profile {symbol}: ATR={atr.atr_percent:.2f}% | "
                f"24h={volatility_24h:.2f}% | multiplier={risk_multiplier:.2f}"
            )
            
            return profile
            
        except Exception as e:
            logger.error(f"Failed to get volatility profile for {symbol}: {e}")
            return None
    
    # ========================================================================
    # DYNAMIC SL/TP
    # ========================================================================
    
    async def calculate_dynamic_sl_tp(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        signal_sl: Optional[float] = None,
        signal_tp: Optional[float] = None,
        user_id: Optional[str] = None  # L13 FIX: Added user_id parameter
    ) -> Tuple[float, float]:
        """
        Calculate dynamic SL/TP based on ATR and volatility.
        
        L13 FIX (2025-12-14): Now uses user-specific SL/TP settings from trading_settings
        
        Args:
            symbol: Trading pair
            side: 'long' or 'short'
            entry_price: Entry price
            signal_sl: SL from signal (optional, used as baseline)
            signal_tp: TP from signal (optional, used as baseline)
            user_id: User ID to get user-specific SL/TP settings
        
        Returns:
            Tuple of (stop_loss, take_profit)
        """
        config = self.dynamic_sltp_config
        
        if not config.enabled:
            # L13 FIX: Use user-specific SL/TP if available, otherwise defaults
            user_sl_pct, user_tp_pct = self.get_default_sl_tp(user_id)
            default_sl_pct = user_sl_pct / 100.0  # Convert from % to decimal
            default_tp_pct = user_tp_pct / 100.0  # Convert from % to decimal
            
            logger.debug(
                f"🎯 Using user SL/TP settings: SL={default_sl_pct*100:.1f}% | TP={default_tp_pct*100:.1f}% "
                f"(user_id={user_id[:8] if user_id else 'None'}...)"
            )
            
            if side == 'long':
                sl = signal_sl or entry_price * (1 - default_sl_pct)
                tp = signal_tp or entry_price * (1 + default_tp_pct)
            else:
                sl = signal_sl or entry_price * (1 + default_sl_pct)
                tp = signal_tp or entry_price * (1 - default_tp_pct)
            
            return sl, tp
        
        # Get ATR for dynamic calculation
        atr = await self.calculate_atr(symbol)
        
        if atr and config.use_atr:
            # ATR-based SL/TP
            sl_distance = atr.atr_value * config.atr_multiplier_sl
            tp_distance = atr.atr_value * config.atr_multiplier_tp
            
            # Ensure minimum R:R ratio
            if tp_distance / sl_distance < config.min_rr_ratio:
                tp_distance = sl_distance * config.min_rr_ratio
            
            # Convert to percentages for bounds checking
            sl_pct = sl_distance / entry_price
            tp_pct = tp_distance / entry_price
            
            # Apply bounds
            sl_pct = max(config.min_sl_percent / 100, min(sl_pct, config.max_sl_percent / 100))
            
            if side == 'long':
                stop_loss = entry_price * (1 - sl_pct)
                take_profit = entry_price * (1 + tp_pct)
            else:
                stop_loss = entry_price * (1 + sl_pct)
                take_profit = entry_price * (1 - tp_pct)
            
            # Calculate R:R ratio safely (avoid division by zero)
            rr_ratio = tp_pct / sl_pct if sl_pct > 0 else 0
            
            logger.info(
                f"🎯 Dynamic SL/TP for {symbol} ({side}): "
                f"SL={stop_loss:.4f} ({sl_pct*100:.2f}%) | "
                f"TP={take_profit:.4f} ({tp_pct*100:.2f}%) | "
                f"R:R=1:{rr_ratio:.1f}"
            )
            
        else:
            # Fallback to percentage-based
            sl_pct = config.min_sl_percent / 100
            tp_pct = sl_pct * config.min_rr_ratio
            
            if side == 'long':
                stop_loss = signal_sl or entry_price * (1 - sl_pct)
                take_profit = signal_tp or entry_price * (1 + tp_pct)
            else:
                stop_loss = signal_sl or entry_price * (1 + sl_pct)
                take_profit = signal_tp or entry_price * (1 - tp_pct)
        
        return stop_loss, take_profit
    
    async def should_adjust_sl_tp(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        current_price: float,
        current_sl: Optional[float],
        current_tp: Optional[float]
    ) -> SLTPAdjustment:
        """
        Determine if SL/TP should be adjusted based on current market conditions.
        
        This is called periodically to check if existing SL/TP need updates.
        """
        # Get fresh ATR
        atr = await self.calculate_atr(symbol)
        
        if not atr:
            return SLTPAdjustment(
                symbol=symbol,
                old_stop_loss=current_sl,
                new_stop_loss=current_sl,
                old_take_profit=current_tp,
                new_take_profit=current_tp,
                reason="No ATR data available",
                should_update=False
            )
        
        # Calculate what SL/TP should be based on current price
        new_sl, new_tp = await self.calculate_dynamic_sl_tp(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            signal_sl=current_sl,
            signal_tp=current_tp
        )
        
        # For long positions: only tighten SL (move up), never loosen
        # For short positions: only tighten SL (move down), never loosen
        should_update = False
        reason = ""
        
        if side == 'long':
            # Can only move SL up
            if current_sl and new_sl and new_sl > current_sl:
                should_update = True
                reason = f"Tightening SL based on volatility: {current_sl:.4f} → {new_sl:.4f}"
            else:
                new_sl = current_sl  # Keep current
                
            # TP can be adjusted in either direction (only if both values exist and TP > 0)
            if current_tp and new_tp and current_tp > 0 and abs(new_tp - current_tp) / current_tp > 0.02:  # >2% difference
                should_update = True
                reason += f" | Adjusting TP: {current_tp:.4f} → {new_tp:.4f}"
            else:
                new_tp = current_tp
                
        else:  # short
            # Can only move SL down
            if current_sl and new_sl and new_sl < current_sl:
                should_update = True
                reason = f"Tightening SL based on volatility: {current_sl:.4f} → {new_sl:.4f}"
            else:
                new_sl = current_sl
                
            # TP can be adjusted (only if both values exist and TP > 0)
            if current_tp and new_tp and current_tp > 0 and abs(new_tp - current_tp) / current_tp > 0.02:
                should_update = True
                reason += f" | Adjusting TP: {current_tp:.4f} → {new_tp:.4f}"
            else:
                new_tp = current_tp
        
        return SLTPAdjustment(
            symbol=symbol,
            old_stop_loss=current_sl,
            new_stop_loss=new_sl,
            old_take_profit=current_tp,
            new_take_profit=new_tp,
            reason=reason or "No adjustment needed",
            should_update=should_update
        )
    
    # ========================================================================
    # TRAILING STOP
    # ========================================================================
    
    def calculate_trailing_stop(
        self,
        side: str,
        entry_price: float,
        current_price: float,
        current_sl: Optional[float],
        highest_price: Optional[float],  # For long
        lowest_price: Optional[float],   # For short
        atr: Optional[ATRData] = None
    ) -> Tuple[Optional[float], Optional[float], Optional[float], bool]:
        """
        Calculate trailing stop level with tiered trailing support.
        
        v2.0: Tiered trailing - tighter trailing at higher profit levels.
        
        Returns:
            Tuple of (new_sl, updated_highest, updated_lowest, should_update)
        """
        config = self.trailing_config
        
        if not config.enabled or current_sl is None:
            return current_sl, highest_price, lowest_price, False
        
        should_update = False
        new_sl = current_sl
        
        if side == 'long':
            # Track highest price
            if highest_price is None or current_price > highest_price:
                highest_price = current_price
            
            # Check if profit threshold is met
            profit_percent = ((current_price - entry_price) / entry_price) * 100
            
            if profit_percent >= config.activation_profit_percent:
                # P2 FIX: Use tiered trailing distance based on profit level
                trailing_distance_pct = self._get_tiered_trailing_distance(profit_percent)
                
                # Calculate trailing distance (prefer ATR if available and reasonable)
                if config.use_atr_distance and atr:
                    atr_distance = atr.atr_value * config.atr_multiplier
                    pct_distance = current_price * (trailing_distance_pct / 100)
                    # Use the smaller of ATR and tiered percentage for tighter trailing
                    trailing_distance = min(atr_distance, pct_distance)
                else:
                    trailing_distance = current_price * (trailing_distance_pct / 100)
                
                # Calculate new trailing SL
                trailing_sl = highest_price - trailing_distance
                
                # Apply step size (round to step increments)
                step_size = entry_price * (config.step_size_percent / 100)
                trailing_sl = round(trailing_sl / step_size) * step_size
                
                # Only move SL up, never down
                if trailing_sl > current_sl:
                    # Ensure we don't exceed current price minus minimum distance
                    min_distance = entry_price * 0.005  # Minimum 0.5% from current price
                    max_sl = current_price - min_distance
                    
                    new_sl = min(trailing_sl, max_sl)
                    should_update = True
                    
                    logger.info(
                        f"📈 Trailing Stop LONG {entry_price:.2f}: "
                        f"SL {current_sl:.4f} → {new_sl:.4f} | "
                        f"Price: {current_price:.4f} | High: {highest_price:.4f} | "
                        f"Profit: {profit_percent:.2f}% | Trail: {trailing_distance_pct:.1f}%"
                    )
        
        else:  # short
            # Track lowest price
            if lowest_price is None or current_price < lowest_price:
                lowest_price = current_price
            
            # Check if profit threshold is met
            profit_percent = ((entry_price - current_price) / entry_price) * 100
            
            if profit_percent >= config.activation_profit_percent:
                # P2 FIX: Use tiered trailing distance
                trailing_distance_pct = self._get_tiered_trailing_distance(profit_percent)
                
                if config.use_atr_distance and atr:
                    atr_distance = atr.atr_value * config.atr_multiplier
                    pct_distance = current_price * (trailing_distance_pct / 100)
                    trailing_distance = min(atr_distance, pct_distance)
                else:
                    trailing_distance = current_price * (trailing_distance_pct / 100)
                
                # Calculate new trailing SL
                trailing_sl = lowest_price + trailing_distance
                
                # Apply step size
                step_size = entry_price * (config.step_size_percent / 100)
                trailing_sl = round(trailing_sl / step_size) * step_size
                
                # Only move SL down, never up
                if trailing_sl < current_sl:
                    # Ensure minimum distance from current price
                    min_distance = entry_price * 0.005
                    min_sl = current_price + min_distance
                    
                    new_sl = max(trailing_sl, min_sl)
                    should_update = True
                    
                    logger.info(
                        f"📈 Trailing Stop SHORT {entry_price:.2f}: "
                        f"SL {current_sl:.4f} → {new_sl:.4f} | "
                        f"Price: {current_price:.4f} | Low: {lowest_price:.4f} | "
                        f"Profit: {profit_percent:.2f}%"
                    )
        
        return new_sl, highest_price, lowest_price, should_update
    
    def _get_tiered_trailing_distance(self, profit_percent: float) -> float:
        """
        Get trailing distance based on profit level (tiered trailing).
        
        Higher profits = tighter trailing to lock in gains.
        
        Args:
            profit_percent: Current profit percentage
            
        Returns:
            Trailing distance percentage
        """
        config = self.trailing_config
        
        if not config.tiered_trailing_enabled or not config.tiers:
            return config.trailing_distance_percent
        
        # Find the appropriate tier
        # Tiers are profit_percent -> trailing_distance_percent
        applicable_distance = config.trailing_distance_percent
        
        for tier_profit, tier_distance in sorted(config.tiers.items()):
            if profit_percent >= tier_profit:
                applicable_distance = tier_distance
        
        return applicable_distance
    
    # ========================================================================
    # KELLY CRITERION SIZING
    # ========================================================================
    
    async def calculate_kelly_size(
        self,
        symbol: str,
        capital: float,
        current_price: float,
        user_id: Optional[str] = None
    ) -> PositionSizeResult:
        """
        Calculate position size using Kelly Criterion.
        
        Kelly Formula: f* = (bp - q) / b
        where:
            b = win/loss ratio (avg_win / avg_loss)
            p = probability of winning (win_rate)
            q = probability of losing (1 - p)
            
        v2.0 FIX: Progressive Kelly - starts conservative with few trades,
        increases as more data collected.
        """
        config = self.kelly_config
        
        if not config.enabled:
            return self._calculate_fixed_risk_size(
                capital=capital,
                current_price=current_price,
                risk_percent=config.fallback_risk_percent,
                method="fixed_risk"
            )
        
        # Get trading statistics
        stats = await self._get_trading_stats(symbol, user_id)
        
        if stats['total_trades'] < config.min_trades_required:
            logger.info(
                f"📊 Kelly: Insufficient trades ({stats['total_trades']}/{config.min_trades_required}) "
                f"for {symbol} - using fallback"
            )
            return self._calculate_fixed_risk_size(
                capital=capital,
                current_price=current_price,
                risk_percent=config.fallback_risk_percent,
                method="kelly_fallback"
            )
        
        win_rate = stats['win_rate']
        avg_win = stats['avg_win']
        avg_loss = abs(stats['avg_loss'])
        
        if avg_loss <= 0:
            logger.warning(f"Invalid avg_loss for Kelly: {avg_loss}")
            return self._calculate_fixed_risk_size(
                capital=capital,
                current_price=current_price,
                risk_percent=config.fallback_risk_percent,
                method="kelly_fallback"
            )
        
        # Calculate Kelly fraction
        b = avg_win / avg_loss  # Win/Loss ratio
        p = win_rate
        q = 1 - p
        
        full_kelly = (b * p - q) / b
        
        # Apply fractional Kelly with progressive scaling
        # FIX: Progressive Kelly - use smaller fraction with fewer trades
        if config.progressive_enabled:
            trade_count = stats['total_trades']
            # Linear interpolation between min_fraction and max_fraction
            # based on trade count from min_trades_required to full_kelly_trades
            if trade_count >= config.full_kelly_trades:
                effective_fraction = config.max_fraction
            else:
                # Scale from min to max as trades increase
                progress = (trade_count - config.min_trades_required) / (config.full_kelly_trades - config.min_trades_required)
                progress = max(0, min(1, progress))
                effective_fraction = config.min_fraction + (config.max_fraction - config.min_fraction) * progress
            
            logger.debug(
                f"Progressive Kelly: {trade_count} trades -> {effective_fraction:.1%} fraction "
                f"(range: {config.min_fraction:.0%}-{config.max_fraction:.0%})"
            )
        else:
            effective_fraction = config.fraction
        
        kelly_fraction = max(0, min(full_kelly, 1.0)) * effective_fraction
        
        # Calculate position size
        risk_amount = capital * kelly_fraction
        size_usd = min(risk_amount, self.max_position_size_usd)
        quantity = size_usd / current_price if current_price > 0 else 0
        
        logger.info(
            f"📊 Kelly Criterion for {symbol}: "
            f"Win Rate={win_rate:.1%} | W/L Ratio={b:.2f} | "
            f"Full Kelly={full_kelly:.1%} | "
            f"Effective Fraction={effective_fraction:.0%} | "
            f"Applied Kelly={kelly_fraction:.1%} | "
            f"Size=${size_usd:.2f}"
        )
        
        return PositionSizeResult(
            quantity=quantity,
            size_usd=size_usd,
            risk_amount=risk_amount,
            method_used="kelly_criterion",
            details={
                'win_rate': win_rate,
                'win_loss_ratio': b,
                'full_kelly': full_kelly,
                'kelly_fraction': kelly_fraction,
                'effective_fraction': effective_fraction,
                'progressive_enabled': config.progressive_enabled,
                'total_trades': stats['total_trades'],
                'avg_win': avg_win,
                'avg_loss': avg_loss
            }
        )
    
    # ========================================================================
    # VOLATILITY-BASED SIZING
    # ========================================================================
    
    async def calculate_volatility_adjusted_size(
        self,
        symbol: str,
        capital: float,
        current_price: float,
        base_stop_loss_percent: float = None,
        user_id: Optional[str] = None
    ) -> PositionSizeResult:
        """
        Calculate position size adjusted for volatility and user settings.
        
        Formula:
        Position Size = (Capital × Risk%) / (Entry Price × SL Distance)
        
        With volatility adjustment:
        - Higher volatility → smaller position
        - Lower volatility → larger position (capped)
        
        Uses user-specific settings if user_id is provided.
        """
        # Get user-specific risk settings or use defaults
        risk_percent = self.get_risk_per_trade(user_id)
        max_position = self.get_max_position_size(user_id)
        default_sl, _ = self.get_default_sl_tp(user_id)
        
        # Use user's default SL if not provided
        if base_stop_loss_percent is None:
            base_stop_loss_percent = default_sl
        
        # Get volatility profile
        profile = await self.get_volatility_profile(symbol)
        
        if profile:
            # Use ATR for stop loss distance
            sl_distance_percent = max(
                base_stop_loss_percent / 100,
                profile.atr.atr_percent * 2 / 100  # 2x ATR
            )
            
            # Apply volatility multiplier
            risk_multiplier = profile.risk_multiplier
        else:
            sl_distance_percent = base_stop_loss_percent / 100
            risk_multiplier = 1.0
        
        # Calculate base position size
        risk_amount = capital * risk_percent
        base_size_usd = risk_amount / sl_distance_percent
        
        # Apply volatility adjustment
        adjusted_size_usd = base_size_usd * risk_multiplier
        
        # Apply user's max position size cap
        final_size_usd = min(adjusted_size_usd, max_position)
        quantity = final_size_usd / current_price if current_price > 0 else 0
        
        logger.info(
            f"📊 Volatility-Adjusted Size for {symbol}: "
            f"Risk={risk_percent:.1%} | SL Distance={sl_distance_percent:.2%} | "
            f"Vol Multiplier={risk_multiplier:.2f} | "
            f"Max Position=${max_position:.0f} | "
            f"Size: ${base_size_usd:.2f} → ${final_size_usd:.2f}"
        )
        
        return PositionSizeResult(
            quantity=quantity,
            size_usd=final_size_usd,
            risk_amount=risk_amount,
            method_used="volatility_adjusted",
            details={
                'risk_percent': risk_percent,
                'sl_distance_percent': sl_distance_percent,
                'volatility_multiplier': risk_multiplier,
                'base_size_usd': base_size_usd,
                'max_position_size': max_position,
                'user_id': user_id,
                'atr_percent': profile.atr.atr_percent if profile else None
            }
        )
    
    # ========================================================================
    # COMBINED POSITION SIZING
    # ========================================================================
    
    async def calculate_optimal_position_size(
        self,
        symbol: str,
        capital: float,
        current_price: float,
        confidence: float = 0.5,
        user_id: Optional[str] = None
    ) -> PositionSizeResult:
        """
        Calculate optimal position size combining Kelly and Volatility methods.
        Uses user-specific settings if user_id is provided.
        
        Strategy:
        1. Get Kelly size (based on historical performance)
        2. Get Volatility-adjusted size (based on current market conditions + user settings)
        3. Take the smaller of the two (conservative approach)
        4. Adjust by signal confidence
        5. Cap at user's max_position_size
        6. NEW: Validate against exchange minimums BEFORE returning
        """
        # Get user-specific max position size
        max_position = self.get_max_position_size(user_id)
        
        # ========================================
        # NEW v2.5: Get exchange minimums FIRST
        # ========================================
        exchange_min_cost = 10.0  # Default minimum
        exchange_min_amount = 0.0001
        
        if self.exchange:
            try:
                if hasattr(self.exchange, 'get_min_order_amount'):
                    minimums = await self.exchange.get_min_order_amount(symbol, current_price)
                    exchange_min_cost = minimums.get('min_cost', 10.0)
                    exchange_min_amount = minimums.get('min_amount', 0.0001)
                    logger.debug(f"📊 Exchange minimums for {symbol}: ${exchange_min_cost:.2f} min cost, {exchange_min_amount} min amount")
            except Exception as e:
                logger.debug(f"Could not get exchange minimums: {e}")
        
        # Calculate both sizes with user settings
        kelly_result = await self.calculate_kelly_size(
            symbol=symbol,
            capital=capital,
            current_price=current_price,
            user_id=user_id
        )
        
        vol_result = await self.calculate_volatility_adjusted_size(
            symbol=symbol,
            capital=capital,
            current_price=current_price,
            user_id=user_id  # Pass user_id for user-specific settings
        )
        
        # Take the smaller (more conservative)
        if kelly_result.size_usd <= vol_result.size_usd:
            base_result = kelly_result
            secondary_method = "volatility_adjusted"
            secondary_size = vol_result.size_usd
        else:
            base_result = vol_result
            secondary_method = "kelly_criterion"
            secondary_size = kelly_result.size_usd
        
        # Adjust by confidence (0.5-1.0 → 0.5-1.0 multiplier)
        confidence_multiplier = 0.5 + (confidence * 0.5)  # Maps 0→0.5, 1→1.0
        
        # Apply confidence multiplier
        adjusted_size_usd = base_result.size_usd * confidence_multiplier
        
        # Final cap with user's max position size
        final_size_usd = min(adjusted_size_usd, max_position)
        final_quantity = final_size_usd / current_price if current_price > 0 else 0
        
        # ========================================
        # NEW v2.5: Validate against exchange minimum BEFORE returning
        # ========================================
        order_value = final_quantity * current_price
        
        if order_value < exchange_min_cost or final_quantity < exchange_min_amount:
            # Position is below exchange minimum
            min_qty_by_cost = (exchange_min_cost * 1.1) / current_price  # 10% buffer
            required_min_qty = max(min_qty_by_cost, exchange_min_amount)
            required_min_value = required_min_qty * current_price
            
            # Check if user can afford minimum
            if required_min_value <= max_position and required_min_value <= capital * 0.5:
                # INCREASE to minimum
                logger.info(
                    f"📊 Position ${order_value:.2f} below exchange min ${exchange_min_cost:.2f}. "
                    f"INCREASING: {final_quantity:.6f} → {required_min_qty:.6f} (${required_min_value:.2f})"
                )
                final_quantity = required_min_qty
                final_size_usd = required_min_value
            else:
                # REJECT - user cannot afford minimum
                logger.warning(
                    f"⚠️ REJECTING {symbol}: Position ${order_value:.2f} < exchange min ${exchange_min_cost:.2f}. "
                    f"User max=${max_position:.2f}, capital=${capital:.2f} - cannot afford minimum ${required_min_value:.2f}"
                )
                return PositionSizeResult(
                    quantity=0,
                    size_usd=0,
                    risk_amount=0,
                    method_used="rejected_below_exchange_minimum",
                    details={
                        'original_quantity': final_quantity,
                        'original_value': order_value,
                        'exchange_min_cost': exchange_min_cost,
                        'required_min_value': required_min_value,
                        'max_position_size': max_position,
                        'capital': capital,
                        'rejection_reason': f'Position below exchange minimum and cannot afford minimum'
                    }
                )
        
        # Log with user settings info
        user_info = f"User: {user_id[:8]}..." if user_id else "Default"
        logger.info(
            f"📊 Optimal Position Size for {symbol} ({user_info}): "
            f"Kelly=${kelly_result.size_usd:.2f} | Vol=${vol_result.size_usd:.2f} | "
            f"Selected: {base_result.method_used} | "
            f"Max Position=${max_position:.0f} | ExMin=${exchange_min_cost:.2f} | "
            f"Confidence adj ({confidence:.0%}): ${base_result.size_usd:.2f} → ${final_size_usd:.2f}"
        )
        
        return PositionSizeResult(
            quantity=final_quantity,
            size_usd=final_size_usd,
            risk_amount=base_result.risk_amount * confidence_multiplier,
            method_used=f"optimal_combined_{base_result.method_used}",
            details={
                'kelly_size': kelly_result.size_usd,
                'volatility_size': vol_result.size_usd,
                'selected_method': base_result.method_used,
                'confidence': confidence,
                'confidence_multiplier': confidence_multiplier,
                'max_position_size': max_position,
                'user_id': user_id,
                **base_result.details
            }
        )
    
    async def validate_against_exchange_minimum(
        self,
        symbol: str,
        quantity: float,
        current_price: float,
        capital: float,
        user_id: Optional[str] = None
    ) -> PositionSizeResult:
        """
        NEW v2.5: Validate position size against exchange minimums.
        
        If position is below minimum:
        - If user has enough capital, INCREASE to minimum
        - If not enough capital, REJECT (return quantity=0)
        
        Returns:
            PositionSizeResult with adjusted quantity or quantity=0 if rejected
        """
        if not self.exchange:
            return PositionSizeResult(
                quantity=quantity,
                size_usd=quantity * current_price,
                risk_amount=0,
                method_used="no_exchange_validation",
                details={}
            )
        
        try:
            # Get exchange minimums
            minimums = await self.exchange.get_min_order_amount(symbol, current_price)
            min_cost = minimums.get('min_cost', 10.0)
            min_amount = minimums.get('min_amount', 0.0001)
            
            order_value = quantity * current_price
            
            # Check if below minimum
            if order_value < min_cost or quantity < min_amount:
                # Calculate minimum required quantity
                min_qty_by_cost = (min_cost * 1.1) / current_price  # 10% buffer
                min_qty_by_amount = min_amount
                required_min_qty = max(min_qty_by_cost, min_qty_by_amount)
                required_min_value = required_min_qty * current_price
                
                # Check if user has enough capital for minimum
                max_position = self.get_max_position_size(user_id)
                
                if required_min_value <= max_position and required_min_value <= capital * 0.5:
                    # User can afford minimum - INCREASE position
                    logger.info(
                        f"📊 Position size ${order_value:.2f} below exchange minimum ${min_cost:.2f}. "
                        f"INCREASING to ${required_min_value:.2f} (qty: {quantity:.6f} → {required_min_qty:.6f})"
                    )
                    return PositionSizeResult(
                        quantity=required_min_qty,
                        size_usd=required_min_value,
                        risk_amount=required_min_value * 0.02,  # Assume 2% risk
                        method_used="adjusted_to_exchange_minimum",
                        details={
                            'original_quantity': quantity,
                            'original_value': order_value,
                            'exchange_min_cost': min_cost,
                            'exchange_min_amount': min_amount,
                            'adjustment_reason': 'below_exchange_minimum'
                        }
                    )
                else:
                    # User CANNOT afford minimum - REJECT trade
                    logger.warning(
                        f"⚠️ Position size ${order_value:.2f} below exchange minimum ${min_cost:.2f}. "
                        f"User cannot afford minimum (max_position=${max_position:.2f}, capital=${capital:.2f}). "
                        f"REJECTING trade for {symbol}."
                    )
                    return PositionSizeResult(
                        quantity=0,  # ZERO = don't trade
                        size_usd=0,
                        risk_amount=0,
                        method_used="rejected_below_minimum",
                        details={
                            'original_quantity': quantity,
                            'original_value': order_value,
                            'exchange_min_cost': min_cost,
                            'required_min_value': required_min_value,
                            'max_position_size': max_position,
                            'capital': capital,
                            'rejection_reason': f'Position ${order_value:.2f} below exchange minimum ${min_cost:.2f} and cannot afford minimum'
                        }
                    )
            
            # Position is OK - return as-is
            return PositionSizeResult(
                quantity=quantity,
                size_usd=order_value,
                risk_amount=order_value * 0.02,
                method_used="validated_ok",
                details={'exchange_min_cost': min_cost, 'exchange_min_amount': min_amount}
            )
            
        except Exception as e:
            logger.warning(f"Could not validate against exchange minimum: {e}")
            return PositionSizeResult(
                quantity=quantity,
                size_usd=quantity * current_price,
                risk_amount=0,
                method_used="validation_error",
                details={'error': str(e)}
            )
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _calculate_fixed_risk_size(
        self,
        capital: float,
        current_price: float,
        risk_percent: float,
        method: str
    ) -> PositionSizeResult:
        """Calculate simple fixed-risk position size."""
        risk_amount = capital * (risk_percent / 100)
        size_usd = min(risk_amount * 10, self.max_position_size_usd)  # 10x risk = typical SL
        quantity = size_usd / current_price if current_price > 0 else 0
        
        return PositionSizeResult(
            quantity=quantity,
            size_usd=size_usd,
            risk_amount=risk_amount,
            method_used=method,
            details={'risk_percent': risk_percent}
        )
    
    async def _fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int
    ) -> Optional[List]:
        """Fetch OHLCV data from exchange."""
        try:
            if hasattr(self.exchange, 'exchange'):
                # CCXT exchange
                ohlcv = await self.exchange.exchange.fetch_ohlcv(
                    symbol, timeframe, limit=limit
                )
                return ohlcv
            elif hasattr(self.exchange, 'fetch_ohlcv'):
                return await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            else:
                logger.warning(f"Exchange adapter doesn't support fetch_ohlcv")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            return None
    
    async def _fetch_ticker(self, symbol: str) -> Optional[Dict]:
        """Fetch ticker data from exchange."""
        try:
            if hasattr(self.exchange, 'exchange'):
                return await self.exchange.exchange.fetch_ticker(symbol)
            elif hasattr(self.exchange, 'fetch_ticker'):
                return await self.exchange.fetch_ticker(symbol)
            return None
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            return None
    
    async def _get_trading_stats(
        self,
        symbol: str,
        user_id: Optional[str] = None
    ) -> Dict:
        """Get trading statistics from database."""
        try:
            from bot.db import DatabaseManager, Trade
            
            with DatabaseManager.session_scope() as session:
                # Get closed trades for this symbol
                query = session.query(Trade).filter(
                    Trade.symbol == symbol
                ).order_by(Trade.created_at.desc()).limit(100)
                
                trades = query.all()
                
                if not trades:
                    return {
                        'total_trades': 0,
                        'win_rate': 0.5,
                        'avg_win': 0.0,
                        'avg_loss': 0.0
                    }
                
                # Calculate statistics
                wins = [t for t in trades if t.pnl and t.pnl > 0]
                losses = [t for t in trades if t.pnl and t.pnl < 0]
                
                total = len(wins) + len(losses)
                win_rate = len(wins) / total if total > 0 else 0.5
                avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
                avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0.0
                
                return {
                    'total_trades': total,
                    'win_rate': win_rate,
                    'avg_win': avg_win,
                    'avg_loss': avg_loss
                }
                
        except Exception as e:
            logger.error(f"Failed to get trading stats: {e}")
            return {
                'total_trades': 0,
                'win_rate': 0.5,
                'avg_win': 0.0,
                'avg_loss': 0.0
            }
    
    def update_risk_level(self, level: RiskLevel):
        """Update the risk level."""
        self.risk_level = level
        logger.info(f"🛡️ Risk level updated to: {level.value}")
    
    def get_status(self, user_id: Optional[str] = None) -> Dict:
        """
        Get current status of Risk Manager.
        If user_id is provided, includes user-specific settings.
        """
        status = {
            'risk_level': self.risk_level.value,
            'risk_per_trade': self._risk_per_trade[self.risk_level],
            'trailing_stop_enabled': self.trailing_config.enabled,
            'dynamic_sltp_enabled': self.dynamic_sltp_config.enabled,
            'kelly_enabled': self.kelly_config.enabled,
            'max_position_size_usd': self.max_position_size_usd,
            'default_leverage': self.default_leverage,
            'atr_cache_size': len(self._atr_cache),
            'volatility_cache_size': len(self._volatility_cache),
            'users_with_settings': len(self._user_settings)
        }
        
        # Add user-specific info if available
        if user_id and user_id in self._user_settings:
            user_settings = self._user_settings[user_id]
            status['user_settings'] = {
                'user_id': user_id,
                'risk_level': user_settings.risk_level,
                'risk_per_trade_percent': user_settings.risk_per_trade_percent,
                'max_position_size': user_settings.max_position_size,
                'max_daily_loss': user_settings.max_daily_loss,
                'stop_loss_percentage': user_settings.stop_loss_percentage,
                'take_profit_percentage': user_settings.take_profit_percentage
            }
        
        return status

    # ========================================================================
    # NEW 2025-12-13: VaR CHECK, MULTI-TF, SESSION FILTERING, SHARPE LIVE
    # ========================================================================
    
    async def calculate_var_daily(
        self, 
        portfolio_value: float,
        confidence_level: float = 0.95,
        lookback_days: int = 30
    ) -> Dict[str, Any]:
        """
        Calculate Daily Value-at-Risk (VaR) for portfolio.
        
        Professional standard: Bank-grade risk metric.
        
        Args:
            portfolio_value: Current portfolio value in USD
            confidence_level: VaR confidence (0.95 = 95%)
            lookback_days: Historical period for calculation
            
        Returns:
            Dict with var_absolute, var_percent, can_trade, warning
        """
        import numpy as np
        try:
            from bot.db import DatabaseManager, TradingStats
            
            with DatabaseManager.session_scope() as session:
                # Get daily returns from TradingStats
                from datetime import datetime, timedelta
                cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)
                
                stats = session.query(TradingStats).filter(
                    TradingStats.date >= cutoff_date
                ).order_by(TradingStats.date.asc()).all()
                
                if len(stats) < 10:
                    logger.warning("VaR: Not enough data (<10 days), using conservative estimate")
                    # Conservative fallback: 5% VaR
                    return {
                        'var_absolute': portfolio_value * 0.05,
                        'var_percent': 5.0,
                        'can_trade': portfolio_value > 100,
                        'warning': None,
                        'data_points': len(stats),
                        'confidence_level': confidence_level
                    }
                
                # Calculate daily returns
                daily_returns = []
                for i in range(1, len(stats)):
                    if stats[i-1].ending_balance > 0:
                        ret = (stats[i].ending_balance - stats[i-1].ending_balance) / stats[i-1].ending_balance
                        daily_returns.append(ret)
                
                if not daily_returns:
                    return {
                        'var_absolute': portfolio_value * 0.05,
                        'var_percent': 5.0,
                        'can_trade': True,
                        'warning': 'No return data available',
                        'data_points': 0,
                        'confidence_level': confidence_level
                    }
                
                # Parametric VaR using normal distribution
                mean_return = np.mean(daily_returns)
                std_return = np.std(daily_returns)
                
                # Z-score for confidence level
                z_scores = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}
                z = z_scores.get(confidence_level, 1.645)
                
                # VaR = portfolio * (mean - z * std)
                var_return = mean_return - z * std_return
                var_absolute = abs(var_return * portfolio_value)
                var_percent = abs(var_return * 100)
                
                # Risk checks
                warning = None
                can_trade = True
                
                # Halt trading if VaR exceeds 10% of portfolio
                if var_percent > 10.0:
                    warning = f"⚠️ HIGH VaR: {var_percent:.2f}% exceeds 10% threshold"
                    can_trade = False
                elif var_percent > 5.0:
                    warning = f"⚠️ Elevated VaR: {var_percent:.2f}%"
                
                logger.info(
                    f"📊 VaR({confidence_level*100:.0f}%): ${var_absolute:.2f} ({var_percent:.2f}%) | "
                    f"Can Trade: {'✅' if can_trade else '❌'}"
                )
                
                return {
                    'var_absolute': var_absolute,
                    'var_percent': var_percent,
                    'can_trade': can_trade,
                    'warning': warning,
                    'data_points': len(daily_returns),
                    'confidence_level': confidence_level,
                    'mean_daily_return': mean_return * 100,
                    'std_daily_return': std_return * 100
                }
                
        except Exception as e:
            logger.error(f"VaR calculation failed: {e}")
            return {
                'var_absolute': portfolio_value * 0.05,
                'var_percent': 5.0,
                'can_trade': True,
                'warning': f'VaR calculation error: {e}',
                'data_points': 0,
                'confidence_level': confidence_level
            }
    
    async def check_multi_timeframe_confirmation(
        self, 
        symbol: str, 
        signal_direction: str,
        timeframes: List[str] = None
    ) -> Dict[str, Any]:
        """
        Check if signal is confirmed on multiple timeframes (4h, 1d).
        
        Professional standard: Higher timeframes filter out noise.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT')
            signal_direction: 'long' or 'short'
            timeframes: List of timeframes to check (default: ['4h', '1d'])
            
        Returns:
            Dict with confirmed, confirmations, timeframe_signals, strength
        """
        if timeframes is None:
            timeframes = ['4h', '1d']
        
        try:
            confirmations = {}
            
            for tf in timeframes:
                # Get OHLCV data for each timeframe
                try:
                    if self.exchange:
                        ohlcv = await self.exchange.fetch_ohlcv(symbol, tf, limit=50)
                        
                        if ohlcv and len(ohlcv) >= 20:
                            # Calculate trend using EMAs
                            closes = [c[4] for c in ohlcv]
                            
                            # EMA 9 and EMA 21
                            ema_9 = self._calculate_ema(closes, 9)
                            ema_21 = self._calculate_ema(closes, 21)
                            
                            # Current trend
                            if ema_9 > ema_21:
                                tf_direction = 'bullish'
                            elif ema_9 < ema_21:
                                tf_direction = 'bearish'
                            else:
                                tf_direction = 'neutral'
                            
                            # Trend strength (EMA distance)
                            ema_diff_pct = (ema_9 - ema_21) / ema_21 * 100 if ema_21 > 0 else 0
                            
                            confirmations[tf] = {
                                'direction': tf_direction,
                                'ema_diff_pct': ema_diff_pct,
                                'confirmed': (
                                    (signal_direction == 'long' and tf_direction == 'bullish') or
                                    (signal_direction == 'short' and tf_direction == 'bearish')
                                )
                            }
                    else:
                        confirmations[tf] = {
                            'direction': 'unknown',
                            'ema_diff_pct': 0,
                            'confirmed': True,  # Allow if no data
                            'error': 'No exchange adapter'
                        }
                        
                except Exception as e:
                    logger.warning(f"Multi-TF check failed for {tf}: {e}")
                    confirmations[tf] = {
                        'direction': 'unknown',
                        'ema_diff_pct': 0,
                        'confirmed': True,  # Don't block on failure
                        'error': str(e)
                    }
            
            # Determine overall confirmation
            confirmed_count = sum(1 for c in confirmations.values() if c.get('confirmed', False))
            total_tfs = len(timeframes)
            
            # Require majority confirmation (e.g., 2/2 or 2/3)
            is_confirmed = confirmed_count >= total_tfs * 0.5
            
            # Calculate strength score
            strength = confirmed_count / total_tfs if total_tfs > 0 else 0
            
            result = {
                'confirmed': is_confirmed,
                'confirmations': confirmed_count,
                'total_timeframes': total_tfs,
                'timeframe_signals': confirmations,
                'strength': strength,
                'symbol': symbol,
                'signal_direction': signal_direction
            }
            
            status = '✅' if is_confirmed else '❌'
            logger.info(
                f"📊 Multi-TF {symbol} {signal_direction}: {status} | "
                f"Confirmed: {confirmed_count}/{total_tfs} | Strength: {strength:.0%}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Multi-TF confirmation failed: {e}")
            return {
                'confirmed': True,  # Don't block on failure
                'confirmations': 0,
                'total_timeframes': len(timeframes),
                'timeframe_signals': {},
                'strength': 0,
                'error': str(e)
            }
    
    def _calculate_ema(self, data: List[float], period: int) -> float:
        """Calculate EMA for given data and period."""
        if len(data) < period:
            return data[-1] if data else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period  # Initial SMA
        
        for price in data[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def is_session_safe(self, symbol: str = None) -> Dict[str, Any]:
        """
        Check if current time is safe for trading (avoids rollover).
        
        Professional standard: Banks avoid trading during daily/weekly rollover.
        
        - Avoids 00:00 UTC daily rollover (±30 min)
        - Avoids Friday 21:00 - Sunday 22:00 UTC weekend gap
        - Avoids major economic releases (optional future enhancement)
        
        Returns:
            Dict with is_safe, reason, next_safe_time
        """
        from datetime import datetime, timedelta
        import pytz
        
        try:
            utc = pytz.UTC
            now = datetime.now(utc)
            
            # Check daily rollover (00:00 UTC ± 30 min)
            minutes_from_midnight = now.hour * 60 + now.minute
            if minutes_from_midnight < 30 or minutes_from_midnight > 1410:  # 23:30-00:30
                next_safe = now.replace(hour=0, minute=30, second=0, microsecond=0)
                if minutes_from_midnight > 1410:
                    next_safe += timedelta(days=1)
                
                return {
                    'is_safe': False,
                    'reason': 'Daily rollover period (00:00 UTC ± 30 min)',
                    'next_safe_time': next_safe.isoformat(),
                    'current_time_utc': now.isoformat(),
                    'suggestion': 'Wait for rollover to complete'
                }
            
            # Check weekend gap (Friday 21:00 - Sunday 22:00 UTC)
            weekday = now.weekday()  # 0=Mon, 6=Sun
            hour = now.hour
            
            # Friday after 21:00
            if weekday == 4 and hour >= 21:
                next_safe = now + timedelta(days=(6 - weekday + 1))  # Next Monday
                next_safe = next_safe.replace(hour=22, minute=0, second=0, microsecond=0)
                
                return {
                    'is_safe': False,
                    'reason': 'Weekend gap approaching (Friday close)',
                    'next_safe_time': next_safe.isoformat(),
                    'current_time_utc': now.isoformat(),
                    'suggestion': 'Avoid opening new positions before weekend'
                }
            
            # Saturday (all day)
            if weekday == 5:
                next_safe = now + timedelta(days=1)  # Sunday
                next_safe = next_safe.replace(hour=22, minute=0, second=0, microsecond=0)
                
                return {
                    'is_safe': False,
                    'reason': 'Weekend (markets closed/low liquidity)',
                    'next_safe_time': next_safe.isoformat(),
                    'current_time_utc': now.isoformat(),
                    'suggestion': 'Wait for Sunday open'
                }
            
            # Sunday before 22:00
            if weekday == 6 and hour < 22:
                next_safe = now.replace(hour=22, minute=0, second=0, microsecond=0)
                
                return {
                    'is_safe': False,
                    'reason': 'Weekend (before market open)',
                    'next_safe_time': next_safe.isoformat(),
                    'current_time_utc': now.isoformat(),
                    'suggestion': 'Wait for Sunday 22:00 UTC'
                }
            
            # All clear
            return {
                'is_safe': True,
                'reason': 'Trading session active',
                'next_safe_time': None,
                'current_time_utc': now.isoformat(),
                'suggestion': None
            }
            
        except Exception as e:
            logger.warning(f"Session safety check failed: {e}")
            return {
                'is_safe': True,  # Allow trading on error
                'reason': f'Check failed: {e}',
                'next_safe_time': None,
                'current_time_utc': None,
                'error': str(e)
            }
    
    async def calculate_sharpe_live(
        self, 
        user_id: str = None,
        lookback_days: int = 30,
        risk_free_rate: float = 0.04  # 4% annual
    ) -> Dict[str, Any]:
        """
        Calculate real-time Sharpe ratio.
        
        Professional standard: Live risk-adjusted return monitoring.
        
        Args:
            user_id: Optional user filter
            lookback_days: Period for calculation
            risk_free_rate: Annual risk-free rate
            
        Returns:
            Dict with sharpe_ratio, quality, can_scale, interpretation
        """
        import numpy as np
        
        try:
            from bot.db import DatabaseManager, TradingStats, Trade
            from datetime import datetime, timedelta
            
            cutoff = datetime.utcnow() - timedelta(days=lookback_days)
            
            with DatabaseManager.session_scope() as session:
                # Get daily returns from trades
                query = session.query(Trade).filter(
                    Trade.created_at >= cutoff,
                    Trade.pnl.isnot(None)
                )
                
                if user_id:
                    query = query.filter(Trade.user_id == user_id)
                
                trades = query.order_by(Trade.created_at.asc()).all()
                
                if len(trades) < 5:
                    return {
                        'sharpe_ratio': None,
                        'quality': 'unknown',
                        'can_scale': False,
                        'interpretation': 'Not enough trades (<5)',
                        'total_trades': len(trades),
                        'lookback_days': lookback_days
                    }
                
                # Group trades by day and calculate daily returns
                daily_pnl = {}
                for trade in trades:
                    day = trade.created_at.date()
                    if day not in daily_pnl:
                        daily_pnl[day] = 0
                    daily_pnl[day] += float(trade.pnl or 0)
                
                if len(daily_pnl) < 5:
                    return {
                        'sharpe_ratio': None,
                        'quality': 'unknown',
                        'can_scale': False,
                        'interpretation': 'Not enough trading days (<5)',
                        'total_trades': len(trades),
                        'trading_days': len(daily_pnl)
                    }
                
                # Calculate returns (assume $10k base for simplicity)
                base_capital = 10000
                daily_returns = [pnl / base_capital for pnl in daily_pnl.values()]
                
                # Sharpe calculation
                mean_return = np.mean(daily_returns)
                std_return = np.std(daily_returns)
                
                if std_return == 0:
                    return {
                        'sharpe_ratio': 0,
                        'quality': 'neutral',
                        'can_scale': False,
                        'interpretation': 'Zero volatility (suspicious)',
                        'total_trades': len(trades)
                    }
                
                # Daily risk-free rate
                daily_rf = risk_free_rate / 365
                
                # Annualized Sharpe
                excess_return = mean_return - daily_rf
                sharpe = (excess_return / std_return) * np.sqrt(365)
                
                # Interpretation
                if sharpe >= 2.0:
                    quality = 'excellent'
                    interpretation = '🌟 Outstanding risk-adjusted returns'
                    can_scale = True
                elif sharpe >= 1.0:
                    quality = 'good'
                    interpretation = '✅ Good risk-adjusted returns'
                    can_scale = True
                elif sharpe >= 0.5:
                    quality = 'acceptable'
                    interpretation = '⚠️ Moderate risk-adjusted returns'
                    can_scale = False
                elif sharpe >= 0:
                    quality = 'poor'
                    interpretation = '❌ Poor risk-adjusted returns'
                    can_scale = False
                else:
                    quality = 'negative'
                    interpretation = '🚫 Negative returns - consider reducing exposure'
                    can_scale = False
                
                logger.info(
                    f"📊 Live Sharpe: {sharpe:.2f} ({quality}) | "
                    f"Can Scale: {'✅' if can_scale else '❌'} | "
                    f"Trades: {len(trades)} over {len(daily_pnl)} days"
                )
                
                return {
                    'sharpe_ratio': round(sharpe, 2),
                    'quality': quality,
                    'can_scale': can_scale,
                    'interpretation': interpretation,
                    'total_trades': len(trades),
                    'trading_days': len(daily_pnl),
                    'mean_daily_return_pct': round(mean_return * 100, 4),
                    'std_daily_return_pct': round(std_return * 100, 4),
                    'annualized_return_pct': round(mean_return * 365 * 100, 2),
                    'annualized_volatility_pct': round(std_return * np.sqrt(365) * 100, 2)
                }
                
        except Exception as e:
            logger.error(f"Live Sharpe calculation failed: {e}")
            return {
                'sharpe_ratio': None,
                'quality': 'error',
                'can_scale': False,
                'interpretation': f'Calculation error: {e}',
                'error': str(e)
            }
    
    async def pre_trade_risk_check(
        self,
        symbol: str,
        signal_direction: str,
        position_size_usd: float,
        portfolio_value: float,
        user_id: str = None
    ) -> Dict[str, Any]:
        """
        Comprehensive pre-trade risk check combining all risk metrics.
        
        Professional standard: All checks must pass before trade execution.
        
        Checks:
        1. VaR limit
        2. Multi-timeframe confirmation
        3. Session safety (rollover avoidance)
        4. Sharpe quality
        5. Position size limits
        
        Args:
            symbol: Trading symbol
            signal_direction: 'long' or 'short'
            position_size_usd: Proposed position size
            portfolio_value: Current portfolio value
            user_id: Optional user ID
            
        Returns:
            Dict with can_trade, checks, warnings, final_position_size
        """
        checks = {}
        warnings = []
        blockers = []
        
        # 1. VaR Check
        var_result = await self.calculate_var_daily(portfolio_value)
        checks['var'] = var_result
        if not var_result['can_trade']:
            blockers.append(f"VaR limit exceeded: {var_result['var_percent']:.2f}%")
        elif var_result.get('warning'):
            warnings.append(var_result['warning'])
        
        # 2. Multi-TF Confirmation
        mtf_result = await self.check_multi_timeframe_confirmation(symbol, signal_direction)
        checks['multi_tf'] = mtf_result
        if not mtf_result['confirmed']:
            # Don't block, but warn and reduce size
            warnings.append(f"Multi-TF not confirmed ({mtf_result['confirmations']}/{mtf_result['total_timeframes']})")
        
        # 3. Session Safety
        session_result = self.is_session_safe(symbol)
        checks['session'] = session_result
        if not session_result['is_safe']:
            blockers.append(f"Unsafe session: {session_result['reason']}")
        
        # 4. Sharpe Quality (only warn, don't block)
        sharpe_result = await self.calculate_sharpe_live(user_id)
        checks['sharpe'] = sharpe_result
        if sharpe_result.get('sharpe_ratio') is not None:
            if sharpe_result['sharpe_ratio'] < 0:
                warnings.append(f"Negative Sharpe ratio: {sharpe_result['sharpe_ratio']:.2f}")
            elif sharpe_result['sharpe_ratio'] < 0.5:
                warnings.append(f"Low Sharpe ratio: {sharpe_result['sharpe_ratio']:.2f}")
        
        # 5. Position Size Limits
        max_size = self.get_max_position_size(user_id)
        if position_size_usd > max_size:
            position_size_usd = max_size
            warnings.append(f"Position size capped to max: ${max_size:.2f}")
        
        # Adjust position size based on risk factors
        size_multiplier = 1.0
        
        # Reduce size if multi-TF not confirmed
        if not mtf_result['confirmed']:
            size_multiplier *= 0.5
        
        # Reduce size if Sharpe is poor
        if sharpe_result.get('sharpe_ratio') is not None and sharpe_result['sharpe_ratio'] < 0.5:
            size_multiplier *= 0.7
        
        final_position_size = position_size_usd * size_multiplier
        
        # Final decision
        can_trade = len(blockers) == 0
        
        result = {
            'can_trade': can_trade,
            'checks': checks,
            'blockers': blockers,
            'warnings': warnings,
            'original_position_size': position_size_usd,
            'final_position_size': final_position_size,
            'size_multiplier': size_multiplier,
            'timestamp': datetime.now().isoformat()
        }
        
        status = '✅ APPROVED' if can_trade else '❌ BLOCKED'
        logger.info(
            f"📋 Pre-Trade Check {symbol} {signal_direction}: {status} | "
            f"Size: ${final_position_size:.2f} ({size_multiplier:.0%} of ${position_size_usd:.2f}) | "
            f"Warnings: {len(warnings)} | Blockers: {len(blockers)}"
        )
        
        return result