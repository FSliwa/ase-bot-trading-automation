"""
Transaction Manager - Atomic database operations for trading.

Ensures that order placement and position creation happen atomically.
If any step fails, the entire transaction is rolled back.
"""

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional, TypeVar
from functools import wraps
import uuid

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class TradeResult:
    """Result of an atomic trade operation."""
    success: bool
    order_id: Optional[str] = None
    position_id: Optional[int] = None
    exchange_order_id: Optional[str] = None
    error: Optional[str] = None
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}


class TransactionManager:
    """
    Manages atomic database transactions for trading operations.
    
    Key Features:
    1. Atomic order + position creation
    2. Automatic rollback on failure
    3. Savepoint support for nested operations
    4. Connection pooling with retry
    
    Usage:
        async with TransactionManager(db_manager) as txn:
            order = txn.create_order(order_data)
            position = txn.create_position(position_data)
            # If either fails, both are rolled back
    """
    
    MAX_RETRIES = 3
    RETRY_DELAY = 0.5  # seconds
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self._session: Optional[Session] = None
        self._in_transaction = False
    
    @contextmanager
    def transaction(self):
        """
        Context manager for atomic transactions.
        
        Usage:
            with txn_manager.transaction() as session:
                session.add(order)
                session.add(position)
                # Auto-commit on success, auto-rollback on exception
        """
        from bot.db import DatabaseManager
        
        session = None
        try:
            # Get a fresh session
            engine = DatabaseManager._get_engine()
            Session = DatabaseManager._get_session_class()
            session = Session()
            self._session = session
            self._in_transaction = True
            
            yield session
            
            # Commit if no exception
            session.commit()
            logger.debug("Transaction committed successfully")
            
        except IntegrityError as e:
            if session:
                session.rollback()
            logger.error(f"Transaction failed - integrity error: {e}")
            raise
        except OperationalError as e:
            if session:
                session.rollback()
            logger.error(f"Transaction failed - operational error: {e}")
            raise
        except Exception as e:
            if session:
                session.rollback()
            logger.error(f"Transaction failed - rolling back: {e}")
            raise
        finally:
            self._in_transaction = False
            if session:
                session.close()
                self._session = None
    
    def atomic_create_order_and_position(
        self,
        order_data: Dict[str, Any],
        position_data: Dict[str, Any],
        on_exchange_success: Optional[Callable] = None
    ) -> TradeResult:
        """
        Atomically create order and position records.
        
        Flow:
        1. Start DB transaction
        2. Create order record (status=PENDING)
        3. Execute exchange order (via callback)
        4. If exchange succeeds: create position, update order status
        5. If exchange fails: rollback everything
        
        Args:
            order_data: Order data dict
            position_data: Position data dict  
            on_exchange_success: Callback to execute exchange order
            
        Returns:
            TradeResult with success status and IDs
        """
        from bot.db import Order, Position
        
        client_order_id = str(uuid.uuid4())
        
        try:
            with self.transaction() as session:
                # Step 1: Create order with PENDING status
                order = Order(
                    client_order_id=client_order_id,
                    user_id=order_data.get('user_id'),
                    strategy=order_data.get('strategy', 'AI_SIGNAL'),
                    symbol=order_data['symbol'],
                    side=order_data['side'],
                    order_type=order_data.get('order_type', 'MARKET'),
                    quantity=order_data['quantity'],
                    price=order_data.get('price'),
                    stop_price=order_data.get('stop_price'),
                    leverage=order_data.get('leverage', 1.0),
                    status='PENDING',
                    reduce_only=order_data.get('reduce_only', False)
                )
                session.add(order)
                session.flush()  # Get order ID without committing
                
                logger.info(f"📝 Created pending order: {client_order_id}")
                
                # Step 2: Execute on exchange (if callback provided)
                exchange_result = None
                if on_exchange_success:
                    try:
                        exchange_result = on_exchange_success(order_data)
                        if not exchange_result or not exchange_result.get('success', False):
                            raise ValueError(f"Exchange order failed: {exchange_result.get('error', 'Unknown')}")
                    except Exception as ex_err:
                        # Exchange failed - transaction will rollback
                        logger.error(f"Exchange order failed: {ex_err}")
                        raise
                
                # Step 3: Update order status and create position
                order.status = 'FILLED'
                order.filled_quantity = order_data['quantity']
                order.avg_fill_price = position_data.get('entry_price', order_data.get('price', 0))
                
                if exchange_result:
                    order.avg_fill_price = exchange_result.get('average_price', order.avg_fill_price)
                
                # Create position
                position = Position(
                    user_id=position_data.get('user_id'),
                    strategy=position_data.get('strategy', 'AI_SIGNAL'),
                    symbol=position_data['symbol'],
                    side=position_data['side'],
                    quantity=position_data['quantity'],
                    entry_price=position_data['entry_price'],
                    current_price=position_data['entry_price'],
                    leverage=position_data.get('leverage', 1.0),
                    stop_loss=position_data.get('stop_loss'),
                    take_profit=position_data.get('take_profit'),
                    status='OPEN',
                    margin_used=position_data.get('margin_used', 0),
                )
                session.add(position)
                session.flush()
                
                logger.info(
                    f"✅ Atomic trade completed: Order={order.id}, Position={position.id}, "
                    f"Symbol={position.symbol}"
                )
                
                return TradeResult(
                    success=True,
                    order_id=client_order_id,
                    position_id=position.id,
                    exchange_order_id=exchange_result.get('order_id') if exchange_result else None,
                    details={
                        'order_db_id': order.id,
                        'filled_price': order.avg_fill_price
                    }
                )
                
        except Exception as e:
            logger.error(f"Atomic trade failed: {e}")
            return TradeResult(
                success=False,
                error=str(e)
            )
    
    def atomic_close_position(
        self,
        position_id: int,
        close_price: float,
        close_reason: str = 'manual',
        on_exchange_close: Optional[Callable] = None
    ) -> TradeResult:
        """
        Atomically close a position and create close order.
        
        Args:
            position_id: ID of position to close
            close_price: Price at which position is closed
            close_reason: Reason for closing (sl, tp, manual, time_exit)
            on_exchange_close: Callback to execute close on exchange
            
        Returns:
            TradeResult
        """
        from bot.db import Order, Position
        
        try:
            with self.transaction() as session:
                # Get position
                position = session.query(Position).filter(
                    Position.id == position_id,
                    Position.status == 'OPEN'
                ).with_for_update().first()
                
                if not position:
                    return TradeResult(
                        success=False,
                        error=f"Position {position_id} not found or already closed"
                    )
                
                # Calculate realized P&L
                if position.side.lower() == 'long':
                    realized_pnl = (close_price - position.entry_price) * position.quantity
                else:
                    realized_pnl = (position.entry_price - close_price) * position.quantity
                
                # Execute on exchange if callback provided
                if on_exchange_close:
                    try:
                        result = on_exchange_close(position.symbol, position.quantity, position.side)
                        if not result or not result.get('success', False):
                            raise ValueError(f"Exchange close failed: {result.get('error')}")
                    except Exception as ex_err:
                        logger.error(f"Exchange close failed: {ex_err}")
                        raise
                
                # Create close order
                close_order = Order(
                    client_order_id=str(uuid.uuid4()),
                    user_id=position.user_id,
                    strategy=position.strategy,
                    symbol=position.symbol,
                    side='sell' if position.side.lower() == 'long' else 'buy',
                    order_type='MARKET',
                    quantity=position.quantity,
                    leverage=position.leverage,
                    status='FILLED',
                    filled_quantity=position.quantity,
                    avg_fill_price=close_price,
                    reduce_only=True
                )
                session.add(close_order)
                
                # Update position
                position.status = 'CLOSED'
                position.current_price = close_price
                position.realized_pnl = realized_pnl
                position.exit_time = datetime.utcnow()
                
                logger.info(
                    f"✅ Position {position_id} closed atomically | "
                    f"P&L: ${realized_pnl:.2f} | Reason: {close_reason}"
                )
                
                return TradeResult(
                    success=True,
                    position_id=position_id,
                    order_id=close_order.client_order_id,
                    details={
                        'realized_pnl': realized_pnl,
                        'close_price': close_price,
                        'close_reason': close_reason
                    }
                )
                
        except Exception as e:
            logger.error(f"Atomic close failed: {e}")
            return TradeResult(
                success=False,
                error=str(e)
            )


def atomic_trade_operation(db_manager):
    """
    Decorator for atomic trade operations.
    
    Usage:
        @atomic_trade_operation(db_manager)
        async def place_order(session, order_data):
            # session is injected, auto-commit/rollback
            order = Order(**order_data)
            session.add(order)
            return order
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            txn_manager = TransactionManager(db_manager)
            with txn_manager.transaction() as session:
                # Inject session as first argument
                return await func(session, *args, **kwargs)
        return wrapper
    return decorator
