"""
Rate Limiter Service - Prevents excessive trading activity.

Addresses the gap: "No rate limiting - many trades at once possible"

Features:
1. Max signals per cycle
2. Max trades per hour/day
3. Cooldown between trades on same symbol
4. Max concurrent positions
5. Daily loss limit check
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    # Per-cycle limits
    max_signals_per_cycle: int = 3          # Max signals to execute per bot cycle
    
    # Time-based limits
    max_trades_per_hour: int = 5            # Max new trades per hour
    max_trades_per_day: int = 15            # Max new trades per day
    
    # Symbol cooldowns
    symbol_cooldown_minutes: int = 60       # Minutes before same symbol can be traded again
    
    # Position limits
    max_concurrent_positions: int = 10      # Max open positions at once
    max_positions_per_symbol: int = 1       # Max positions per symbol (avoid doubling down)
    
    # Risk limits
    max_daily_loss_pct: float = 5.0         # Stop trading if daily loss exceeds this %
    max_drawdown_pct: float = 10.0          # Stop trading if drawdown exceeds this %
    
    # Pause conditions
    pause_after_consecutive_losses: int = 3  # Pause after N consecutive losses


@dataclass 
class TradingMetrics:
    """Track trading activity metrics."""
    trades_this_hour: int = 0
    trades_today: int = 0
    consecutive_losses: int = 0
    daily_pnl_pct: float = 0.0
    current_drawdown_pct: float = 0.0
    last_trade_time: Optional[datetime] = None
    last_hour_reset: Optional[datetime] = None
    last_day_reset: Optional[datetime] = None


@dataclass
class RateLimitResult:
    """Result of rate limit check."""
    is_allowed: bool
    reason: str = ""
    wait_seconds: Optional[int] = None
    signals_allowed: int = 0


class RateLimiter:
    """
    Rate limiter to prevent excessive trading.
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        
        # Track per-user metrics
        self._user_metrics: Dict[str, TradingMetrics] = defaultdict(TradingMetrics)
        
        # Track symbol cooldowns per user {user_id: {symbol: last_trade_time}}
        self._symbol_cooldowns: Dict[str, Dict[str, datetime]] = defaultdict(dict)
        
        # Track current positions per user {user_id: set(symbols)}
        self._current_positions: Dict[str, Set[str]] = defaultdict(set)
        
        # Track signals executed this cycle per user
        self._cycle_signals: Dict[str, int] = defaultdict(int)
        
        logger.info(f"⏱️ Rate Limiter initialized: max {self.config.max_signals_per_cycle}/cycle, "
                   f"{self.config.max_trades_per_hour}/hour, {self.config.max_trades_per_day}/day")
    
    def start_cycle(self, user_id: str):
        """Call at start of each bot cycle to reset cycle counters."""
        self._cycle_signals[user_id] = 0
        self._reset_time_windows(user_id)
    
    def _reset_time_windows(self, user_id: str):
        """Reset hourly/daily counters if windows have passed."""
        user_id_str = str(user_id)  # Convert UUID to string if needed
        metrics = self._user_metrics[user_id]
        now = datetime.now()
        
        # Reset hourly counter
        if metrics.last_hour_reset is None or (now - metrics.last_hour_reset) >= timedelta(hours=1):
            metrics.trades_this_hour = 0
            metrics.last_hour_reset = now
            logger.debug(f"Reset hourly counter for user {user_id_str[:8]}")
        
        # Reset daily counter (at midnight)
        if metrics.last_day_reset is None or now.date() > metrics.last_day_reset.date():
            metrics.trades_today = 0
            metrics.daily_pnl_pct = 0.0
            metrics.last_day_reset = now
            logger.debug(f"Reset daily counter for user {user_id_str[:8]}")
    
    def check_can_trade(
        self, 
        user_id: str, 
        symbol: str,
        current_positions: Optional[List[str]] = None
    ) -> RateLimitResult:
        """
        Check if a trade is allowed based on rate limits.
        
        Returns RateLimitResult with:
        - is_allowed: True if trade can proceed
        - reason: Explanation if not allowed
        - wait_seconds: How long to wait before retrying (if applicable)
        """
        metrics = self._user_metrics[user_id]
        now = datetime.now()
        
        # Update positions if provided
        if current_positions is not None:
            self._current_positions[user_id] = set(current_positions)
        
        # 1. Check cycle limit
        if self._cycle_signals[user_id] >= self.config.max_signals_per_cycle:
            return RateLimitResult(
                is_allowed=False,
                reason=f"Cycle limit reached ({self.config.max_signals_per_cycle} signals/cycle)",
                signals_allowed=0
            )
        
        # 2. Check hourly limit
        if metrics.trades_this_hour >= self.config.max_trades_per_hour:
            wait = 3600 - (now - metrics.last_hour_reset).seconds if metrics.last_hour_reset else 3600
            return RateLimitResult(
                is_allowed=False,
                reason=f"Hourly limit reached ({self.config.max_trades_per_hour} trades/hour)",
                wait_seconds=wait
            )
        
        # 3. Check daily limit
        if metrics.trades_today >= self.config.max_trades_per_day:
            return RateLimitResult(
                is_allowed=False,
                reason=f"Daily limit reached ({self.config.max_trades_per_day} trades/day)"
            )
        
        # 4. Check symbol cooldown
        base_symbol = self._normalize_symbol(symbol)
        if base_symbol in self._symbol_cooldowns[user_id]:
            last_trade = self._symbol_cooldowns[user_id][base_symbol]
            cooldown_end = last_trade + timedelta(minutes=self.config.symbol_cooldown_minutes)
            if now < cooldown_end:
                wait = int((cooldown_end - now).total_seconds())
                return RateLimitResult(
                    is_allowed=False,
                    reason=f"Symbol {base_symbol} in cooldown ({wait}s remaining)",
                    wait_seconds=wait
                )
        
        # 5. Check max concurrent positions
        current_pos_count = len(self._current_positions[user_id])
        if current_pos_count >= self.config.max_concurrent_positions:
            return RateLimitResult(
                is_allowed=False,
                reason=f"Max positions reached ({current_pos_count}/{self.config.max_concurrent_positions})"
            )
        
        # 6. Check if already holding this symbol
        if base_symbol in self._current_positions[user_id]:
            return RateLimitResult(
                is_allowed=False,
                reason=f"Already holding position in {base_symbol}"
            )
        
        # 7. Check consecutive losses
        if metrics.consecutive_losses >= self.config.pause_after_consecutive_losses:
            return RateLimitResult(
                is_allowed=False,
                reason=f"Paused after {metrics.consecutive_losses} consecutive losses"
            )
        
        # 8. Check daily loss limit
        if metrics.daily_pnl_pct < -self.config.max_daily_loss_pct:
            return RateLimitResult(
                is_allowed=False,
                reason=f"Daily loss limit exceeded ({metrics.daily_pnl_pct:.1f}%)"
            )
        
        # All checks passed
        remaining_cycle = self.config.max_signals_per_cycle - self._cycle_signals[user_id]
        return RateLimitResult(
            is_allowed=True,
            signals_allowed=remaining_cycle
        )
    
    def record_trade(self, user_id: str, symbol: str):
        """Record that a trade was executed."""
        metrics = self._user_metrics[user_id]
        now = datetime.now()
        base_symbol = self._normalize_symbol(symbol)
        
        # Update counters
        self._cycle_signals[user_id] += 1
        metrics.trades_this_hour += 1
        metrics.trades_today += 1
        metrics.last_trade_time = now
        
        # Set symbol cooldown
        self._symbol_cooldowns[user_id][base_symbol] = now
        
        # Add to current positions
        self._current_positions[user_id].add(base_symbol)
        
        user_id_str = str(user_id)
        logger.info(f"📝 Recorded trade for {user_id_str[:8]}: {symbol} "
                   f"(cycle: {self._cycle_signals[user_id]}/{self.config.max_signals_per_cycle}, "
                   f"hour: {metrics.trades_this_hour}/{self.config.max_trades_per_hour}, "
                   f"day: {metrics.trades_today}/{self.config.max_trades_per_day})")
    
    def record_close(self, user_id: str, symbol: str, profit_pct: float):
        """Record that a position was closed."""
        metrics = self._user_metrics[user_id]
        base_symbol = self._normalize_symbol(symbol)
        user_id_str = str(user_id)
        
        # Update daily P&L
        metrics.daily_pnl_pct += profit_pct
        
        # Track consecutive losses
        if profit_pct < 0:
            metrics.consecutive_losses += 1
            logger.warning(f"Loss #{metrics.consecutive_losses} for {user_id_str[:8]}: {profit_pct:.2f}%")
        else:
            metrics.consecutive_losses = 0  # Reset on profit
        
        # Remove from current positions
        self._current_positions[user_id].discard(base_symbol)
        
        logger.info(f"📝 Recorded close for {user_id_str[:8]}: {symbol} P&L={profit_pct:.2f}%, "
                   f"Daily P&L={metrics.daily_pnl_pct:.2f}%")
    
    def reset_consecutive_losses(self, user_id: str):
        """Manually reset consecutive losses (e.g., after user reviews)."""
        self._user_metrics[user_id].consecutive_losses = 0
        logger.info(f"Reset consecutive losses for {str(user_id)[:8]}")
    
    def get_metrics(self, user_id: str) -> Dict:
        """Get current metrics for a user."""
        metrics = self._user_metrics[user_id]
        return {
            "trades_this_hour": metrics.trades_this_hour,
            "trades_today": metrics.trades_today,
            "consecutive_losses": metrics.consecutive_losses,
            "daily_pnl_pct": metrics.daily_pnl_pct,
            "current_positions": len(self._current_positions[user_id]),
            "positions": list(self._current_positions[user_id]),
            "signals_this_cycle": self._cycle_signals[user_id],
            "max_signals_per_cycle": self.config.max_signals_per_cycle,
            "max_trades_per_hour": self.config.max_trades_per_hour,
            "max_trades_per_day": self.config.max_trades_per_day
        }
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to base asset (e.g., BTC/USDT -> BTC)."""
        if '/' in symbol:
            return symbol.split('/')[0]
        # Handle formats like BTCUSDT
        for quote in ['USDT', 'BUSD', 'USD', 'EUR', 'USDC']:
            if symbol.endswith(quote):
                return symbol[:-len(quote)]
        return symbol
    
    def filter_signals(
        self, 
        user_id: str, 
        signals: List[Dict],
        current_positions: Optional[List[str]] = None
    ) -> Tuple[List[Dict], List[Tuple[Dict, str]]]:
        """
        Filter signals based on rate limits.
        
        Returns:
        - allowed_signals: List of signals that can be executed
        - rejected_signals: List of (signal, reason) tuples
        """
        allowed = []
        rejected = []
        
        for signal in signals:
            symbol = signal.get('symbol', '')
            result = self.check_can_trade(user_id, symbol, current_positions)
            
            if result.is_allowed:
                allowed.append(signal)
                # Don't record yet - will be recorded when actually executed
            else:
                rejected.append((signal, result.reason))
        
        if rejected:
            logger.info(f"Rate limiter filtered {len(rejected)}/{len(signals)} signals for {str(user_id)[:8]}")
            for sig, reason in rejected:
                logger.debug(f"  Rejected {sig.get('symbol', 'unknown')}: {reason}")
        
        return allowed, rejected


# Default instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(config: Optional[RateLimitConfig] = None) -> RateLimiter:
    """Get or create the global RateLimiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(config)
    return _rate_limiter
