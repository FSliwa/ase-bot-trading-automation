"""
Enhanced Paper Broker with order matching engine and bracket orders
"""

import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from bot.db import DatabaseManager, Position, Fill


@dataclass
class OrderBookLevel:
    """Order book price level"""
    price: float
    quantity: float
    orders: List[str] = field(default_factory=list)


@dataclass
class OrderBook:
    """Simple order book for matching"""
    bids: Dict[float, OrderBookLevel] = field(default_factory=dict)  # price -> level
    asks: Dict[float, OrderBookLevel] = field(default_factory=dict)  # price -> level
    
    def add_order(self, order_id: str, side: str, price: float, quantity: float):
        """Add order to book"""
        book_side = self.bids if side == "BUY" else self.asks
        
        if price not in book_side:
            book_side[price] = OrderBookLevel(price=price, quantity=0.0)
        
        book_side[price].quantity += quantity
        book_side[price].orders.append(order_id)
    
    def remove_order(self, order_id: str, side: str, price: float, quantity: float):
        """Remove order from book"""
        book_side = self.bids if side == "BUY" else self.asks
        
        if price in book_side:
            level = book_side[price]
            level.quantity -= quantity
            if order_id in level.orders:
                level.orders.remove(order_id)
            
            if level.quantity <= 0:
                del book_side[price]
    
    def get_best_bid(self) -> Optional[float]:
        """Get best bid price"""
        return max(self.bids.keys()) if self.bids else None
    
    def get_best_ask(self) -> Optional[float]:
        """Get best ask price"""
        return min(self.asks.keys()) if self.asks else None
    
    def get_spread(self) -> Optional[float]:
        """Get bid-ask spread"""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        
        if best_bid and best_ask:
            return best_ask - best_bid
        return None


@dataclass
class MarketData:
    """Market data for symbol"""
    symbol: str
    price: float
    bid: float
    ask: float
    volume_24h: float = 0.0
    last_update: datetime = field(default_factory=datetime.utcnow)


