"""
Daily Loss Tracker - Enforces daily loss limits per user.

Tracks realized and unrealized P&L throughout the day
and blocks new trades when limit is exceeded.

v2.0: Added database persistence for crash recovery.
"""

import logging
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)


# Persistence file path (fallback if DB unavailable)
PERSISTENCE_DIR = Path.home() / ".ase_bot" / "daily_loss"


@dataclass
class DailyPnL:
    """Daily P&L tracking for a user."""
    user_id: str
    date: date
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    trades_count: int = 0
    wins: int = 0
    losses: int = 0
    max_drawdown: float = 0.0
    peak_pnl: float = 0.0
    trading_blocked: bool = False
    blocked_reason: Optional[str] = None
    
    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl
    
    @property
    def win_rate(self) -> float:
        if self.trades_count == 0:
            return 0.0
        return (self.wins / self.trades_count) * 100
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'user_id': self.user_id,
            'date': self.date.isoformat(),
            'realized_pnl': self.realized_pnl,
            'unrealized_pnl': self.unrealized_pnl,
            'trades_count': self.trades_count,
            'wins': self.wins,
            'losses': self.losses,
            'max_drawdown': self.max_drawdown,
            'peak_pnl': self.peak_pnl,
            'trading_blocked': self.trading_blocked,
            'blocked_reason': self.blocked_reason,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DailyPnL':
        """Create from dictionary."""
        return cls(
            user_id=data['user_id'],
            date=date.fromisoformat(data['date']) if isinstance(data['date'], str) else data['date'],
            realized_pnl=float(data.get('realized_pnl', 0)),
            unrealized_pnl=float(data.get('unrealized_pnl', 0)),
            trades_count=int(data.get('trades_count', 0)),
            wins=int(data.get('wins', 0)),
            losses=int(data.get('losses', 0)),
            max_drawdown=float(data.get('max_drawdown', 0)),
            peak_pnl=float(data.get('peak_pnl', 0)),
            trading_blocked=bool(data.get('trading_blocked', False)),
            blocked_reason=data.get('blocked_reason'),
        )


@dataclass
class LossLimitConfig:
    """Configuration for loss limits."""
    max_daily_loss_pct: float = 5.0      # % of account equity
    max_daily_loss_usd: float = 500.0    # Absolute USD limit
    max_consecutive_losses: int = 5       # Consecutive losing trades
    max_daily_trades: int = 50           # Max trades per day
    cooldown_after_limit_hours: float = 4.0  # Hours to wait after hitting limit
    warn_at_pct: float = 70.0            # Warn when 70% of limit reached


