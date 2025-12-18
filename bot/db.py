"""Supabase-backed database layer for trading bot."""

from __future__ import annotations

import os
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence
import uuid

# Load environment variables early to ensure DATABASE_URL is available
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///trading.db"

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.utcnow()


def extract_base_symbol(symbol: str) -> str:
    """
    Extract base currency from trading pair symbol.
    Signals should be stored as base symbol only (BTC, ETH, SOL).
    Quote currency (USDT, USDC, USD) is added locally based on user's balance.
    
    L8 FIX: This is a LEGACY function for backward compatibility.
    For new code, use: from bot.core.symbol_normalizer import get_base
    
    Examples:
        "BTC/USDC" -> "BTC"
        "ETH/USDT" -> "ETH"
        "BTCUSDT" -> "BTC"
        "SOL/USD" -> "SOL"
        "BTC" -> "BTC"
    """
    # L8 FIX: Delegate to central normalizer if available
    try:
        from bot.core.symbol_normalizer import get_base
        return get_base(symbol)
    except ImportError:
        pass  # Fall back to local implementation
    
    if not symbol:
        return symbol
    
    symbol = symbol.strip().upper()
    
    # Handle formats with slash: "BTC/USDC", "ETH/USDT", "SOL/USD"
    if '/' in symbol:
        return symbol.split('/')[0]
    
    # Handle concatenated formats: "BTCUSDT", "ETHUSDC"
    quote_currencies = ['USDT', 'USDC', 'USD', 'EUR', 'GBP', 'PLN', 'BUSD']
    for quote in quote_currencies:
        if symbol.endswith(quote):
            return symbol[:-len(quote)]
    
    # Already base symbol (e.g., "BTC", "ETH")
    return symbol


class Position(Base):  # type: ignore[misc]
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True, nullable=True)
    strategy = Column(String, nullable=True)
    symbol = Column(String, index=True, nullable=False)
    side = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    leverage = Column(Float, nullable=False, default=1.0)
    status = Column(String, nullable=False, default="OPEN", index=True)
    unrealized_pnl = Column(Float, nullable=False, default=0.0)
    realized_pnl = Column(Float, nullable=False, default=0.0)
    margin_used = Column(Float, nullable=False, default=0.0)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    entry_time = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    
    # v4.1: Source tracking - identifies who opened the position
    # Values: "bot", "manual", "unknown", "external"
    # Bot will NOT auto-manage positions with source="manual"
    source = Column(String, nullable=True, default="bot", index=True)
    
    # v4.0: Liquidation monitoring fields
    liquidation_price = Column(Float, nullable=True)
    close_reason = Column(String, nullable=True)  # normal, sl_triggered, tp_triggered, time_exit, auto_close_liquidation, ghost_cleanup

    @property
    def size(self) -> float:
        return self.quantity


# v4.0: Liquidation Events Audit Table
class LiquidationEventDB(Base):  # type: ignore[misc]
    """
    Audit table for liquidation-related events.
    Records all warnings, auto-close attempts, and outcomes.
    """
    __tablename__ = "liquidation_events"
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    symbol = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=True)
    event_type = Column(String, nullable=False, index=True)  # warning, danger, auto_close_attempt, auto_close_success, auto_close_failed
    risk_level = Column(String, nullable=False)  # safe, warning, danger, critical, liquidated
    distance_to_liquidation_pct = Column(Float, nullable=False)
    liquidation_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    leverage = Column(Float, nullable=False)
    action_taken = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


# v4.0: Position Reevaluation Audit Table  
class PositionReevaluation(Base):  # type: ignore[misc]
    """
    Audit table for position SL/TP reevaluations.
    Records all dynamic adjustments and their reasons.
    """
    __tablename__ = "position_reevaluations"
    
    id = Column(Integer, primary_key=True)
    position_id = Column(String, nullable=False, index=True)
    user_id = Column(String, index=True, nullable=True)
    symbol = Column(String, index=True, nullable=False)
    reevaluation_type = Column(String, nullable=False)  # trailing_stop, dynamic_sl, partial_tp, time_exit
    old_sl = Column(Float, nullable=True)
    new_sl = Column(Float, nullable=True)
    old_tp = Column(Float, nullable=True)
    new_tp = Column(Float, nullable=True)
    current_price = Column(Float, nullable=False)
    profit_pct = Column(Float, nullable=False)
    reason = Column(String, nullable=True)
    action_taken = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class Order(Base):  # type: ignore[misc]
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    client_order_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=True)
    strategy = Column(String, nullable=True)
    symbol = Column(String, index=True, nullable=False)
    side = Column(String, nullable=False)
    order_type = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)
    time_in_force = Column(String, nullable=True)
    reduce_only = Column(Boolean, nullable=False, default=False)
    leverage = Column(Float, nullable=False, default=1.0)
    status = Column(String, nullable=False, default="NEW", index=True)
    filled_quantity = Column(Float, nullable=False, default=0.0)
    avg_fill_price = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    fills = relationship("Fill", back_populates="order", cascade="all, delete-orphan")


