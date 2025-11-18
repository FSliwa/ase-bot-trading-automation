"""Portfolio API backed by database state."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from bot.db import DatabaseManager, Fill, Order, PortfolioSnapshot, Position, TradingStats
from .auth_routes import verify_token

portfolio_router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])


class PortfolioSummary(BaseModel):
    total_balance: float
    total_pnl: float
    total_pnl_percentage: float
    available_balance: float
    margin_used: float
    free_margin: float


class PositionResponse(BaseModel):
    id: int
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: float
    pnl: float
    pnl_percentage: float
    margin_used: float
    timestamp: datetime
    stop_loss: Optional[float]
    take_profit: Optional[float]


class Transaction(BaseModel):
    id: int
    symbol: str
    type: str
    amount: float
    price: Optional[float]
    fee: float
    status: str
    timestamp: datetime


class ClosePositionRequest(BaseModel):
    exit_price: Optional[float] = None


def _latest_snapshot(db: DatabaseManager, user_id: Optional[str]) -> Optional[PortfolioSnapshot]:
    query = db.session.query(PortfolioSnapshot)
    if user_id:
        query = query.filter(PortfolioSnapshot.user_id == user_id)
    return query.order_by(PortfolioSnapshot.timestamp.desc()).first()


@portfolio_router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(token_data: dict = Depends(verify_token)) -> PortfolioSummary:
    user_id = token_data.get("sub")
    with DatabaseManager() as db:
        snapshot = _latest_snapshot(db, user_id)
        positions = db.get_open_positions()

        total_unrealized = sum(p.unrealized_pnl for p in positions)
        margin_used = sum(p.margin_used for p in positions)

        if snapshot:
            total_balance = snapshot.total_balance
            available = snapshot.available_balance
        else:
            total_balance = sum((p.current_price or p.entry_price) * p.quantity for p in positions)
            available = max(total_balance - margin_used, 0.0)

        total_pnl = total_unrealized + sum(p.realized_pnl for p in positions)
        base_equity = total_balance - total_pnl if total_balance else 0.0
        pnl_pct = (total_pnl / base_equity * 100) if base_equity else 0.0

        return PortfolioSummary(
            total_balance=round(total_balance, 2),
            total_pnl=round(total_pnl, 2),
            total_pnl_percentage=round(pnl_pct, 2),
            available_balance=round(available, 2),
            margin_used=round(margin_used, 2),
            free_margin=round(max(available - margin_used, 0.0), 2),
        )
def _position_side_label(side: str) -> str:
    return "long" if side.upper() in {"BUY", "LONG"} else "short"


def _position_to_response(position: Position) -> PositionResponse:
    current_price = position.current_price or position.entry_price
    notional = abs(position.quantity * position.entry_price)
    pnl_pct = (position.unrealized_pnl / notional * 100) if notional else 0.0
    return PositionResponse(
        id=position.id,
        symbol=position.symbol,
        side=_position_side_label(position.side),
        size=round(position.quantity, 8),
        entry_price=round(position.entry_price, 8),
        current_price=round(current_price, 8),
        pnl=round(position.unrealized_pnl + position.realized_pnl, 8),
        pnl_percentage=round(pnl_pct, 4),
        margin_used=round(position.margin_used, 8),
        timestamp=position.entry_time,
        stop_loss=position.stop_loss,
        take_profit=position.take_profit,
    )


def _balances_from_snapshot(snapshot: Optional[PortfolioSnapshot]) -> Dict[str, Dict[str, float]]:
    if snapshot and isinstance(snapshot.metadata_payload, dict):
        balances = snapshot.metadata_payload.get("balances")
        if isinstance(balances, dict):
            result: Dict[str, Dict[str, float]] = {}
            for currency, payload in balances.items():
                free = float(payload.get("free", 0.0))
                used = float(payload.get("used", 0.0))
                total = float(payload.get("total", free + used))
                result[currency] = {
                    "free": round(free, 8),
                    "used": round(used, 8),
                    "total": round(total if total else free + used, 8),
                }
            if result:
                return result
    return {}


def _fills_to_transactions(fills: List[Fill]) -> List[Transaction]:
    transactions: List[Transaction] = []
    for fill in fills:
        order_status = fill.order.status if fill.order else "completed"
        status = order_status.lower() if order_status else "completed"
        if status == "filled":
            status = "completed"
        transactions.append(
            Transaction(
                id=fill.id,
                symbol=fill.symbol,
                type=fill.side.lower(),
                amount=round(fill.quantity, 8),
                price=round(fill.price, 8),
                fee=round(fill.fee, 8),
                status=status,
                timestamp=fill.timestamp,
            )
        )
    return transactions


@portfolio_router.get("/positions", response_model=List[PositionResponse])
async def get_positions(token_data: dict = Depends(verify_token)) -> List[PositionResponse]:
    user_id = token_data.get("sub")
    with DatabaseManager() as db:
        query = db.session.query(Position).filter(Position.status == "OPEN")
        if user_id:
            query = query.filter(Position.user_id == user_id)
        positions = query.order_by(Position.entry_time.asc()).all()
        return [_position_to_response(p) for p in positions]


@portfolio_router.get("/transactions", response_model=List[Transaction])
async def get_transactions(
    limit: int = 50,
    offset: int = 0,
    token_data: dict = Depends(verify_token),
) -> List[Transaction]:
    if limit > 200:
        limit = 200
    user_id = token_data.get("sub")
    with DatabaseManager() as db:
        query = (
            db.session.query(Fill)
            .join(Order, Fill.order_id == Order.id)
            .order_by(Fill.timestamp.desc())
        )
        if user_id:
            query = query.filter(Order.user_id == user_id)
        fills = query.offset(offset).limit(limit).all()
        return _fills_to_transactions(fills)


@portfolio_router.get("/balance")
async def get_balance(token_data: dict = Depends(verify_token)) -> Dict[str, object]:
    user_id = token_data.get("sub")
    with DatabaseManager() as db:
        snapshot = _latest_snapshot(db, user_id)
        balances = _balances_from_snapshot(snapshot)
        if not balances:
            query = db.session.query(Position).filter(Position.status == "OPEN")
            if user_id:
                query = query.filter(Position.user_id == user_id)
            positions = query.all()
            total_margin = 0.0
            cash_balance = snapshot.available_balance if snapshot else 0.0
            for position in positions:
                total_margin += position.margin_used
            balances = {
                "USDT": {
                    "free": round(max(cash_balance - total_margin, 0.0), 8),
                    "used": round(total_margin, 8),
                    "total": round(max(cash_balance, total_margin), 8),
                }
            }
        return {"balances": balances, "timestamp": datetime.utcnow()}


@portfolio_router.get("/performance")
async def get_performance(
    period: str = "1d",
    token_data: dict = Depends(verify_token),
) -> Dict[str, object]:
    period_map = {
        "1d": timedelta(days=1),
        "1w": timedelta(weeks=1),
        "1m": timedelta(days=30),
        "3m": timedelta(days=90),
        "1y": timedelta(days=365),
    }
    window = period_map.get(period, period_map["1d"])
    user_id = token_data.get("sub")

    with DatabaseManager() as db:
        since = datetime.utcnow() - window
        query = db.session.query(PortfolioSnapshot).filter(PortfolioSnapshot.timestamp >= since)
        if user_id:
            query = query.filter(PortfolioSnapshot.user_id == user_id)
        snapshots = query.order_by(PortfolioSnapshot.timestamp.asc()).all()

        data_points: List[Dict[str, object]] = []
        previous_value: Optional[float] = None
        returns: List[float] = []

        for snap in snapshots:
            portfolio_value = snap.total_balance
            base_value = portfolio_value - snap.unrealized_pnl
            pnl = snap.unrealized_pnl
            if previous_value:
                returns.append((portfolio_value - previous_value) / previous_value)
            previous_value = portfolio_value
            data_points.append(
                {
                    "timestamp": snap.timestamp,
                    "portfolio_value": round(portfolio_value, 2),
                    "pnl": round(pnl, 2),
                    "pnl_percentage": round((pnl / base_value * 100) if base_value else 0.0, 4),
                }
            )

        if not data_points:
            return {
                "period": period,
                "data": [],
                "metrics": {
                    "total_return": 0.0,
                    "volatility": 0.0,
                    "max_drawdown": 0.0,
                    "sharpe_ratio": 0.0,
                    "win_rate": 0.0,
                },
                "timestamp": datetime.utcnow(),
            }

        first_value = data_points[0]["portfolio_value"]
        last_value = data_points[-1]["portfolio_value"]
        total_return = ((last_value - first_value) / first_value * 100) if first_value else 0.0

        volatility = 0.0
        if returns:
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            volatility = (variance ** 0.5) * (252 ** 0.5) * 100

        peak = data_points[0]["portfolio_value"]
        max_drawdown = 0.0
        for point in data_points:
            value = point["portfolio_value"]
            peak = max(peak, value)
            drawdown = (value - peak) / peak * 100 if peak else 0.0
            max_drawdown = min(max_drawdown, drawdown)

        recent_stats = (
            db.session.query(TradingStats)
            .order_by(TradingStats.date.desc())
            .first()
        )

        sharpe = recent_stats.sharpe_ratio if recent_stats and recent_stats.sharpe_ratio else 0.0
        win_rate = recent_stats.win_rate if recent_stats else 0.0

        return {
            "period": period,
            "data": data_points,
            "metrics": {
                "total_return": round(total_return, 2),
                "volatility": round(volatility, 2),
                "max_drawdown": round(max_drawdown, 2),
                "sharpe_ratio": round(sharpe, 2),
                "win_rate": round(win_rate, 2),
            },
            "timestamp": datetime.utcnow(),
        }


@portfolio_router.post("/positions/{position_id}/close")
async def close_position(
    position_id: int,
    request: Optional[ClosePositionRequest] = None,
    token_data: dict = Depends(verify_token),
):
    user_id = token_data.get("sub")
    with DatabaseManager() as db:
        position = db.session.get(Position, position_id)
        if not position or position.status != "OPEN":
            raise HTTPException(status_code=404, detail="Position not found or already closed")
        if user_id and position.user_id and position.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not permitted to close this position")

        exit_price = None
        if request and request.exit_price:
            exit_price = request.exit_price
        elif position.current_price:
            exit_price = position.current_price
        else:
            exit_price = position.entry_price

        closed = db.close_position(position_id, exit_price)

        return {
            "message": f"Position {position_id} closed successfully",
            "position": _position_to_response(closed),
            "timestamp": datetime.utcnow(),
        }


@portfolio_router.get("/risk-metrics")
async def get_risk_metrics(token_data: dict = Depends(verify_token)) -> Dict[str, object]:
    user_id = token_data.get("sub")
    lookback = timedelta(days=60)
    with DatabaseManager() as db:
        since = datetime.utcnow() - lookback
        snapshot_query = db.session.query(PortfolioSnapshot).filter(PortfolioSnapshot.timestamp >= since)
        if user_id:
            snapshot_query = snapshot_query.filter(PortfolioSnapshot.user_id == user_id)
        snapshots = snapshot_query.order_by(PortfolioSnapshot.timestamp.asc()).all()

        returns: List[float] = []
        max_drawdown = 0.0
        annualized_vol = 0.0
        value_at_risk = 0.0
        correlation_btc = None
        alpha = None
        beta = None
        sortino = None
        portfolio_value = 0.0

        if snapshots:
            running_peak = snapshots[0].total_balance
            previous_value = snapshots[0].total_balance
            portfolio_value = snapshots[-1].total_balance
            for snap in snapshots[1:]:
                if previous_value:
                    returns.append((snap.total_balance - previous_value) / previous_value)
                previous_value = snap.total_balance
                running_peak = max(running_peak, snap.total_balance)
                drawdown = (snap.total_balance - running_peak) / running_peak * 100 if running_peak else 0.0
                max_drawdown = min(max_drawdown, drawdown)

            if returns:
                mean_return = sum(returns) / len(returns)
                variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
                daily_vol = variance ** 0.5
                annualized_vol = daily_vol * (252 ** 0.5) * 100
                value_at_risk = 1.65 * daily_vol * portfolio_value

        snapshot_meta = (
            snapshots[-1].metadata_payload
            if snapshots and isinstance(snapshots[-1].metadata_payload, dict)
            else {}
        )
        if isinstance(snapshot_meta, dict):
            risk_meta = snapshot_meta.get("risk_metrics", {})
            if isinstance(risk_meta, dict):
                correlation_btc = risk_meta.get("correlation_btc")
                alpha = risk_meta.get("alpha")
                beta = risk_meta.get("beta")
                sortino = risk_meta.get("sortino_ratio")

        recent_stats = (
            db.session.query(TradingStats)
            .order_by(TradingStats.date.desc())
            .first()
        )
        sharpe = recent_stats.sharpe_ratio if recent_stats and recent_stats.sharpe_ratio else 0.0
        win_rate = recent_stats.win_rate if recent_stats else 0.0

        risk_level = "Medium"
        if max_drawdown < -20:
            risk_level = "High"
        elif max_drawdown > -10:
            risk_level = "Low"

        risk_score = 5.0
        if annualized_vol:
            risk_score = max(0.0, min(10.0, annualized_vol / 10.0))

        return {
            "value_at_risk": round(value_at_risk, 2),
            "max_drawdown": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2) if sortino is not None else None,
            "volatility": round(annualized_vol, 2),
            "beta": round(beta, 2) if beta is not None else None,
            "alpha": round(alpha, 2) if alpha is not None else None,
            "correlation_btc": round(correlation_btc, 2) if correlation_btc is not None else None,
            "risk_score": round(risk_score, 2),
            "risk_level": risk_level,
            "win_rate": round(win_rate, 2),
            "timestamp": datetime.utcnow(),
        }

@portfolio_router.get("/health")
async def portfolio_health_check():
    """Health check for portfolio service"""
    return {
        "service": "portfolio",
        "status": "healthy",
        "timestamp": datetime.now(),
        "features": [
            "portfolio_summary",
            "positions",
            "transactions",
            "balance",
            "performance",
            "close_positions"
        ],
        "version": "1.0.0"
    }