class DailyLossTracker:
    """
    Tracks daily P&L and enforces loss limits.
    
    Features:
    1. Real-time P&L tracking (realized + unrealized)
    2. Multiple limit types (%, USD, consecutive losses)
    3. Automatic trading blocks when limits hit
    4. Cooldown periods
    5. Per-user tracking
    6. Database/file persistence for crash recovery
    
    Usage:
        tracker = DailyLossTracker()
        
        # Before opening trade
        can_trade, reason = tracker.can_open_trade("user_123", account_equity=10000)
        if not can_trade:
            logger.warning(f"Trade blocked: {reason}")
            return
        
        # After closing trade
        tracker.record_trade_result("user_123", pnl=-50.0, is_win=False)
        
        # Update unrealized P&L periodically
        tracker.update_unrealized_pnl("user_123", -150.0)
    """
    
    def __init__(self, config: LossLimitConfig = None, db_manager=None):
        self.config = config or LossLimitConfig()
        self._daily_pnl: Dict[str, DailyPnL] = {}  # user_id -> DailyPnL
        self._consecutive_losses: Dict[str, int] = {}  # user_id -> count
        self._block_until: Dict[str, datetime] = {}  # user_id -> unblock time
        self._lock = asyncio.Lock()
        self._db_manager = db_manager
        
        # Ensure persistence directory exists
        PERSISTENCE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Load persisted state on init
        self._load_persisted_state()
    
    def _get_persistence_path(self, user_id: str) -> Path:
        """Get persistence file path for user."""
        safe_user_id = user_id.replace('/', '_').replace('\\', '_')[:50]
        return PERSISTENCE_DIR / f"daily_loss_{safe_user_id}.json"
    
    def _persist_state(self, user_id: str) -> None:
        """Persist state to file for crash recovery."""
        try:
            daily = self._daily_pnl.get(user_id)
            if not daily:
                return
            
            state = {
                'daily_pnl': daily.to_dict(),
                'consecutive_losses': self._consecutive_losses.get(user_id, 0),
                'block_until': self._block_until.get(user_id, datetime.min).isoformat() if user_id in self._block_until else None,
                'persisted_at': datetime.utcnow().isoformat(),
            }
            
            file_path = self._get_persistence_path(user_id)
            with open(file_path, 'w') as f:
                json.dump(state, f, indent=2)
                
            logger.debug(f"Persisted daily loss state for {user_id[:8]}...")
            
        except Exception as e:
            logger.warning(f"Failed to persist daily loss state: {e}")
    
    def _load_persisted_state(self) -> None:
        """Load persisted state from files."""
        try:
            if not PERSISTENCE_DIR.exists():
                return
            
            today = date.today()
            loaded_count = 0
            
            for file_path in PERSISTENCE_DIR.glob("daily_loss_*.json"):
                try:
                    with open(file_path, 'r') as f:
                        state = json.load(f)
                    
                    daily_data = state.get('daily_pnl', {})
                    if not daily_data:
                        continue
                    
                    # Only load if it's today's data
                    state_date = date.fromisoformat(daily_data.get('date', '2000-01-01'))
                    if state_date != today:
                        # Old data - delete file
                        file_path.unlink()
                        continue
                    
                    user_id = daily_data['user_id']
                    self._daily_pnl[user_id] = DailyPnL.from_dict(daily_data)
                    self._consecutive_losses[user_id] = state.get('consecutive_losses', 0)
                    
                    block_until_str = state.get('block_until')
                    if block_until_str:
                        block_until = datetime.fromisoformat(block_until_str)
                        if block_until > datetime.utcnow():
                            self._block_until[user_id] = block_until
                    
                    loaded_count += 1
                    logger.info(
                        f"✅ Restored daily loss state for {user_id[:8]}... | "
                        f"P&L: ${self._daily_pnl[user_id].realized_pnl:+.2f} | "
                        f"Trades: {self._daily_pnl[user_id].trades_count}"
                    )
                    
                except Exception as e:
                    logger.warning(f"Failed to load state from {file_path}: {e}")
            
            if loaded_count > 0:
                logger.info(f"📂 Loaded {loaded_count} persisted daily loss states")
                
        except Exception as e:
            logger.warning(f"Failed to load persisted daily loss states: {e}")
    
    def _get_or_create_daily(self, user_id: str) -> DailyPnL:
        """Get or create daily P&L record for user."""
        today = date.today()
        
        if user_id not in self._daily_pnl or self._daily_pnl[user_id].date != today:
            # New day - reset tracking
            self._daily_pnl[user_id] = DailyPnL(user_id=user_id, date=today)
            # Keep consecutive losses across days
            # Persist the new state
            self._persist_state(user_id)
        
        return self._daily_pnl[user_id]
    
    def can_open_trade(
        self,
        user_id: str,
        account_equity: float,
        proposed_risk_usd: float = 0.0
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if user can open a new trade.
        
        Args:
            user_id: User identifier
            account_equity: Current account equity in USD
            proposed_risk_usd: Risk amount of proposed trade
            
        Returns:
            Tuple of (can_trade: bool, reason: Optional[str])
        """
        daily = self._get_or_create_daily(user_id)
        
        # Check if manually blocked
        if daily.trading_blocked:
            return False, daily.blocked_reason
        
        # Check cooldown
        if user_id in self._block_until:
            if datetime.utcnow() < self._block_until[user_id]:
                remaining = (self._block_until[user_id] - datetime.utcnow()).total_seconds() / 60
                return False, f"Cooldown active, {remaining:.0f} min remaining"
            else:
                del self._block_until[user_id]
        
        # Check max daily trades
        if daily.trades_count >= self.config.max_daily_trades:
            self._block_trading(user_id, "Max daily trades reached")
            return False, f"Max daily trades ({self.config.max_daily_trades}) reached"
        
        # Check consecutive losses
        consecutive = self._consecutive_losses.get(user_id, 0)
        if consecutive >= self.config.max_consecutive_losses:
            self._block_trading(user_id, f"{consecutive} consecutive losses")
            return False, f"Too many consecutive losses ({consecutive})"
        
        # Check daily loss limits
        current_loss = -daily.total_pnl if daily.total_pnl < 0 else 0
        
        # Check percentage limit
        loss_pct = (current_loss / account_equity * 100) if account_equity > 0 else 0
        if loss_pct >= self.config.max_daily_loss_pct:
            self._block_trading(user_id, f"Daily loss limit {loss_pct:.1f}% reached")
            return False, f"Daily loss limit ({self.config.max_daily_loss_pct}%) reached"
        
        # Check absolute USD limit
        if current_loss >= self.config.max_daily_loss_usd:
            self._block_trading(user_id, f"Daily loss ${current_loss:.2f} reached")
            return False, f"Daily loss limit (${self.config.max_daily_loss_usd}) reached"
        
        # Check if proposed trade would exceed limit
        potential_loss = current_loss + proposed_risk_usd
        if potential_loss >= self.config.max_daily_loss_usd:
            return False, f"Trade would exceed daily loss limit (${self.config.max_daily_loss_usd})"
        
        # Warning if approaching limit
        if loss_pct >= (self.config.max_daily_loss_pct * self.config.warn_at_pct / 100):
            logger.warning(
                f"⚠️ User {user_id[:8]}... approaching daily loss limit: "
                f"{loss_pct:.1f}% of {self.config.max_daily_loss_pct}%"
            )
        
        return True, None
    
    def record_trade_result(
        self,
        user_id: str,
        pnl: float,
        is_win: bool,
        symbol: str = None
    ):
        """
        Record result of a closed trade.
        
        Args:
            user_id: User identifier
            pnl: Realized P&L in USD
            is_win: Whether trade was profitable
            symbol: Optional symbol for logging
        """
        daily = self._get_or_create_daily(user_id)
        
        # Update daily stats
        daily.realized_pnl += pnl
        daily.trades_count += 1
        
        if is_win:
            daily.wins += 1
            self._consecutive_losses[user_id] = 0
        else:
            daily.losses += 1
            self._consecutive_losses[user_id] = self._consecutive_losses.get(user_id, 0) + 1
        
        # Update peak and drawdown
        if daily.total_pnl > daily.peak_pnl:
            daily.peak_pnl = daily.total_pnl
        
        drawdown = daily.peak_pnl - daily.total_pnl
        if drawdown > daily.max_drawdown:
            daily.max_drawdown = drawdown
        
        # Log
        consecutive = self._consecutive_losses.get(user_id, 0)
        logger.info(
            f"📊 Trade recorded for {user_id[:8]}... | "
            f"P&L: ${pnl:+.2f} | Daily: ${daily.realized_pnl:+.2f} | "
            f"W/L: {daily.wins}/{daily.losses} | "
            f"Consecutive losses: {consecutive}"
        )
        
        # Persist state after recording trade
        self._persist_state(user_id)
    
    def update_unrealized_pnl(self, user_id: str, unrealized_pnl: float):
        """Update unrealized P&L for user."""
        daily = self._get_or_create_daily(user_id)
        daily.unrealized_pnl = unrealized_pnl
        
        # Update drawdown tracking
        if daily.total_pnl > daily.peak_pnl:
            daily.peak_pnl = daily.total_pnl
        
        drawdown = daily.peak_pnl - daily.total_pnl
        if drawdown > daily.max_drawdown:
            daily.max_drawdown = drawdown
    
    def _block_trading(self, user_id: str, reason: str):
        """Block trading for user."""
        daily = self._get_or_create_daily(user_id)
        daily.trading_blocked = True
        daily.blocked_reason = reason
        
        # Set cooldown
        cooldown_hours = self.config.cooldown_after_limit_hours
        self._block_until[user_id] = datetime.utcnow() + timedelta(hours=cooldown_hours)
        
        logger.warning(
            f"🚫 Trading BLOCKED for {user_id[:8]}...: {reason} | "
            f"Cooldown: {cooldown_hours}h"
        )
        
        # Persist block state
        self._persist_state(user_id)
    
    def unblock_trading(self, user_id: str, reason: str = "manual"):
        """Manually unblock trading for user."""
        if user_id in self._daily_pnl:
            self._daily_pnl[user_id].trading_blocked = False
            self._daily_pnl[user_id].blocked_reason = None
        
        if user_id in self._block_until:
            del self._block_until[user_id]
        
        logger.info(f"✅ Trading UNBLOCKED for {user_id[:8]}...: {reason}")
    
    def reset_consecutive_losses(self, user_id: str):
        """Reset consecutive loss counter (e.g., after manual review)."""
        self._consecutive_losses[user_id] = 0
        logger.info(f"✅ Consecutive losses reset for {user_id[:8]}...")
    
    def get_daily_summary(self, user_id: str) -> Dict:
        """Get daily summary for user."""
        daily = self._get_or_create_daily(user_id)
        
        return {
            'date': daily.date.isoformat(),
            'realized_pnl': daily.realized_pnl,
            'unrealized_pnl': daily.unrealized_pnl,
            'total_pnl': daily.total_pnl,
            'trades_count': daily.trades_count,
            'wins': daily.wins,
            'losses': daily.losses,
            'win_rate': daily.win_rate,
            'max_drawdown': daily.max_drawdown,
            'consecutive_losses': self._consecutive_losses.get(user_id, 0),
            'trading_blocked': daily.trading_blocked,
            'blocked_reason': daily.blocked_reason,
            'cooldown_until': self._block_until.get(user_id, None)
        }
    
    def get_risk_status(self, user_id: str, account_equity: float) -> Dict:
        """Get risk status relative to limits."""
        daily = self._get_or_create_daily(user_id)
        current_loss = -daily.total_pnl if daily.total_pnl < 0 else 0
        
        loss_pct = (current_loss / account_equity * 100) if account_equity > 0 else 0
        
        return {
            'current_loss_pct': loss_pct,
            'max_loss_pct': self.config.max_daily_loss_pct,
            'loss_pct_used': (loss_pct / self.config.max_daily_loss_pct * 100) if self.config.max_daily_loss_pct > 0 else 0,
            'current_loss_usd': current_loss,
            'max_loss_usd': self.config.max_daily_loss_usd,
            'loss_usd_used': (current_loss / self.config.max_daily_loss_usd * 100) if self.config.max_daily_loss_usd > 0 else 0,
            'trades_remaining': max(0, self.config.max_daily_trades - daily.trades_count),
            'consecutive_losses': self._consecutive_losses.get(user_id, 0),
            'max_consecutive_losses': self.config.max_consecutive_losses,
            'risk_level': self._calculate_risk_level(loss_pct, self._consecutive_losses.get(user_id, 0))
        }
    
    def _calculate_risk_level(self, loss_pct: float, consecutive_losses: int) -> str:
        """Calculate overall risk level."""
        loss_ratio = loss_pct / self.config.max_daily_loss_pct if self.config.max_daily_loss_pct > 0 else 0
        loss_ratio_from_consecutive = consecutive_losses / self.config.max_consecutive_losses if self.config.max_consecutive_losses > 0 else 0
        
        max_ratio = max(loss_ratio, loss_ratio_from_consecutive)
        
        if max_ratio >= 1.0:
            return 'CRITICAL'
        elif max_ratio >= 0.7:
            return 'HIGH'
        elif max_ratio >= 0.4:
            return 'MEDIUM'
        else:
            return 'LOW'


# Global singleton
_tracker: Optional[DailyLossTracker] = None


def get_daily_loss_tracker(config: LossLimitConfig = None) -> DailyLossTracker:
    """Get or create the global daily loss tracker."""
    global _tracker
    if _tracker is None:
        _tracker = DailyLossTracker(config)
    return _tracker
