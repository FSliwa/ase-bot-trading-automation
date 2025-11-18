"""Supabase-backed database layer for trading bot."""

from __future__ import annotations

import os
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence
import uuid

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

    @property
    def size(self) -> float:
        return self.quantity


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
    TradingMetricsCache = TradingMetricsCache

    def __init__(self) -> None:
        self.session: Optional[Session] = None

    def __enter__(self) -> "DatabaseManager":
        self.session = SessionLocal()
        return self

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