class Fill(Base):  # type: ignore[misc]
    __tablename__ = "fills"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    fee = Column(Float, nullable=False, default=0.0)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    order = relationship("Order", back_populates="fills")


class TradingStats(Base):  # type: ignore[misc]
    __tablename__ = "trading_stats"

    id = Column(Integer, primary_key=True)
    date = Column(DateTime(timezone=True), nullable=False, index=True, default=_utcnow)
    starting_balance = Column(Float, nullable=False, default=0.0)
    ending_balance = Column(Float, nullable=False, default=0.0)
    realized_pnl = Column(Float, nullable=False, default=0.0)
    unrealized_pnl = Column(Float, nullable=False, default=0.0)
    trades = Column(Integer, nullable=False, default=0)
    win_rate = Column(Float, nullable=False, default=0.0)
    avg_win = Column(Float, nullable=False, default=0.0)
    avg_loss = Column(Float, nullable=False, default=0.0)
    max_drawdown = Column(Float, nullable=False, default=0.0)
    sharpe_ratio = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class RiskEvent(Base):  # type: ignore[misc]
    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True)
    event_type = Column(String, index=True, nullable=False)
    severity = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    symbol = Column(String, nullable=True)
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class StrategyDailyPerformance(Base):  # type: ignore[misc]
    __tablename__ = "strategy_daily_performance"

    id = Column(Integer, primary_key=True)
    date = Column(DateTime(timezone=True), nullable=False)
    strategy = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    trades = Column(Integer, nullable=False, default=0)
    avg_slippage_bps = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (UniqueConstraint("date", "strategy", "symbol", name="uq_strategy_daily"),)


class SlippageSample(Base):  # type: ignore[misc]
    __tablename__ = "slippage_samples"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    notional = Column(Float, nullable=False)
    expected_px = Column(Float, nullable=False)
    fill_px = Column(Float, nullable=False)
    mid_at_submit = Column(Float, nullable=True)
    slippage_bps = Column(Float, nullable=False)
    market_state_snapshot_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TradingBot(Base):  # type: ignore[misc]
    __tablename__ = "trading_bots"

    id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=True)
    name = Column(String, nullable=False)
    strategy = Column(String, nullable=False)
    status = Column(String, nullable=False, default="inactive")
    settings = Column(JSON, nullable=True)
    performance = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class AIAnalysis(Base):  # type: ignore[misc]
    __tablename__ = "ai_analyses"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    model_used = Column(String, nullable=True)
    recommendation = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    validation_model = Column(String, nullable=True)
    validation_status = Column(String, nullable=True)
    validation_reason = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)


class PortfolioSnapshot(Base):  # type: ignore[misc]
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True, nullable=True)
    total_balance = Column(Float, nullable=False)
    available_balance = Column(Float, nullable=False)
    margin_used = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    metadata_payload = Column("metadata", JSON, nullable=True)


class TradingMetricsCache(Base):  # type: ignore[misc]
    __tablename__ = "trading_metrics_cache"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    metric_type = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    calculated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    value = Column(Float, nullable=False)
    metadata_payload = Column("metadata", JSON, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("user_id", "metric_type", "timeframe", name="uq_metrics_scope"),
    )


class Trade(Base):  # type: ignore[misc]
    """Model pasujący do rzeczywistej tabeli trades w Supabase."""
    __tablename__ = "trades"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)  # UUID użytkownika - wymagane!
    exchange = Column(String, nullable=False, default='kraken')  # exchange enum: kraken, binance, etc
    symbol = Column(String, nullable=False, index=True)
    trade_type = Column(String, nullable=False)  # buy/sell enum
    amount = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    fee = Column(Float, nullable=True)
    fee_currency = Column(String, nullable=True)
    status = Column(String, nullable=True, default='completed')  # pending/completed/cancelled
    exchange_order_id = Column(String, nullable=True)
    strategy_name = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    emotion = Column(String, nullable=True)
    journal_notes = Column(String, nullable=True)
    ai_insight = Column(String, nullable=True)
    pnl = Column(Float, nullable=True)
    source = Column(String, nullable=True)  # bot/manual/position_monitor
    
    # L2 FIX v3.0: Add missing SL/TP/leverage fields for full trade tracking
    stop_loss = Column(Float, nullable=True)      # Stop loss price used
    take_profit = Column(Float, nullable=True)    # Take profit price used
    leverage = Column(Float, nullable=True)       # Leverage used (1.0 = no leverage)
    entry_price = Column(Float, nullable=True)    # Original entry price (may differ from price)
    exit_price = Column(Float, nullable=True)     # Actual exit price (for closed trades)


