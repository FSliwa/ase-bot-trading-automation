from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


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

    def check_sltp_triggers(self, market_prices: Dict[str, float]) -> List[Tuple[str, str, float]]:
        """
        Check if any position's SL/TP has been triggered based on current market prices.
        Returns a list of (symbol, trigger_type, trigger_price) for triggered positions.
        """
        triggered = []
        positions_to_close = []
        
        for symbol, pos in self.positions.items():
            if symbol not in market_prices:
                continue
                
            current_price = market_prices[symbol]
            
            if pos.side == "buy":  # Long position
                # Stop Loss - price fell below SL
                if pos.stop_loss and current_price <= pos.stop_loss:
                    logger.info(f"🛑 SL triggered for {symbol}: Price {current_price} <= SL {pos.stop_loss}")
                    triggered.append((symbol, "stop_loss", pos.stop_loss))
                    positions_to_close.append(symbol)
                # Take Profit - price rose above TP
                elif pos.take_profit and current_price >= pos.take_profit:
                    logger.info(f"✅ TP triggered for {symbol}: Price {current_price} >= TP {pos.take_profit}")
                    triggered.append((symbol, "take_profit", pos.take_profit))
                    positions_to_close.append(symbol)
                    
            elif pos.side == "sell":  # Short position
                # Stop Loss - price rose above SL
                if pos.stop_loss and current_price >= pos.stop_loss:
                    logger.info(f"🛑 SL triggered for {symbol}: Price {current_price} >= SL {pos.stop_loss}")
                    triggered.append((symbol, "stop_loss", pos.stop_loss))
                    positions_to_close.append(symbol)
                # Take Profit - price fell below TP
                elif pos.take_profit and current_price <= pos.take_profit:
                    logger.info(f"✅ TP triggered for {symbol}: Price {current_price} <= TP {pos.take_profit}")
                    triggered.append((symbol, "take_profit", pos.take_profit))
                    positions_to_close.append(symbol)
        
        # Close triggered positions
        for symbol in positions_to_close:
            self.close_position(symbol=symbol)
            
        return triggered

    def simulate_market_tick(self, market_prices: Dict[str, float]) -> List[Tuple[str, str, float]]:
        """
        Simulate a market tick - check SL/TP triggers.
        Call this method periodically with current market prices to simulate SL/TP execution.
        """
        return self.check_sltp_triggers(market_prices)

    # ===== P3-1: ASYNC WRAPPERS FOR COMPATIBILITY WITH LIVE BROKER =====
    # These async methods provide a unified interface regardless of broker type
    
    async def async_place_order(
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
        """Async wrapper for place_order for compatibility with LiveBroker."""
        return self.place_order(
            side=side,
            symbol=symbol,
            order_type=order_type,
            quantity=quantity,
            market_price=market_price,
            price=price,
            tif=tif,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reduce_only=reduce_only,
            leverage=leverage,
        )
    
    async def async_close_position(self, *, symbol: str) -> bool:
        """Async wrapper for close_position for compatibility with LiveBroker."""
        return self.close_position(symbol=symbol)
    
    async def async_close_all_positions(self) -> int:
        """Async wrapper for close_all_positions for compatibility with LiveBroker."""
        return self.close_all_positions()
    
    async def async_get_positions(self) -> List[Position]:
        """Async wrapper for get_positions - returns List for compatibility with LiveBroker."""
        return list(self.positions.values())
    
    async def async_get_balance(self) -> float:
        """Async wrapper for getting balance (mock for paper trading)."""
        # Paper broker doesn't track actual balance, return a default
        return 10000.0  # $10,000 paper balance
    
    async def async_check_sltp_triggers(self, market_prices: Dict[str, float]) -> List[Tuple[str, str, float]]:
        """Async wrapper for check_sltp_triggers for compatibility."""
        return self.check_sltp_triggers(market_prices)


