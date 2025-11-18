from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Position:
    symbol: str
    side: str  # buy -> long, sell -> short
    quantity: float
    entry_price: float
    leverage: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass
class OrderFill:
    symbol: str
    side: str
    quantity: float
    price: float
    order_type: str
    tif: Optional[str]
    reduce_only: bool


class PaperBroker:
    """In-memory simulator of basic order execution and positions."""

    def __init__(self) -> None:
        self.positions: Dict[str, Position] = {}
        self.fills: List[OrderFill] = []

    def _apply_fill(self, fill: OrderFill) -> None:
        pos = self.positions.get(fill.symbol)
        if pos is None:
            if fill.reduce_only:
                return  # nothing to reduce
            # open new position
            self.positions[fill.symbol] = Position(
                symbol=fill.symbol,
                side=fill.side,
                quantity=fill.quantity,
                entry_price=fill.price,
                leverage=1.0,
            )
            return

        # If same side, adjust position size and average price
        if pos.side == fill.side and not fill.reduce_only:
            new_qty = pos.quantity + fill.quantity
            pos.entry_price = (pos.entry_price * pos.quantity + fill.price * fill.quantity) / new_qty
            pos.quantity = new_qty
            return

        # Opposite side or reduce-only: reduce/close
        if fill.quantity >= pos.quantity:
            # position fully closed
            del self.positions[fill.symbol]
        else:
            pos.quantity -= fill.quantity

    def place_order(
        self,
        *,
        side: str,
        symbol: str,
        order_type: str,
        quantity: float,
        market_price: Optional[float] = None,
        price: Optional[float] = None,
        tif: Optional[str] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reduce_only: bool = False,
        leverage: Optional[float] = None,
    ) -> OrderFill:
        # Simple execution model
        exec_price: float
        if order_type == "market":
            if market_price is None:
                raise ValueError("market_price is required for market orders in paper trading")
            exec_price = float(market_price)
        elif order_type == "limit":
            if price is None:
                raise ValueError("price is required for limit orders in paper trading")
            # Assume immediate fill at limit price for MVP
            exec_price = float(price)
        else:
            raise ValueError(f"Unsupported order_type: {order_type}")

        fill = OrderFill(
            symbol=symbol,
            side=side,
            quantity=float(quantity),
            price=exec_price,
            order_type=order_type,
            tif=tif,
            reduce_only=reduce_only,
        )
        self._apply_fill(fill)

        # Update SL/TP/leverage on resulting position
        pos = self.positions.get(symbol)
        if pos is not None:
            if stop_loss is not None:
                pos.stop_loss = stop_loss
            if take_profit is not None:
                pos.take_profit = take_profit
            if leverage is not None:
                pos.leverage = leverage

        self.fills.append(fill)
        return fill

    def close_position(self, *, symbol: str) -> bool:
        if symbol in self.positions:
            del self.positions[symbol]
            return True
        return False

    def close_all_positions(self) -> int:
        count = len(self.positions)
        self.positions.clear()
        return count

    def get_positions(self) -> Dict[str, Position]:
        return dict(self.positions)

    def get_fills(self) -> List[OrderFill]:
        return list(self.fills)