class TradingSignal(Base):  # type: ignore[misc]
    __tablename__ = "trading_signals"

    # Primary key - UUID w Supabase
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=True)  # UUID użytkownika
    
    # Core signal data
    symbol = Column(String, nullable=False, index=True)
    signal_type = Column(String, nullable=False)  # buy/sell/hold
    strength = Column(Numeric, nullable=True, default=0)  # numeric w DB
    confidence_score = Column(Integer, nullable=True, default=0)  # integer w DB (0-100)
    
    # Price targets
    price_target = Column(Numeric, nullable=True)
    stop_loss = Column(Numeric, nullable=True)
    take_profit = Column(Numeric, nullable=True)
    entry_price = Column(Numeric, nullable=True)
    
    # Analysis fields
    ai_analysis = Column(Text, nullable=True)
    source = Column(String, nullable=True)
    ai_model = Column(String, nullable=True)
    reasoning = Column(Text, nullable=True)
    market_sentiment = Column(String, nullable=True)
    technical_analysis = Column(Text, nullable=True)
    historical_insight = Column(Text, nullable=True)
    
    # Status and metadata
    is_active = Column(Boolean, nullable=False, default=True)
    status = Column(String, nullable=True, default='pending')  # pending/executed/expired/cancelled
    action = Column(String, nullable=True)  # dodatkowa akcja
    timeframe = Column(String, nullable=True)  # np. "1h", "4h", "1d"
    duration = Column(String, nullable=True)  # np. "12-24h"
    expected_profit_percentage = Column(Numeric, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Verification fields
    actual_price_24h = Column(Numeric, nullable=True)
    was_successful = Column(Boolean, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verification_notes = Column(Text, nullable=True)


# ============================================================================
# DCA (Dollar Cost Averaging) Models - NEW 2025-12-14
# ============================================================================

class DCAPosition(Base):  # type: ignore[misc]
    """
    DCA Position - tracks a Dollar Cost Averaging position.
    One DCA position can have multiple orders (base + safety orders).
    """
    __tablename__ = "dca_positions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    signal_id = Column(String, nullable=True, index=True)  # FK to trading_signals
    
    # Position details
    symbol = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False)  # 'long' or 'short'
    exchange = Column(String, nullable=False, default='binance')
    
    # DCA Configuration used
    base_order_percent = Column(Float, nullable=False, default=40.0)
    safety_order_count = Column(Integer, nullable=False, default=3)
    safety_order_percent = Column(Float, nullable=False, default=20.0)
    price_deviation_percent = Column(Float, nullable=False, default=3.0)
    price_deviation_scale = Column(Float, nullable=False, default=1.5)
    
    # Aggregated values (updated on each fill)
    total_quantity = Column(Float, nullable=False, default=0.0)
    average_entry_price = Column(Float, nullable=False, default=0.0)
    total_invested = Column(Float, nullable=False, default=0.0)
    filled_orders_count = Column(Integer, nullable=False, default=0)
    max_investment = Column(Float, nullable=True)  # Total budget allocated
    
    # Targets (calculated from average price)
    take_profit_percent = Column(Float, nullable=False, default=3.0)
    stop_loss_percent = Column(Float, nullable=False, default=10.0)
    take_profit_price = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)
    
    # Status
    status = Column(String, nullable=False, default='active', index=True)  # active, completed, cancelled
    
    # Results (filled when closed)
    exit_price = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    realized_pnl_percent = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True)  # 'take_profit', 'stop_loss', 'manual', 'time_exit'
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationship to orders
    orders = relationship("DCAOrder", back_populates="dca_position", cascade="all, delete-orphan")


