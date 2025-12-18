"""
Position Monitor Service - Background monitoring for SL/TP execution.
Monitors positions independently from the trading cycle to ensure
stop-loss and take-profit orders are triggered promptly.

Enhanced with:
- Trailing Stop Loss support
- Dynamic SL/TP adjustments based on volatility
- Integration with RiskManager service
- Email alerts via Resend
- Reevaluation logging to database
- v3.0: Position locking to prevent race conditions
- v4.0: Liquidation Price Monitor + Auto-Close at Risk (2025-12-14)
- v4.1: Hybrid RAM + Supabase Persistence for SL/TP (2025-01-10)
"""

import asyncio
import logging
import os
import json
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum

# Supabase for hybrid persistence
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None

# FIX 2025-12-16: Import RateLimiter for close operations
try:
    from .rate_limiter import RateLimiter, RateLimitConfig
    RATE_LIMITER_AVAILABLE = True
except ImportError:
    RATE_LIMITER_AVAILABLE = False
    RateLimiter = None
    RateLimitConfig = None

from bot.logging_setup import get_logger
logger = get_logger(__name__)


# ============================================================================
# v4.0: LIQUIDATION MONITOR CONFIGURATION
# ============================================================================
class LiquidationRiskLevel(Enum):
    """Risk levels for liquidation proximity."""
    SAFE = "safe"                # > 30% from liquidation
    WARNING = "warning"          # 20-30% from liquidation
    DANGER = "danger"            # 10-20% from liquidation
    CRITICAL = "critical"        # < 10% from liquidation - AUTO-CLOSE triggered
    LIQUIDATED = "liquidated"    # Already liquidated


@dataclass
class LiquidationConfig:
    """
    Configuration for liquidation monitoring.
    
    IMPORTANT: This monitors DISTANCE TO LIQUIDATION PRICE, not free margin!
    
    Liquidation happens when:
    - LONG: current_price drops to liquidation_price
    - SHORT: current_price rises to liquidation_price
    
    Distance to liquidation = how much price can move before liquidation (in %)
    - NOT related to free margin being negative
    - Free margin can be negative but position still safe if price hasn't moved much
    
    Example with 10x leverage LONG:
    - Entry: $100
    - Liquidation price: ~$90.5 (varies by exchange maintenance margin)
    - Current price: $95
    - Distance to liquidation: (95-90.5)/95 = 4.7%
    
    Auto-close triggers ONLY when distance < auto_close_distance_pct (3.5% default)
    """
    enabled: bool = True
    warn_distance_pct: float = 15.0          # Warn when within 15% of liquidation price
    danger_distance_pct: float = 7.0         # Danger level at 7%
    auto_close_distance_pct: float = 3.5     # AUTO-CLOSE when within 3.5% of liquidation price
    emergency_close_distance_pct: float = 1.5  # Emergency partial close at 1.5%
    auto_close_max_retries: int = 5
    check_interval_seconds: float = 10.0     # Check every 10 seconds
    
    # Feature flags
    enable_auto_close: bool = True
    enable_partial_emergency_close: bool = True  # Close 50% at emergency level
    enable_alerts: bool = True
    enable_db_logging: bool = True


@dataclass
class LiquidationEvent:
    """Record of a liquidation-related event."""
    timestamp: datetime
    symbol: str
    user_id: Optional[str]
    event_type: str  # "warning", "danger", "auto_close_attempt", "auto_close_success", "auto_close_failed"
    risk_level: LiquidationRiskLevel
    distance_to_liquidation_pct: float
    liquidation_price: float
    current_price: float
    entry_price: float
    leverage: float
    action_taken: Optional[str] = None
    error_message: Optional[str] = None

# NEW v3.0: Import position lock manager
try:
    from bot.core import PositionLockManager
    CORE_MODULES_AVAILABLE = True
except ImportError:
    CORE_MODULES_AVAILABLE = False
    PositionLockManager = None

# Alert service import (lazy loaded)
_alert_service = None

def get_alert_service():
    """Lazy load alert service."""
    global _alert_service
    if _alert_service is None:
        try:
            from bot.services.alert_service import get_alert_service as _get_alert
            _alert_service = _get_alert()
        except Exception as e:
            logger.warning(f"Could not load alert service: {e}")
            _alert_service = None
    return _alert_service

@dataclass
class MonitoredPosition:
    """A position being monitored for SL/TP triggers."""
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: float
    quantity: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    user_id: Optional[str] = None
    created_at: datetime = None
    opened_at: datetime = None  # NEW: Track when position was opened
    
    # v4.1: Source tracking - identifies who opened the position
    # Values: "bot", "manual", "unknown", "external"
    # Bot will NOT auto-close positions with source="manual"
    source: str = "bot"
    
    # K1 FIX: Leverage tracking for proper SL/TP calculation
    leverage: float = 1.0  # 1.0 = no leverage (spot)
    leverage_aware_sl_tp: bool = True  # If True, SL/TP % is applied on capital basis, not price basis
    
    # Trailing Stop fields
    trailing_enabled: bool = False
    trailing_distance_percent: float = 2.0  # Default 2% trailing
    highest_price: Optional[float] = None   # Track highest price since entry (long)
    lowest_price: Optional[float] = None    # Track lowest price since entry (short)
    trailing_activated: bool = False        # Whether trailing has been activated
    
    # L12 FIX (2025-12-14): Disable exchange SL when trailing is active
    # When True, the exchange-side SL order will be cancelled when trailing activates
    # This prevents conflicts between trailing SL and static exchange SL
    disable_exchange_sl_when_trailing: bool = True
    exchange_sl_cancelled: bool = False  # Track if exchange SL was cancelled
    
    # Dynamic SL/TP fields
    dynamic_sl_enabled: bool = False
    original_stop_loss: Optional[float] = None  # Store original SL for reference
    last_sl_update: Optional[datetime] = None
    
    # NEW: Time-based exit
    max_hold_hours: float = 12.0  # Auto-close after 12 hours by default
    
    # NEW v1.1: Quick Exit for Scalping Mode
    # Allows quick profit-taking within first N minutes
    enable_quick_exit: bool = False
    quick_exit_profit_pct: float = 0.5  # Exit if this profit reached quickly
    quick_exit_time_minutes: int = 5    # "Quickly" = within these minutes
    quick_exit_triggered: bool = False  # Track if quick exit was used
    
    # NEW v1.2: Smart Break-Even
    # Automatically move SL to entry price when profit threshold reached
    enable_break_even: bool = True       # Enabled by default
    break_even_trigger_pct: float = 1.0  # Move to BE after 1% profit
    break_even_activated: bool = False   # Track if BE was activated
    break_even_buffer_pct: float = 0.1   # Small buffer above entry (0.1%)
    
    # NEW v1.2: Momentum Scalper
    # Exit if 50% of TP target reached within 60 minutes
    enable_momentum_scalp: bool = False
    momentum_scalp_pct: float = 50.0     # % of TP target to trigger early exit
    momentum_scalp_minutes: int = 60     # Time window for momentum scalp
    momentum_scalp_triggered: bool = False
    
    # NEW v1.2: News/Event Protection
    # Auto-close profitable positions before major economic events
    enable_news_protection: bool = False
    news_close_minutes_before: int = 30  # Close 30 min before event
    news_protection_triggered: bool = False
    
    # NEW: Partial Take Profit tracking
    partial_tp_executed: List[int] = None  # Track which TP levels were hit
    original_quantity: Optional[float] = None  # Original position size
    
    # FIX 2025-12-16: Notes field for special handling (e.g., currency restrictions)
    notes: Optional[str] = None  # "MANUAL_CLOSE_REQUIRED" if auto-close blocked
    
    # v4.0: LIQUIDATION MONITORING FIELDS
    liquidation_price: Optional[float] = None  # Calculated liquidation price
    maintenance_margin: Optional[float] = None  # Required maintenance margin
    margin_ratio: Optional[float] = None  # Current margin ratio (used_margin / total_equity)
    last_liquidation_check: Optional[datetime] = None
    liquidation_risk_level: str = "safe"  # safe/warning/danger/critical
    liquidation_warnings_sent: int = 0  # Count of warnings sent
    auto_close_attempted: bool = False  # Whether auto-close was attempted
    
    # v4.2 (2025-12-15): Manual position flag for Liquidation-only monitoring
    is_manual_position: bool = False  # If True, only liquidation protection is active
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.opened_at is None:
            self.opened_at = datetime.now()
        # Store original SL when position is created
        if self.original_stop_loss is None and self.stop_loss is not None:
            self.original_stop_loss = self.stop_loss
        # Initialize partial TP tracking
        if self.partial_tp_executed is None:
            self.partial_tp_executed = []
        if self.original_quantity is None:
            self.original_quantity = self.quantity


