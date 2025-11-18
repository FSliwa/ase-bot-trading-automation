"""AI and trading bot routes backed by Supabase PostgreSQL."""

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator
from sqlalchemy import case, func, or_

from .auth_routes import verify_token
from bot.database import DatabaseManager
from bot.models import (
    AIInsight,
    MarketAlert,
    MarketData as MarketDataModel,
    Trade,
    TradingSettings,
    TradingSignal,
)

logger = logging.getLogger(__name__)

# Create router
ai_router = APIRouter(prefix="/api/ai", tags=["AI"])


# ---------------------------------------------------------------------------
# Configuration & helpers
# ---------------------------------------------------------------------------

DEFAULT_STRATEGIES = [
    "RSI Scalping",
    "Moving Average Crossover",
    "Bollinger Bands Mean Reversion",
    "Momentum Trading",
    "Grid Trading",
    "DCA (Dollar Cost Averaging)",
    "Arbitrage",
    "Market Making",
]

PRIORITY_ORDER = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

RISK_LEVEL_LABEL_TO_SCORE = {
    "low": 1,
    "medium": 3,
    "high": 5,
}

RISK_LEVEL_SCORE_TO_LABEL = {
    1: "low",
    2: "low",
    3: "medium",
    4: "medium",
    5: "high",
}


def decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    """Convert Decimal (or numeric) values to float."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def safe_float(value: Optional[Decimal]) -> float:
    result = decimal_to_float(value)
    return result if result is not None else 0.0


def parse_user_uuid(token_data: Dict[str, Any]) -> uuid.UUID:
    try:
        return uuid.UUID(str(token_data["sub"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication token") from exc


def parse_bot_uuid(bot_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(bot_id))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid bot identifier") from exc


def extract_strategy_name(settings: TradingSettings) -> Tuple[str, str]:
    config = settings.strategy_config or {}
    name = config.get("name") or config.get("label") or f"{settings.exchange.title()} Bot"
    strategy = (
        config.get("strategy")
        or config.get("strategy_name")
        or config.get("name")
        or "custom"
    )
    return str(name), str(strategy)


def collect_user_trades(session, user_id: uuid.UUID, strategy_name: Optional[str]) -> List[Trade]:
    query = session.query(Trade).filter(Trade.user_id == user_id)
    if strategy_name:
        query = query.filter(Trade.strategy_name == strategy_name)
    return query.order_by(Trade.created_at.asc()).all()


def calculate_performance_metrics(trades: List[Trade]) -> Tuple[Dict[str, float], Dict[str, float]]:
    if not trades:
        summary = {
            "total_pnl": 0.0,
            "pnl_percentage": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
        }
        details = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0,
            "total_pnl_percentage": 0.0,
            "win_rate": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
        }
        return summary, details

    buy_value = Decimal("0")
    sell_value = Decimal("0")
    winning_trades = 0
    cumulative = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")

    ordered_trades = sorted(
        trades,
        key=lambda trade: trade.created_at or trade.updated_at or datetime.utcnow(),
    )

    for trade in ordered_trades:
        amount = trade.amount or Decimal("0")
        price = trade.price or Decimal("0")
        value = amount * price
        trade_type = (trade.trade_type or "").lower()

        if trade_type == "buy":
            buy_value += value
            cumulative -= value
        elif trade_type == "sell":
            sell_value += value
            winning_trades += 1
            cumulative += value
        else:
            cumulative += value

        if cumulative > peak:
            peak = cumulative
        drawdown = cumulative - peak
        if drawdown < max_drawdown:
            max_drawdown = drawdown

    total_trades = len(trades)
    losing_trades = total_trades - winning_trades
    total_pnl = sell_value - buy_value
    invested = buy_value if buy_value > 0 else Decimal("0")

    pnl_percentage = (total_pnl / invested * Decimal("100")) if invested else Decimal("0")
    win_rate = (
        Decimal(winning_trades) / Decimal(total_trades) * Decimal("100")
        if total_trades
        else Decimal("0")
    )

    average_win = (
        sell_value / Decimal(winning_trades)
        if winning_trades
        else Decimal("0")
    )
    average_loss = (
        buy_value / Decimal(losing_trades)
        if losing_trades
        else Decimal("0")
    )
    profit_factor = (
        sell_value / buy_value
        if buy_value > 0
        else Decimal("0")
    )

    summary = {
        "total_pnl": float(total_pnl),
        "pnl_percentage": float(pnl_percentage),
        "win_rate": float(win_rate),
        "total_trades": total_trades,
    }

    details = {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "total_pnl": float(total_pnl),
        "total_pnl_percentage": float(pnl_percentage),
        "win_rate": float(win_rate),
        "average_win": float(average_win),
        "average_loss": float(average_loss),
        "profit_factor": float(profit_factor),
        "max_drawdown": float(max_drawdown),
    }

    return summary, details


def to_decimal(value: Optional[float]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


def build_bot_payload(session, settings: TradingSettings) -> "TradingBot":
    name, strategy = extract_strategy_name(settings)
    summary_metrics, _ = calculate_performance_metrics(
        collect_user_trades(session, settings.user_id, strategy)
    )

    risk_label = None
    if settings.risk_level is not None:
        risk_label = RISK_LEVEL_SCORE_TO_LABEL.get(int(settings.risk_level), "medium")

    config = settings.strategy_config or {}

    performance = {
        "total_pnl": round(summary_metrics["total_pnl"], 2),
        "pnl_percentage": round(summary_metrics["pnl_percentage"], 2),
        "win_rate": round(summary_metrics["win_rate"], 2),
        "total_trades": summary_metrics["total_trades"],
    }

    bot_settings: Dict[str, Any] = {
        "risk_level": risk_label or config.get("risk_level_label", "medium"),
        "max_position_size": safe_float(settings.max_position_size),
        "stop_loss_percentage": safe_float(settings.stop_loss_percentage),
        "take_profit_percentage": safe_float(settings.take_profit_percentage),
        "trading_pairs": settings.preferred_pairs or [],
        "is_active": bool(settings.is_trading_enabled),
    }

    return TradingBot(
        id=str(settings.id),
        name=name,
        strategy=strategy,
        status="active" if settings.is_trading_enabled else "inactive",
        created_at=settings.created_at or datetime.utcnow(),
        last_updated=settings.updated_at or settings.created_at or datetime.utcnow(),
        performance=performance,
        settings=bot_settings,
    )


def serialize_ai_insight(insight: AIInsight) -> "AIInsightResponse":
    return AIInsightResponse(
        id=str(insight.id),
        insight_type=insight.insight_type,
        title=insight.title,
        description=insight.description,
        confidence_score=insight.confidence_score,
        action_required=insight.action_required,
        priority=insight.priority,
        related_symbols=insight.related_symbols or [],
    metadata=insight.metadata_payload or {},
        is_read=bool(insight.is_read),
        expires_at=insight.expires_at,
        created_at=insight.created_at or datetime.utcnow(),
        updated_at=insight.updated_at or insight.created_at or datetime.utcnow(),
    )


def serialize_trading_signal(signal: TradingSignal) -> "TradingSignalResponse":
    return TradingSignalResponse(
        id=str(signal.id),
        symbol=signal.symbol,
        signal_type=signal.signal_type,
        strength=signal.strength,
        price_target=decimal_to_float(signal.price_target),
        stop_loss=decimal_to_float(signal.stop_loss),
        take_profit=decimal_to_float(signal.take_profit),
        confidence_score=signal.confidence_score,
        ai_analysis=signal.ai_analysis,
        source=signal.source,
        is_active=bool(signal.is_active),
        expires_at=signal.expires_at,
        created_at=signal.created_at or datetime.utcnow(),
    )


def serialize_market_alert(alert: MarketAlert) -> "MarketAlertResponse":
    return MarketAlertResponse(
        id=str(alert.id),
        alert_type=alert.alert_type,
        symbol=alert.symbol,
        title=alert.title,
        description=alert.description,
        trigger_price=decimal_to_float(alert.trigger_price),
        current_price=decimal_to_float(alert.current_price),
        target_price=decimal_to_float(alert.target_price),
        percentage_change=decimal_to_float(alert.percentage_change),
        is_triggered=bool(alert.is_triggered),
        is_read=bool(alert.is_read),
        priority=alert.priority,
    metadata=alert.metadata_payload or {},
        created_at=alert.created_at or datetime.utcnow(),
        triggered_at=alert.triggered_at,
    )


def get_latest_price(session, symbol: str) -> Optional[float]:
    record = (
        session.query(MarketDataModel)
        .filter(MarketDataModel.symbol == symbol)
        .order_by(MarketDataModel.timestamp.desc())
        .first()
    )
    if not record:
        return None
    return decimal_to_float(record.price)


def determine_recommendation(insight: AIInsight) -> str:
    metadata = insight.metadata_payload or {}
    if metadata.get("recommendation"):
        return str(metadata["recommendation"]).lower()
    if insight.insight_type in {"warning", "risk_alert"}:
        return "sell"
    if insight.insight_type in {"opportunity", "strategy"}:
        return "buy"
    return "hold"


def determine_risk_level(insight: AIInsight) -> str:
    metadata = insight.metadata_payload or {}
    if metadata.get("risk_level"):
        return str(metadata["risk_level"]).lower()
    priority = (insight.priority or "medium").lower()
    if priority in {"critical", "high"}:
        return "high"
    if priority == "medium":
        return "medium"
    return "low"


def build_prediction_from_signal(
    session,
    signal: TradingSignal,
    symbol: str,
) -> "MarketPrediction":
    current_price = get_latest_price(session, symbol)
    if current_price is None:
        current_price = decimal_to_float(signal.price_target) or 0.0

    strength_factor = max(signal.strength or 0, 0) / 100
    price_target = decimal_to_float(signal.price_target)
    stop_loss = decimal_to_float(signal.stop_loss)
    take_profit = decimal_to_float(signal.take_profit)

    if price_target is None:
        adjustment = current_price * strength_factor * 0.1
        if signal.signal_type.lower() == "buy":
            price_target = current_price + adjustment
        elif signal.signal_type.lower() == "sell":
            price_target = current_price - adjustment
        else:
            price_target = current_price

    predicted_price_1h = price_target * (1 - 0.01) if signal.signal_type.lower() == "sell" else price_target * (1 + 0.01)
    predicted_price_24h = price_target
    predicted_price_7d = (
        take_profit
        if take_profit is not None
        else price_target * (1 + strength_factor * 0.5)
    )

    confidence = float(signal.confidence_score)
    confidence_1h = min(100.0, confidence)
    confidence_24h = max(0.0, confidence - 5)
    confidence_7d = max(0.0, confidence - 10)

    trend_map = {
        "buy": "bullish",
        "sell": "bearish",
        "hold": "neutral",
    }
    trend = trend_map.get(signal.signal_type.lower(), "neutral")

    key_factors: List[str] = []
    if signal.ai_analysis:
        for line in signal.ai_analysis.splitlines():
            cleaned = line.strip("• ")
            if cleaned:
                key_factors.append(cleaned)
    if not key_factors:
        key_factors = [
            f"Signal strength score: {signal.strength}",
            f"Confidence score: {signal.confidence_score}",
            f"Source: {signal.source}",
        ]

    return MarketPrediction(
        symbol=symbol,
        current_price=round(current_price, 6),
        predicted_price_1h=round(predicted_price_1h, 6),
        predicted_price_24h=round(predicted_price_24h, 6),
        predicted_price_7d=round(predicted_price_7d, 6),
        confidence_1h=round(confidence_1h, 2),
        confidence_24h=round(confidence_24h, 2),
        confidence_7d=round(confidence_7d, 2),
        trend=trend,
        key_factors=key_factors[:5],
        timestamp=signal.created_at or datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Shared data helpers
# ---------------------------------------------------------------------------


def fetch_distinct_strategies(session) -> List[str]:
    strategies: set[str] = set()
    results = (
        session.query(TradingSettings.strategy_config)
        .filter(TradingSettings.strategy_config.isnot(None))
        .all()
    )
    for (config,) in results:
        if not config:
            continue
        for key in ("strategy", "strategy_name", "name"):
            value = config.get(key)
            if value:
                strategies.add(str(value))

    if not strategies:
        strategies.update(DEFAULT_STRATEGIES)

    return sorted(strategies)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TradingBot(BaseModel):
    id: str
    name: str
    strategy: str
    status: str
    created_at: datetime
    last_updated: datetime
    performance: Dict[str, float]
    settings: Dict[str, Any]


class BotPerformance(BaseModel):
    bot_id: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: float
    total_pnl_percentage: float
    win_rate: float
    average_win: float
    average_loss: float
    profit_factor: float
    max_drawdown: float
    timestamp: datetime


class AIAnalysis(BaseModel):
    symbol: str
    analysis_type: str
    recommendation: str
    confidence: float
    price_target: Optional[float]
    risk_level: str
    summary: str
    detailed_analysis: str
    timestamp: datetime


class MarketPrediction(BaseModel):
    symbol: str
    current_price: float
    predicted_price_1h: float
    predicted_price_24h: float
    predicted_price_7d: float
    confidence_1h: float
    confidence_24h: float
    confidence_7d: float
    trend: str
    key_factors: List[str]
    timestamp: datetime


class BotSettings(BaseModel):
    name: Optional[str]
    strategy: Optional[str]
    risk_level: Optional[str]
    max_position_size: Optional[float]
    stop_loss_percentage: Optional[float]
    take_profit_percentage: Optional[float]
    trading_pairs: Optional[List[str]]
    is_active: Optional[bool]

    @validator("risk_level")
    def validate_risk_level(cls, value):
        if value and value.lower() not in {"low", "medium", "high"}:
            raise ValueError("Risk level must be low, medium, or high")
        return value.lower() if value else value


class AIInsightCreateRequest(BaseModel):
    title: str
    description: str
    insight_type: str = "opportunity"
    priority: str = "medium"
    confidence_score: int = 75
    related_symbols: List[str] = Field(default_factory=list)
    action_required: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    expires_at: Optional[datetime] = None

    @validator("priority")
    def validate_priority(cls, value):
        if value.lower() not in PRIORITY_ORDER:
            raise ValueError("Priority must be low, medium, high, or critical")
        return value.lower()

    @validator("confidence_score")
    def validate_confidence(cls, value):
        if not 0 <= value <= 100:
            raise ValueError("Confidence must be between 0 and 100")
        return value


class AIInsightResponse(BaseModel):
    id: str
    insight_type: str
    title: str
    description: str
    confidence_score: int
    action_required: Optional[str]
    priority: str
    related_symbols: List[str]
    metadata: Dict[str, Any]
    is_read: bool
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class TradingSignalResponse(BaseModel):
    id: str
    symbol: str
    signal_type: str
    strength: int
    price_target: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    confidence_score: int
    ai_analysis: Optional[str]
    source: str
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime


class MarketAlertResponse(BaseModel):
    id: str
    alert_type: str
    symbol: str
    title: str
    description: str
    trigger_price: Optional[float]
    current_price: Optional[float]
    target_price: Optional[float]
    percentage_change: Optional[float]
    is_triggered: bool
    is_read: bool
    priority: str
    metadata: Dict[str, Any]
    created_at: datetime
    triggered_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Routes - Trading bots
# ---------------------------------------------------------------------------


@ai_router.get("/bots", response_model=List[TradingBot])
async def get_trading_bots(token_data: dict = Depends(verify_token)):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            bots = (
                db.session.query(TradingSettings)
                .filter(TradingSettings.user_id == user_uuid)
                .order_by(TradingSettings.created_at.asc())
                .all()
            )

            logger.info("Trading bots retrieved", extra={"user_id": str(user_uuid), "count": len(bots)})
            return [build_bot_payload(db.session, settings) for settings in bots]
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get bots error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve trading bots") from exc


@ai_router.get("/bots/{bot_id}", response_model=TradingBot)
async def get_bot(bot_id: str, token_data: dict = Depends(verify_token)):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            target_id = parse_bot_uuid(bot_id)
            settings = (
                db.session.query(TradingSettings)
                .filter(TradingSettings.id == target_id)
                .filter(TradingSettings.user_id == user_uuid)
                .first()
            )

            if not settings:
                raise HTTPException(status_code=404, detail="Bot not found")

            return build_bot_payload(db.session, settings)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get bot error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve bot") from exc


@ai_router.post("/bots", response_model=TradingBot)
async def create_bot(settings: BotSettings, token_data: dict = Depends(verify_token)):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            config = {
                "name": settings.name or settings.strategy or "Automated Strategy",
                "strategy": settings.strategy or "custom",
                "risk_level_label": settings.risk_level or "medium",
            }

            new_bot = TradingSettings(
                user_id=user_uuid,
                exchange="binance",
                is_trading_enabled=bool(settings.is_active),
                risk_level=RISK_LEVEL_LABEL_TO_SCORE.get(settings.risk_level or "medium", 3),
                max_position_size=to_decimal(settings.max_position_size),
                stop_loss_percentage=to_decimal(settings.stop_loss_percentage),
                take_profit_percentage=to_decimal(settings.take_profit_percentage),
                preferred_pairs=settings.trading_pairs or [],
                strategy_config=config,
                updated_at=datetime.utcnow(),
            )

            db.session.add(new_bot)
            db.session.commit()
            db.session.refresh(new_bot)

            logger.info("Bot created", extra={"user_id": str(user_uuid), "bot_id": str(new_bot.id)})
            return build_bot_payload(db.session, new_bot)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Create bot error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create bot") from exc


@ai_router.put("/bots/{bot_id}", response_model=TradingBot)
async def update_bot(bot_id: str, settings: BotSettings, token_data: dict = Depends(verify_token)):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            target_id = parse_bot_uuid(bot_id)
            bot = (
                db.session.query(TradingSettings)
                .filter(TradingSettings.id == target_id)
                .filter(TradingSettings.user_id == user_uuid)
                .first()
            )

            if not bot:
                raise HTTPException(status_code=404, detail="Bot not found")

            if settings.is_active is not None:
                bot.is_trading_enabled = bool(settings.is_active)
            if settings.max_position_size is not None:
                bot.max_position_size = to_decimal(settings.max_position_size)
            if settings.stop_loss_percentage is not None:
                bot.stop_loss_percentage = to_decimal(settings.stop_loss_percentage)
            if settings.take_profit_percentage is not None:
                bot.take_profit_percentage = to_decimal(settings.take_profit_percentage)
            if settings.trading_pairs is not None:
                bot.preferred_pairs = settings.trading_pairs
            if settings.risk_level is not None:
                bot.risk_level = RISK_LEVEL_LABEL_TO_SCORE.get(settings.risk_level, bot.risk_level)

            config = bot.strategy_config or {}
            if settings.name is not None:
                config["name"] = settings.name
            if settings.strategy is not None:
                config["strategy"] = settings.strategy
            if settings.risk_level is not None:
                config["risk_level_label"] = settings.risk_level
            bot.strategy_config = config
            bot.updated_at = datetime.utcnow()

            db.session.commit()
            db.session.refresh(bot)

            logger.info("Bot updated", extra={"user_id": str(user_uuid), "bot_id": str(bot.id)})
            return build_bot_payload(db.session, bot)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Update bot error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update bot") from exc


@ai_router.delete("/bots/{bot_id}")
async def delete_bot(bot_id: str, token_data: dict = Depends(verify_token)):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            target_id = parse_bot_uuid(bot_id)
            bot = (
                db.session.query(TradingSettings)
                .filter(TradingSettings.id == target_id)
                .filter(TradingSettings.user_id == user_uuid)
                .first()
            )

            if not bot:
                raise HTTPException(status_code=404, detail="Bot not found")

            db.session.delete(bot)
            db.session.commit()

            logger.info("Bot deleted", extra={"user_id": str(user_uuid), "bot_id": bot_id})
            return {
                "message": f"Bot {bot_id} deleted successfully",
                "bot_id": bot_id,
                "timestamp": datetime.utcnow(),
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Delete bot error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to delete bot") from exc


@ai_router.post("/bots/{bot_id}/start")
async def start_bot(bot_id: str, token_data: dict = Depends(verify_token)):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            target_id = parse_bot_uuid(bot_id)
            bot = (
                db.session.query(TradingSettings)
                .filter(TradingSettings.id == target_id)
                .filter(TradingSettings.user_id == user_uuid)
                .first()
            )

            if not bot:
                raise HTTPException(status_code=404, detail="Bot not found")

            bot.is_trading_enabled = True
            bot.updated_at = datetime.utcnow()
            db.session.commit()

            logger.info("Bot started", extra={"user_id": str(user_uuid), "bot_id": bot_id})
            return {
                "message": f"Bot {bot_id} started successfully",
                "bot_id": bot_id,
                "status": "active",
                "timestamp": datetime.utcnow(),
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Start bot error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to start bot") from exc


@ai_router.post("/bots/{bot_id}/stop")
async def stop_bot(bot_id: str, token_data: dict = Depends(verify_token)):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            target_id = parse_bot_uuid(bot_id)
            bot = (
                db.session.query(TradingSettings)
                .filter(TradingSettings.id == target_id)
                .filter(TradingSettings.user_id == user_uuid)
                .first()
            )

            if not bot:
                raise HTTPException(status_code=404, detail="Bot not found")

            bot.is_trading_enabled = False
            bot.updated_at = datetime.utcnow()
            db.session.commit()

            logger.info("Bot stopped", extra={"user_id": str(user_uuid), "bot_id": bot_id})
            return {
                "message": f"Bot {bot_id} stopped successfully",
                "bot_id": bot_id,
                "status": "inactive",
                "timestamp": datetime.utcnow(),
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Stop bot error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to stop bot") from exc


@ai_router.get("/bots/{bot_id}/performance", response_model=BotPerformance)
async def get_bot_performance(bot_id: str, token_data: dict = Depends(verify_token)):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            target_id = parse_bot_uuid(bot_id)
            bot = (
                db.session.query(TradingSettings)
                .filter(TradingSettings.id == target_id)
                .filter(TradingSettings.user_id == user_uuid)
                .first()
            )

            if not bot:
                raise HTTPException(status_code=404, detail="Bot not found")

            name, strategy = extract_strategy_name(bot)
            trades = collect_user_trades(db.session, user_uuid, strategy)
            _, details = calculate_performance_metrics(trades)

            logger.info(
                "Bot performance retrieved",
                extra={"user_id": str(user_uuid), "bot_id": bot_id, "trades": details["total_trades"]},
            )

            return BotPerformance(
                bot_id=bot_id,
                total_trades=details["total_trades"],
                winning_trades=details["winning_trades"],
                losing_trades=details["losing_trades"],
                total_pnl=round(details["total_pnl"], 2),
                total_pnl_percentage=round(details["total_pnl_percentage"], 2),
                win_rate=round(details["win_rate"], 2),
                average_win=round(details["average_win"], 2),
                average_loss=round(details["average_loss"], 2),
                profit_factor=round(details["profit_factor"], 2),
                max_drawdown=round(details["max_drawdown"], 2),
                timestamp=datetime.utcnow(),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Bot performance error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve bot performance") from exc


# ---------------------------------------------------------------------------
# Routes - AI insights, signals, alerts
# ---------------------------------------------------------------------------


@ai_router.get("/insights", response_model=List[AIInsightResponse])
async def list_ai_insights(token_data: dict = Depends(verify_token)):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            now = datetime.utcnow()
            priority_rank = case(
                (AIInsight.priority == "critical", 4),
                (AIInsight.priority == "high", 3),
                (AIInsight.priority == "medium", 2),
                else_=1,
            )

            insights = (
                db.session.query(AIInsight)
                .filter(AIInsight.user_id == user_uuid)
                .filter(or_(AIInsight.expires_at.is_(None), AIInsight.expires_at > now))
                .order_by(priority_rank.desc(), AIInsight.created_at.desc())
                .all()
            )

            logger.info("AI insights retrieved", extra={"user_id": str(user_uuid), "count": len(insights)})
            return [serialize_ai_insight(insight) for insight in insights]
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("List insights error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve AI insights") from exc


@ai_router.post("/insights", response_model=AIInsightResponse)
async def create_ai_insight(
    payload: AIInsightCreateRequest,
    token_data: dict = Depends(verify_token),
):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            insight = AIInsight(
                user_id=user_uuid,
                insight_type=payload.insight_type,
                title=payload.title,
                description=payload.description,
                confidence_score=payload.confidence_score,
                action_required=payload.action_required,
                priority=payload.priority,
                related_symbols=payload.related_symbols,
                metadata_payload=payload.metadata,
                expires_at=payload.expires_at,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            db.session.add(insight)
            db.session.commit()
            db.session.refresh(insight)

            logger.info("AI insight created", extra={"user_id": str(user_uuid), "insight_id": str(insight.id)})
            return serialize_ai_insight(insight)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Create insight error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create AI insight") from exc


@ai_router.get("/alerts", response_model=List[MarketAlertResponse])
async def list_market_alerts(token_data: dict = Depends(verify_token)):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            alerts = (
                db.session.query(MarketAlert)
                .filter(
                    or_(
                        MarketAlert.user_id == user_uuid,
                        MarketAlert.user_id.is_(None),
                    )
                )
                .order_by(MarketAlert.created_at.desc())
                .all()
            )

            logger.info("Market alerts retrieved", extra={"user_id": str(user_uuid), "count": len(alerts)})
            return [serialize_market_alert(alert) for alert in alerts]
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("List alerts error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve market alerts") from exc


@ai_router.get("/signals/{symbol}", response_model=List[TradingSignalResponse])
async def list_trading_signals(symbol: str, token_data: dict = Depends(verify_token)):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            now = datetime.utcnow()
            signals = (
                db.session.query(TradingSignal)
                .filter(TradingSignal.symbol == symbol)
                .filter(TradingSignal.is_active.is_(True))
                .filter(or_(TradingSignal.user_id.is_(None), TradingSignal.user_id == user_uuid))
                .filter(or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now))
                .order_by(TradingSignal.confidence_score.desc(), TradingSignal.created_at.desc())
                .all()
            )

            logger.info("Trading signals retrieved", extra={"user_id": str(user_uuid), "symbol": symbol, "count": len(signals)})
            return [serialize_trading_signal(signal) for signal in signals]
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("List signals error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve trading signals") from exc


# ---------------------------------------------------------------------------
# Routes - Analysis & predictions (legacy endpoints backed by Supabase data)
# ---------------------------------------------------------------------------


@ai_router.get("/analysis/{symbol}", response_model=AIAnalysis)
async def get_ai_analysis(symbol: str, token_data: dict = Depends(verify_token)):
    try:
        user_uuid = parse_user_uuid(token_data)
        with DatabaseManager() as db:
            now = datetime.utcnow()
            insight = (
                db.session.query(AIInsight)
                .filter(or_(AIInsight.user_id == user_uuid, AIInsight.user_id.is_(None)))
                .filter(
                    or_(
                        AIInsight.related_symbols.contains([symbol]),
                        AIInsight.related_symbols.is_(None),
                    )
                )
                .filter(or_(AIInsight.expires_at.is_(None), AIInsight.expires_at > now))
                .order_by(AIInsight.created_at.desc())
                .first()
            )

            if not insight:
                raise HTTPException(status_code=404, detail="No analysis available")

            recommendation = determine_recommendation(insight)
            risk_level = determine_risk_level(insight)
            price_target = None
            metadata = insight.metadata_payload or {}
            if metadata.get("price_target") is not None:
                try:
                    price_target = float(metadata["price_target"])
                except (TypeError, ValueError):
                    price_target = None

            summary = insight.title
            detailed_analysis = insight.description

            return AIAnalysis(
                symbol=symbol,
                analysis_type=insight.insight_type,
                recommendation=recommendation,
                confidence=float(insight.confidence_score),
                price_target=price_target,
                risk_level=risk_level,
                summary=summary,
                detailed_analysis=detailed_analysis,
                timestamp=insight.created_at or datetime.utcnow(),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("AI analysis error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve AI analysis") from exc


@ai_router.get("/predictions/{symbol}", response_model=MarketPrediction)
async def get_market_prediction(symbol: str, token_data: dict = Depends(verify_token)):
    try:
        parse_user_uuid(token_data)
        with DatabaseManager() as db:
            now = datetime.utcnow()
            signal = (
                db.session.query(TradingSignal)
                .filter(TradingSignal.symbol == symbol)
                .filter(TradingSignal.is_active.is_(True))
                .filter(or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now))
                .order_by(TradingSignal.confidence_score.desc(), TradingSignal.created_at.desc())
                .first()
            )

            if not signal:
                raise HTTPException(status_code=404, detail="No market prediction available")

            return build_prediction_from_signal(db.session, signal, symbol)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Market prediction error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve market prediction") from exc


@ai_router.get("/strategies")
async def get_strategies():
    try:
        with DatabaseManager() as db:
            strategies = fetch_distinct_strategies(db.session)
            return {
                "strategies": strategies,
                "count": len(strategies),
                "timestamp": datetime.utcnow(),
            }
    except Exception as exc:
        logger.exception("Strategies error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve strategies") from exc


@ai_router.get("/health")
async def ai_health_check():
    try:
        with DatabaseManager() as db:
            insight_count = db.session.query(func.count(AIInsight.id)).scalar() or 0
            active_signals = (
                db.session.query(func.count(TradingSignal.id))
                .filter(TradingSignal.is_active.is_(True))
                .scalar()
                or 0
            )
            active_alerts = (
                db.session.query(func.count(MarketAlert.id))
                .filter(MarketAlert.is_triggered.is_(True))
                .scalar()
                or 0
            )

            strategies = fetch_distinct_strategies(db.session)

            return {
                "service": "ai",
                "status": "healthy",
                "timestamp": datetime.utcnow(),
                "metrics": {
                    "insights": insight_count,
                    "active_signals": active_signals,
                    "triggered_alerts": active_alerts,
                },
                "available_strategies": len(strategies),
                "features": [
                    "trading_bots",
                    "ai_analysis",
                    "market_predictions",
                    "bot_performance",
                    "strategy_management",
                    "insights",
                    "signals",
                    "alerts",
                ],
                "version": "1.0.0",
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("AI health check error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to perform AI health check") from exc