class DCAOrder(Base):  # type: ignore[misc]
    """
    DCA Order - individual order within a DCA position.
    Can be base order or safety order (1, 2, 3, etc.)
    """
    __tablename__ = "dca_orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dca_position_id = Column(String, ForeignKey("dca_positions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Order type
    order_type = Column(String, nullable=False)  # 'base', 'safety_1', 'safety_2', etc.
    order_number = Column(Integer, nullable=False, default=0)  # 0=base, 1=SO1, 2=SO2, etc.
    
    # Trigger conditions
    trigger_price = Column(Float, nullable=False)  # Price at which to execute
    trigger_deviation_percent = Column(Float, nullable=True)  # Deviation from base entry
    
    # Order details
    target_quantity = Column(Float, nullable=False)  # Planned quantity
    target_value = Column(Float, nullable=False)  # Planned investment ($)
    
    # Execution status
    status = Column(String, nullable=False, default='pending', index=True)  # pending, triggered, filled, cancelled, failed
    
    # Fill details (populated when executed)
    fill_price = Column(Float, nullable=True)
    fill_quantity = Column(Float, nullable=True)
    fill_value = Column(Float, nullable=True)
    fill_fee = Column(Float, nullable=True)
    fill_time = Column(DateTime(timezone=True), nullable=True)
    
    # Exchange order tracking
    exchange_order_id = Column(String, nullable=True)
    exchange_order_status = Column(String, nullable=True)
    
    # Error tracking
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationship to position
    dca_position = relationship("DCAPosition", back_populates="orders")


class DCASettings(Base):  # type: ignore[misc]
    """
    User-specific DCA settings.
    """
    __tablename__ = "dca_settings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, unique=True, index=True)
    
    # Enable/disable
    dca_enabled = Column(Boolean, nullable=False, default=False)
    
    # Default DCA configuration
    default_base_order_percent = Column(Float, nullable=False, default=40.0)
    default_safety_order_count = Column(Integer, nullable=False, default=3)
    default_safety_order_percent = Column(Float, nullable=False, default=20.0)
    default_price_deviation_percent = Column(Float, nullable=False, default=3.0)
    default_price_deviation_scale = Column(Float, nullable=False, default=1.5)
    default_take_profit_percent = Column(Float, nullable=False, default=3.0)
    default_stop_loss_percent = Column(Float, nullable=False, default=10.0)
    
    # Advanced settings
    max_active_dca_positions = Column(Integer, nullable=False, default=3)
    min_time_between_safety_orders = Column(Integer, nullable=True)  # Seconds
    use_limit_orders = Column(Boolean, nullable=False, default=False)  # Limit vs Market
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "Supabase connection not configured. Set SUPABASE_DB_URL (preferred) or DATABASE_URL."
    )

if SUPABASE_DB_URL and "sslmode" not in SUPABASE_DB_URL:
    DATABASE_URL = f"{SUPABASE_DB_URL}{'&' if '?' in SUPABASE_DB_URL else '?'}sslmode=require"

if DATABASE_URL.startswith("sqlite") and not os.getenv("ALLOW_SQLITE_FALLBACK"):
    raise RuntimeError(
        "SQLite fallback is disabled. Configure Supabase by setting SUPABASE_DB_URL or allow "
        "local development with ALLOW_SQLITE_FALLBACK=1."
    )

_engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)


def get_session() -> Session:
    """
    Get a new database session.
    
    This is a convenience function for modules that need direct session access.
    Caller is responsible for calling session.close() when done.
    
    Usage:
        session = get_session()
        try:
            # do database work
            session.commit()
        finally:
            session.close()
            
    Or use DatabaseManager for context-managed sessions:
        with DatabaseManager() as db:
            # do database work
    """
    return SessionLocal()


def init_db() -> None:
    """Create tables if they do not exist."""
    Base.metadata.create_all(_engine)


@dataclass
class OrderResult:
    id: int
    client_order_id: str
    status: str
    filled_quantity: float


