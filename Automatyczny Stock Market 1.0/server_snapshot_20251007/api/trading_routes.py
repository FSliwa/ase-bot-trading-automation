"""Trading API routes backed by Supabase PostgreSQL."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy import func

from .auth_routes import verify_token
from bot.database import DatabaseManager
from bot.models import MarketData as MarketDataModel
from bot.models import Trade, TradingSettings

logger = logging.getLogger(__name__)

# Create router
trading_router = APIRouter(prefix="/api/trading", tags=["Trading"])

# Pydantic Models
class MarketDataResponse(BaseModel):
    symbol: str
    price: float
    change: float
    change_percentage: float
    volume: float
    high_24h: float
    low_24h: float
    timestamp: datetime

class OrderRequest(BaseModel):
    symbol: str
    type: str  # "market", "limit", "stop"
    side: str  # "buy", "sell"
    amount: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    exchange: Optional[str] = "binance"
    strategy_name: Optional[str] = None
    notes: Optional[str] = None
    
    @validator('type')
    def validate_order_type(cls, v):
        if v not in ['market', 'limit', 'stop']:
            raise ValueError('Order type must be market, limit, or stop')
        return v
    
    @validator('side')
    def validate_side(cls, v):
        if v not in ['buy', 'sell']:
            raise ValueError('Side must be buy or sell')
        return v

    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be greater than zero')
        return v

    @validator('price')
    def validate_price(cls, v, values):
        if values.get('type') in ('limit', 'stop') and v is None:
            raise ValueError('Price required for limit and stop orders')
        if v is not None and v <= 0:
            raise ValueError('Price must be greater than zero')
        return v

class OrderResponse(BaseModel):
    id: str
    symbol: str
    type: str
    side: str
    amount: float
    price: Optional[float]
    filled: float
    remaining: float
    status: str  # "pending", "filled", "partially_filled", "cancelled"
    timestamp: datetime
    fee: float

class OrderBookResponse(BaseModel):
    symbol: str
    bids: List[List[float]]  # [price, amount]
    asks: List[List[float]]  # [price, amount]
    timestamp: datetime

def decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    """Convert Decimal values to float for JSON serialization."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def parse_user_id(token_data: dict) -> uuid.UUID:
    """Extract and validate user UUID from token data."""
    try:
        return uuid.UUID(str(token_data["sub"]))
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid authentication token")


def get_available_symbols(session) -> List[str]:
    """Return distinct symbols from market data or user trading settings."""
    symbols = [
        row[0]
        for row in session.query(MarketDataModel.symbol)
        .group_by(MarketDataModel.symbol)
        .order_by(MarketDataModel.symbol)
        .all()
    ]

    if symbols:
        return symbols

    preferred_pairs = set()
    for (pairs,) in session.query(TradingSettings.preferred_pairs).filter(TradingSettings.preferred_pairs.isnot(None)).all():
        if pairs:
            preferred_pairs.update(pairs)

    if preferred_pairs:
        return sorted(preferred_pairs)

    logger.warning("No trading symbols found, using fallback defaults")
    return ["BTC/USDT", "ETH/USDT", "ADA/USDT", "SOL/USDT", "DOT/USDT"]


def fetch_latest_market_data(session, symbol: Optional[str] = None) -> List[MarketDataModel]:
    """Fetch the most recent market data per symbol."""
    subquery = (
        session.query(
            MarketDataModel.symbol,
            func.max(MarketDataModel.timestamp).label("latest_ts"),
        )
        .group_by(MarketDataModel.symbol)
        .subquery()
    )

    query = session.query(MarketDataModel).join(
        subquery,
        (MarketDataModel.symbol == subquery.c.symbol)
        & (MarketDataModel.timestamp == subquery.c.latest_ts),
    )

    if symbol:
        query = query.filter(MarketDataModel.symbol == symbol)

    return query.order_by(MarketDataModel.symbol).all()


def convert_market_data(record: MarketDataModel) -> MarketDataResponse:
    """Convert ORM market data record to API response."""
    price = decimal_to_float(record.price) or 0.0
    change_abs = decimal_to_float(record.change_24h) or 0.0
    volume = decimal_to_float(record.volume_24h) or 0.0

    base_price = price - change_abs if price else 0.0
    change_pct = 0.0
    if price and base_price:
        try:
            change_pct = (change_abs / base_price) * 100
        except ZeroDivisionError:
            change_pct = 0.0

    high = price * 1.02 if price else 0.0
    low = price * 0.98 if price else 0.0

    return MarketDataResponse(
        symbol=record.symbol,
        price=round(price, 6),
        change=round(change_abs, 6),
        change_percentage=round(change_pct, 4),
        volume=round(volume, 6),
        high_24h=round(high, 6),
        low_24h=round(low, 6),
        timestamp=record.timestamp or datetime.utcnow(),
    )