class EnhancedPaperBroker:
    """Enhanced paper trading broker with order matching"""
    
    def __init__(self, initial_balance: float = 10000.0, strategy_name: str = "paper"):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.strategy_name = strategy_name
        self.order_books: Dict[str, OrderBook] = defaultdict(OrderBook)
        self.market_data: Dict[str, MarketData] = {}
        self.pending_orders: Dict[str, dict] = {}  # order_id -> order_data
        self.bracket_orders: Dict[str, List[str]] = {}  # parent_id -> [child_order_ids]
        
        # Initialize database
        self.db = DatabaseManager()
        
        # Simulate some market data
        self._init_market_data()
    
    def _init_market_data(self):
        """Initialize market data for common symbols"""
        symbols_data = {
            "BTCUSDT": {"price": 67432.10, "bid": 67431.50, "ask": 67432.50},
            "ETHUSD": {"price": 3245.50, "bid": 3245.00, "ask": 3246.00},
            "SOLUSDT": {"price": 145.80, "bid": 145.75, "ask": 145.85},
            "XRPUSDT": {"price": 0.5234, "bid": 0.5233, "ask": 0.5235},
            "ADAUSDT": {"price": 0.4567, "bid": 0.4566, "ask": 0.4568},
        }
        
        for symbol, data in symbols_data.items():
            self.market_data[symbol] = MarketData(
                symbol=symbol,
                price=data["price"],
                bid=data["bid"],
                ask=data["ask"]
            )
    
    def update_market_price(self, symbol: str, price: float, bid: float = None, ask: float = None):
        """Update market price for symbol"""
        if symbol not in self.market_data:
            self.market_data[symbol] = MarketData(symbol=symbol, price=price, bid=bid or price, ask=ask or price)
        else:
            self.market_data[symbol].price = price
            if bid:
                self.market_data[symbol].bid = bid
            if ask:
                self.market_data[symbol].ask = ask
            self.market_data[symbol].last_update = datetime.utcnow()
        
        # Check for triggered orders
        self._check_triggered_orders(symbol)
        
        # Update position PnL
        self._update_positions_pnl(symbol)
    
    def place_order(self, symbol: str, side: str, order_type: str, quantity: float,
                   price: Optional[float] = None, stop_price: Optional[float] = None,
                   time_in_force: str = "GTC", reduce_only: bool = False,
                   leverage: float = 1.0, stop_loss: Optional[float] = None,
                   take_profit: Optional[float] = None) -> dict:
        """Place order with enhanced features"""
        
        order_id = str(uuid.uuid4())
        
        # Validate order
        validation_result = self._validate_order(symbol, side, order_type, quantity, price, leverage)
        if not validation_result["valid"]:
            return {"success": False, "error": validation_result["error"], "order_id": None}
        
        # Create order
        order = {
            "id": order_id,
            "client_order_id": f"paper_{order_id[:8]}",
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
            "price": price,
            "stop_price": stop_price,
            "filled_quantity": 0.0,
            "remaining_quantity": quantity,
            "status": "NEW",
            "time_in_force": time_in_force,
            "reduce_only": reduce_only,
            "leverage": leverage,
            "created_at": datetime.utcnow(),
            "parent_order_id": None
        }
        
        # Store in database
        with DatabaseManager() as db:
            db_order = db.create_order(
                client_order_id=order["client_order_id"],
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                stop_price=stop_price,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                leverage=leverage
            )
            order["db_id"] = db_order.id
        
        self.pending_orders[order_id] = order
        
        # Handle different order types
        if order_type == "MARKET":
            fill_result = self._execute_market_order(order)
        elif order_type == "LIMIT":
            fill_result = self._handle_limit_order(order)
        elif order_type in ["STOP", "STOP_LIMIT"]:
            fill_result = {"filled": False, "message": "Stop order placed, waiting for trigger"}
        else:
            return {"success": False, "error": f"Unsupported order type: {order_type}"}
        
        # Create bracket orders if specified
        bracket_order_ids = []
        if fill_result.get("filled") and (stop_loss or take_profit):
            bracket_order_ids = self._create_bracket_orders(order_id, symbol, side, quantity, stop_loss, take_profit)
        
        return {
            "success": True,
            "order_id": order_id,
            "status": order["status"],
            "filled_quantity": order["filled_quantity"],
            "bracket_orders": bracket_order_ids,
            "message": fill_result.get("message", "Order placed successfully")
        }
    
    def _validate_order(self, symbol: str, side: str, order_type: str, quantity: float,
                       price: Optional[float], leverage: float) -> dict:
        """Validate order parameters"""
        
        # Check if symbol exists in market data
        if symbol not in self.market_data:
            return {"valid": False, "error": f"Unknown symbol: {symbol}"}
        
        # Check quantity
        if quantity <= 0:
            return {"valid": False, "error": "Quantity must be positive"}
        
        # Check price for limit orders
        if order_type == "LIMIT" and not price:
            return {"valid": False, "error": "Limit orders require price"}
        
        # Check available balance
        market_price = price or self.market_data[symbol].price
        required_margin = abs(quantity * market_price / leverage)
        
        if required_margin > self.balance:
            return {"valid": False, "error": f"Insufficient balance. Required: {required_margin:.2f}, Available: {self.balance:.2f}"}
        
        return {"valid": True}
    
    def _execute_market_order(self, order: dict) -> dict:
        """Execute market order immediately"""
        symbol = order["symbol"]
        side = order["side"]
        quantity = order["quantity"]
        
        # Get market price
        market_data = self.market_data[symbol]
        fill_price = market_data.ask if side == "BUY" else market_data.bid
        expected_px = fill_price
        mid_at_submit = (market_data.bid + market_data.ask) / 2.0 if (market_data.bid and market_data.ask) else market_data.price
        
        # Simulate slippage for large orders
        if quantity * fill_price > 10000:  # Large order threshold
            slippage = 0.001 if side == "BUY" else -0.001  # 0.1% slippage
            fill_price *= (1 + slippage)
        
        # Execute fill
        # Record slippage sample
        try:
            slippage_bps = ((fill_price - expected_px) / expected_px) * 10000.0 if expected_px else 0.0
            notional = abs(quantity * fill_price)
            with DatabaseManager() as db:
                db.save_slippage_sample(
                    symbol=symbol,
                    side=side,
                    notional=notional,
                    expected_px=expected_px,
                    fill_px=fill_price,
                    mid_at_submit=mid_at_submit,
                    slippage_bps=slippage_bps,
                    market_state_snapshot_id=None,
                )
                # Update daily performance aggregate (slippage average, trades count)
                self._update_daily_performance_slippage(db, symbol, slippage_bps)
        except Exception:
            pass

        self._fill_order(order, quantity, fill_price)
        
        return {"filled": True, "fill_price": fill_price, "message": f"Market order filled at {fill_price}"}
    
    def _handle_limit_order(self, order: dict) -> dict:
        """Handle limit order (add to book or fill if crossed)"""
        symbol = order["symbol"]
        side = order["side"]
        price = order["price"]
        quantity = order["quantity"]
        
        # Check if order can be filled immediately
        market_data = self.market_data[symbol]
        
        can_fill = False
        if side == "BUY" and price >= market_data.ask:
            can_fill = True
            fill_price = market_data.ask
        elif side == "SELL" and price <= market_data.bid:
            can_fill = True
            fill_price = market_data.bid
        
        if can_fill:
            self._fill_order(order, quantity, fill_price)
            return {"filled": True, "fill_price": fill_price, "message": f"Limit order filled immediately at {fill_price}"}
        else:
            # Add to order book
            self.order_books[symbol].add_order(order["id"], side, price, quantity)
            return {"filled": False, "message": f"Limit order added to book at {price}"}
    
    def _fill_order(self, order: dict, fill_quantity: float, fill_price: float):
        """Fill order (partial or complete)"""
        
        # Calculate fee (0.1% taker fee)
        fee = fill_quantity * fill_price * 0.001
        
        # Update order
        order["filled_quantity"] += fill_quantity
        order["remaining_quantity"] -= fill_quantity
        
        if order["remaining_quantity"] <= 0:
            order["status"] = "FILLED"
        else:
            order["status"] = "PARTIALLY_FILLED"
        
        # Update balance
        if order["side"] == "BUY":
            self.balance -= (fill_quantity * fill_price + fee)
        else:
            self.balance += (fill_quantity * fill_price - fee)
        
        # Create or update position
        self._update_position(order, fill_quantity, fill_price)
        
        # Record fill in database
        with DatabaseManager() as db:
            db.fill_order(
                order_id=order["db_id"],
                filled_qty=fill_quantity,
                fill_price=fill_price,
                fee=fee
            )

    def _update_daily_performance_slippage(self, db: DatabaseManager, symbol: str, slippage_bps: float):
        """Update StrategyDailyPerformance with one more trade and updated avg slippage."""
        try:
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            existing = db.get_strategy_daily_performance(
                strategy=self.strategy_name,
                symbol=symbol,
                start_date=today,
                end_date=today + timedelta(days=1)
            )
            trades = 0
            avg_slip = None
            if existing:
                rec = existing[0]
                trades = rec.trades or 0
                avg_slip = rec.avg_slippage_bps
            new_trades = trades + 1
            new_avg_slip = slippage_bps if (avg_slip is None or trades == 0) else ((avg_slip * trades) + slippage_bps) / new_trades
            db.upsert_strategy_daily_performance(
                date=today,
                strategy=self.strategy_name,
                symbol=symbol,
                trades=new_trades,
                avg_slippage_bps=new_avg_slip,
            )
        except Exception:
            # Soft-fail, metrics should not block trading
            pass
    
    def _update_position(self, order: dict, fill_quantity: float, fill_price: float):
        """Update or create position"""
        symbol = order["symbol"]
        side = order["side"]
        leverage = order["leverage"]
        
        with DatabaseManager() as db:
            existing_position = db.get_position_by_symbol(symbol)
            
            if existing_position:
                # Update existing position
                if existing_position.side == side:
                    # Same side - add to position
                    total_quantity = existing_position.quantity + fill_quantity
                    avg_price = ((existing_position.quantity * existing_position.entry_price) + 
                               (fill_quantity * fill_price)) / total_quantity
                    
                    existing_position.quantity = total_quantity
                    existing_position.entry_price = avg_price
                    existing_position.current_price = fill_price
                else:
                    # Opposite side - reduce or reverse position
                    if existing_position.quantity > fill_quantity:
                        # Reduce position
                        existing_position.quantity -= fill_quantity
                        existing_position.current_price = fill_price
                    elif existing_position.quantity < fill_quantity:
                        # Reverse position
                        remaining_qty = fill_quantity - existing_position.quantity
                        db.close_position(existing_position.id, fill_price)
                        
                        # Create new position in opposite direction
                        new_side = "SELL" if existing_position.side == "BUY" else "BUY"
                        db.create_position(symbol, new_side, remaining_qty, fill_price, leverage)
                    else:
                        # Close position exactly
                        db.close_position(existing_position.id, fill_price)
            else:
                # Create new position
                db.create_position(symbol, side, fill_quantity, fill_price, leverage)
    
    def _create_bracket_orders(self, parent_order_id: str, symbol: str, side: str, 
                              quantity: float, stop_loss: Optional[float] = None,
                              take_profit: Optional[float] = None) -> List[str]:
        """Create stop-loss and take-profit orders"""
        bracket_ids = []
        
        # Determine opposite side for closing orders
        close_side = "SELL" if side == "BUY" else "BUY"
        
        # Create stop-loss order
        if stop_loss:
            sl_order_id = str(uuid.uuid4())
            sl_order = {
                "id": sl_order_id,
                "client_order_id": f"sl_{sl_order_id[:8]}",
                "symbol": symbol,
                "side": close_side,
                "type": "STOP",
                "quantity": quantity,
                "price": None,
                "stop_price": stop_loss,
                "filled_quantity": 0.0,
                "remaining_quantity": quantity,
                "status": "NEW",
                "time_in_force": "GTC",
                "reduce_only": True,
                "leverage": 1.0,
                "created_at": datetime.utcnow(),
                "parent_order_id": parent_order_id
            }
            
            self.pending_orders[sl_order_id] = sl_order
            bracket_ids.append(sl_order_id)
        
        # Create take-profit order
        if take_profit:
            tp_order_id = str(uuid.uuid4())
            tp_order = {
                "id": tp_order_id,
                "client_order_id": f"tp_{tp_order_id[:8]}",
                "symbol": symbol,
                "side": close_side,
                "type": "LIMIT",
                "quantity": quantity,
                "price": take_profit,
                "stop_price": None,
                "filled_quantity": 0.0,
                "remaining_quantity": quantity,
                "status": "NEW",
                "time_in_force": "GTC",
                "reduce_only": True,
                "leverage": 1.0,
                "created_at": datetime.utcnow(),
                "parent_order_id": parent_order_id
            }
            
            self.pending_orders[tp_order_id] = tp_order
            
            # Add TP limit order to book
            self.order_books[symbol].add_order(tp_order_id, close_side, take_profit, quantity)
            bracket_ids.append(tp_order_id)
        
        # Store bracket relationship
        if bracket_ids:
            self.bracket_orders[parent_order_id] = bracket_ids
        
        return bracket_ids
    
    def _check_triggered_orders(self, symbol: str):
        """Check for triggered stop orders"""
        current_price = self.market_data[symbol].price
        
        triggered_orders = []
        
        for order_id, order in self.pending_orders.items():
            if order["symbol"] != symbol or order["type"] not in ["STOP", "STOP_LIMIT"]:
                continue
            
            stop_price = order["stop_price"]
            side = order["side"]
            
            # Check trigger conditions
            triggered = False
            if side == "BUY" and current_price >= stop_price:
                triggered = True
            elif side == "SELL" and current_price <= stop_price:
                triggered = True
            
            if triggered:
                triggered_orders.append(order_id)
        
        # Execute triggered orders
        for order_id in triggered_orders:
            order = self.pending_orders[order_id]
            if order["type"] == "STOP":
                # Convert to market order
                order["type"] = "MARKET"
                self._execute_market_order(order)
            elif order["type"] == "STOP_LIMIT":
                # Convert to limit order
                order["type"] = "LIMIT"
                self._handle_limit_order(order)
    
    def _update_positions_pnl(self, symbol: str):
        """Update unrealized PnL for positions"""
        current_price = self.market_data[symbol].price
        
        with DatabaseManager() as db:
            positions = db.get_open_positions()
            for position in positions:
                if position.symbol == symbol:
                    db.update_position_price(position.id, current_price)
    
    def cancel_order(self, order_id: str) -> dict:
        """Cancel pending order"""
        if order_id not in self.pending_orders:
            return {"success": False, "error": "Order not found"}
        
        order = self.pending_orders[order_id]
        
        if order["status"] in ["FILLED", "CANCELED"]:
            return {"success": False, "error": f"Cannot cancel order with status: {order['status']}"}
        
        # Remove from order book if it's a limit order
        if order["type"] == "LIMIT":
            self.order_books[order["symbol"]].remove_order(
                order_id, order["side"], order["price"], order["remaining_quantity"]
            )
        
        order["status"] = "CANCELED"
        
        # Cancel bracket orders if this is a parent
        if order_id in self.bracket_orders:
            for bracket_id in self.bracket_orders[order_id]:
                if bracket_id in self.pending_orders:
                    self.cancel_order(bracket_id)
        
        # Update database
        with DatabaseManager() as db:
            db.cancel_order(order["db_id"])
        
        return {"success": True, "message": "Order canceled successfully"}
    
    def get_open_orders(self) -> List[dict]:
        """Get all open orders"""
        return [
            order for order in self.pending_orders.values()
            if order["status"] in ["NEW", "PARTIALLY_FILLED"]
        ]
    
    def get_open_positions(self) -> List[dict]:
        """Get all open positions"""
        with DatabaseManager() as db:
            db_positions = db.get_open_positions()
            
            positions = []
            for pos in db_positions:
                positions.append({
                    "id": pos.id,
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price or pos.entry_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "realized_pnl": pos.realized_pnl,
                    "leverage": pos.leverage,
                    "margin_used": pos.margin_used,
                    "entry_time": pos.entry_time,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit
                })
            
            return positions
    
    def close_position(self, symbol: str, quantity: Optional[float] = None) -> dict:
        """Close position (partial or full)"""
        try:
            with DatabaseManager() as db:
                position = db.get_position_by_symbol(symbol)
                
                if not position:
                    return {"success": False, "error": f"No open position for {symbol}"}
                
                close_quantity = quantity or position.quantity
                if close_quantity > position.quantity:
                    close_quantity = position.quantity
                
                # Get current price for the symbol
                current_price = self.market_data.get(symbol, MarketData(symbol, position.entry_price)).price
                
                # Calculate PnL
                if position.side == "BUY":
                    pnl = (current_price - position.entry_price) * close_quantity
                else:
                    pnl = (position.entry_price - current_price) * close_quantity
                
                # Close position in database
                if close_quantity >= position.quantity:
                    # Full close
                    db.close_position(position.id, current_price)
                    self.balance += pnl  # Add PnL to balance
                    return {
                        "success": True, 
                        "message": f"Position {symbol} fully closed",
                        "pnl": pnl,
                        "closed_quantity": close_quantity
                    }
                else:
                    # Partial close - update position
                    position.quantity -= close_quantity
                    position.realized_pnl += pnl
                    db.session.commit()
                    self.balance += pnl  # Add PnL to balance
                    return {
                        "success": True, 
                        "message": f"Position {symbol} partially closed",
                        "pnl": pnl,
                        "closed_quantity": close_quantity,
                        "remaining_quantity": position.quantity
                    }
                    
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def close_position_by_id(self, position_id: str):
        """Close a position by ID (async version for compatibility)."""
        with DatabaseManager() as db:
            position = db.session.query(Position).filter(Position.id == position_id).first()
            if position and position.status == "OPEN":
                # Get current price
                current_price = self.market_data.get(position.symbol, MarketData(position.symbol, position.entry_price)).price
                
                # Close the position
                db.close_position(position.id, current_price)
                
                # Update balance
                if position.side == "BUY":
                    pnl = (current_price - position.entry_price) * position.quantity
                else:
                    pnl = (position.entry_price - current_price) * position.quantity
                
                self.balance += pnl
                
                # Update balance
                self.balance += position.realized_pnl
                
                # Create fill record
                fill = Fill(
                    order_id=f"close_{position_id}",
                    symbol=position.symbol,
                    side="sell" if position.side == "buy" else "buy",
                    quantity=position.size,
                    price=current_price,
                    timestamp=datetime.now()
                )
                db.session.add(fill)
                db.session.commit()
                
                return True
        return False
    
    def get_account_info(self) -> dict:
        """Get account information"""
        with DatabaseManager() as db:
            positions = db.get_open_positions()
            
            total_unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)
            total_margin_used = sum(pos.margin_used for pos in positions)
            
            total_balance = self.balance + total_unrealized_pnl
            
            return {
                "balance": self.balance,
                "total_balance": total_balance,
                "available_balance": self.balance - total_margin_used,
                "equity": total_balance,
                "margin_used": total_margin_used,
                "free_margin": self.balance - total_margin_used,
                "unrealized_pnl": total_unrealized_pnl,
                "positions_count": len(positions),
                "orders_count": len(self.get_open_orders()),
                "initial_balance": self.initial_balance
            }
    
    def get_order_book(self, symbol: str) -> Dict:
        """Get simulated order book for a symbol."""
        # Simulated order book
        base_price = self.market_data.get(symbol, MarketData(symbol, 50000)).price
        
        bids = []
        asks = []
        
        # Generate bids (buy orders)
        for i in range(10):
            price = base_price * (1 - 0.0001 * (i + 1))
            size = 0.1 + (i * 0.05)
            bids.append([price, size])
            
        # Generate asks (sell orders)
        for i in range(10):
            price = base_price * (1 + 0.0001 * (i + 1))
            size = 0.1 + (i * 0.05)
            asks.append([price, size])
            
        return {
            'bids': bids,
            'asks': asks,
            'timestamp': datetime.now().isoformat()
        }
    
    def get_account_balance(self) -> dict:
        """Get account balance information - compatible with web API"""
        with DatabaseManager() as db:
            positions = db.get_open_positions()
            
            total_unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)
            total_margin_used = sum(pos.margin_used for pos in positions)
            
            return {
                "total_balance": self.balance,
                "available_balance": max(0, self.balance - total_margin_used),
                "margin_used": total_margin_used,
                "unrealized_pnl": total_unrealized_pnl,
                "initial_balance": self.initial_balance
            }
    
    def get_order_book(self, symbol: str) -> dict:
        """Get order book for symbol"""
        if symbol not in self.order_books:
            return {"bids": [], "asks": []}
        
        book = self.order_books[symbol]
        
        return {
            "bids": [{"price": price, "quantity": level.quantity} 
                    for price, level in sorted(book.bids.items(), reverse=True)],
            "asks": [{"price": price, "quantity": level.quantity} 
                    for price, level in sorted(book.asks.items())]
        }