class DatabaseManager(AbstractContextManager["DatabaseManager"]):
    """Context-managed database helper."""

    Position = Position
    Order = Order
    Fill = Fill
    TradingStats = TradingStats
    RiskEvent = RiskEvent
    StrategyDailyPerformance = StrategyDailyPerformance
    TradingBot = TradingBot
    AIAnalysis = AIAnalysis
    TradingBot = TradingBot
    AIAnalysis = AIAnalysis
    TradingMetricsCache = TradingMetricsCache
    Trade = Trade
    TradingSignal = TradingSignal

    def __init__(self) -> None:
        self.session: Optional[Session] = None

    def __enter__(self) -> "DatabaseManager":
        self.session = SessionLocal()
        return self

    @staticmethod
    def session_scope():
        """
        Context manager for database sessions.
        
        Usage:
            with DatabaseManager.session_scope() as session:
                session.query(Position).all()
        """
        from contextlib import contextmanager
        
        @contextmanager
        def _session_scope():
            session = SessionLocal()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        
        return _session_scope()

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        if not self.session:
            return
        try:
            if exc:
                self.session.rollback()
            else:
                self.session.commit()
        finally:
            self.session.close()
            self.session = None

    # -- Order management -------------------------------------------------
    def create_order(
        self,
        *,
        client_order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float],
        stop_price: Optional[float],
        time_in_force: Optional[str],
        reduce_only: bool,
        leverage: float,
        user_id: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> Order:
        assert self.session is not None
        order = Order(
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            reduce_only=reduce_only,
            leverage=leverage,
            user_id=user_id,
            strategy=strategy,
        )
        self.session.add(order)
        self.session.flush()
        return order

    def cancel_order(self, order_id: int) -> None:
        assert self.session is not None
        order = self.session.get(Order, order_id)
        if order:
            order.status = "CANCELED"
            order.updated_at = _utcnow()
            self.session.add(order)

    def fill_order(self, *, order_id: int, filled_qty: float, fill_price: float, fee: float) -> Fill:
        assert self.session is not None
        order = self.session.get(Order, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        fill = Fill(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=filled_qty,
            price=fill_price,
            fee=fee,
        )
        order.filled_quantity += filled_qty
        previous_notional = order.avg_fill_price * max(order.filled_quantity - filled_qty, 0.0)
        new_notional = previous_notional + fill_price * filled_qty
        if order.filled_quantity > 0:
            order.avg_fill_price = new_notional / order.filled_quantity
        if order.filled_quantity >= order.quantity:
            order.status = "FILLED"
        else:
            order.status = "PARTIALLY_FILLED"
        order.updated_at = _utcnow()

        self.session.add(fill)
        self.session.add(order)
        return fill

    # -- Position management ----------------------------------------------
    def create_position(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        leverage: float,
        *,
        user_id: Optional[str] = None,
        strategy: Optional[str] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Position:
        assert self.session is not None
        margin_used = abs(quantity * entry_price / max(leverage, 1e-9))
        position = Position(
            user_id=user_id,
            strategy=strategy,
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            leverage=leverage,
            margin_used=margin_used,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        self.session.add(position)
        self.session.flush()
        return position

    def get_position_by_symbol(self, symbol: str) -> Optional[Position]:
        assert self.session is not None
        return (
            self.session.query(Position)
            .filter(Position.symbol == symbol, Position.status == "OPEN")
            .order_by(Position.entry_time.desc())
            .first()
        )

    def get_open_positions(self) -> List[Position]:
        assert self.session is not None
        return (
            self.session.query(Position)
            .filter(Position.status == "OPEN")
            .order_by(Position.entry_time.asc())
            .all()
        )

    def update_position_price(self, position_id: int, current_price: float) -> None:
        assert self.session is not None
        position = self.session.get(Position, position_id)
        if not position:
            return
        position.current_price = current_price
        if position.side.upper() == "BUY":
            position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
        else:
            position.unrealized_pnl = (position.entry_price - current_price) * position.quantity
        position.updated_at = _utcnow()
        self.session.add(position)

    def close_position(self, position_id: int, exit_price: float) -> Position:
        assert self.session is not None
        position = self.session.get(Position, position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")
        if position.status == "CLOSED":
            return position

        if position.side.upper() == "BUY":
            realized = (exit_price - position.entry_price) * position.quantity
        else:
            realized = (position.entry_price - exit_price) * position.quantity

        position.status = "CLOSED"
        position.exit_time = _utcnow()
        position.current_price = exit_price
        position.realized_pnl += realized
        position.unrealized_pnl = 0.0
        position.margin_used = 0.0
        position.updated_at = _utcnow()
        self.session.add(position)
        return position

    # -- Metrics -----------------------------------------------------------
    def save_slippage_sample(
        self,
        *,
        symbol: str,
        side: str,
        notional: float,
        expected_px: float,
        fill_px: float,
        mid_at_submit: Optional[float],
        slippage_bps: float,
        market_state_snapshot_id: Optional[str],
    ) -> SlippageSample:
        assert self.session is not None
        sample = SlippageSample(
            symbol=symbol,
            side=side,
            notional=notional,
            expected_px=expected_px,
            fill_px=fill_px,
            mid_at_submit=mid_at_submit,
            slippage_bps=slippage_bps,
            market_state_snapshot_id=market_state_snapshot_id,
        )
        self.session.add(sample)
        return sample

    def get_strategy_daily_performance(
        self,
        *,
        strategy: str,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[StrategyDailyPerformance]:
        assert self.session is not None
        return (
            self.session.query(StrategyDailyPerformance)
            .filter(
                StrategyDailyPerformance.strategy == strategy,
                StrategyDailyPerformance.symbol == symbol,
                StrategyDailyPerformance.date >= start_date,
                StrategyDailyPerformance.date <= end_date,
            )
            .all()
        )

    def upsert_strategy_daily_performance(
        self,
        *,
        date: datetime,
        strategy: str,
        symbol: str,
        trades: int,
        avg_slippage_bps: float,
    ) -> StrategyDailyPerformance:
        assert self.session is not None
        record = (
            self.session.query(StrategyDailyPerformance)
            .filter(
                StrategyDailyPerformance.date == date,
                StrategyDailyPerformance.strategy == strategy,
                StrategyDailyPerformance.symbol == symbol,
            )
            .one_or_none()
        )
        if record:
            record.trades = trades
            record.avg_slippage_bps = avg_slippage_bps
            record.updated_at = _utcnow()
        else:
            record = StrategyDailyPerformance(
                date=date,
                strategy=strategy,
                symbol=symbol,
                trades=trades,
                avg_slippage_bps=avg_slippage_bps,
            )
            self.session.add(record)
        return record

    def record_trading_stats(
        self,
        *,
        date: datetime,
        starting_balance: float,
        ending_balance: float,
        realized_pnl: float,
        unrealized_pnl: float,
        trades: int,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        max_drawdown: float,
        sharpe_ratio: Optional[float] = None,
    ) -> TradingStats:
        assert self.session is not None
        stats = TradingStats(
            date=date,
            starting_balance=starting_balance,
            ending_balance=ending_balance,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            trades=trades,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
        )
        self.session.add(stats)
        return stats

    # -- Risk events -------------------------------------------------------
    def log_risk_event(
        self,
        *,
        event_type: str,
        severity: str,
        message: str,
        symbol: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> RiskEvent:
        assert self.session is not None
        event = RiskEvent(
            event_type=event_type,
            severity=severity,
            message=message,
            symbol=symbol,
            data=data,
        )
        self.session.add(event)
        return event

    # -- AI analyses -------------------------------------------------------
    def record_ai_analysis(
        self,
        *,
        symbol: str,
        model_used: str,
        recommendation: Optional[str],
        confidence: Optional[float],
        payload: Dict[str, Any],
        validation_model: Optional[str] = None,
        validation_status: Optional[str] = None,
        validation_reason: Optional[str] = None,
    ) -> AIAnalysis:
        assert self.session is not None
        analysis = AIAnalysis(
            symbol=symbol,
            model_used=model_used,
            recommendation=recommendation,
            confidence=confidence,
            payload=payload,
            validation_model=validation_model,
            validation_status=validation_status,
            validation_reason=validation_reason,
        )
        self.session.add(analysis)
        return analysis

    def get_latest_analysis(self, symbol: str) -> Optional[AIAnalysis]:
        assert self.session is not None
        return (
            self.session.query(AIAnalysis)
            .filter(AIAnalysis.symbol == symbol)
            .order_by(AIAnalysis.created_at.desc())
            .first()
        )

    # -- Trading bots -----------------------------------------------------
    def list_trading_bots(self, user_id: Optional[str] = None) -> List[TradingBot]:
        assert self.session is not None
        query = self.session.query(TradingBot)
        if user_id:
            query = query.filter(TradingBot.user_id == user_id)
        return query.order_by(TradingBot.created_at.asc()).all()

    def get_trading_bot(self, bot_id: str) -> Optional[TradingBot]:
        assert self.session is not None
        return self.session.get(TradingBot, bot_id)

    def create_trading_bot(
        self,
        *,
        name: str,
        strategy: str,
        status: str,
        settings: Optional[Dict[str, Any]] = None,
        performance: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
    ) -> TradingBot:
        assert self.session is not None
        bot = TradingBot(
            id=bot_id or str(uuid.uuid4()),
            user_id=user_id,
            name=name,
            strategy=strategy,
            status=status,
            settings=settings,
            performance=performance,
        )
        self.session.add(bot)
        return bot

    def update_trading_bot(
        self,
        bot_id: str,
        *,
        name: Optional[str] = None,
        strategy: Optional[str] = None,
        status: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
        performance: Optional[Dict[str, Any]] = None,
    ) -> Optional[TradingBot]:
        assert self.session is not None
        bot = self.session.get(TradingBot, bot_id)
        if not bot:
            return None
        if name is not None:
            bot.name = name
        if strategy is not None:
            bot.strategy = strategy
        if status is not None:
            bot.status = status
        if settings is not None:
            bot.settings = settings
        if performance is not None:
            bot.performance = performance
        bot.updated_at = _utcnow()
        self.session.add(bot)
        return bot

    def delete_trading_bot(self, bot_id: str) -> bool:
        assert self.session is not None
        bot = self.session.get(TradingBot, bot_id)
        if not bot:
            return False
        self.session.delete(bot)
        return True

    # -- Portfolio snapshots ----------------------------------------------
    def record_portfolio_snapshot(
        self,
        *,
        user_id: Optional[str],
        total_balance: float,
        available_balance: float,
        margin_used: float,
        unrealized_pnl: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PortfolioSnapshot:
        assert self.session is not None
        snapshot = PortfolioSnapshot(
            user_id=user_id,
            total_balance=total_balance,
            available_balance=available_balance,
            margin_used=margin_used,
            unrealized_pnl=unrealized_pnl,
            metadata_payload=metadata,
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def get_portfolio_history(
        self,
        *,
        user_id: str,
        start_timestamp: datetime,
    ) -> List[PortfolioSnapshot]:
        assert self.session is not None
        return (
            self.session.query(PortfolioSnapshot)
            .filter(
                PortfolioSnapshot.user_id == user_id,
                PortfolioSnapshot.timestamp >= start_timestamp,
            )
            .order_by(PortfolioSnapshot.timestamp.asc())
            .all()
        )

    def list_snapshot_user_ids(self) -> List[str]:
        assert self.session is not None
        rows = self.session.query(PortfolioSnapshot.user_id).distinct().all()
        return [row[0] for row in rows if row[0] is not None]

    # -- Trading metrics cache -------------------------------------------
    def upsert_metric_cache(
        self,
        *,
        user_id: str,
        metric_type: str,
        timeframe: str,
        value: float,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
    ) -> TradingMetricsCache:
        assert self.session is not None
        record = (
            self.session.query(TradingMetricsCache)
            .filter(
                TradingMetricsCache.user_id == user_id,
                TradingMetricsCache.metric_type == metric_type,
                TradingMetricsCache.timeframe == timeframe,
            )
            .one_or_none()
        )
        if record:
            record.value = value
            record.metadata_payload = metadata
            record.expires_at = expires_at
            record.calculated_at = _utcnow()
        else:
            record = TradingMetricsCache(
                user_id=user_id,
                metric_type=metric_type,
                timeframe=timeframe,
                value=value,
                metadata_payload=metadata,
                expires_at=expires_at,
            )
            self.session.add(record)
        return record

    # -- Trading Signals ---------------------------------------------------
    def save_trading_signal(
        self,
        *,
        symbol: str,
        signal_type: str,
        confidence_score: float = 0,
        price_target: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        entry_price: Optional[float] = None,
        ai_analysis: Optional[str] = None,
        source: str = "bot",
        strength: Optional[float] = None,
        user_id: Optional[str] = None,
        is_active: bool = True,
        status: str = "pending",
        timeframe: Optional[str] = None,
        reasoning: Optional[str] = None,
        market_sentiment: Optional[str] = None,
    ) -> TradingSignal:
        assert self.session is not None
        
        # Store only base symbol (BTC, ETH, SOL) - quote currency added locally when reading
        base_symbol = extract_base_symbol(symbol)
        
        signal = TradingSignal(
            id=str(uuid.uuid4()),
            user_id=user_id,
            symbol=base_symbol,  # Store only base symbol
            signal_type=signal_type.lower(),  # Normalize to lowercase
            confidence_score=int(confidence_score * 100) if confidence_score <= 1 else int(confidence_score),  # Convert 0-1 to 0-100
            price_target=price_target,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_price=entry_price,
            ai_analysis=ai_analysis,
            source=source,
            strength=strength if strength is not None else 0,
            is_active=is_active,
            status=status,
            timeframe=timeframe,
            reasoning=reasoning,
            market_sentiment=market_sentiment,
        )
        self.session.add(signal)
        return signal

    def get_recent_signals(
        self,
        symbol: str,
        hours: int = 1,
        limit: int = 10
    ) -> List[TradingSignal]:
        """
        Get recent trading signals for a symbol.
        Returns a NEW list (immutable pattern).
        Uses base symbol (BTC, ETH) for querying since signals are stored as base symbols.
        """
        assert self.session is not None
        from datetime import timedelta
        
        # Normalize to base symbol (BTC/USDC -> BTC)
        base_symbol = extract_base_symbol(symbol)
        
        cutoff = _utcnow() - timedelta(hours=hours)
        
        signals = (
            self.session.query(TradingSignal)
            .filter(TradingSignal.symbol == base_symbol)  # Use base symbol
            .filter(TradingSignal.created_at > cutoff)
            .order_by(TradingSignal.created_at.desc())
            .limit(limit)
            .all()
        )
        
        return list(signals)  # Return new list

    def get_signal_consensus(
        self,
        symbol: str,
        signal_type: str,
        hours: int = 1
    ) -> Dict[str, any]:
        """
        Calculate consensus for a signal type based on recent history.
        Returns immutable result dict.
        """
        assert self.session is not None
        
        recent = self.get_recent_signals(symbol, hours=hours, limit=10)
        
        if not recent:
            return {
                'consensus': 0.0,
                'matching_count': 0,
                'total_count': 0,
                'avg_confidence': 0.0
            }
        
        matching = [s for s in recent if s.signal_type.upper() == signal_type.upper()]
        avg_conf = sum(float(s.confidence_score or 0.5) for s in matching) / len(matching) if matching else 0.0
        
        return {
            'consensus': len(matching) / len(recent),
            'matching_count': len(matching),
            'total_count': len(recent),
            'avg_confidence': avg_conf
        }

    def save_trade(
        self,
        *,
        user_id: str,
        symbol: str,
        trade_type: str,
        price: float,
        amount: float,
        pnl: Optional[float] = None,
        source: str = "bot",
        emotion: Optional[str] = None,
        exchange: str = "kraken",
        # L2 FIX v3.0: Add SL/TP/leverage parameters
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        leverage: Optional[float] = None,
        entry_price: Optional[float] = None,
        exit_price: Optional[float] = None,
    ) -> Trade:
        """Save an executed trade to the database.
        
        L2 FIX v3.0: Now accepts stop_loss, take_profit, leverage, entry_price, exit_price
        for complete trade tracking and analytics.
        """
        assert self.session is not None
        trade = Trade(
            user_id=user_id,
            symbol=symbol,
            trade_type=trade_type.lower(),  # DB enum uses lowercase: 'buy', 'sell'
            price=price,
            amount=amount,
            pnl=pnl,
            source=source,
            emotion=emotion,
            exchange=exchange.lower() if exchange else "kraken",  # DB enum: kraken, binance
            status="completed",
            # L2 FIX v3.0: Save SL/TP/leverage data
            stop_loss=stop_loss,
            take_profit=take_profit,
            leverage=leverage,
            entry_price=entry_price,
            exit_price=exit_price,
        )
        self.session.add(trade)
        self.session.flush()
        return trade

    def get_trades(
        self,
        *,
        symbol: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[Trade]:
        """Get trades with optional filters."""
        assert self.session is not None
        query = self.session.query(Trade)
        if symbol:
            query = query.filter(Trade.symbol == symbol)
        if source:
            query = query.filter(Trade.source == source)
        return query.order_by(Trade.created_at.desc()).limit(limit).all()

    def get_latest_metric_cache(
        self,
        *,
        user_id: str,
        metric_type: str,
        timeframe: str,
        require_fresh: bool = True,
    ) -> Optional[TradingMetricsCache]:
        assert self.session is not None
        query = self.session.query(TradingMetricsCache).filter(
            TradingMetricsCache.user_id == user_id,
            TradingMetricsCache.metric_type == metric_type,
            TradingMetricsCache.timeframe == timeframe,
        )
        if require_fresh:
            query = query.filter(
                (TradingMetricsCache.expires_at.is_(None))
                | (TradingMetricsCache.expires_at > _utcnow())
            )
        return query.order_by(TradingMetricsCache.calculated_at.desc()).first()

    def purge_expired_metric_cache(self) -> int:
        assert self.session is not None
        return (
            self.session.query(TradingMetricsCache)
            .filter(
                TradingMetricsCache.expires_at.isnot(None),
                TradingMetricsCache.expires_at <= _utcnow(),
            )
            .delete(synchronize_session=False)
        )

    def list_active_metrics_cache(self, *, user_id: str) -> List[TradingMetricsCache]:
        assert self.session is not None
        return (
            self.session.query(TradingMetricsCache)
            .filter(TradingMetricsCache.user_id == user_id)
            .filter(
                (TradingMetricsCache.expires_at.is_(None))
                | (TradingMetricsCache.expires_at > _utcnow())
            )
            .order_by(TradingMetricsCache.calculated_at.desc())
            .all()
        )


__all__ = [
    "DatabaseManager",
    "init_db",
    "Position",
    "Order",
    "Fill",
    "TradingStats",
    "RiskEvent",
    "StrategyDailyPerformance",
    "TradingBot",
    "AIAnalysis",
    "PortfolioSnapshot",
    "TradingMetricsCache",
]
