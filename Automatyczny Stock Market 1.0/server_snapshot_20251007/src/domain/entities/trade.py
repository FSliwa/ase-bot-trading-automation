from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    """Order direction."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Supported order types."""

    MARKET = "market"
    LIMIT = "limit"


@dataclass(slots=True)
class TradeRequest:
    """Command object describing an order submission."""

    exchange: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    user_id: Optional[int] = None
    api_key_id: Optional[int] = None

    def validate(self) -> None:
        """Apply basic validation rules before sending to an exchange."""

        if self.order_type is OrderType.LIMIT and (self.price is None or self.price <= 0):
            raise ValueError("Limit orders require a positive price")
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        if not self.symbol:
            raise ValueError("Symbol is required")


@dataclass(slots=True)
class TradeResponse:
    """Summary of an executed or pending order."""

    exchange: str
    symbol: str
    order_id: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    executed_quantity: float = 0.0
    price: Optional[float] = None
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)
    raw: Optional[dict] = None