def get_latest_price(session, symbol: str) -> Optional[float]:
    """Return the most recent price for a symbol."""
    record = (
        session.query(MarketDataModel)
        .filter(MarketDataModel.symbol == symbol)
        .order_by(MarketDataModel.timestamp.desc())
        .first()
    )
    return decimal_to_float(record.price) if record and record.price else None


def serialize_trade(trade: Trade) -> dict:
    """Convert Trade ORM object to API response payload."""
    metadata = {}
    if trade.notes:
        try:
            metadata = json.loads(trade.notes)
        except json.JSONDecodeError:
            metadata = {}

    amount = decimal_to_float(trade.amount) or 0.0
    price = decimal_to_float(trade.price)
    filled = amount if (trade.status or "").lower() in {"filled", "executed", "closed"} else 0.0
    remaining = max(amount - filled, 0.0)

    return OrderResponse(
        id=str(trade.id),
        symbol=trade.symbol,
        type=metadata.get("order_type", "market"),
        side=(trade.trade_type or "buy").lower(),
        amount=amount,
        price=price,
        filled=filled,
        remaining=remaining,
        status=(trade.status or "pending").lower(),
        timestamp=trade.executed_at or trade.created_at,
        fee=decimal_to_float(trade.fee) or 0.0,
    ).dict()


def build_order_book(symbol: str, price: float) -> OrderBookResponse:
    """Generate order book bands around the latest price."""
    if price <= 0:
        price = 1.0

    bids: List[List[float]] = []
    asks: List[List[float]] = []

    for i in range(10):
        adjustment = 0.001 * (i + 1)
        size = round(max(0.1, 5 - i * 0.3), 6)
        bids.append([round(price * (1 - adjustment), 6), size])
        asks.append([round(price * (1 + adjustment), 6), size])

    return OrderBookResponse(
        symbol=symbol,
        bids=bids,
        asks=asks,
        timestamp=datetime.utcnow(),
    )

# Routes
@trading_router.get("/market-data", response_model=List[MarketDataResponse])
async def get_market_data():
    """Return latest market data snapshots for all symbols."""
    try:
        with DatabaseManager() as db:
            records = fetch_latest_market_data(db.session)
            if not records:
                raise HTTPException(status_code=404, detail="Market data not available")

            data = [convert_market_data(record).dict() for record in records]

        logger.info(f"Market data retrieved from Supabase: {len(data)} symbols")
        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Market data error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve market data")

@trading_router.get("/market-data/{symbol}", response_model=MarketDataResponse)
async def get_symbol_market_data(symbol: str):
    """Get latest market data for a specific symbol."""
    try:
        with DatabaseManager() as db:
            symbols = get_available_symbols(db.session)
            if symbol not in symbols:
                raise HTTPException(status_code=404, detail="Symbol not found")

            records = fetch_latest_market_data(db.session, symbol=symbol)
            if not records:
                raise HTTPException(status_code=404, detail="Market data not available")

            response = convert_market_data(records[0]).dict()

        logger.info(f"Market data retrieved for symbol: {symbol}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Symbol market data error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve symbol data")

@trading_router.get("/symbols")
async def get_trading_symbols():
    """Get list of available trading symbols"""
    try:
        with DatabaseManager() as db:
            symbols = get_available_symbols(db.session)

        return {
            "symbols": symbols,
            "count": len(symbols),
            "timestamp": datetime.utcnow()
        }

    except Exception as e:
        logger.error(f"Symbols error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve symbols")

@trading_router.post("/orders", response_model=OrderResponse)
async def create_order(
    order_request: OrderRequest,
    token_data: dict = Depends(verify_token)
):
    """Create a new trading order"""
    try:
        user_uuid = parse_user_id(token_data)

        with DatabaseManager() as db:
            symbols = get_available_symbols(db.session)
            if order_request.symbol not in symbols:
                raise HTTPException(status_code=400, detail="Invalid symbol")

            execution_price = order_request.price
            status = "pending"
            executed_at = None

            if order_request.type == "market":
                latest_price = get_latest_price(db.session, order_request.symbol)
                if latest_price is None and execution_price is None:
                    raise HTTPException(status_code=400, detail="Market price unavailable")
                execution_price = execution_price or latest_price
                status = "filled"
                executed_at = datetime.utcnow()

            amount_dec = Decimal(str(order_request.amount))
            price_dec = Decimal(str(execution_price)) if execution_price is not None else None
            fee = None
            if status == "filled" and price_dec is not None:
                fee = (price_dec * amount_dec * Decimal("0.001")).quantize(Decimal("0.00000001"))

            trade = Trade(
                user_id=user_uuid,
                exchange=order_request.exchange or "binance",
                symbol=order_request.symbol,
                trade_type=order_request.side.lower(),
                amount=amount_dec,
                price=price_dec,
                fee=fee,
                status=status,
                fee_currency="USDT",
                strategy_name=order_request.strategy_name,
                notes=json.dumps({
                    "order_type": order_request.type,
                    "stop_price": order_request.stop_price,
                    "notes": order_request.notes,
                }),
                executed_at=executed_at,
            )

            db.session.add(trade)
            db.session.commit()
            db.session.refresh(trade)

        logger.info(f"Order created for user {user_uuid}: {trade.id}")
        return serialize_trade(trade)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create order error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create order")