class PositionMonitorService:
    """
    Background service that monitors all active positions for SL/TP triggers.
    Runs independently from the main trading cycle.
    
    Enhanced with:
    - Trailing Stop Loss support
    - Dynamic SL/TP adjustments
    - Integration with RiskManager
    - AUTO-SET SL/TP for unprotected positions
    - MAX HOLD TIME - auto-close after X hours
    - PARTIAL TAKE PROFIT - scale out at multiple levels
    - v4.0: LIQUIDATION PRICE MONITOR + AUTO-CLOSE AT RISK
    """
    
    # Default Partial Take Profit levels
    DEFAULT_PARTIAL_TP_LEVELS = [
        {"profit_percent": 3.0, "close_percent": 40},  # Close 40% at +3%
        {"profit_percent": 5.0, "close_percent": 30},  # Close 30% at +5%
        {"profit_percent": 7.0, "close_percent": 30},  # Close remaining 30% at +7%
    ]
    
    # Default SL/TP percentages for auto-set
    DEFAULT_SL_PERCENT = 5.0  # 5% stop loss
    DEFAULT_TP_PERCENT = 7.0  # 7% take profit
    DEFAULT_MAX_HOLD_HOURS = 12.0  # 12 hours max hold
    
    # v4.0: Default Liquidation Monitor settings
    DEFAULT_LIQUIDATION_CONFIG = LiquidationConfig()
    
    def __init__(
        self,
        exchange_adapter,
        check_interval: float = 5.0,  # Check every 5 seconds
        on_sl_triggered: Optional[Callable] = None,
        on_tp_triggered: Optional[Callable] = None,
        on_partial_tp_triggered: Optional[Callable] = None,  # NEW
        on_time_exit_triggered: Optional[Callable] = None,   # NEW
        on_liquidation_risk: Optional[Callable] = None,      # v4.0: Liquidation risk callback
        on_auto_close_triggered: Optional[Callable] = None,  # v4.0: Auto-close callback
        risk_manager=None,  # Optional RiskManager integration
        enable_trailing: bool = True,
        enable_dynamic_sl: bool = True,
        enable_partial_tp: bool = True,   # NEW
        enable_time_exit: bool = True,    # NEW
        enable_auto_sl_tp: bool = True,   # NEW
        enable_liquidation_monitor: bool = True,  # v4.0: Enable liquidation monitoring
        # v1.2: New feature toggles
        enable_break_even: bool = True,       # Smart Break-Even
        enable_momentum_scalp: bool = False,  # Momentum Scalper
        enable_news_protection: bool = False, # News/Event Protection
        partial_tp_levels: List[Dict] = None,  # NEW
        user_settings: Dict = None,  # NEW: User-specific settings
        liquidation_config: LiquidationConfig = None,  # v4.0: Liquidation config
        default_user_id: str = None  # v4.3: Default user_id for sync from exchange
    ):
        self.exchange = exchange_adapter
        self.default_user_id = default_user_id  # v4.3: Store for sync operations
        self.check_interval = check_interval
        self.on_sl_triggered = on_sl_triggered
        self.on_tp_triggered = on_tp_triggered
        self.on_partial_tp_triggered = on_partial_tp_triggered
        self.on_time_exit_triggered = on_time_exit_triggered
        self.on_liquidation_risk = on_liquidation_risk  # v4.0
        self.on_auto_close_triggered = on_auto_close_triggered  # v4.0
        self.risk_manager = risk_manager
        self.enable_trailing = enable_trailing
        self.enable_dynamic_sl = enable_dynamic_sl
        self.enable_partial_tp = enable_partial_tp
        self.enable_time_exit = enable_time_exit
        self.enable_auto_sl_tp = enable_auto_sl_tp
        self.enable_liquidation_monitor = enable_liquidation_monitor  # v4.0
        # v1.2: New features
        self.enable_break_even = enable_break_even
        self.enable_momentum_scalp = enable_momentum_scalp
        self.enable_news_protection = enable_news_protection
        self.partial_tp_levels = partial_tp_levels or self.DEFAULT_PARTIAL_TP_LEVELS
        
        # v4.0: Liquidation configuration
        self.liquidation_config = liquidation_config or self.DEFAULT_LIQUIDATION_CONFIG
        
        # User settings for auto SL/TP
        self.user_settings = user_settings or {}
        self.default_sl_percent = self.user_settings.get('sl_percent', self.DEFAULT_SL_PERCENT)
        self.default_tp_percent = self.user_settings.get('tp_percent', self.DEFAULT_TP_PERCENT)
        self.default_max_hold_hours = self.user_settings.get('max_hold_hours', self.DEFAULT_MAX_HOLD_HOURS)
        
        self.positions: Dict[str, MonitoredPosition] = {}
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._price_cache: Dict[str, float] = {}
        
        # Counter for periodic dynamic SL/TP checks (every 60 seconds)
        self._dynamic_check_counter = 0
        self._dynamic_check_interval = 12  # Every 12 * 5s = 60s
        
        # v4.0: Counter for liquidation checks (every 10 seconds = 2 iterations at 5s)
        self._liquidation_check_counter = 0
        self._liquidation_check_interval = 2  # Every 2 * 5s = 10s
        
        # v4.0: Liquidation events log (in-memory, also persisted to DB)
        self._liquidation_events: List[LiquidationEvent] = []
        
        # Database manager for reevaluation logging
        self._db_manager = None
        
        # NEW v3.0: Position lock manager to prevent race conditions
        self._position_lock_manager = None
        if CORE_MODULES_AVAILABLE:
            self._position_lock_manager = PositionLockManager()
            logger.info("✅ Position lock manager initialized for PositionMonitor")
        
        # v4.1: HYBRID PERSISTENCE (RAM + Supabase)
        self._supabase_client: Optional[Client] = None
        self._persistence_task: Optional[asyncio.Task] = None
        self._persistence_interval = 5.0  # Sync every 5 seconds
        self._positions_dirty = False  # Track if positions changed since last sync
        self._last_sync_time: Optional[datetime] = None
        self._sync_failures = 0
        self._max_sync_failures = 10  # Alert after 10 consecutive failures
        # Track which type of Supabase key was used (service or anon) to help diagnose RLS issues
        self._supabase_key_type: Optional[str] = None
        
        # T4 FIX: Lock for Supabase sync to prevent race conditions
        self._sync_lock = asyncio.Lock()
        
        # FIX 2025-12-16: Rate limiter for close operations to prevent API hammering
        self._close_rate_limiter: Optional['RateLimiter'] = None
        self._close_attempts_this_minute: Dict[str, int] = {}  # {symbol: count}
        self._max_close_attempts_per_minute = 3  # Max 3 close attempts per symbol per minute
        self._last_close_attempt_reset = datetime.now()
        if RATE_LIMITER_AVAILABLE:
            # Create specialized rate limiter for close operations
            close_config = RateLimitConfig(
                max_trades_per_hour=60,  # Max 60 closes per hour
                max_trades_per_day=200,  # Max 200 closes per day
                max_concurrent_positions=50,
                symbol_cooldown_minutes=1,  # 1 min cooldown per symbol
                max_signals_per_cycle=10
            )
            self._close_rate_limiter = RateLimiter(close_config)
            logger.info("✅ Close operation RateLimiter initialized for PositionMonitor")
        
        logger.info(
            f"PositionMonitorService initialized (interval: {check_interval}s) | "
            f"Trailing: {enable_trailing} | Dynamic SL/TP: {enable_dynamic_sl} | "
            f"Partial TP: {enable_partial_tp} | Time Exit: {enable_time_exit} | "
            f"Auto SL/TP: {enable_auto_sl_tp} | "
            f"🚨 Liquidation Monitor: {enable_liquidation_monitor} "
            f"(warn:{self.liquidation_config.warn_distance_pct}% / auto-close:{self.liquidation_config.auto_close_distance_pct}%) | "
            f"💾 Hybrid Persistence: {SUPABASE_AVAILABLE} (interval: {self._persistence_interval}s)"
        )
    
    def set_db_manager(self, db_manager):
        """Set database manager for reevaluation logging."""
        self._db_manager = db_manager
        logger.info("DatabaseManager connected to PositionMonitor for reevaluation logging")
    
    # ========================================================================
    # v4.1: HYBRID PERSISTENCE - RAM + SUPABASE
    # ========================================================================
    
    def _init_supabase(self) -> bool:
        """
        Initialize Supabase client for hybrid persistence.
        Returns True if successful, False otherwise.
        """
        if not SUPABASE_AVAILABLE:
            logger.warning("💾 Supabase library not available - persistence disabled")
            return False
        
        try:
            # Support both SUPABASE_URL and VITE_SUPABASE_URL (frontend prefix)
            supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
            # IMPORTANT: Use SERVICE_KEY first (has full access), fallback to anon key
            supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY")
            
            if not supabase_url or not supabase_key:
                logger.warning("💾 Supabase credentials not configured - persistence disabled")
                return False
            
            self._supabase_client = create_client(supabase_url, supabase_key)
            # Remember which key type we're using so we can detect if RLS will block writes
            if os.getenv("SUPABASE_SERVICE_KEY"):
                self._supabase_key_type = "service"
            elif os.getenv("SUPABASE_KEY"):
                self._supabase_key_type = "anon"
            else:
                self._supabase_key_type = "unknown"
            logger.info(f"💾 Supabase client initialized for hybrid persistence (key_type={self._supabase_key_type})")
            return True
            
        except Exception as e:
            logger.error(f"💾 Failed to initialize Supabase: {e}")
            return False
    
    async def _load_from_supabase(self) -> int:
        """
        Load monitored positions from Supabase on startup.
        
        RAM is primary source of truth during runtime, but on startup
        we restore state from Supabase to handle bot restarts gracefully.
        
        v4.1: Now respects 'source' field - skips manual positions.
        
        Returns:
            Number of positions restored
        """
        if not self._supabase_client:
            return 0
        
        restored_count = 0
        manual_skipped = 0
        
        try:
            # Query active positions from Supabase
            response = self._supabase_client.table("monitored_positions").select("*").eq("is_active", True).execute()
            
            if not response.data:
                logger.info("💾 No active positions in Supabase to restore")
                return 0
            
            for row in response.data:
                try:
                    # v4.1: Check source - skip manual positions
                    position_source = row.get("source", "bot") or "bot"
                    if position_source == "manual":
                        manual_skipped += 1
                        logger.info(
                            f"📋 SKIPPING MANUAL POSITION from Supabase: {row['symbol']} | "
                            f"User maintains full control"
                        )
                        continue
                    
                    # Reconstruct MonitoredPosition from row
                    position = MonitoredPosition(
                        symbol=row["symbol"],
                        side=row["side"],
                        entry_price=float(row["entry_price"]),
                        quantity=float(row["quantity"]),
                        stop_loss=float(row["stop_loss"]) if row.get("stop_loss") else None,
                        take_profit=float(row["take_profit"]) if row.get("take_profit") else None,
                        user_id=row.get("user_id"),
                        source=position_source,  # v4.1: Track source
                        leverage=float(row.get("leverage", 1.0)),
                        leverage_aware_sl_tp=row.get("leverage_aware_sl_tp", True),
                        trailing_enabled=row.get("trailing_enabled", False),
                        trailing_distance_percent=float(row.get("trailing_distance_pct", 2.0)),
                        highest_price=float(row["highest_price"]) if row.get("highest_price") else None,
                        lowest_price=float(row["lowest_price"]) if row.get("lowest_price") else None,
                        trailing_activated=row.get("trailing_activated", False),
                        dynamic_sl_enabled=row.get("dynamic_sl_enabled", False),
                        original_stop_loss=float(row["original_stop_loss"]) if row.get("original_stop_loss") else None,
                        max_hold_hours=float(row.get("max_hold_hours", 12.0)),
                        liquidation_price=float(row["liquidation_price"]) if row.get("liquidation_price") else None,
                        liquidation_risk_level=row.get("liquidation_risk_level", "safe"),
                        original_quantity=float(row["original_quantity"]) if row.get("original_quantity") else None,
                    )
                    
                    # Parse created_at and opened_at
                    if row.get("created_at"):
                        position.created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                    if row.get("opened_at"):
                        position.opened_at = datetime.fromisoformat(row["opened_at"].replace("Z", "+00:00"))
                    
                    # Parse partial_tp_executed JSON array
                    if row.get("partial_tp_executed"):
                        if isinstance(row["partial_tp_executed"], str):
                            position.partial_tp_executed = json.loads(row["partial_tp_executed"])
                        else:
                            position.partial_tp_executed = row["partial_tp_executed"]
                    
                    # Add to RAM
                    key = f"{position.user_id}:{position.symbol}" if position.user_id else position.symbol
                    self.positions[key] = position
                    restored_count += 1
                    
                    logger.debug(
                        f"💾 Restored position: {key} | SL={position.stop_loss} TP={position.take_profit} | Source={position_source}"
                    )
                    
                except Exception as parse_err:
                    logger.error(f"💾 Failed to parse position row: {parse_err} | Row: {row}")
            
            if restored_count > 0:
                logger.info(f"💾 Restored {restored_count} positions from Supabase")
            if manual_skipped > 0:
                logger.info(f"📋 Skipped {manual_skipped} manual positions (user-managed)")
            
        except Exception as e:
            logger.error(f"💾 Failed to load positions from Supabase: {e}")
            import traceback
            traceback.print_exc()
        
        return restored_count
    
    async def _sync_to_supabase(self, force: bool = False) -> bool:
        """
        Batch sync RAM positions to Supabase.
        
        Called periodically (every 5-10 seconds) to persist current state.
        Only syncs if positions changed (dirty flag) or force=True.
        
        T4 FIX: Added asyncio.Lock to prevent race conditions.
        T4 FIX: Changed sync strategy - no longer marks all positions inactive first.
        
        Args:
            force: Force sync even if no changes detected
            
        Returns:
            True if sync successful, False otherwise
        """
        if not self._supabase_client:
            return False
        
        if not force and not self._positions_dirty:
            return True  # No changes to sync
        
        # T4 FIX: Use lock to prevent concurrent syncs
        async with self._sync_lock:
            try:
                # Get current position keys in RAM
                current_position_keys = set(self.positions.keys())
                
                # Prepare batch upsert data
                batch_data = []
                
                for key, pos in self.positions.items():
                    # Convert position to dict for Supabase
                    # Convert UUID to string if needed for JSON serialization
                    user_id_str = str(pos.user_id) if pos.user_id else None
                    
                    pos_data = {
                        "position_key": key,
                        "user_id": user_id_str,
                        "symbol": pos.symbol,
                        "side": pos.side,
                        "entry_price": pos.entry_price,
                        "quantity": pos.quantity,
                        "stop_loss": pos.stop_loss,
                        "take_profit": pos.take_profit,
                        "leverage": pos.leverage,
                        "leverage_aware_sl_tp": pos.leverage_aware_sl_tp,
                        "trailing_enabled": pos.trailing_enabled,
                        "trailing_distance_pct": pos.trailing_distance_percent,
                        "highest_price": pos.highest_price,
                        "lowest_price": pos.lowest_price,
                        "trailing_activated": pos.trailing_activated,
                        "dynamic_sl_enabled": pos.dynamic_sl_enabled,
                        "original_stop_loss": pos.original_stop_loss,
                        "max_hold_hours": pos.max_hold_hours,
                        "liquidation_price": pos.liquidation_price,
                        "liquidation_risk_level": pos.liquidation_risk_level,
                        "original_quantity": pos.original_quantity,
                        "partial_tp_executed": json.dumps(pos.partial_tp_executed or []),
                        "created_at": pos.created_at.isoformat() if pos.created_at else None,
                        "opened_at": pos.opened_at.isoformat() if pos.opened_at else None,
                        "source": pos.source,  # Track if position is bot/manual/external
                        "is_active": True,
                        "last_sync": datetime.now().isoformat()
                    }
                    batch_data.append(pos_data)
                
                # T4 FIX: IMPROVED STRATEGY - Instead of marking all inactive first (dangerous!),
                # we now: 1) Upsert current positions, 2) Mark ONLY removed positions as inactive
                
                # Step 1: Upsert all current positions (they're all active)
                if batch_data:
                    self._supabase_client.table("monitored_positions").upsert(
                        batch_data,
                        on_conflict="position_key"
                    ).execute()
                
                # Step 2: Get all active positions from Supabase that are NOT in current RAM
                # and mark them as inactive (they were removed/closed)
                try:
                    response = self._supabase_client.table("monitored_positions").select(
                        "position_key"
                    ).eq("is_active", True).execute()
                    
                    supabase_keys = set(row["position_key"] for row in response.data)
                    removed_keys = supabase_keys - current_position_keys
                    
                    if removed_keys:
                        # Mark removed positions as inactive
                        self._supabase_client.table("monitored_positions").update({
                            "is_active": False,
                            "closed_at": datetime.now().isoformat()
                        }).in_("position_key", list(removed_keys)).execute()
                        
                        logger.debug(f"💾 Marked {len(removed_keys)} removed positions as inactive")
                        
                except Exception as cleanup_err:
                    logger.warning(f"💾 Failed to cleanup removed positions: {cleanup_err}")
                
                # Clear dirty flag
                self._positions_dirty = False
                self._last_sync_time = datetime.now()
                self._sync_failures = 0
                
                logger.debug(f"💾 Synced {len(batch_data)} positions to Supabase")
                return True
                
            except Exception as e:
                self._sync_failures += 1
                logger.error(f"💾 Supabase sync failed ({self._sync_failures}/{self._max_sync_failures}): {e}")
                
                # Detect common Row-Level Security (RLS) error and gracefully fall back
                try:
                    err_str = str(e).lower()
                except Exception:
                    err_str = ''
                
                if 'row-level security' in err_str or '42501' in err_str or 'new row violates row-level security' in err_str:
                    # Create a local backup of the batch_data to avoid data loss
                    try:
                        backup_fname = f"logs/positions_backup_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
                        os.makedirs(os.path.dirname(backup_fname), exist_ok=True)
                        with open(backup_fname, 'w') as bf:
                            json.dump(batch_data, bf, default=str, indent=2)
                        logger.critical(
                            f"💾 Supabase RLS detected (writes blocked). Backed up {len(batch_data)} positions to {backup_fname}."
                        )
                    except Exception as be:
                        logger.critical(f"💾 Supabase RLS detected and failed to write local backup: {be}")
                    
                    # Disable Supabase persistence to stop repeated failures; user must fix RLS or provide a SUPABASE_SERVICE_KEY
                    self._supabase_client = None
                    logger.critical(
                        "💾 Supabase persistence disabled due to RLS errors. "
                        "Please set SUPABASE_SERVICE_KEY or update the monitored_positions RLS policy to allow the bot to write."
                    )
                    return False
                
                if self._sync_failures >= self._max_sync_failures:
                    logger.critical(
                        f"💾 CRITICAL: {self._sync_failures} consecutive Supabase sync failures! "
                        "Position data may be lost on restart!"
                    )
                
                return False
    
    async def _remove_from_supabase(self, key: str) -> bool:
        """
        Mark a position as inactive in Supabase (soft delete).
        
        Args:
            key: Position key (user_id:symbol or symbol)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._supabase_client:
            return False
        
        try:
            self._supabase_client.table("monitored_positions").update({
                "is_active": False,
                "closed_at": datetime.now().isoformat()
            }).eq("position_key", key).execute()
            
            logger.debug(f"💾 Marked position {key} as inactive in Supabase")
            return True
            
        except Exception as e:
            logger.error(f"💾 Failed to remove position {key} from Supabase: {e}")
            return False
    
    async def _persistence_loop(self):
        """
        Background task for periodic Supabase sync.
        Runs every _persistence_interval seconds.
        """
        logger.info(f"💾 Persistence loop started (interval: {self._persistence_interval}s)")
        
        while self.running:
            try:
                await asyncio.sleep(self._persistence_interval)
                
                if self.positions:  # Only sync if we have positions
                    await self._sync_to_supabase()
                    
            except asyncio.CancelledError:
                # Final sync before shutdown
                logger.info("💾 Persistence loop cancelled - performing final sync...")
                await self._sync_to_supabase(force=True)
                break
            except Exception as e:
                logger.error(f"💾 Persistence loop error: {e}")
        
        logger.info("💾 Persistence loop stopped")
    
    def _mark_dirty(self):
        """Mark positions as changed (needs sync to Supabase)."""
        self._positions_dirty = True
    
    def get_persistence_status(self) -> Dict[str, Any]:
        """Get status of hybrid persistence system."""
        return {
            "supabase_available": SUPABASE_AVAILABLE,
            "supabase_connected": self._supabase_client is not None,
            "persistence_task_running": self._persistence_task is not None and not self._persistence_task.done(),
            "positions_count": len(self.positions),
            "positions_dirty": self._positions_dirty,
            "last_sync_time": self._last_sync_time.isoformat() if self._last_sync_time else None,
            "sync_failures": self._sync_failures,
            "sync_interval_seconds": self._persistence_interval
        }
    # ========================================================================
    # END v4.1: HYBRID PERSISTENCE
    # ========================================================================

    async def _save_reevaluation(
        self,
        pos: 'MonitoredPosition',
        reevaluation_type: str,
        old_sl: Optional[float],
        new_sl: Optional[float],
        old_tp: Optional[float],
        new_tp: Optional[float],
        current_price: float,
        profit_pct: float,
        reason: str,
        action_taken: str
    ):
        """Save reevaluation event to database."""
        if not self._db_manager:
            return
        
        # FIX 2025-12-16: Skip saving if user_id is None (position from exchange sync without DB record)
        if not pos.user_id:
            logger.debug(
                f"📝 Skipping reevaluation save for {pos.symbol} - no user_id "
                f"(position may be from exchange sync without DB record)"
            )
            return
        
        try:
            from sqlalchemy import text
            # FIX: DatabaseManager.__enter__() returns DatabaseManager, not Session
            # Use db.session to access the actual SQLAlchemy Session
            with self._db_manager as db:
                db.session.execute(text("""
                    INSERT INTO position_reevaluations 
                    (position_id, user_id, symbol, reevaluation_type, 
                     old_sl, new_sl, old_tp, new_tp, current_price, 
                     profit_pct, reason, action_taken)
                    VALUES (:pos_id, :user_id, :symbol, :type, 
                            :old_sl, :new_sl, :old_tp, :new_tp, :price,
                            :profit, :reason, :action)
                """), {
                    'pos_id': f"{pos.symbol}_{pos.entry_price}",
                    'user_id': pos.user_id,
                    'symbol': pos.symbol,
                    'type': reevaluation_type,
                    'old_sl': old_sl,
                    'new_sl': new_sl,
                    'old_tp': old_tp,
                    'new_tp': new_tp,
                    'price': current_price,
                    'profit': profit_pct,
                    'reason': reason,
                    'action': action_taken
                })
                # Note: commit is handled by DatabaseManager.__exit__()
                logger.debug(f"📝 Saved reevaluation: {pos.symbol} - {reevaluation_type}")
        except Exception as e:
            logger.error(f"Failed to save reevaluation: {e}")
    
    async def _send_alert(
        self,
        alert_type: str,
        pos: 'MonitoredPosition',
        current_price: float,
        **kwargs
    ):
        """Send email alert for position event."""
        alert_service = get_alert_service()
        if not alert_service:
            return
        
        # Get user email from database
        user_email = await self._get_user_email(pos.user_id)
        if not user_email:
            return
        
        try:
            if alert_type == 'sl_triggered':
                pnl = (current_price - pos.entry_price) * pos.quantity
                if pos.side == 'short':
                    pnl = -pnl
                await alert_service.send_sl_alert(
                    user_email=user_email,
                    symbol=pos.symbol,
                    entry_price=pos.entry_price,
                    sl_price=pos.stop_loss,
                    current_price=current_price,
                    pnl=pnl,
                    quantity=pos.quantity
                )
            elif alert_type == 'tp_triggered':
                pnl = (current_price - pos.entry_price) * pos.quantity
                if pos.side == 'short':
                    pnl = -pnl
                await alert_service.send_tp_alert(
                    user_email=user_email,
                    symbol=pos.symbol,
                    entry_price=pos.entry_price,
                    tp_price=pos.take_profit,
                    current_price=current_price,
                    pnl=pnl,
                    quantity=pos.quantity,
                    partial=kwargs.get('partial', False),
                    level=kwargs.get('level', 0)
                )
            elif alert_type == 'trailing_update':
                profit_pct = ((current_price / pos.entry_price) - 1) * 100
                if pos.side == 'short':
                    profit_pct = -profit_pct
                await alert_service.send_trailing_update_alert(
                    user_email=user_email,
                    symbol=pos.symbol,
                    old_sl=kwargs.get('old_sl', 0),
                    new_sl=kwargs.get('new_sl', 0),
                    current_price=current_price,
                    profit_pct=profit_pct
                )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    async def _get_user_email(self, user_id: str) -> Optional[str]:
        """Get user email from database."""
        if not user_id or not self._db_manager:
            return None
        
        try:
            from sqlalchemy import text
            with self._db_manager as session:
                result = session.execute(
                    text("SELECT email FROM profiles WHERE id = :user_id"),
                    {'user_id': user_id}
                )
                row = result.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.debug(f"Could not get user email: {e}")
            return None
    
    def set_risk_manager(self, risk_manager):
        """Set or update the RiskManager instance."""
        self.risk_manager = risk_manager
        logger.info("RiskManager connected to PositionMonitor")
    
    def _auto_set_sl_tp(
        self,
        side: str,
        entry_price: float,
        sl_percent: float = None,
        tp_percent: float = None,
        leverage: float = 1.0,
        leverage_aware: bool = True
    ) -> tuple:
        """
        AUTO-SET SL/TP based on default percentages.
        
        K1 FIX: Now supports leverage-aware SL/TP calculation.
        
        If leverage_aware=True:
            - SL/TP % refers to CAPITAL loss/gain, not price movement
            - With 5% SL and 10x leverage: actual price SL = 0.5% move (5%/10)
            - This protects users from unexpected large losses
            
        If leverage_aware=False (legacy):
            - SL/TP % refers to PRICE movement directly
            - With 5% SL and 10x leverage: actual capital loss = 50%!
        
        Returns (stop_loss, take_profit) tuple.
        """
        sl_pct = sl_percent or self.default_sl_percent
        tp_pct = tp_percent or self.default_tp_percent
        
        # K1 FIX: Adjust percentages for leverage if leverage_aware
        effective_leverage = max(leverage, 1.0)  # Ensure at least 1x
        
        if leverage_aware and effective_leverage > 1.0:
            # Convert capital-based % to price-based %
            # Example: 5% capital SL with 10x leverage = 0.5% price movement
            effective_sl_pct = sl_pct / effective_leverage
            effective_tp_pct = tp_pct / effective_leverage
            
            logger.info(
                f"🔧 K1 FIX: Leverage-aware SL/TP for {effective_leverage}x leverage: "
                f"SL {sl_pct}% capital → {effective_sl_pct:.2f}% price | "
                f"TP {tp_pct}% capital → {effective_tp_pct:.2f}% price"
            )
        else:
            effective_sl_pct = sl_pct
            effective_tp_pct = tp_pct
        
        if side.lower() == 'long':
            stop_loss = entry_price * (1 - effective_sl_pct / 100)
            take_profit = entry_price * (1 + effective_tp_pct / 100)
        else:  # short
            stop_loss = entry_price * (1 + effective_sl_pct / 100)
            take_profit = entry_price * (1 - effective_tp_pct / 100)
        
        return stop_loss, take_profit
    
    def add_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        user_id: Optional[str] = None,
        trailing_enabled: bool = None,
        trailing_distance_percent: float = 2.0,
        dynamic_sl_enabled: bool = None,
        max_hold_hours: float = None,
        leverage: float = 1.0,  # K1 FIX: Add leverage parameter
        leverage_aware_sl_tp: bool = True,  # K1 FIX: Enable leverage-aware SL/TP by default
        # Quick Exit parameters (for scalping mode)
        enable_quick_exit: bool = False,
        quick_exit_profit_pct: float = 0.5,
        quick_exit_time_minutes: float = 30.0,
        # v1.2: Smart Break-Even parameters
        enable_break_even: bool = True,
        break_even_trigger_pct: float = 1.0,
        break_even_buffer_pct: float = 0.1,
        # v1.2: Momentum Scalper parameters
        enable_momentum_scalp: bool = False,
        momentum_scalp_pct: float = 50.0,
        momentum_scalp_minutes: int = 60,
        # v1.2: News Protection parameters
        enable_news_protection: bool = False,
        news_close_minutes_before: int = 30,
        # v4.1: Source tracking - "bot", "manual", "unknown", "external"
        source: str = "bot"
    ):
        """Add a position to monitor with optional trailing stop and dynamic SL.
        
        K1 FIX: Now supports leverage parameter. If leverage_aware_sl_tp=True,
        SL/TP percentages are automatically adjusted to protect capital.
        
        v4.1: If source="manual", position will be monitored but NOT auto-closed.
        v4.2 (2025-12-15): Manual positions now have ONLY Liquidation Protection enabled.
        """
        # v4.2: Manual positions - add to monitoring with ONLY Liquidation Protection
        if source == "manual":
            logger.info(
                f"📋 MANUAL POSITION DETECTED: {symbol} | "
                f"Adding with LIQUIDATION PROTECTION ONLY. "
                f"No SL/TP/Trailing/TimeExit will trigger."
            )
            # Create position with ALL auto-features disabled except liquidation monitoring
            manual_position = MonitoredPosition(
                symbol=symbol,
                side=side.lower(),
                entry_price=entry_price,
                quantity=quantity,
                stop_loss=None,  # No SL auto-close for manual
                take_profit=None,  # No TP auto-close for manual
                user_id=user_id,
                source=source,
                trailing_enabled=False,  # Disabled for manual
                trailing_distance_percent=0,
                dynamic_sl_enabled=False,  # Disabled for manual
                original_stop_loss=None,
                max_hold_hours=None,  # No time exit for manual
                leverage=leverage,  # IMPORTANT: Track leverage for liquidation calc
                leverage_aware_sl_tp=False,
                original_quantity=quantity,
                enable_quick_exit=False,  # Disabled for manual
                enable_break_even=False,  # Disabled for manual
                enable_momentum_scalp=False,  # Disabled for manual
                enable_news_protection=False,  # Disabled for manual
                is_manual_position=True  # v4.2: Flag for manual handling
            )
            
            key = f"{user_id}:{symbol}" if user_id else symbol
            self.positions[key] = manual_position
            self._mark_dirty()
            
            logger.info(
                f"🛡️ MANUAL POSITION ADDED: {key} | {side.upper()} @ {entry_price} | "
                f"Leverage: {leverage}x | LIQUIDATION PROTECTION ACTIVE | "
                f"All other features: DISABLED"
            )
            return  # Exit early - don't apply other defaults
        
        # Use instance defaults if not specified
        if trailing_enabled is None:
            trailing_enabled = self.enable_trailing
        if dynamic_sl_enabled is None:
            dynamic_sl_enabled = self.enable_dynamic_sl
        if max_hold_hours is None:
            max_hold_hours = self.default_max_hold_hours
        
        # ========== AUTO-SET SL/TP if missing ==========
        auto_set_applied = False
        if self.enable_auto_sl_tp and (stop_loss is None or take_profit is None):
            # K1 FIX: Pass leverage to _auto_set_sl_tp
            auto_sl, auto_tp = self._auto_set_sl_tp(
                side, 
                entry_price, 
                leverage=leverage,
                leverage_aware=leverage_aware_sl_tp
            )
            
            if stop_loss is None:
                stop_loss = auto_sl
                auto_set_applied = True
            if take_profit is None:
                take_profit = auto_tp
                auto_set_applied = True
            
            if auto_set_applied:
                effective_sl_pct = self.default_sl_percent / max(leverage, 1.0) if leverage_aware_sl_tp and leverage > 1 else self.default_sl_percent
                effective_tp_pct = self.default_tp_percent / max(leverage, 1.0) if leverage_aware_sl_tp and leverage > 1 else self.default_tp_percent
                logger.info(
                    f"🛡️ AUTO-SET SL/TP for {symbol} ({leverage}x leverage): "
                    f"SL={stop_loss:.4f} ({effective_sl_pct:.2f}% price = {self.default_sl_percent}% capital) | "
                    f"TP={take_profit:.4f} ({effective_tp_pct:.2f}% price = {self.default_tp_percent}% capital)"
                )
            
        position = MonitoredPosition(
            symbol=symbol,
            side=side.lower(),
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            user_id=user_id,
            source=source,  # v4.1: Source tracking
            trailing_enabled=trailing_enabled,
            trailing_distance_percent=trailing_distance_percent,
            dynamic_sl_enabled=dynamic_sl_enabled,
            original_stop_loss=stop_loss,
            max_hold_hours=max_hold_hours,
            leverage=leverage,  # K1 FIX
            leverage_aware_sl_tp=leverage_aware_sl_tp,  # K1 FIX
            original_quantity=quantity,
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
        
        key = f"{user_id}:{symbol}" if user_id else symbol
        self.positions[key] = position
        
        # v4.1: Mark dirty for Supabase sync
        self._mark_dirty()
        
        # Build feature flags for logging
        features = []
        if enable_quick_exit:
            features.append(f"QuickExit={quick_exit_profit_pct}%/{quick_exit_time_minutes}m")
        if enable_break_even:
            features.append(f"BreakEven@{break_even_trigger_pct}%")
        if enable_momentum_scalp:
            features.append(f"MomentumScalp={momentum_scalp_pct}%/{momentum_scalp_minutes}m")
        if enable_news_protection:
            features.append(f"NewsProtect={news_close_minutes_before}min")
        
        features_str = " | " + " | ".join(features) if features else ""
        
        logger.info(
            f"📍 Monitoring position: {key} | {side.upper()} @ {entry_price} | "
            f"SL={stop_loss} TP={take_profit} | "
            f"Trailing={trailing_enabled} | Dynamic={dynamic_sl_enabled} | "
            f"MaxHold={max_hold_hours}h{features_str}"
        )
    
    def remove_position(self, symbol: str, user_id: Optional[str] = None):
        """Remove a position from monitoring."""
        key = f"{user_id}:{symbol}" if user_id else symbol
        
        if key in self.positions:
            del self.positions[key]
            # v4.1: Mark dirty and remove from Supabase
            self._mark_dirty()
            asyncio.create_task(self._remove_from_supabase(key))
            logger.info(f"Removed position monitoring: {key}")
    
    def update_sl_tp(
        self,
        symbol: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        user_id: Optional[str] = None
    ):
        """Update SL/TP for a monitored position."""
        key = f"{user_id}:{symbol}" if user_id else symbol
        
        if key in self.positions:
            if stop_loss is not None:
                self.positions[key].stop_loss = stop_loss
            if take_profit is not None:
                self.positions[key].take_profit = take_profit
            # v4.1: Mark dirty for Supabase sync
            self._mark_dirty()
            logger.info(f"Updated {key}: SL={stop_loss} TP={take_profit}")
    
    async def sync_from_database(self, db_manager=None) -> int:
        """
        Synchronize positions from database into the monitor.
        
        This should be called at bot startup to restore monitoring
        for positions that were opened in previous sessions.
        
        P0-NEW-2 FIX: Auto-set default SL/TP for positions without them.
        v4.1: Skip positions with source="manual" (user-managed positions)
        
        Returns:
            Number of positions synchronized.
        """
        # P0-NEW-2: Default SL/TP percentages for positions without protection
        DEFAULT_SL_PERCENT = 0.05   # 5% stop loss
        DEFAULT_TP_PERCENT = 0.10   # 10% take profit
        
        synced_count = 0
        auto_protected_count = 0
        manual_skipped_count = 0
        
        try:
            if db_manager is None:
                from bot.db import DatabaseManager
                db_manager = DatabaseManager()
            
            with db_manager.session_scope() as session:
                from bot.db import Position as DBPosition
                
                # Get all open positions from database
                open_positions = (
                    session.query(DBPosition)
                    .filter(DBPosition.status == "OPEN")
                    .all()
                )
                
                for pos in open_positions:
                    key = f"{pos.user_id}:{pos.symbol}" if pos.user_id else pos.symbol
                    
                    # v4.1: Skip manual positions - don't auto-manage them
                    position_source = getattr(pos, 'source', None) or 'unknown'
                    if position_source == 'manual':
                        manual_skipped_count += 1
                        logger.info(
                            f"📋 SKIPPING MANUAL POSITION: {pos.symbol} | "
                            f"User maintains full control (not auto-managed)"
                        )
                        continue
                    
                    # Don't overwrite if already monitoring this position
                    if key not in self.positions:
                        # P0-NEW-2 FIX: Auto-set SL/TP for unprotected positions
                        stop_loss = pos.stop_loss
                        take_profit = pos.take_profit
                        
                        if stop_loss is None or take_profit is None:
                            entry_price = pos.entry_price or 0
                            side = (pos.side or 'long').lower()
                            
                            if entry_price > 0:
                                if side == 'long':
                                    # Long: SL below entry, TP above entry
                                    if stop_loss is None:
                                        stop_loss = entry_price * (1 - DEFAULT_SL_PERCENT)
                                    if take_profit is None:
                                        take_profit = entry_price * (1 + DEFAULT_TP_PERCENT)
                                else:
                                    # Short: SL above entry, TP below entry
                                    if stop_loss is None:
                                        stop_loss = entry_price * (1 + DEFAULT_SL_PERCENT)
                                    if take_profit is None:
                                        take_profit = entry_price * (1 - DEFAULT_TP_PERCENT)
                                
                                # Update position in DB with auto-calculated SL/TP
                                if pos.stop_loss is None:
                                    pos.stop_loss = stop_loss
                                if pos.take_profit is None:
                                    pos.take_profit = take_profit
                                session.flush()
                                
                                auto_protected_count += 1
                                logger.warning(
                                    f"🛡️ AUTO-PROTECTED position {pos.symbol}: "
                                    f"Set default SL={stop_loss:.4f} ({DEFAULT_SL_PERCENT*100}%) "
                                    f"TP={take_profit:.4f} ({DEFAULT_TP_PERCENT*100}%)"
                                )
                        
                        self.add_position(
                            symbol=pos.symbol,
                            side=pos.side,
                            entry_price=pos.entry_price,
                            quantity=pos.quantity,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            user_id=pos.user_id,
                            source=position_source  # v4.1: Pass source for tracking
                        )
                        synced_count += 1
                        
                        # Log restore status
                        if pos.stop_loss is not None or pos.take_profit is not None:
                            logger.info(
                                f"🔄 Restored position monitoring: {pos.symbol} | "
                                f"SL={stop_loss} TP={take_profit} | Source: {position_source}"
                            )
                
                if synced_count > 0:
                    logger.info(f"✅ Synchronized {synced_count} positions from database")
                    if auto_protected_count > 0:
                        logger.info(
                            f"🛡️ Auto-protected {auto_protected_count} positions "
                            f"with default SL/TP (5%/10%)"
                        )
                if manual_skipped_count > 0:
                    logger.info(
                        f"📋 Skipped {manual_skipped_count} manual positions "
                        f"(user maintains control)"
                    )
                if synced_count == 0 and manual_skipped_count == 0:
                    logger.info("No existing positions to restore from database")
                    
        except Exception as e:
            logger.error(f"Failed to sync positions from database: {e}")
        
        return synced_count
    
    async def sync_from_exchange(self, db_manager=None, retry_count: int = 2) -> int:
        """
        Synchronize positions from exchange (works for Futures, Margin, AND SPOT).
        
        Fetches open positions from exchange and cross-references with DB
        to get SL/TP values (since exchange API doesn't return them directly).
        
        FIXED: Now works correctly for SPOT mode (Binance SPOT, Kraken spot).
        
        Returns:
            Number of positions synchronized.
        """
        synced_count = 0
        
        try:
            # SPOT FIX: Retry a few times to handle API warmup
            exchange_positions = []
            for attempt in range(retry_count + 1):
                exchange_positions = await self.exchange.get_positions()
                if exchange_positions:
                    break
                if attempt < retry_count:
                    logger.debug(f"No positions found, retrying ({attempt + 1}/{retry_count})...")
                    await asyncio.sleep(1)  # Small delay between retries
            
            if not exchange_positions:
                # More accurate log message
                exchange_id = getattr(self.exchange, 'exchange', None)
                if exchange_id and hasattr(exchange_id, 'id'):
                    exchange_name = exchange_id.id
                else:
                    exchange_name = 'exchange'
                logger.info(f"No positions on {exchange_name} to sync")
                return 0
            
            logger.info(f"📊 sync_from_exchange: Found {len(exchange_positions)} positions to sync")
            
            # P0 FIX: Define minimum thresholds for dust detection
            DUST_THRESHOLD = 0.0001  # Absolute minimum
            MIN_VALUE_USD = 1.0  # Positions worth less than $1 are dust
            
            if db_manager is None:
                from bot.db import DatabaseManager
                db_manager = DatabaseManager()
            
            with db_manager.session_scope() as session:
                from bot.db import Position as DBPosition
                
                for ex_pos in exchange_positions:
                    symbol = ex_pos.symbol
                    
                    # P0 FIX: Skip dust positions
                    if ex_pos.quantity < DUST_THRESHOLD:
                        logger.info(
                            f"🧹 Skipping dust position during sync: {symbol} qty={ex_pos.quantity:.10f}"
                        )
                        continue
                    
                    # Check position value in USD (if possible)
                    try:
                        if hasattr(self.exchange, 'get_market_price'):
                            price = await self.exchange.get_market_price(symbol)
                            position_value = ex_pos.quantity * price
                            if position_value < MIN_VALUE_USD:
                                logger.info(
                                    f"🧹 Skipping low-value position: {symbol} qty={ex_pos.quantity:.6f} "
                                    f"worth ${position_value:.4f} (< ${MIN_VALUE_USD})"
                                )
                                continue
                    except Exception as price_err:
                        logger.debug(f"Could not check position value: {price_err}")
                    
                    # Try to find matching position in DB to get SL/TP
                    db_pos = (
                        session.query(DBPosition)
                        .filter(
                            DBPosition.symbol == symbol,
                            DBPosition.status == "OPEN"
                        )
                        .first()
                    )
                    
                    # v4.1: Check if this is a manual position
                    position_source = getattr(db_pos, 'source', None) if db_pos else None
                    if position_source == 'manual':
                        logger.info(
                            f"📋 SKIPPING MANUAL POSITION from exchange: {symbol} | "
                            f"User maintains full control (not auto-managed)"
                        )
                        continue
                    
                    stop_loss = db_pos.stop_loss if db_pos else None
                    take_profit = db_pos.take_profit if db_pos else None
                    user_id = db_pos.user_id if db_pos else self.default_user_id
                    
                    # v4.3 FIX: If position exists on exchange but NOT in database, CREATE it
                    if db_pos is None and user_id:
                        logger.info(
                            f"🆕 EXTERNAL POSITION DETECTED: {symbol} exists on exchange but not in DB | "
                            f"Creating DB record for user {user_id}"
                        )
                        # Create new position in database
                        new_db_pos = DBPosition(
                            user_id=user_id,
                            symbol=symbol,
                            side=ex_pos.side.upper(),
                            quantity=ex_pos.quantity,
                            entry_price=ex_pos.entry_price,
                            current_price=ex_pos.entry_price,
                            leverage=getattr(ex_pos, 'leverage', 1.0),
                            status="OPEN",
                            source="external",  # Mark as externally opened position
                            unrealized_pnl=0.0,
                            realized_pnl=0.0,
                            margin_used=0.0
                        )
                        session.add(new_db_pos)
                        session.commit()
                        logger.info(
                            f"✅ Created DB record for external position: {symbol} | "
                            f"ID={new_db_pos.id} | Entry={ex_pos.entry_price} | Qty={ex_pos.quantity}"
                        )
                        position_source = "external"
                    elif db_pos is None:
                        # No user_id available - skip but log
                        logger.warning(
                            f"⚠️ Exchange position {symbol} has no matching DB record and no user_id available. "
                            f"Position will be monitored but not tracked in DB."
                        )
                        position_source = "unknown"
                    
                    key = f"{user_id}:{symbol}" if user_id else symbol
                    
                    if key not in self.positions:
                        self.add_position(
                            symbol=symbol,
                            side=ex_pos.side,
                            entry_price=ex_pos.entry_price,
                            quantity=ex_pos.quantity,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            user_id=user_id,
                            source=position_source or 'unknown'  # v4.1
                        )
                        synced_count += 1
                        
                        # Check if position now has SL/TP (may have been auto-set by add_position)
                        key = f"{user_id}:{symbol}" if user_id else symbol
                        monitored_pos = self.positions.get(key)
                        final_sl = monitored_pos.stop_loss if monitored_pos else stop_loss
                        final_tp = monitored_pos.take_profit if monitored_pos else take_profit
                        
                        # Warn if position STILL has no SL/TP after auto-set attempt
                        if final_sl is None and final_tp is None:
                            logger.warning(
                                f"⚠️ Exchange position {symbol} has NO SL/TP - RISKY! "
                                f"Position will be monitored but won't auto-close. "
                                f"Use update_sl_tp() to set protection levels."
                            )
                        else:
                            logger.info(
                                f"🔄 Synced exchange position: {symbol} | "
                                f"SL={final_sl} TP={final_tp}"
                            )
            
            if synced_count > 0:
                logger.info(f"✅ Synchronized {synced_count} positions from exchange")
                    
        except Exception as e:
            logger.error(f"Failed to sync positions from exchange: {e}")
        
        return synced_count
    
    async def reconcile_ghost_positions(self, db_manager=None) -> int:
        """
        NEW v2.5: Reconcile database positions with exchange positions.
        
        Identifies "ghost positions" - positions that exist in DB but not on exchange.
        These can occur when:
        - User manually closes position on exchange web UI
        - Exchange auto-liquidated position
        - SL/TP triggered on exchange side but DB wasn't updated
        
        Returns:
            Number of ghost positions cleaned up
        """
        cleaned_count = 0
        
        try:
            if db_manager is None:
                from bot.db import DatabaseManager
                db_manager = DatabaseManager()
            
            # Get all positions from exchange
            exchange_positions = await self.exchange.get_positions()
            
            # Also get spot balances for spot trading
            spot_balances = {}
            try:
                all_balances = await self.exchange.get_all_balances()
                spot_balances = {k: v for k, v in all_balances.items() if v > 0.00001}
            except Exception as e:
                logger.debug(f"Could not fetch spot balances: {e}")
            
            # Build set of symbols that actually exist on exchange
            exchange_symbols = set()
            for pos in exchange_positions:
                exchange_symbols.add(pos.symbol)
            
            # Add spot balances as potential positions
            for asset in spot_balances.keys():
                if asset not in ['USDT', 'USDC', 'USD', 'EUR', 'PLN']:
                    # Could be ETH/USDC, ETH/USDT, etc.
                    exchange_symbols.add(f"{asset}/USDC")
                    exchange_symbols.add(f"{asset}/USDT")
            
            logger.info(f"🔍 Reconciliation: Exchange has {len(exchange_symbols)} active positions/balances")
            
            with db_manager.session_scope() as session:
                from bot.db import Position as DBPosition
                
                # Get all OPEN positions from database
                db_positions = (
                    session.query(DBPosition)
                    .filter(DBPosition.status == "OPEN")
                    .all()
                )
                
                logger.info(f"🔍 Reconciliation: Database has {len(db_positions)} OPEN positions")
                
                for db_pos in db_positions:
                    symbol = db_pos.symbol
                    base_asset = symbol.split('/')[0] if '/' in symbol else symbol
                    
                    # Check if position exists on exchange
                    position_exists = False
                    
                    # Check in exchange positions
                    if symbol in exchange_symbols:
                        position_exists = True
                    
                    # Check in spot balances
                    balance = spot_balances.get(base_asset, 0)
                    if balance > 0.00001:
                        position_exists = True
                    
                    if not position_exists:
                        # GHOST POSITION DETECTED
                        logger.warning(
                            f"🧹 GHOST POSITION DETECTED: {symbol} (ID: {db_pos.id}) | "
                            f"DB shows OPEN but exchange has no position/balance for {base_asset}"
                        )
                        
                        # Mark position as closed
                        db_pos.status = "CLOSED"
                        db_pos.close_reason = "ghost_position_cleanup"
                        db_pos.closed_at = datetime.now()
                        
                        # Remove from monitoring if present
                        key_to_remove = None
                        for key in list(self.positions.keys()):
                            if symbol in key:
                                key_to_remove = key
                                break
                        
                        if key_to_remove and key_to_remove in self.positions:
                            del self.positions[key_to_remove]
                            logger.info(f"🧹 Removed {key_to_remove} from position monitor")
                        
                        cleaned_count += 1
                
                if cleaned_count > 0:
                    session.commit()
                    logger.info(f"✅ Reconciliation complete: Cleaned up {cleaned_count} ghost positions")
                else:
                    logger.info("✅ Reconciliation complete: No ghost positions found")
                    
        except Exception as e:
            logger.error(f"Ghost position reconciliation failed: {e}")
            import traceback
            traceback.print_exc()
        
        return cleaned_count
    
    async def start(self):
        """Start the background monitoring loop."""
        if self.running:
            logger.warning("Position monitor already running")
            return
        
        # v4.1: Initialize Supabase and load persisted positions
        supabase_ok = self._init_supabase()
        if supabase_ok:
            restored = await self._load_from_supabase()
            logger.info(f"💾 Hybrid Persistence: Restored {restored} positions from Supabase")
        else:
            logger.warning("💾 Hybrid Persistence: Supabase not available - using RAM only")
        
        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        
        # v4.1: Start persistence background task
        if self._supabase_client:
            self._persistence_task = asyncio.create_task(self._persistence_loop())
            logger.info("💾 Persistence task started")
        
        logger.info("✅ Position monitor started")
    
    async def stop(self):
        """Stop the monitoring loop."""
        self.running = False
        
        # v4.1: Stop persistence task first (with final sync)
        if self._persistence_task:
            self._persistence_task.cancel()
            try:
                await self._persistence_task
            except asyncio.CancelledError:
                pass
            logger.info("💾 Persistence task stopped")
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Position monitor stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop with periodic validation."""
        logger.info("Position monitoring loop started")
        
        # Counter for periodic validation (every 60 seconds = 12 iterations at 5s interval)
        validation_counter = 0
        validation_interval = 12  # Run validation every 12 * check_interval seconds
        
        # Counter for ghost position reconciliation (every 5 minutes = 60 iterations at 5s)
        reconciliation_counter = 0
        reconciliation_interval = 60  # Run reconciliation every 60 * check_interval seconds
        
        while self.running:
            try:
                await self._check_all_positions()
                
                # v4.0: LIQUIDATION MONITOR CHECK (every 10s = 2 iterations at 5s)
                if self.enable_liquidation_monitor and self.liquidation_config.enabled:
                    self._liquidation_check_counter += 1
                    if self._liquidation_check_counter >= self._liquidation_check_interval:
                        self._liquidation_check_counter = 0
                        try:
                            await self._check_liquidation_risk_all()
                        except Exception as liq_err:
                            logger.error(f"🚨 Liquidation check failed: {liq_err}")
                
                # Periodic validation to detect position discrepancies
                validation_counter += 1
                if validation_counter >= validation_interval:
                    validation_counter = 0
                    try:
                        await self.validate_margin_positions()
                    except Exception as ve:
                        logger.warning(f"Periodic validation failed: {ve}")
                
                # NEW v2.5: Periodic ghost position reconciliation
                reconciliation_counter += 1
                if reconciliation_counter >= reconciliation_interval:
                    reconciliation_counter = 0
                    try:
                        await self.reconcile_ghost_positions()
                    except Exception as re:
                        logger.warning(f"Ghost position reconciliation failed: {re}")
                
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Position monitor error: {e}")
                await asyncio.sleep(self.check_interval)
        
        logger.info("Position monitoring loop ended")
    
    async def _check_all_positions(self):
        """Check all positions against current prices with Trailing Stop support."""
        if not self.positions:
            return
        
        # Get unique symbols
        symbols = list(set(
            pos.symbol for pos in self.positions.values()
        ))
        
        # Fetch current prices
        prices = await self._fetch_prices(symbols)
        
        if not prices:
            return
        
        # Increment dynamic check counter
        self._dynamic_check_counter += 1
        should_check_dynamic = (
            self._dynamic_check_counter >= self._dynamic_check_interval
        )
        if should_check_dynamic:
            self._dynamic_check_counter = 0
        
        # Check each position
        positions_to_remove = []
        
        for key, pos in self.positions.items():
            current_price = prices.get(pos.symbol)
            
            if current_price is None:
                continue
            
            # v4.2: Manual positions - ONLY update price cache for liquidation monitoring
            # Skip ALL auto-close triggers (SL/TP/Trailing/Time/News/Momentum/QuickExit)
            if pos.is_manual_position:
                # Update price cache for liquidation calculation
                self._price_cache[pos.symbol] = current_price
                # Liquidation risk is checked separately in _check_liquidation_risk_all()
                continue  # Skip all auto-close features for manual positions
            
            # ========== NEWS/EVENT PROTECTION (NEW v1.2) ==========
            if self.enable_news_protection and pos.enable_news_protection and not pos.news_protection_triggered:
                should_news_exit = await self._check_news_protection(key, pos, current_price)
                if should_news_exit:
                    positions_to_remove.append(key)
                    continue
            
            # ========== MOMENTUM SCALPER (NEW v1.2) ==========
            if self.enable_momentum_scalp and pos.enable_momentum_scalp and not pos.momentum_scalp_triggered:
                should_momentum_exit = await self._check_momentum_scalp(key, pos, current_price)
                if should_momentum_exit:
                    positions_to_remove.append(key)
                    continue
            
            # ========== QUICK EXIT FOR SCALPING (NEW v1.1) ==========
            if pos.enable_quick_exit and not pos.quick_exit_triggered:
                should_quick_exit = await self._check_quick_exit(key, pos, current_price)
                if should_quick_exit:
                    positions_to_remove.append(key)
                    continue
            
            # ========== TIME-BASED EXIT (NEW) ==========
            if self.enable_time_exit and pos.max_hold_hours > 0:
                should_time_exit = await self._check_time_exit(key, pos, current_price)
                if should_time_exit:
                    positions_to_remove.append(key)
                    continue
            
            # ========== SMART BREAK-EVEN (NEW v1.2) ==========
            if self.enable_break_even and pos.enable_break_even and not pos.break_even_activated:
                await self._check_break_even(key, pos, current_price)
            
            # ========== PARTIAL TAKE PROFIT (NEW) ==========
            if self.enable_partial_tp:
                partial_closed = await self._check_partial_tp(key, pos, current_price)
                # Don't remove - partial TP keeps position open with reduced size
            
            # ========== TRAILING STOP LOGIC ==========
            if pos.trailing_enabled and pos.stop_loss:
                await self._apply_trailing_stop(key, pos, current_price)
            
            # ========== DYNAMIC SL/TP ADJUSTMENT (periodic) ==========
            if should_check_dynamic and pos.dynamic_sl_enabled and self.risk_manager:
                await self._apply_dynamic_sl_tp(key, pos, current_price)
            
            # ========== CHECK STOP LOSS ==========
            if pos.stop_loss:
                sl_triggered = False
                
                if pos.side == 'long' and current_price <= pos.stop_loss:
                    sl_triggered = True
                elif pos.side == 'short' and current_price >= pos.stop_loss:
                    sl_triggered = True
                
                if sl_triggered:
                    trailing_info = " (Trailing)" if pos.trailing_activated else ""
                    logger.warning(
                        f"🛑 STOP LOSS TRIGGERED{trailing_info}: {key} | "
                        f"Price: {current_price:.4f} | SL: {pos.stop_loss:.4f} | "
                        f"Entry: {pos.entry_price:.4f}"
                    )
                    await self._handle_sl_trigger(key, pos, current_price)
                    positions_to_remove.append(key)
                    continue
            
            # ========== CHECK TAKE PROFIT ==========
            if pos.take_profit:
                tp_triggered = False
                
                if pos.side == 'long' and current_price >= pos.take_profit:
                    tp_triggered = True
                elif pos.side == 'short' and current_price <= pos.take_profit:
                    tp_triggered = True
                
                if tp_triggered:
                    logger.info(
                        f"✅ TAKE PROFIT TRIGGERED: {key} | "
                        f"Price: {current_price:.4f} | TP: {pos.take_profit:.4f}"
                    )
                    await self._handle_tp_trigger(key, pos, current_price)
                    positions_to_remove.append(key)
                    continue
        
        # Remove triggered positions
        for key in positions_to_remove:
            if key in self.positions:
                del self.positions[key]
    
    async def _check_time_exit(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float
    ) -> bool:
        """
        Check if position has exceeded max hold time.
        Returns True if position should be closed.
        """
        if not pos.opened_at:
            return False
        
        # Fix timezone-aware vs naive datetime comparison
        now = datetime.now(timezone.utc)
        opened_at = pos.opened_at
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        
        hold_duration = now - opened_at
        hold_hours = hold_duration.total_seconds() / 3600
        
        if hold_hours >= pos.max_hold_hours:
            # Calculate P&L (with safety check for entry_price)
            if pos.entry_price and pos.entry_price > 0:
                if pos.side == 'long':
                    pnl_percent = ((current_price - pos.entry_price) / pos.entry_price) * 100
                else:
                    pnl_percent = ((pos.entry_price - current_price) / pos.entry_price) * 100
            else:
                pnl_percent = 0.0
            
            # FIX 2025-12-13: Only close if profitable OR if exceeded 2x max_hold_hours (force close)
            # This prevents closing losing positions due to time alone
            force_close_hours = pos.max_hold_hours * 2  # E.g. 24h if max is 12h
        """Handle time-based exit.
        
        FIX 2025-12-16: Try alternative quote currencies for European accounts
        that have USDT restrictions.
        """
        try:
            if self.exchange:
                logger.info(f"⏰ Attempting Time Exit for {key}...")
                await self._close_position(pos)
            
            # Call callback
            if self.on_time_exit_triggered:
                await self.on_time_exit_triggered(pos, current_price)
                
        except Exception as e:
            logger.error(f"Failed to execute time exit for {key}: {e}")
    
    # QUICK EXIT (for scalping mode - fast profit taking)
    
    async def _check_quick_exit(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float
    ) -> bool:
        """
        Quick Exit for scalping mode.
        Closes position if minimum profit achieved within short time window.
        
        Logic:
        - If position is held < quick_exit_time_minutes
        - AND profit >= quick_exit_profit_pct
        - THEN close immediately to lock in quick profit
        
        This is optimized for scalping/fast trading where small quick profits
        are preferred over waiting for larger gains.
        """
        if not pos.enable_quick_exit:
            return False
            
        if pos.quick_exit_triggered:
            return False
            
        # Calculate time held - FIX: Use opened_at instead of entry_time
        now = datetime.now(timezone.utc)
        if pos.opened_at:
            if isinstance(pos.opened_at, str):
                entry_time = datetime.fromisoformat(pos.opened_at.replace('Z', '+00:00'))
            else:
                entry_time = pos.opened_at
            
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)
        else:
            return False
            
        time_held = now - entry_time
        time_held_minutes = time_held.total_seconds() / 60
        
        # Only apply Quick Exit within the time window
        if time_held_minutes > pos.quick_exit_time_minutes:
            # Time window passed - disable quick exit for this position
            logger.debug(
                f"⚡ Quick Exit window expired for {key} | "
                f"Held: {time_held_minutes:.1f}m > {pos.quick_exit_time_minutes}m"
            )
            return False
        
        # Calculate current profit
        if pos.entry_price and pos.entry_price > 0:
            if pos.side == 'long':
                profit_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
            else:
                profit_pct = ((pos.entry_price - current_price) / pos.entry_price) * 100
        else:
            return False
        
        # Check if profit threshold met
        if profit_pct >= pos.quick_exit_profit_pct:
            logger.info(
                f"⚡ QUICK EXIT TRIGGERED: {key} | "
                f"Profit: {profit_pct:.2f}% >= {pos.quick_exit_profit_pct}% target | "
                f"Time held: {time_held_minutes:.1f}m (within {pos.quick_exit_time_minutes}m window) | "
                f"Entry: {pos.entry_price:.4f} → Current: {current_price:.4f}"
            )
            
            # Mark as triggered
            pos.quick_exit_triggered = True
            await self._sync_to_supabase(key, pos, 'update')
            
            # Execute quick exit
            await self._handle_quick_exit(key, pos, current_price, profit_pct)
            return True
        
        return False
    
    async def _handle_quick_exit(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float,
        profit_pct: float
    ):
        """Handle quick exit order execution."""
        try:
            if self.exchange:
                logger.info(f"⚡ Attempting Quick Exit for {key} (Profit: {profit_pct:.2f}%)")
                await self._close_position(pos)
            
            # Call time exit callback (same handling as time exit)
            if self.on_time_exit_triggered:
                await self.on_time_exit_triggered(pos, current_price)
                
        except Exception as e:
            logger.error(f"⚡ Failed to execute Quick Exit for {key}: {e}")
            # Revert triggered flag on failure
            pos.quick_exit_triggered = False
    
    # =====================================================================
    # SMART BREAK-EVEN (NEW v1.2)
    # =====================================================================
    
    async def _check_break_even(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float
    ) -> None:
        """
        Smart Break-Even: Move SL to entry price when profit threshold reached.
        
        This protects profits by ensuring position cannot go into loss
        once a certain profit level is achieved.
        """
        if not pos.entry_price or pos.entry_price <= 0:
            return
        
        if pos.break_even_activated:
            return
        
        # Calculate current profit
        if pos.side == 'long':
            profit_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
        else:
            profit_pct = ((pos.entry_price - current_price) / pos.entry_price) * 100
        
        # Check if profit threshold met
        if profit_pct >= pos.break_even_trigger_pct:
            # Calculate break-even price with small buffer
            buffer = pos.entry_price * (pos.break_even_buffer_pct / 100)
            
            if pos.side == 'long':
                new_sl = pos.entry_price + buffer  # Slightly above entry
            else:
                new_sl = pos.entry_price - buffer  # Slightly below entry
            
            old_sl = pos.stop_loss
            pos.stop_loss = new_sl
            pos.break_even_activated = True
            
            logger.info(
                f"🛡️ BREAK-EVEN ACTIVATED: {key} | "
                f"Profit: {profit_pct:.2f}% >= {pos.break_even_trigger_pct}% trigger | "
                f"SL moved: {old_sl:.4f} → {new_sl:.4f} (entry + {pos.break_even_buffer_pct}% buffer) | "
                f"Position is now RISK-FREE!"
            )
            
            # Sync to Supabase
            await self._sync_to_supabase(key, pos, 'update')
    
    # =====================================================================
    # MOMENTUM SCALPER (NEW v1.2)
    # =====================================================================
    
    async def _check_momentum_scalp(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float
    ) -> bool:
        """
        Momentum Scalper: Exit if 50% of TP target reached within 60 minutes.
        
        Logic:
        - If position achieves >= 50% of Take Profit target
        - Within the first 60 minutes of opening
        - Exit immediately to lock in profits
        
        This captures momentum moves without waiting for full TP.
        """
        if not pos.entry_price or pos.entry_price <= 0:
            return False
        
        if not pos.take_profit or pos.take_profit <= 0:
            return False
        
        if pos.momentum_scalp_triggered:
            return False
        
        # Check time window
        now = datetime.now(timezone.utc)
        if pos.entry_time:
            if isinstance(pos.entry_time, str):
                entry_time = datetime.fromisoformat(pos.entry_time.replace('Z', '+00:00'))
            else:
                entry_time = pos.entry_time
            
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)
        else:
            return False
        
        time_held = now - entry_time
        time_held_minutes = time_held.total_seconds() / 60
        
        # Only apply within time window
        if time_held_minutes > pos.momentum_scalp_minutes:
            return False
        
        # Calculate target profit (full TP distance)
        if pos.side == 'long':
            full_tp_pct = ((pos.take_profit - pos.entry_price) / pos.entry_price) * 100
            current_profit_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
        else:
            full_tp_pct = ((pos.entry_price - pos.take_profit) / pos.entry_price) * 100
            current_profit_pct = ((pos.entry_price - current_price) / pos.entry_price) * 100
        
        # Calculate what % of TP target we've achieved
        if full_tp_pct > 0:
            progress_pct = (current_profit_pct / full_tp_pct) * 100
        else:
            return False
        
        # Check if momentum threshold met
        if progress_pct >= pos.momentum_scalp_pct:
            logger.info(
                f"🚀 MOMENTUM SCALP TRIGGERED: {key} | "
                f"Achieved {progress_pct:.1f}% of TP target ({current_profit_pct:.2f}%/{full_tp_pct:.2f}%) | "
                f"Within {time_held_minutes:.1f}m (window: {pos.momentum_scalp_minutes}m) | "
                f"Entry: {pos.entry_price:.4f} → Current: {current_price:.4f}"
            )
            
            pos.momentum_scalp_triggered = True
            await self._sync_to_supabase(key, pos, 'update')
            
            # Execute exit
            await self._handle_momentum_exit(key, pos, current_price, current_profit_pct)
            return True
        
        return False
    
    async def _handle_momentum_exit(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float,
        profit_pct: float
    ):
        """Handle momentum scalp exit execution."""
        try:
            if self.exchange:
                logger.info(f"🚀 Attempting Momentum Scalp Exit for {key} (Profit: {profit_pct:.2f}%)")
                await self._close_position(pos)
            
            if self.on_time_exit_triggered:
                await self.on_time_exit_triggered(pos, current_price)
                
        except Exception as e:
            logger.error(f"🚀 Failed to execute Momentum Scalp for {key}: {e}")
            pos.momentum_scalp_triggered = False
    
    # =====================================================================
    # NEWS/EVENT PROTECTION (NEW v1.2)
    # =====================================================================
    
    # Major economic events that cause high volatility
    MAJOR_ECONOMIC_EVENTS = [
        "CPI",           # Consumer Price Index
        "FOMC",          # Federal Reserve Meeting
        "NFP",           # Non-Farm Payrolls
        "GDP",           # Gross Domestic Product
        "Interest Rate", # Interest Rate Decision
        "PCE",           # Personal Consumption Expenditure
        "Unemployment",  # Unemployment Rate
        "Retail Sales",  # Retail Sales Data
        "PPI",           # Producer Price Index
    ]
    
    async def _check_news_protection(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float
    ) -> bool:
        """
        News/Event Protection: Auto-close profitable positions before major events.
        
        This protects against volatility spikes during:
        - CPI releases
        - FOMC meetings
        - NFP reports
        - Other major economic events
        
        Only closes if position is profitable (no forced loss).
        """
        if pos.news_protection_triggered:
            return False
        
        # Check if position is profitable first
        if pos.entry_price and pos.entry_price > 0:
            if pos.side == 'long':
                profit_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
            else:
                profit_pct = ((pos.entry_price - current_price) / pos.entry_price) * 100
        else:
            return False
        
        # Only close if profitable
        if profit_pct <= 0:
            return False
        
        # Check for upcoming events
        upcoming_event = await self._get_upcoming_economic_event(pos.news_close_minutes_before)
        
        if upcoming_event:
            event_name, minutes_until = upcoming_event
            
            logger.warning(
                f"📰 NEWS PROTECTION TRIGGERED: {key} | "
                f"Event: {event_name} in {minutes_until:.0f} minutes | "
                f"Closing profitable position ({profit_pct:.2f}%) to protect gains"
            )
            
            pos.news_protection_triggered = True
            await self._sync_to_supabase(key, pos, 'update')
            
            # Execute exit
            await self._handle_news_exit(key, pos, current_price, profit_pct, event_name)
            return True
        
        return False
    
    async def _get_upcoming_economic_event(self, minutes_ahead: int) -> Optional[tuple]:
        """
        Check for upcoming major economic events using EconomicCalendarService.
        
        Returns tuple of (event_name, minutes_until) or None.
        
        Data Sources (in priority order):
        1. Local hardcoded events (FOMC, CPI, NFP, PPI, GDP, PCE dates 2024-2025)
        2. Forex Factory RSS feed (live data)
        3. Pattern-based heuristics (fallback)
        
        Updated: 2025-12-15 - Full implementation with real economic calendar
        """
        try:
            # Use the new EconomicCalendarService
            from bot.services.economic_calendar import get_upcoming_economic_event
            
            result = await get_upcoming_economic_event(
                minutes_ahead=minutes_ahead,
                min_impact="high"  # Only high-impact events trigger protection
            )
            
            if result:
                event_name, minutes_until = result
                logger.debug(
                    f"📅 Economic event detected: {event_name} in {minutes_until:.0f} minutes"
                )
                return result
            
            return None
            
        except ImportError as e:
            logger.warning(f"EconomicCalendarService not available: {e}")
            # Fallback to legacy heuristics
            return self._check_cached_events_legacy(minutes_ahead)
        except Exception as e:
            logger.debug(f"Error checking economic events: {e}")
            return None
    
    def _check_cached_events_legacy(self, minutes_ahead: int) -> Optional[tuple]:
        """
        Legacy fallback: Check for events using simple heuristics.
        Only used if EconomicCalendarService fails to import.
        """
        now = datetime.now(timezone.utc)
        hour = now.hour
        minute = now.minute
        weekday = now.weekday()
        day = now.day
        
        # NFP - First Friday of month at 13:30 UTC
        if weekday == 4 and day <= 7:
            release_minute = 13 * 60 + 30
            current_minute = hour * 60 + minute
            minutes_until = release_minute - current_minute
            if 0 < minutes_until <= minutes_ahead:
                return ("NFP (Non-Farm Payrolls)", minutes_until)
        
        # FOMC - Wednesdays at 19:00 UTC (approximate)
        if weekday == 2:
            release_minute = 19 * 60
            current_minute = hour * 60 + minute
            minutes_until = release_minute - current_minute
            if 0 < minutes_until <= minutes_ahead:
                return ("FOMC Meeting (estimated)", minutes_until)
        
        # CPI - Mid-month at 13:30 UTC (approximate)
        if 10 <= day <= 15:
            release_minute = 13 * 60 + 30
            current_minute = hour * 60 + minute
            minutes_until = release_minute - current_minute
            if 0 < minutes_until <= minutes_ahead:
                return ("CPI Release (estimated)", minutes_until)
        
        return None
    
    async def _handle_news_exit(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float,
        profit_pct: float,
        event_name: str
    ):
        """Handle news protection exit execution."""
        try:
            if self.exchange:
                logger.info(f"📰 Attempting News Protection Exit for {key} (Profit: {profit_pct:.2f}%)")
                await self._close_position(pos)
            
            if self.on_time_exit_triggered:
                await self.on_time_exit_triggered(pos, current_price)
                
        except Exception as e:
            logger.error(f"📰 Failed to execute News Protection for {key}: {e}")
            pos.news_protection_triggered = False
    
    async def _check_partial_tp(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float
    ) -> bool:
        """
        Check and execute partial take profit levels.
        Returns True if any partial TP was executed.
        """
        if not self.partial_tp_levels or pos.quantity <= 0:
            return False
        
        # Safety check: entry_price must be valid (non-zero)
        if not pos.entry_price or pos.entry_price <= 0:
            return False
        
        # Calculate current profit %
        if pos.side == 'long':
            profit_percent = ((current_price - pos.entry_price) / pos.entry_price) * 100
        else:
            profit_percent = ((pos.entry_price - current_price) / pos.entry_price) * 100
        
        executed = False
        
        for i, level in enumerate(self.partial_tp_levels):
            # Skip if already executed
            if i in pos.partial_tp_executed:
                continue
            
            level_profit = level['profit_percent']
            close_percent = level['close_percent']
            
            if profit_percent >= level_profit:
                # Calculate quantity to close
                close_qty = pos.original_quantity * (close_percent / 100)
                
                # Don't close more than remaining
                close_qty = min(close_qty, pos.quantity)
                
                if close_qty > 0:
                    logger.info(
                        f"🎯 PARTIAL TP LEVEL {i+1}: {key} | "
                        f"Profit: {profit_percent:.2f}% >= {level_profit}% | "
                        f"Closing {close_percent}% ({close_qty:.6f}) | "
                        f"Price: {current_price:.4f}"
                    )
                    
                    # Execute partial close
                    success = await self._execute_partial_close(key, pos, close_qty, current_price, i)
                    
                    if success:
                        pos.partial_tp_executed.append(i)
                        pos.quantity -= close_qty
                        executed = True
                        
                        # L6 FIX: Adjust SL to break-even after FIRST partial TP (level 0)
                        # Works for both LONG and SHORT positions
                        if i == 0 and pos.stop_loss:
                            if pos.side == 'long' and pos.stop_loss < pos.entry_price:
                                old_sl = pos.stop_loss
                                pos.stop_loss = pos.entry_price  # Move to break-even
                                logger.info(
                                    f"🛡️ LONG SL moved to break-even: {old_sl:.4f} → {pos.stop_loss:.4f}"
                                )
                            elif pos.side == 'short' and pos.stop_loss > pos.entry_price:
                                old_sl = pos.stop_loss
                                pos.stop_loss = pos.entry_price  # Move to break-even
                                logger.info(
                                    f"🛡️ SHORT SL moved to break-even: {old_sl:.4f} → {pos.stop_loss:.4f}"
                                )
                        
                        # L6 FIX v2: For higher TP levels (1+), tighten SL progressively
                        # After level 1: SL at 50% of profit locked
                        # After level 2: SL at 75% of profit locked
                        if i > 0 and pos.stop_loss:
                            profit_lock_pct = 0.5 + (i * 0.25)  # 50%, 75%, 100%...
                            profit_lock_pct = min(profit_lock_pct, 0.90)  # Cap at 90%
                            
                            if pos.side == 'long':
                                locked_profit = (current_price - pos.entry_price) * profit_lock_pct
                                new_sl = pos.entry_price + locked_profit
                                if new_sl > pos.stop_loss:
                                    old_sl = pos.stop_loss
                                    pos.stop_loss = new_sl
                                    logger.info(
                                        f"🛡️ LONG SL tightened (level {i+1}): "
                                        f"{old_sl:.4f} → {pos.stop_loss:.4f} "
                                        f"(locking {profit_lock_pct*100:.0f}% profit)"
                                    )
                            else:  # short
                                locked_profit = (pos.entry_price - current_price) * profit_lock_pct
                                new_sl = pos.entry_price - locked_profit
                                if new_sl < pos.stop_loss:
                                    old_sl = pos.stop_loss
                                    pos.stop_loss = new_sl
                                    logger.info(
                                        f"🛡️ SHORT SL tightened (level {i+1}): "
                                        f"{old_sl:.4f} → {pos.stop_loss:.4f} "
                                        f"(locking {profit_lock_pct*100:.0f}% profit)"
                                    )
        
        return executed
    
    async def _execute_partial_close(
        self,
        key: str,
        pos: MonitoredPosition,
        quantity: float,
        current_price: float,
        level_index: int
    ) -> bool:
        """Execute partial position close."""
        try:
            if self.exchange:
                close_side = 'sell' if pos.side == 'long' else 'buy'
                await self.exchange.place_order(
                    symbol=pos.symbol,
                    side=close_side,
                    order_type='market',
                    quantity=quantity,
                    reduce_only=True
                )
                logger.info(f"✅ Partial close executed: {key} | Qty: {quantity:.6f}")
                
                # Call callback
                if self.on_partial_tp_triggered:
                    await self.on_partial_tp_triggered(pos, current_price, quantity, level_index)
                
                return True
        except Exception as e:
            logger.error(f"Failed to execute partial close for {key}: {e}")
        
        return False
    
    async def _apply_trailing_stop(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float
    ):
        """Apply trailing stop logic to a position."""
        try:
            # Use RiskManager if available
            if self.risk_manager:
                # Get ATR for more intelligent trailing
                atr = await self.risk_manager.calculate_atr(pos.symbol)
                
                new_sl, highest, lowest, should_update = self.risk_manager.calculate_trailing_stop(
                    side=pos.side,
                    entry_price=pos.entry_price,
                    current_price=current_price,
                    current_sl=pos.stop_loss,
                    highest_price=pos.highest_price,
                    lowest_price=pos.lowest_price,
                    atr=atr
                )
                
                if should_update:
                    old_sl = pos.stop_loss
                    pos.stop_loss = new_sl
                    pos.trailing_activated = True
                    pos.last_sl_update = datetime.now()
                    
                    # L12 FIX: Cancel exchange SL when trailing activates
                    if pos.disable_exchange_sl_when_trailing and not pos.exchange_sl_cancelled:
                        await self._cancel_exchange_sl_order(key, pos)
                        pos.exchange_sl_cancelled = True
                    
                    # Calculate profit percentage
                    profit_pct = ((current_price / pos.entry_price) - 1) * 100
                    if pos.side == 'short':
                        profit_pct = -profit_pct
                    
                    logger.info(
                        f"📈 Trailing Stop updated for {key}: "
                        f"{old_sl:.4f} → {new_sl:.4f} | "
                        f"Current: {current_price:.4f}"
                    )
                    
                    # Update in database
                    await self._update_position_sl_in_db(pos, new_sl)
                    
                    # Save reevaluation to DB
                    await self._save_reevaluation(
                        pos=pos,
                        reevaluation_type='trailing_update',
                        old_sl=old_sl,
                        new_sl=new_sl,
                        old_tp=pos.take_profit,
                        new_tp=pos.take_profit,
                        current_price=current_price,
                        profit_pct=profit_pct,
                        reason=f"Trailing stop raised from {old_sl:.4f} to {new_sl:.4f}",
                        action_taken='adjusted'
                    )
                    
                    # Send alert (only for significant updates > 1%)
                    if profit_pct > 1.0:
                        await self._send_alert(
                            alert_type='trailing_update',
                            pos=pos,
                            current_price=current_price,
                            old_sl=old_sl,
                            new_sl=new_sl
                        )
                
                # Update tracking prices
                pos.highest_price = highest
                pos.lowest_price = lowest
                
            else:
                # Fallback: Simple percentage-based trailing
                await self._apply_simple_trailing(key, pos, current_price)
                
        except Exception as e:
            logger.error(f"Error applying trailing stop for {key}: {e}")
    
    async def _apply_simple_trailing(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float
    ):
        """Apply simple percentage-based trailing stop."""
        # Safety check: entry_price must be valid
        if not pos.entry_price or pos.entry_price <= 0:
            return
            
        trailing_distance = pos.entry_price * (pos.trailing_distance_percent / 100)
        
        if pos.side == 'long':
            # Track highest price
            if pos.highest_price is None or current_price > pos.highest_price:
                pos.highest_price = current_price
            
            # Calculate profit %
            profit_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
            
            # Activate trailing after 1% profit
            if profit_pct >= 1.0:
                new_trailing_sl = pos.highest_price - trailing_distance
                
                # Only move SL up
                if pos.stop_loss is None or new_trailing_sl > pos.stop_loss:
                    old_sl = pos.stop_loss
                    pos.stop_loss = new_trailing_sl
                    pos.trailing_activated = True
                    
                    logger.info(
                        f"📈 Simple Trailing (LONG) {key}: "
                        f"SL {old_sl:.4f if old_sl else 'None'} → {new_trailing_sl:.4f} | "
                        f"High: {pos.highest_price:.4f} | Profit: {profit_pct:.2f}%"
                    )
                    
                    await self._update_position_sl_in_db(pos, new_trailing_sl)
        
        else:  # short
            # Track lowest price
            if pos.lowest_price is None or current_price < pos.lowest_price:
                pos.lowest_price = current_price
            
            # Calculate profit %
            profit_pct = ((pos.entry_price - current_price) / pos.entry_price) * 100
            
            # Activate trailing after 1% profit
            if profit_pct >= 1.0:
                new_trailing_sl = pos.lowest_price + trailing_distance
                
                # Only move SL down
                if pos.stop_loss is None or new_trailing_sl < pos.stop_loss:
                    old_sl = pos.stop_loss
                    pos.stop_loss = new_trailing_sl
                    pos.trailing_activated = True
                    
                    logger.info(
                        f"📈 Simple Trailing (SHORT) {key}: "
                        f"SL {old_sl:.4f if old_sl else 'None'} → {new_trailing_sl:.4f} | "
                        f"Low: {pos.lowest_price:.4f} | Profit: {profit_pct:.2f}%"
                    )
                    
                    await self._update_position_sl_in_db(pos, new_trailing_sl)
    
    async def _apply_dynamic_sl_tp(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float
    ):
        """Apply dynamic SL/TP adjustment based on volatility."""
        if not self.risk_manager:
            return
        
        # Skip if position has no SL/TP set (nothing to adjust)
        if not pos.stop_loss and not pos.take_profit:
            logger.debug(f"Skipping dynamic SL/TP for {key}: no SL/TP set")
            return
        
        # Skip if entry_price is invalid
        if not pos.entry_price or pos.entry_price <= 0:
            logger.debug(f"Skipping dynamic SL/TP for {key}: invalid entry_price")
            return
            
        try:
            adjustment = await self.risk_manager.should_adjust_sl_tp(
                symbol=pos.symbol,
                side=pos.side,
                entry_price=pos.entry_price,
                current_price=current_price,
                current_sl=pos.stop_loss,
                current_tp=pos.take_profit
            )
            
            if adjustment.should_update:
                # Update SL
                if adjustment.new_stop_loss != pos.stop_loss:
                    logger.info(
                        f"🎯 Dynamic SL adjustment for {key}: "
                        f"{pos.stop_loss:.4f} → {adjustment.new_stop_loss:.4f} | "
                        f"Reason: {adjustment.reason}"
                    )
                    pos.stop_loss = adjustment.new_stop_loss
                    pos.last_sl_update = datetime.now()
                    await self._update_position_sl_in_db(pos, adjustment.new_stop_loss)
                
                # Update TP
                if adjustment.new_take_profit != pos.take_profit:
                    logger.info(
                        f"🎯 Dynamic TP adjustment for {key}: "
                        f"{pos.take_profit:.4f} → {adjustment.new_take_profit:.4f}"
                    )
                    pos.take_profit = adjustment.new_take_profit
                    await self._update_position_tp_in_db(pos, adjustment.new_take_profit)
                    
        except Exception as e:
            logger.error(f"Error applying dynamic SL/TP for {key}: {e}")
    
    async def _cancel_exchange_sl_order(
        self,
        key: str,
        pos: MonitoredPosition
    ):
        """
        L12 FIX (2025-12-14): Cancel exchange-side SL order when trailing activates.
        This prevents conflicts between Position Monitor's trailing SL and exchange's static SL.
        """
        try:
            if self.on_trailing_update:
                # Notify the broker to cancel exchange SL
                logger.warning(
                    f"🚫 L12 FIX: Cancelling exchange SL for {key} "
                    f"(trailing activated, now managed by Position Monitor)"
                )
                # The actual cancellation is done via callback to auto_trader
                # which has access to the broker/exchange
                await self.on_trailing_update(pos, pos.stop_loss, 'cancel_exchange_sl')
            else:
                logger.debug(
                    f"L12: No trailing update callback set for {key}, "
                    f"exchange SL cancellation skipped"
                )
        except Exception as e:
            logger.error(f"L12: Failed to cancel exchange SL for {key}: {e}")
    
    async def _update_position_sl_in_db(
        self,
        pos: MonitoredPosition,
        new_sl: float
    ):
        """Update stop loss in database."""
        try:
            from bot.db import DatabaseManager, Position as DBPosition
            
            with DatabaseManager.session_scope() as session:
                db_pos = (
                    session.query(DBPosition)
                    .filter(
                        DBPosition.symbol == pos.symbol,
                        DBPosition.status == "OPEN"
                    )
                )
                if pos.user_id:
                    db_pos = db_pos.filter(DBPosition.user_id == pos.user_id)
                
                db_pos = db_pos.first()
                
                if db_pos:
                    db_pos.stop_loss = new_sl
                    session.commit()
                    logger.debug(f"Updated SL in DB for {pos.symbol}: {new_sl}")
        except Exception as e:
            logger.warning(f"Failed to update SL in DB: {e}")
    
    async def _update_position_tp_in_db(
        self,
        pos: MonitoredPosition,
        new_tp: float
    ):
        """Update take profit in database."""
        try:
            from bot.db import DatabaseManager, Position as DBPosition
            
            with DatabaseManager.session_scope() as session:
                db_pos = (
                    session.query(DBPosition)
                    .filter(
                        DBPosition.symbol == pos.symbol,
                        DBPosition.status == "OPEN"
                    )
                )
                if pos.user_id:
                    db_pos = db_pos.filter(DBPosition.user_id == pos.user_id)
                
                db_pos = db_pos.first()
                
                if db_pos:
                    db_pos.take_profit = new_tp
                    session.commit()
                    logger.debug(f"Updated TP in DB for {pos.symbol}: {new_tp}")
        except Exception as e:
            logger.warning(f"Failed to update TP in DB: {e}")
    
    async def _fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch current prices for symbols."""
        prices = {}
        
        try:
            if hasattr(self.exchange, 'exchange'):
                # CCXT adapter
                for symbol in symbols:
                    try:
                        ticker = await self.exchange.exchange.fetch_ticker(symbol)
                        prices[symbol] = ticker['last']
                    except Exception as e:
                        logger.debug(f"Failed to fetch price for {symbol}: {e}")
            elif hasattr(self.exchange, 'get_market_price'):
                # Legacy adapter
                for symbol in symbols:
                    try:
                        price = await self.exchange.get_market_price(symbol)
                        prices[symbol] = price
                    except Exception as e:
                        logger.debug(f"Failed to fetch price for {symbol}: {e}")
        except Exception as e:
            logger.error(f"Error fetching prices: {e}")
        
        # Update cache
        self._price_cache.update(prices)
        
        return prices
    
    async def _handle_sl_trigger(self, key: str, position: MonitoredPosition, price: float):
        """Handle stop loss trigger."""
        try:
            if self.on_sl_triggered:
                if asyncio.iscoroutinefunction(self.on_sl_triggered):
                    await self.on_sl_triggered(position, price)
                else:
                    self.on_sl_triggered(position, price)
            
            # Try to close position on exchange
            await self._close_position(position)
            
            # Calculate P&L
            pnl_pct = ((price / position.entry_price) - 1) * 100
            if position.side == 'short':
                pnl_pct = -pnl_pct
            
            # Save reevaluation and send alert
            await self._save_reevaluation(
                pos=position,
                reevaluation_type='sl_triggered',
                old_sl=position.stop_loss,
                new_sl=None,
                old_tp=position.take_profit,
                new_tp=None,
                current_price=price,
                profit_pct=pnl_pct,
                reason=f"Stop loss hit at {price:.4f}",
                action_taken='closed'
            )
            
            # Send email alert
            await self._send_alert('sl_triggered', position, price)
            
        except Exception as e:
            logger.error(f"Error handling SL trigger for {key}: {e}")
    
    async def _handle_tp_trigger(self, key: str, position: MonitoredPosition, price: float):
        """Handle take profit trigger."""
        try:
            if self.on_tp_triggered:
                if asyncio.iscoroutinefunction(self.on_tp_triggered):
                    await self.on_tp_triggered(position, price)
                else:
                    self.on_tp_triggered(position, price)
            
            # Try to close position on exchange
            await self._close_position(position)
            
            # Calculate P&L
            pnl_pct = ((price / position.entry_price) - 1) * 100
            if position.side == 'short':
                pnl_pct = -pnl_pct
            
            # Save reevaluation and send alert
            await self._save_reevaluation(
                pos=position,
                reevaluation_type='tp_triggered',
                old_sl=position.stop_loss,
                new_sl=None,
                old_tp=position.take_profit,
                new_tp=None,
                current_price=price,
                profit_pct=pnl_pct,
                reason=f"Take profit hit at {price:.4f}",
                action_taken='closed'
            )
            
            # Send email alert
            await self._send_alert('tp_triggered', position, price)
            
        except Exception as e:
            logger.error(f"Error handling TP trigger for {key}: {e}")
    
    async def _close_position(self, position: MonitoredPosition, max_retries: int = 3):
        """Close a position on the exchange.
        
        NEW v3.0: Uses position locking to prevent race conditions.
        P1-6 FIX: Added retry logic with exponential backoff for critical SL/TP closes.
        P0 FIX: Handle "dust positions" (below minimum) by removing from monitoring.
        FIX 2025-12-16: Added rate limiter to prevent API hammering during volatile markets.
        
        Args:
            position: Position to close
            max_retries: Maximum retry attempts (default 3)
        """
        try:
            # FIX 2025-12-16: Rate limit check before attempting close
            if self._close_rate_limiter:
                # Reset minute counter if needed
                now = datetime.now()
                if (now - self._last_close_attempt_reset).seconds >= 60:
                    self._close_attempts_this_minute.clear()
                    self._last_close_attempt_reset = now
                
                # Check per-symbol rate limit (max 3 attempts per minute)
                symbol_attempts = self._close_attempts_this_minute.get(position.symbol, 0)
                if symbol_attempts >= self._max_close_attempts_per_minute:
                    logger.warning(
                        f"⏱️ Rate limit: Too many close attempts for {position.symbol} "
                        f"({symbol_attempts}/{self._max_close_attempts_per_minute} per minute). "
                        f"Waiting for next window."
                    )
                    return  # Skip this attempt, will retry next cycle
                
                # Increment attempt counter
                self._close_attempts_this_minute[position.symbol] = symbol_attempts + 1
            
            # P0 FIX: Check for dust positions (below exchange minimum)
            # Most exchanges have minimum order sizes around 0.001-0.01 for most assets
            DUST_THRESHOLD = 0.0001  # Positions below this are considered dust
            
            if position.quantity <= 0 or position.quantity < DUST_THRESHOLD:
                logger.warning(
                    f"🧹 DUST POSITION DETECTED: {position.symbol} qty={position.quantity:.10f} "
                    f"(below threshold {DUST_THRESHOLD}). Removing from monitoring."
                )
                # Remove from monitoring - it's too small to close via order
                key = f"{position.symbol}_{position.entry_price}"
                if key in self.positions:
                    del self.positions[key]
                    logger.info(f"✅ Dust position {position.symbol} removed from monitoring")
                return  # Exit without trying to place order
            
            # NEW v3.0: Acquire lock before closing position
            async def _do_close() -> bool:
                """Inner function to close position (for locking)."""
                # NEW v2.5: Verify position exists on exchange before closing
                if hasattr(self.exchange, 'get_positions'):
                    exchange_positions = await self.exchange.get_positions()
                    position_exists = False
                    
                    for ex_pos in exchange_positions:
                        if ex_pos.symbol == position.symbol and ex_pos.quantity > 0:
                            position_exists = True
                            # Update quantity to actual exchange quantity (may differ from DB)
                            if abs(ex_pos.quantity - position.quantity) > 0.0001:
                                logger.info(
                                    f"📊 Adjusting close quantity: {position.quantity:.6f} → {ex_pos.quantity:.6f}"
                                )
                                position.quantity = ex_pos.quantity
                            break
                    
                    # Also check spot balances for spot trading
                    if not position_exists:
                        try:
                            base_asset = position.symbol.split('/')[0]
                            balance = await self.exchange.get_specific_balance(base_asset)
                            
                            if balance > 0.00001:
                                position_exists = True
                                if abs(balance - position.quantity) > 0.0001:
                                    logger.info(
                                        f"📊 Adjusting close quantity from balance: {position.quantity:.6f} → {balance:.6f}"
                                    )
                                    position.quantity = balance
                        except Exception as be:
                            logger.debug(f"Could not check spot balance: {be}")
                    
                    if not position_exists:
                        logger.warning(
                            f"⚠️ GHOST POSITION: {position.symbol} exists in DB but NOT on exchange. "
                            f"Skipping close order. Position will be cleaned up by reconciliation."
                        )
                        # P0 FIX: Remove ghost position from monitoring
                        key = f"{position.symbol}_{position.entry_price}"
                        if key in self.positions:
                            del self.positions[key]
                            logger.info(f"🧹 Ghost position {position.symbol} removed from monitoring")
                        return True  # Return True to avoid retry on ghost positions
                
                # P0 FIX: Check minimum order size before placing close order
                if hasattr(self.exchange, 'get_symbol_info'):
                    try:
                        symbol_info = await self.exchange.get_symbol_info(position.symbol)
                        if symbol_info:
                            min_amount = symbol_info.get('min_amount', 0)
                            if position.quantity < min_amount:
                                logger.warning(
                                    f"🧹 DUST POSITION: {position.symbol} qty={position.quantity:.8f} "
                                    f"below exchange minimum {min_amount}. Cannot close via order."
                                )
                                # Remove from monitoring - it's too small to close
                                key = f"{position.symbol}_{position.entry_price}"
                                if key in self.positions:
                                    del self.positions[key]
                                    logger.info(f"✅ Dust position {position.symbol} removed from monitoring")
                                return True  # Return True to indicate "handled"
                    except Exception as info_err:
                        logger.debug(f"Could not check symbol info: {info_err}")
                
                if hasattr(self.exchange, 'place_order'):
                    # Determine close side
                    close_side = 'sell' if position.side == 'long' else 'buy'
                    
                    # FIX 2025-12-16: Try alternative quote currencies for European accounts
                    # User may have bought with USDT but account only permits USDC trading
                    symbol_to_close = position.symbol
                    base_asset = position.symbol.split('/')[0] if '/' in position.symbol else position.symbol
                    original_quote = position.symbol.split('/')[1] if '/' in position.symbol else 'USDT'
                    
                    # Try order with original symbol first, then alternatives
                    quote_currencies = [original_quote]  # Start with original
                    if original_quote == 'USDT':
                        quote_currencies.extend(['USDC', 'EUR', 'USD'])
                    elif original_quote == 'USDC':
                        quote_currencies.extend(['USDT', 'EUR', 'USD'])
                    elif original_quote == 'EUR':
                        quote_currencies.extend(['USDC', 'USDT', 'USD'])
                    
                    order_placed = False
                    last_error = None
                    
                    for quote in quote_currencies:
                        try_symbol = f"{base_asset}/{quote}"
                        try:
                            await self.exchange.place_order(
                                symbol=try_symbol,
                                side=close_side,
                                order_type='market',
                                quantity=position.quantity,
                                reduce_only=True
                            )
                            logger.info(f"✅ Position closed: {try_symbol}" + 
                                       (f" (alternative to {position.symbol})" if try_symbol != position.symbol else ""))
                            order_placed = True
                            break
                        except Exception as order_err:
                            error_str = str(order_err)
                            # Check if it's a "symbol not permitted" error
                            if 'not permitted' in error_str.lower() or '-2010' in error_str or 'invalid permissions' in error_str.lower():
                                logger.warning(f"⚠️ {try_symbol} not permitted, trying alternative quote currency...")
                                last_error = order_err
                                continue
                            else:
                                # Different error - re-raise
                                raise order_err
                    
                    if order_placed:
                        return True
                    elif last_error:
                        # All alternatives failed with "not permitted"
                        logger.error(
                            f"❌ CURRENCY RESTRICTION: Cannot close {position.symbol} - "
                            f"None of the quote currencies [{', '.join(quote_currencies)}] are permitted. "
                            f"MANUAL CLOSE REQUIRED on exchange!"
                        )
                        # Mark position as needing manual intervention
                        key = f"{position.symbol}_{position.entry_price}"
                        if key in self.positions:
                            self.positions[key].notes = "MANUAL_CLOSE_REQUIRED"
                        return False  # Will trigger retry but ultimately fail
                    
                return False
            
            # P1-6 FIX: Retry logic with exponential backoff
            last_error = None
            currency_restriction_hit = False  # FIX 2025-12-16: Track if all currencies failed
            
            for attempt in range(max_retries):
                try:
                    # Use lock if available
                    if self._position_lock_manager and CORE_MODULES_AVAILABLE:
                        async with self._position_lock_manager.acquire_lock(
                            position.symbol, 
                            "position_monitor",
                            timeout=30.0
                        ) as locked:
                            if locked:
                                success = await _do_close()
                                if success:
                                    return  # Success, exit
                                else:
                                    # _do_close returned False - likely currency restriction
                                    # Check if position was marked for manual close
                                    key = f"{position.symbol}_{position.entry_price}"
                                    if key in self.positions and getattr(self.positions[key], 'notes', '') == "MANUAL_CLOSE_REQUIRED":
                                        currency_restriction_hit = True
                                        logger.warning(f"⚠️ Currency restriction for {position.symbol} - stopping retry")
                                        break
                            else:
                                logger.warning(
                                    f"⚠️ Could not acquire lock to close {position.symbol} - "
                                    f"attempt {attempt + 1}/{max_retries}"
                                )
                    else:
                        success = await _do_close()
                        if success:
                            return  # Success, exit
                            
                except Exception as retry_err:
                    last_error = retry_err
                    error_str = str(retry_err).lower()
                    
                    # FIX 2025-12-16: Don't retry on "not permitted" errors - it won't help
                    if 'not permitted' in error_str or '-2010' in error_str or 'invalid permissions' in error_str:
                        logger.warning(f"⚠️ Symbol not permitted error for {position.symbol} - not retrying")
                        currency_restriction_hit = True
                        break
                    
                    delay = (2 ** attempt) * 0.5  # 0.5s, 1s, 2s
                    logger.warning(
                        f"⚠️ Close position attempt {attempt + 1}/{max_retries} failed for {position.symbol}: {retry_err}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay)
            
            # FIX 2025-12-16: Different handling for currency restriction vs other failures
            if currency_restriction_hit:
                logger.error(
                    f"❌ CURRENCY RESTRICTION: {position.symbol} cannot be closed automatically. "
                    f"User must manually sell this position on the exchange. "
                    f"Position will remain monitored but close orders disabled."
                )
                # Remove from automatic monitoring to prevent repeated failures
                key = f"{position.symbol}_{position.entry_price}"
                if key in self.positions:
                    del self.positions[key]
                    logger.info(f"🧹 Removed {position.symbol} from monitoring due to currency restriction")
                return  # Exit without CRITICAL alert - this is expected for some users
            
            # P1-6 FIX: All retries exhausted - CRITICAL ALERT
            logger.critical(
                f"🚨 CRITICAL: Failed to close position {position.symbol} after {max_retries} attempts! "
                f"Last error: {last_error}. MANUAL INTERVENTION REQUIRED!"
            )
            
            # Send critical alert
            try:
                alert_service = get_alert_service()
                if alert_service and position.user_id:
                    user_email = await self._get_user_email(position.user_id)
                    if user_email:
                        await alert_service.send_critical_alert(
                            user_email=user_email,
                            subject=f"🚨 CRITICAL: Position Close Failed - {position.symbol}",
                            message=(
                                f"Failed to close position {position.symbol} after {max_retries} attempts!\n"
                                f"Side: {position.side}\n"
                                f"Quantity: {position.quantity}\n"
                                f"Entry: {position.entry_price}\n"
                                f"Last error: {last_error}\n\n"
                                f"MANUAL INTERVENTION REQUIRED!"
                            )
                        )
            except Exception as alert_err:
                logger.error(f"Failed to send critical alert: {alert_err}")
                
        except Exception as e:
            logger.error(f"Failed to close position {position.symbol}: {e}")
    
    def get_monitored_count(self) -> int:
        """Get number of monitored positions."""
        return len(self.positions)
    
    def get_all_positions(self) -> List[Dict]:
        """Get all monitored positions as dicts."""
        return [
            {
                "key": key,
                "symbol": pos.symbol,
                "side": pos.side,
                "entry_price": pos.entry_price,
                "quantity": pos.quantity,
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
                "user_id": pos.user_id,
                "current_price": self._price_cache.get(pos.symbol),
            }
            for key, pos in self.positions.items()
        ]

    async def validate_margin_positions(self) -> Dict[str, Any]:
        """
        Validate that all margin positions on the exchange are being monitored.
        
        This performs a consistency check between:
        1. Positions on the exchange (live)
        2. Positions being monitored (in memory)
        3. Positions in database (persistent)
        
        v4.0: Now includes liquidation risk reporting.
        
        Returns:
            Dict with validation results including any discrepancies found.
        """
        validation_result = {
            "exchange_positions": 0,
            "monitored_positions": len(self.positions),
            "unmonitored": [],
            "orphaned_monitors": [],
            "missing_sl_tp": [],
            "liquidation_risk": [],  # v4.0: Positions at liquidation risk
            "status": "OK"
        }
        
        try:
            # 1. Get positions from exchange - use self.exchange (not self.exchange_adapter)
            exchange_positions = await self.exchange.get_positions()
            validation_result["exchange_positions"] = len(exchange_positions)
            
            # 2. Build set of exchange symbols for comparison
            exchange_symbols = set()
            for ex_pos in exchange_positions:
                symbol = ex_pos.symbol
                exchange_symbols.add(symbol)
                
                # Check if this position is being monitored
                monitored_key = next(
                    (k for k, p in self.positions.items() if p.symbol == symbol),
                    None
                )
                
                if monitored_key is None:
                    validation_result["unmonitored"].append({
                        "symbol": symbol,
                        "side": ex_pos.side,
                        "quantity": ex_pos.quantity,
                        "entry_price": ex_pos.entry_price,
                        "reason": "Position exists on exchange but not being monitored"
                    })
            
            # 3. Find monitors for positions that no longer exist on exchange
            for key, pos in self.positions.items():
                if pos.symbol not in exchange_symbols:
                    validation_result["orphaned_monitors"].append({
                        "key": key,
                        "symbol": pos.symbol,
                        "reason": "Monitor exists but position no longer on exchange"
                    })
            
            # 4. Check for positions without SL/TP (risky)
            for ex_pos in exchange_positions:
                monitored = next(
                    (p for p in self.positions.values() if p.symbol == ex_pos.symbol),
                    None
                )
                if monitored:
                    if monitored.stop_loss is None and monitored.take_profit is None:
                        validation_result["missing_sl_tp"].append({
                            "symbol": ex_pos.symbol,
                            "reason": "Position monitored but has no SL or TP set"
                        })
            
            # v4.0: 4b. Check for positions at liquidation risk
            if self.enable_liquidation_monitor:
                for key, pos in self.positions.items():
                    if pos.leverage <= 1.0:
                        continue  # Skip spot
                    
                    current_price = self._price_cache.get(pos.symbol)
                    if not current_price:
                        continue
                    
                    if pos.liquidation_price is None:
                        pos.liquidation_price = self.calculate_liquidation_price(
                            pos.entry_price, pos.leverage, pos.side
                        )
                    
                    distance_pct = self.calculate_distance_to_liquidation(
                        current_price, pos.liquidation_price, pos.side
                    )
                    
                    risk_level = self.get_liquidation_risk_level(distance_pct)
                    
                    if risk_level in [
                        LiquidationRiskLevel.WARNING,
                        LiquidationRiskLevel.DANGER,
                        LiquidationRiskLevel.CRITICAL
                    ]:
                        validation_result["liquidation_risk"].append({
                            "symbol": pos.symbol,
                            "side": pos.side,
                            "leverage": pos.leverage,
                            "current_price": current_price,
                            "liquidation_price": pos.liquidation_price,
                            "distance_pct": distance_pct,
                            "risk_level": risk_level.value,
                            "reason": f"Position at {risk_level.value.upper()} liquidation risk ({distance_pct:.1f}% from liquidation)"
                        })
            
            # 5. Set overall status
            issues_count = (
                len(validation_result["unmonitored"]) +
                len(validation_result["orphaned_monitors"])
            )
            
            # v4.0: Also count critical/danger liquidation risks as issues
            critical_liq_count = sum(
                1 for r in validation_result["liquidation_risk"]
                if r["risk_level"] in ["critical", "danger"]
            )
            
            if critical_liq_count > 0:
                validation_result["status"] = "CRITICAL"
                logger.critical(
                    f"🚨 Position validation: {critical_liq_count} positions at CRITICAL/DANGER liquidation risk!"
                )
            elif issues_count > 0:
                validation_result["status"] = "WARNING"
                logger.warning(
                    f"⚠️ Position validation found {issues_count} issues: "
                    f"{len(validation_result['unmonitored'])} unmonitored, "
                    f"{len(validation_result['orphaned_monitors'])} orphaned"
                )
            else:
                logger.info(
                    f"✅ Position validation OK: {validation_result['exchange_positions']} "
                    f"positions on exchange, {validation_result['monitored_positions']} monitored"
                )
            
            # 6. Clean up orphaned monitors
            for orphan in validation_result["orphaned_monitors"]:
                key = orphan["key"]
                if key in self.positions:
                    del self.positions[key]
                    logger.info(f"🧹 Removed orphaned monitor: {key}")
                    
        except Exception as e:
            validation_result["status"] = "ERROR"
            validation_result["error"] = str(e)
            logger.error(f"Position validation failed: {e}")
        
        return validation_result
    
    async def auto_sync_unmonitored(self, db_manager=None) -> int:
        """
        Automatically sync any unmonitored exchange positions.
        
        This is useful for recovering positions that may have been
        opened externally or lost due to bot restart.
        
        Returns:
            Number of positions newly added to monitoring.
        """
        validation = await self.validate_margin_positions()
        
        if not validation["unmonitored"]:
            return 0
        
        synced = 0
        
        try:
            if db_manager is None:
                from bot.db import DatabaseManager
                db_manager = DatabaseManager()
            
            with db_manager.session_scope() as session:
                from bot.db import Position as DBPosition
                
                for unmon in validation["unmonitored"]:
                    symbol = unmon["symbol"]
                    
                    # Try to find SL/TP in database
                    db_pos = (
                        session.query(DBPosition)
                        .filter(
                            DBPosition.symbol == symbol,
                            DBPosition.status == "OPEN"
                        )
                        .first()
                    )
                    
                    if db_pos and (db_pos.stop_loss or db_pos.take_profit):
                        self.add_position(
                            symbol=symbol,
                            side=unmon["side"],
                            entry_price=unmon["entry_price"],
                            quantity=unmon["quantity"],
                            stop_loss=db_pos.stop_loss,
                            take_profit=db_pos.take_profit,
                            user_id=db_pos.user_id
                        )
                        synced += 1
                        logger.info(f"🔄 Auto-synced unmonitored position: {symbol}")
                    else:
                        logger.warning(
                            f"⚠️ Cannot auto-sync {symbol}: no SL/TP found in database"
                        )
                        
        except Exception as e:
            logger.error(f"Auto-sync failed: {e}")
        
        return synced

    # ============================================================================
    # v4.0: LIQUIDATION PRICE MONITOR + AUTO-CLOSE AT RISK
    # ============================================================================
    
    def calculate_liquidation_price(
        self,
        entry_price: float,
        leverage: float,
        side: str,
        maintenance_margin_rate: float = 0.005  # 0.5% default maintenance margin
    ) -> float:
        """
        Calculate estimated liquidation price for a leveraged position.
        
        THIS IS THE KEY METRIC - not free margin!
        
        How liquidation works:
        - Exchange requires "maintenance margin" to keep position open
        - When unrealized loss eats into margin beyond maintenance, position is liquidated
        - Liquidation price = price at which your loss = (initial_margin - maintenance_margin)
        
        Formula derivation:
        - Initial Margin = Position Value / Leverage
        - For LONG: Loss = (Entry - Liq_Price) * Quantity
        - Liquidation when: Loss = Initial_Margin - Maintenance_Margin
        
        Simplified formulas:
        - LONG:  Liq_Price = Entry * (1 - 1/Leverage + maintenance_margin_rate)
        - SHORT: Liq_Price = Entry * (1 + 1/Leverage - maintenance_margin_rate)
        
        Examples with 10x leverage (maintenance 0.5%):
        - LONG @ $100:  Liq = $100 * (1 - 0.1 + 0.005) = $90.50
          (price can drop 9.5% before liquidation)
        - SHORT @ $100: Liq = $100 * (1 + 0.1 - 0.005) = $109.50
          (price can rise 9.5% before liquidation)
        
        Args:
            entry_price: Position entry price
            leverage: Position leverage (1.0 for spot)
            side: 'long' or 'short'
            maintenance_margin_rate: Exchange maintenance margin rate (typically 0.5%-1%)
            
        Returns:
            Estimated liquidation price (0 for spot long, inf for spot short)
        """
        if leverage <= 1.0:
            # Spot positions don't have liquidation
            return 0.0 if side == 'long' else float('inf')
        
        if side.lower() == 'long':
            # Long: liquidation when price drops
            # Loss = Entry - LiqPrice, Margin = Entry/Lev
            # LiqPrice = Entry * (1 - 1/Lev + MM)
            liquidation_price = entry_price * (1 - (1 / leverage) + maintenance_margin_rate)
        else:
            # Short: liquidation when price rises
            # Loss = LiqPrice - Entry, Margin = Entry/Lev  
            # LiqPrice = Entry * (1 + 1/Lev - MM)
            liquidation_price = entry_price * (1 + (1 / leverage) - maintenance_margin_rate)
        
        return liquidation_price
    
    def calculate_distance_to_liquidation(
        self,
        current_price: float,
        liquidation_price: float,
        side: str
    ) -> float:
        """
        Calculate distance (in %) from current price to liquidation price.
        
        THIS IS WHAT TRIGGERS AUTO-CLOSE - not free margin!
        
        Distance = how much price can move against you before liquidation.
        
        For LONG positions:
            Distance% = (Current - Liquidation) / Current * 100
            Example: Current=$95, Liq=$90.50
            Distance = (95-90.50)/95 * 100 = 4.74%
            Meaning: price can drop 4.74% more before liquidation
            
        For SHORT positions:
            Distance% = (Liquidation - Current) / Current * 100
            Example: Current=$105, Liq=$109.50
            Distance = (109.50-105)/105 * 100 = 4.29%
            Meaning: price can rise 4.29% more before liquidation
        
        IMPORTANT:
        - Free margin can be NEGATIVE and we still don't auto-close!
        - Only when distance < 3.5% do we trigger auto-close
        - This ensures we only close when actually close to liquidation
        
        Returns:
            Positive percentage = safe distance to liquidation
            Zero or negative = at or past liquidation price (shouldn't happen normally)
        """
        if liquidation_price <= 0:
            return 100.0  # Spot position, no liquidation risk
        
        if side.lower() == 'long':
            # For long: distance = how much price can DROP before liquidation
            distance_pct = ((current_price - liquidation_price) / current_price) * 100
        else:
            # For short: distance = how much price can RISE before liquidation
            distance_pct = ((liquidation_price - current_price) / current_price) * 100
        
        return max(distance_pct, 0.0)
    
    def get_liquidation_risk_level(self, distance_pct: float) -> LiquidationRiskLevel:
        """
        Determine risk level based on DISTANCE TO LIQUIDATION PRICE (not free margin!).
        
        Distance = how much the price can move against you before liquidation.
        
        Thresholds (configurable via LiquidationConfig):
        - SAFE: > 15% distance to liquidation price
        - WARNING: 7-15% distance
        - DANGER: 3.5-7% distance  
        - CRITICAL: < 3.5% distance → AUTO-CLOSE triggered immediately
        - LIQUIDATED: <= 0% (already liquidated or past liquidation price)
        
        NOTE: Free margin being negative does NOT trigger auto-close!
        Only distance to actual liquidation price matters.
        """
        if distance_pct <= 0:
            return LiquidationRiskLevel.LIQUIDATED
        elif distance_pct <= self.liquidation_config.emergency_close_distance_pct:
            # < 1.5% - EMERGENCY CRITICAL (partial close)
            return LiquidationRiskLevel.CRITICAL
        elif distance_pct <= self.liquidation_config.auto_close_distance_pct:
            # < 3.5% - AUTO-CLOSE CRITICAL
            return LiquidationRiskLevel.CRITICAL
        elif distance_pct <= self.liquidation_config.danger_distance_pct:
            # 3.5-7% - DANGER
            return LiquidationRiskLevel.DANGER
        elif distance_pct <= self.liquidation_config.warn_distance_pct:
            # 7-15% - WARNING
            return LiquidationRiskLevel.WARNING
        else:
            # > 15% - SAFE
            return LiquidationRiskLevel.SAFE
    
    async def _check_liquidation_risk_all(self):
        """
        Check liquidation risk for ALL monitored leveraged positions.
        This is called periodically from the main monitor loop.
        """
        if not self.positions:
            return
        
        positions_to_close = []
        
        for key, pos in self.positions.items():
            # Skip spot positions (leverage = 1)
            if pos.leverage <= 1.0:
                continue
            
            current_price = self._price_cache.get(pos.symbol)
            if not current_price:
                continue
            
            # Calculate liquidation price if not already set
            if pos.liquidation_price is None:
                pos.liquidation_price = self.calculate_liquidation_price(
                    pos.entry_price,
                    pos.leverage,
                    pos.side
                )
            
            # Calculate distance to liquidation
            distance_pct = self.calculate_distance_to_liquidation(
                current_price,
                pos.liquidation_price,
                pos.side
            )
            
            # Determine risk level
            risk_level = self.get_liquidation_risk_level(distance_pct)
            pos.liquidation_risk_level = risk_level.value
            pos.last_liquidation_check = datetime.now()
            
            # Handle based on risk level
            if risk_level == LiquidationRiskLevel.CRITICAL:
                logger.critical(
                    f"🚨🚨🚨 CRITICAL LIQUIDATION RISK: {key} | "
                    f"Distance: {distance_pct:.2f}% | "
                    f"Liq Price: {pos.liquidation_price:.4f} | "
                    f"Current: {current_price:.4f} | "
                    f"Leverage: {pos.leverage}x"
                )
                
                if self.liquidation_config.enable_auto_close and not pos.auto_close_attempted:
                    positions_to_close.append((key, pos, current_price, distance_pct))
                    
            elif risk_level == LiquidationRiskLevel.DANGER:
                logger.warning(
                    f"🚨 DANGER - Liquidation approaching: {key} | "
                    f"Distance: {distance_pct:.2f}% | "
                    f"Liq Price: {pos.liquidation_price:.4f} | "
                    f"Current: {current_price:.4f}"
                )
                await self._send_liquidation_alert(pos, current_price, distance_pct, risk_level)
                
            elif risk_level == LiquidationRiskLevel.WARNING:
                if pos.liquidation_warnings_sent < 3:  # Limit warnings
                    logger.warning(
                        f"⚠️ WARNING - Liquidation risk elevated: {key} | "
                        f"Distance: {distance_pct:.2f}% | "
                        f"Leverage: {pos.leverage}x"
                    )
                    pos.liquidation_warnings_sent += 1
                    await self._send_liquidation_alert(pos, current_price, distance_pct, risk_level)
        
        # Execute auto-close for critical positions
        for key, pos, current_price, distance_pct in positions_to_close:
            await self._execute_liquidation_auto_close(key, pos, current_price, distance_pct)
    
    async def _send_liquidation_alert(
        self,
        pos: MonitoredPosition,
        current_price: float,
        distance_pct: float,
        risk_level: LiquidationRiskLevel
    ):
        """Send liquidation risk alert via email/webhook."""
        if not self.liquidation_config.enable_alerts:
            return
        
        alert_service = get_alert_service()
        if not alert_service:
            return
        
        user_email = await self._get_user_email(pos.user_id)
        if not user_email:
            return
        
        try:
            # Determine emoji and severity
            if risk_level == LiquidationRiskLevel.CRITICAL:
                emoji = "🚨🚨🚨"
                subject = f"CRITICAL: {pos.symbol} - Liquidation Imminent!"
            elif risk_level == LiquidationRiskLevel.DANGER:
                emoji = "🚨"
                subject = f"DANGER: {pos.symbol} - Liquidation Risk High"
            else:
                emoji = "⚠️"
                subject = f"WARNING: {pos.symbol} - Liquidation Risk Elevated"
            
            message = (
                f"{emoji} LIQUIDATION RISK ALERT {emoji}\n\n"
                f"Symbol: {pos.symbol}\n"
                f"Side: {pos.side.upper()}\n"
                f"Leverage: {pos.leverage}x\n"
                f"Entry Price: {pos.entry_price:.4f}\n"
                f"Current Price: {current_price:.4f}\n"
                f"Liquidation Price: {pos.liquidation_price:.4f}\n"
                f"Distance to Liquidation: {distance_pct:.2f}%\n"
                f"Risk Level: {risk_level.value.upper()}\n\n"
                f"ACTION REQUIRED: Consider reducing position size or adding margin."
            )
            
            if hasattr(alert_service, 'send_critical_alert'):
                await alert_service.send_critical_alert(
                    user_email=user_email,
                    subject=subject,
                    message=message
                )
            
            # Log event
            await self._log_liquidation_event(
                pos, current_price, distance_pct, risk_level,
                event_type="alert_sent",
                action_taken=f"Alert sent: {risk_level.value}"
            )
            
        except Exception as e:
            logger.error(f"Failed to send liquidation alert: {e}")
    
    async def _execute_liquidation_auto_close(
        self,
        key: str,
        pos: MonitoredPosition,
        current_price: float,
        distance_pct: float
    ):
        """
        Execute auto-close for position at critical liquidation risk.
        
        Strategy:
        1. Try full close first
        2. If fails, try partial close (50%) as emergency measure
        3. Log all attempts and send critical alerts
        
        v4.2: Manual positions receive CRITICAL ALERTS but NO auto-close.
        User maintains full control over manual position closures.
        """
        pos.auto_close_attempted = True
        
        # v4.3: Manual positions NOW HAVE Liquidation Protection with AUTO-CLOSE
        # This is the ONLY protection feature enabled for manual positions
        # (SL/TP/Trailing/TimeExit remain disabled for user control)
        if pos.is_manual_position:
            logger.critical(
                f"🚨🚨🚨 MANUAL POSITION LIQUIDATION PROTECTION TRIGGERED: {key} | "
                f"Distance: {distance_pct:.2f}% | Leverage: {pos.leverage}x | "
                f"⚠️ EMERGENCY AUTO-CLOSE INITIATING to prevent liquidation!"
            )
            # Send critical alert
            await self._send_liquidation_alert(pos, current_price, distance_pct, LiquidationRiskLevel.CRITICAL)
            # Log event - but continue to auto-close (don't return!)
            await self._log_liquidation_event(
                pos, current_price, distance_pct,
                LiquidationRiskLevel.CRITICAL,
                event_type="manual_position_liquidation_protection",
                action_taken="Auto-close initiated for manual position (liquidation protection)"
            )
            # NOTE: Don't return here - continue to auto-close logic below
        
        max_retries = self.liquidation_config.auto_close_max_retries
        
        logger.critical(
            f"🚨 INITIATING AUTO-CLOSE for {key} | "
            f"Distance to liquidation: {distance_pct:.2f}% | "
            f"Max retries: {max_retries}"
        )
        
        # Log event
        await self._log_liquidation_event(
            pos, current_price, distance_pct,
            LiquidationRiskLevel.CRITICAL,
            event_type="auto_close_attempt",
            action_taken="Initiating auto-close"
        )
        
        success = False
        last_error = None
        
        for attempt in range(max_retries):
            try:
                logger.info(f"🚨 Auto-close attempt {attempt + 1}/{max_retries} for {pos.symbol}")
                
                # Try full close
                await self._close_position(pos, max_retries=1)
                
                success = True
                logger.info(
                    f"✅ AUTO-CLOSE SUCCESSFUL: {key} | "
                    f"Avoided liquidation at {distance_pct:.2f}% distance"
                )
                
                # Send success alert
                await self._send_auto_close_alert(pos, current_price, distance_pct, success=True)
                
                # Log success
                await self._log_liquidation_event(
                    pos, current_price, distance_pct,
                    LiquidationRiskLevel.CRITICAL,
                    event_type="auto_close_success",
                    action_taken="Position fully closed"
                )
                
                # Call callback
                if self.on_auto_close_triggered:
                    await self.on_auto_close_triggered(pos, current_price, "liquidation_risk")
                
                # Remove from monitoring
                if key in self.positions:
                    del self.positions[key]
                
                break
                
            except Exception as e:
                last_error = str(e)
                delay = (2 ** attempt) * 0.5
                logger.error(
                    f"🚨 Auto-close attempt {attempt + 1} failed for {pos.symbol}: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
        
        if not success:
            # All retries failed - try emergency partial close
            if self.liquidation_config.enable_partial_emergency_close:
                logger.critical(
                    f"🚨🚨 FULL CLOSE FAILED - Attempting emergency partial close (50%) for {key}"
                )
                
                try:
                    await self._execute_partial_close(
                        pos,
                        current_price,
                        close_percent=50,  # Emergency 50% close
                        reason="emergency_liquidation_risk"
                    )
                    
                    logger.warning(
                        f"⚠️ PARTIAL CLOSE EXECUTED: {key} | "
                        f"50% position closed to reduce liquidation risk"
                    )
                    
                    await self._log_liquidation_event(
                        pos, current_price, distance_pct,
                        LiquidationRiskLevel.CRITICAL,
                        event_type="partial_close_success",
                        action_taken="Emergency 50% partial close"
                    )
                    
                except Exception as pe:
                    logger.critical(
                        f"🚨🚨🚨 EMERGENCY PARTIAL CLOSE ALSO FAILED: {key} | Error: {pe}"
                    )
            
            # Send failure alert
            await self._send_auto_close_alert(
                pos, current_price, distance_pct,
                success=False, error=last_error
            )
            
            # Log failure
            await self._log_liquidation_event(
                pos, current_price, distance_pct,
                LiquidationRiskLevel.CRITICAL,
                event_type="auto_close_failed",
                action_taken="All close attempts failed",
                error_message=last_error
            )
            
            logger.critical(
                f"🚨🚨🚨 AUTO-CLOSE FAILED COMPLETELY for {key}! "
                f"MANUAL INTERVENTION REQUIRED! Last error: {last_error}"
            )
    
    async def _send_auto_close_alert(
        self,
        pos: MonitoredPosition,
        current_price: float,
        distance_pct: float,
        success: bool,
        error: str = None
    ):
        """Send alert about auto-close attempt result."""
        alert_service = get_alert_service()
        if not alert_service:
            return
        
        user_email = await self._get_user_email(pos.user_id)
        if not user_email:
            return
        
        try:
            if success:
                subject = f"✅ AUTO-CLOSE SUCCESS: {pos.symbol}"
                message = (
                    f"✅ POSITION AUTO-CLOSED TO AVOID LIQUIDATION ✅\n\n"
                    f"Symbol: {pos.symbol}\n"
                    f"Side: {pos.side.upper()}\n"
                    f"Leverage: {pos.leverage}x\n"
                    f"Entry Price: {pos.entry_price:.4f}\n"
                    f"Close Price: {current_price:.4f}\n"
                    f"Distance to Liquidation was: {distance_pct:.2f}%\n\n"
                    f"The position was automatically closed to protect your capital from liquidation."
                )
            else:
                subject = f"🚨 CRITICAL: AUTO-CLOSE FAILED for {pos.symbol}!"
                message = (
                    f"🚨🚨🚨 AUTO-CLOSE FAILED - MANUAL ACTION REQUIRED! 🚨🚨🚨\n\n"
                    f"Symbol: {pos.symbol}\n"
                    f"Side: {pos.side.upper()}\n"
                    f"Leverage: {pos.leverage}x\n"
                    f"Entry Price: {pos.entry_price:.4f}\n"
                    f"Current Price: {current_price:.4f}\n"
                    f"Liquidation Price: {pos.liquidation_price:.4f}\n"
                    f"Distance to Liquidation: {distance_pct:.2f}%\n"
                    f"Error: {error}\n\n"
                    f"⚠️ IMMEDIATE MANUAL INTERVENTION REQUIRED! ⚠️\n"
                    f"Log into your exchange immediately and close or reduce this position!"
                )
            
            if hasattr(alert_service, 'send_critical_alert'):
                await alert_service.send_critical_alert(
                    user_email=user_email,
                    subject=subject,
                    message=message
                )
                
        except Exception as e:
            logger.error(f"Failed to send auto-close alert: {e}")
    
    async def _log_liquidation_event(
        self,
        pos: MonitoredPosition,
        current_price: float,
        distance_pct: float,
        risk_level: LiquidationRiskLevel,
        event_type: str,
        action_taken: str = None,
        error_message: str = None
    ):
        """Log liquidation event to memory and database."""
        event = LiquidationEvent(
            timestamp=datetime.now(),
            symbol=pos.symbol,
            user_id=pos.user_id,
            event_type=event_type,
            risk_level=risk_level,
            distance_to_liquidation_pct=distance_pct,
            liquidation_price=pos.liquidation_price or 0,
            current_price=current_price,
            entry_price=pos.entry_price,
            leverage=pos.leverage,
            action_taken=action_taken,
            error_message=error_message
        )
        
        # Store in memory
        self._liquidation_events.append(event)
        
        # Limit memory storage to last 1000 events
        if len(self._liquidation_events) > 1000:
            self._liquidation_events = self._liquidation_events[-1000:]
        
        # Persist to database if enabled and available
        if self.liquidation_config.enable_db_logging and self._db_manager:
            try:
                from sqlalchemy import text
                with self._db_manager as session:
                    session.execute(text("""
                        INSERT INTO liquidation_events 
                        (timestamp, symbol, user_id, event_type, risk_level,
                         distance_to_liquidation_pct, liquidation_price,
                         current_price, entry_price, leverage,
                         action_taken, error_message)
                        VALUES (:ts, :symbol, :user_id, :event_type, :risk_level,
                                :distance, :liq_price, :current_price, :entry_price,
                                :leverage, :action, :error)
                    """), {
                        'ts': event.timestamp,
                        'symbol': event.symbol,
                        'user_id': event.user_id,
                        'event_type': event.event_type,
                        'risk_level': event.risk_level.value,
                        'distance': event.distance_to_liquidation_pct,
                        'liq_price': event.liquidation_price,
                        'current_price': event.current_price,
                        'entry_price': event.entry_price,
                        'leverage': event.leverage,
                        'action': event.action_taken,
                        'error': event.error_message
                    })
                    session.commit()
            except Exception as e:
                logger.debug(f"Could not persist liquidation event to DB: {e}")
    
    def get_liquidation_events(
        self,
        symbol: str = None,
        user_id: str = None,
        event_type: str = None,
        limit: int = 100
    ) -> List[LiquidationEvent]:
        """Get recent liquidation events with optional filters."""
        events = self._liquidation_events
        
        if symbol:
            events = [e for e in events if e.symbol == symbol]
        if user_id:
            events = [e for e in events if e.user_id == user_id]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        return events[-limit:]
    
    def get_positions_by_risk_level(self, risk_level: LiquidationRiskLevel = None) -> List[Dict]:
        """Get positions filtered by liquidation risk level."""
        positions = []
        
        for key, pos in self.positions.items():
            if pos.leverage <= 1.0:
                continue  # Skip spot
            
            current_price = self._price_cache.get(pos.symbol)
            if not current_price:
                continue
            
            if pos.liquidation_price is None:
                pos.liquidation_price = self.calculate_liquidation_price(
                    pos.entry_price, pos.leverage, pos.side
                )
            
            distance_pct = self.calculate_distance_to_liquidation(
                current_price, pos.liquidation_price, pos.side
            )
            
            level = self.get_liquidation_risk_level(distance_pct)
            
            if risk_level is None or level == risk_level:
                positions.append({
                    "key": key,
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "leverage": pos.leverage,
                    "entry_price": pos.entry_price,
                    "current_price": current_price,
                    "liquidation_price": pos.liquidation_price,
                    "distance_to_liquidation_pct": distance_pct,
                    "risk_level": level.value,
                    "user_id": pos.user_id
                })
        
        return sorted(positions, key=lambda x: x["distance_to_liquidation_pct"])
    
    def get_liquidation_summary(self) -> Dict[str, Any]:
        """Get summary of liquidation risk across all positions."""
        summary = {
            "total_leveraged_positions": 0,
            "safe": 0,
            "warning": 0,
            "danger": 0,
            "critical": 0,
            "highest_risk_positions": [],
            "config": {
                "enabled": self.liquidation_config.enabled,
                "warn_distance_pct": self.liquidation_config.warn_distance_pct,
                "auto_close_distance_pct": self.liquidation_config.auto_close_distance_pct,
                "auto_close_enabled": self.liquidation_config.enable_auto_close
            }
        }
        
        all_positions = self.get_positions_by_risk_level()
        summary["total_leveraged_positions"] = len(all_positions)
        
        for pos in all_positions:
            level = pos["risk_level"]
            if level in summary:
                summary[level] += 1
        
        # Top 5 highest risk
        summary["highest_risk_positions"] = all_positions[:5]
        
        return summary