@trading_router.get("/orders", response_model=List[OrderResponse])
async def get_order_history(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    token_data: dict = Depends(verify_token)
):
    """Get user order history with optional filters"""
    try:
        user_uuid = parse_user_id(token_data)

        with DatabaseManager() as db:
            query = db.session.query(Trade).filter(Trade.user_id == user_uuid)

            if status:
                query = query.filter(Trade.status == status.lower())

            if symbol:
                query = query.filter(Trade.symbol == symbol)

            trades = (
                query
                .order_by(Trade.created_at.desc())
                .offset(offset)
                .limit(min(limit, 100))
                .all()
            )

        logger.info(f"Order history retrieved for user {user_uuid}: {len(trades)} records")
        return [serialize_trade(trade) for trade in trades]

    except Exception as e:
        logger.error(f"Order history error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve order history")

@trading_router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    token_data: dict = Depends(verify_token)
):
    """Get specific order details"""
    try:
        user_uuid = parse_user_id(token_data)

        with DatabaseManager() as db:
            trade = (
                db.session.query(Trade)
                .filter(Trade.id == order_id, Trade.user_id == user_uuid)
                .first()
            )

            if not trade:
                raise HTTPException(status_code=404, detail="Order not found")

        logger.info(f"Order details retrieved for user {user_uuid}, order_id: {order_id}")
        return serialize_trade(trade)

    except Exception as e:
        logger.error(f"Get order error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve order")

@trading_router.delete("/orders/{order_id}")
async def cancel_order(
    order_id: str,
    token_data: dict = Depends(verify_token)
):
    """Cancel a pending order"""
    try:
        user_uuid = parse_user_id(token_data)

        with DatabaseManager() as db:
            trade = (
                db.session.query(Trade)
                .filter(Trade.id == order_id, Trade.user_id == user_uuid)
                .first()
            )

            if not trade:
                raise HTTPException(status_code=404, detail="Order not found")

            if (trade.status or "").lower() == "cancelled":
                return {
                    "message": f"Order {order_id} already cancelled",
                    "order_id": order_id,
                    "status": trade.status,
                    "timestamp": datetime.utcnow()
                }

            trade.status = "cancelled"
            trade.updated_at = datetime.utcnow()
            db.session.commit()

        logger.info(f"Order cancelled for user {user_uuid}, order_id: {order_id}")

        return {
            "message": f"Order {order_id} cancelled successfully",
            "order_id": order_id,
            "status": "cancelled",
            "timestamp": datetime.utcnow()
        }

    except Exception as e:
        logger.error(f"Cancel order error: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel order")

@trading_router.get("/orderbook/{symbol}", response_model=OrderBookResponse)
async def get_order_book(symbol: str):
    """Get order book for a symbol"""
    try:
        with DatabaseManager() as db:
            symbols = get_available_symbols(db.session)
            if symbol not in symbols:
                raise HTTPException(status_code=404, detail="Symbol not found")

            price = get_latest_price(db.session, symbol) or 0.0

        order_book = build_order_book(symbol, price)
        logger.info(f"Order book generated for symbol: {symbol}")
        return order_book.dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Order book error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve order book")

@trading_router.get("/price/{symbol}")
async def get_current_price(symbol: str):
    """Get current price for a symbol"""
    try:
        with DatabaseManager() as db:
            symbols = get_available_symbols(db.session)
            if symbol not in symbols:
                raise HTTPException(status_code=404, detail="Symbol not found")

            price = get_latest_price(db.session, symbol)
            if price is None:
                raise HTTPException(status_code=404, detail="Price data not available")

        return {
            "symbol": symbol,
            "price": price,
            "timestamp": datetime.utcnow()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Price error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve price")

@trading_router.get("/health")
async def trading_health_check():
    """Health check for trading service"""
    try:
        with DatabaseManager() as db:
            symbol_count = len(get_available_symbols(db.session))
            total_trades = db.session.query(func.count(Trade.id)).scalar() or 0

        return {
            "service": "trading",
            "status": "healthy",
            "timestamp": datetime.utcnow(),
            "available_symbols": symbol_count,
            "total_trades": total_trades,
            "features": [
                "market_data",
                "order_management",
                "order_book",
                "price_feeds",
                "order_history"
            ],
            "version": "2.0.0"
        }
    except Exception as e:
        logger.error(f"Trading health check failed: {e}")
        return {
            "service": "trading",
            "status": "degraded",
            "timestamp": datetime.utcnow(),
            "error": str(e),
            "version": "2.0.0"
        }
