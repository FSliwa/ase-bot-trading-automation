"""
DCA (Dollar Cost Averaging) Manager Service

This service manages DCA positions:
- Opens DCA positions with base order + safety orders
- Monitors price for safety order triggers
- Calculates average entry price
- Manages TP/SL from average price

Author: ASE BOT Team
Date: 2025-12-14
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from bot.db import (
    DCAPosition, 
    DCAOrder, 
    DCASettings,
    SessionLocal,
    DatabaseManager
)

if TYPE_CHECKING:
    # P1-NEW-1 FIX: Use correct import path (exchange_adapters instead of http)
    from bot.exchange_adapters.ccxt_adapter import CCXTAdapter

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration Dataclasses
# ============================================================================

@dataclass
class DCAConfig:
    """DCA configuration for a position."""
    enabled: bool = True
    base_order_percent: float = 40.0       # % of budget for initial entry
    safety_order_count: int = 3            # Number of safety orders
    safety_order_percent: float = 20.0     # % of budget per safety order
    price_deviation_percent: float = 3.0   # % drop for first SO trigger
    price_deviation_scale: float = 1.5     # Multiplier for subsequent SO deviations
    take_profit_percent: float = 3.0       # TP % from average price
    stop_loss_percent: float = 10.0        # SL % from average price
    use_limit_orders: bool = False         # Use limit orders vs market
    min_time_between_orders: int = 60      # Minimum seconds between SO executions
    
    @classmethod
    def from_db_settings(cls, settings: DCASettings) -> 'DCAConfig':
        """Create config from database settings."""
        return cls(
            enabled=settings.dca_enabled,
            base_order_percent=settings.default_base_order_percent,
            safety_order_count=settings.default_safety_order_count,
            safety_order_percent=settings.default_safety_order_percent,
            price_deviation_percent=settings.default_price_deviation_percent,
            price_deviation_scale=settings.default_price_deviation_scale,
            take_profit_percent=settings.default_take_profit_percent,
            stop_loss_percent=settings.default_stop_loss_percent,
            use_limit_orders=settings.use_limit_orders,
            min_time_between_orders=settings.min_time_between_safety_orders or 60
        )
    
    @classmethod
    def default(cls) -> 'DCAConfig':
        """Return default DCA configuration."""
        return cls()


@dataclass
class DCAExecutionResult:
    """Result of a DCA operation."""
    success: bool
    position_id: Optional[str] = None
    message: str = ""
    orders_created: int = 0
    base_order_filled: bool = False
    average_entry_price: float = 0.0
    total_invested: float = 0.0
    error: Optional[str] = None


@dataclass  
class SafetyOrderTrigger:
    """Information about a triggered safety order."""
    order_id: str
    position_id: str
    order_number: int
    trigger_price: float
    current_price: float
    target_quantity: float
    target_value: float


# ============================================================================
# DCA Manager Service
# ============================================================================

class DCAManager:
    """
    Manages Dollar Cost Averaging (DCA) positions.
    
    DCA Strategy:
    1. When signal received, open position with base order (e.g., 40% of budget)
    2. Place safety orders at lower prices (e.g., -3%, -4.5%, -6.75%)
    3. If price drops, safety orders trigger and average down entry price
    4. TP/SL calculated from volume-weighted average price
    """
    
    def __init__(
        self,
        exchange_adapter: 'CCXTAdapter',
        user_id: str,
        config: Optional[DCAConfig] = None
    ):
        self.exchange = exchange_adapter
        self.user_id = user_id
        self.config = config or DCAConfig.default()
        
        # Active positions being monitored
        self._active_positions: Dict[str, DCAPosition] = {}
        
        # Monitoring state
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._check_interval = 5  # seconds
        
        logger.info(
            f"DCAManager initialized | User: {user_id[:8]}... | "
            f"Base: {self.config.base_order_percent}% | "
            f"SO count: {self.config.safety_order_count} | "
            f"Deviation: {self.config.price_deviation_percent}%"
        )
    
    # ========================================================================
    # Configuration
    # ========================================================================
    
    def load_user_config(self) -> DCAConfig:
        """Load DCA config from database for user."""
        try:
            with DatabaseManager.session_scope() as session:
                settings = session.query(DCASettings).filter_by(
                    user_id=self.user_id
                ).first()
                
                if settings:
                    self.config = DCAConfig.from_db_settings(settings)
                    logger.info(f"Loaded DCA config from DB for user {self.user_id[:8]}...")
                else:
                    logger.info(f"No DCA settings in DB, using defaults")
                    
        except Exception as e:
            logger.error(f"Failed to load DCA config: {e}")
        
        return self.config
    
    def is_enabled(self) -> bool:
        """Check if DCA is enabled for this user."""
        return self.config.enabled
    
    def get_user_dca_settings(self) -> dict:
        """
        Get user's DCA settings as dict (for auto_trader compatibility).
        Returns dict with dca_enabled, base_order_percent, safety_order_count, etc.
        """
        return {
            'dca_enabled': self.config.enabled,
            'base_order_percent': self.config.base_order_percent,
            'safety_order_count': self.config.safety_order_count,
            'price_deviation_percent': self.config.price_deviation_percent,
            'safety_order_scale': self.config.safety_order_scale,
            'safety_order_volume_scale': self.config.safety_order_volume_scale,
            'take_profit_percent': self.config.take_profit_percent,
            'stop_loss_percent': self.config.stop_loss_percent,
        }
    
    # ========================================================================
    # Position Opening
    # ========================================================================
    
    async def open_dca_position(
        self,
        symbol: str,
        side: str,  # 'long' or 'short'
        total_budget: float,
        entry_price: float,
        signal_id: Optional[str] = None,
        config_override: Optional[DCAConfig] = None
    ) -> DCAExecutionResult:
        """
        Open a new DCA position.
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            side: 'long' or 'short'
            total_budget: Total $ to allocate to this DCA position
            entry_price: Current/entry price
            signal_id: Optional reference to originating signal
            config_override: Optional config to use instead of default
            
        Returns:
            DCAExecutionResult with position details
        """
        config = config_override or self.config
        
        logger.info(
            f"📊 Opening DCA position | {symbol} {side.upper()} | "
            f"Budget: ${total_budget:.2f} | Entry: ${entry_price:.2f}"
        )
        
        try:
            # Calculate order plan
            order_plan = self._calculate_order_plan(
                total_budget=total_budget,
                entry_price=entry_price,
                side=side,
                config=config
            )
            
            # Create position in database
            position_id = str(uuid.uuid4())
            
            with DatabaseManager.session_scope() as session:
                # Create DCA position
                position = DCAPosition(
                    id=position_id,
                    user_id=self.user_id,
                    signal_id=signal_id,
                    symbol=symbol,
                    side=side,
                    exchange=self.exchange.exchange.id,
                    base_order_percent=config.base_order_percent,
                    safety_order_count=config.safety_order_count,
                    safety_order_percent=config.safety_order_percent,
                    price_deviation_percent=config.price_deviation_percent,
                    price_deviation_scale=config.price_deviation_scale,
                    max_investment=total_budget,
                    take_profit_percent=config.take_profit_percent,
                    stop_loss_percent=config.stop_loss_percent,
                    status='active'
                )
                session.add(position)
                
                # Create orders (base + safety)
                for order_info in order_plan:
                    order = DCAOrder(
                        id=str(uuid.uuid4()),
                        dca_position_id=position_id,
                        order_type=order_info['type'],
                        order_number=order_info['number'],
                        trigger_price=order_info['trigger_price'],
                        trigger_deviation_percent=order_info.get('deviation_percent'),
                        target_quantity=order_info['quantity'],
                        target_value=order_info['value'],
                        status='pending'
                    )
                    session.add(order)
                
                session.commit()
                logger.info(f"💾 Created DCA position {position_id[:8]}... with {len(order_plan)} orders")
            
            # Execute base order immediately
            base_result = await self._execute_base_order(position_id, symbol, side, order_plan[0])
            
            if not base_result['success']:
                # Cancel position if base order fails
                await self._cancel_position(position_id, f"Base order failed: {base_result.get('error')}")
                return DCAExecutionResult(
                    success=False,
                    position_id=position_id,
                    error=base_result.get('error', 'Base order execution failed')
                )
            
            # Update position with base order fill
            await self._update_position_after_fill(
                position_id=position_id,
                fill_price=base_result['fill_price'],
                fill_quantity=base_result['fill_quantity'],
                fill_value=base_result['fill_value']
            )
            
            # Calculate TP/SL prices
            avg_price = base_result['fill_price']  # Initially just base order
            tp_price, sl_price = self._calculate_tp_sl(avg_price, side, config)
            
            # Update TP/SL in database
            with DatabaseManager.session_scope() as session:
                pos = session.query(DCAPosition).filter_by(id=position_id).first()
                if pos:
                    pos.take_profit_price = tp_price
                    pos.stop_loss_price = sl_price
                    session.commit()
            
            # Add to active monitoring
            self._active_positions[position_id] = position
            
            logger.info(
                f"✅ DCA position opened | {symbol} {side.upper()} | "
                f"Base filled @ ${base_result['fill_price']:.2f} | "
                f"TP: ${tp_price:.2f} | SL: ${sl_price:.2f} | "
                f"Pending SO: {config.safety_order_count}"
            )
            
            return DCAExecutionResult(
                success=True,
                position_id=position_id,
                message=f"DCA position opened with base order filled",
                orders_created=len(order_plan),
                base_order_filled=True,
                average_entry_price=base_result['fill_price'],
                total_invested=base_result['fill_value']
            )
            
        except Exception as e:
            logger.error(f"Failed to open DCA position: {e}")
            import traceback
            traceback.print_exc()
            return DCAExecutionResult(
                success=False,
                error=str(e)
            )
    
    def _calculate_order_plan(
        self,
        total_budget: float,
        entry_price: float,
        side: str,
        config: DCAConfig
    ) -> List[Dict[str, Any]]:
        """
        Calculate the order plan (base + safety orders).
        
        Returns list of order specifications.
        """
        orders = []
        
        # Base order
        base_value = total_budget * (config.base_order_percent / 100)
        base_quantity = base_value / entry_price
        
        orders.append({
            'type': 'base',
            'number': 0,
            'trigger_price': entry_price,
            'quantity': base_quantity,
            'value': base_value,
            'deviation_percent': 0
        })
        
        # Safety orders
        remaining_budget = total_budget - base_value
        so_value = remaining_budget / config.safety_order_count if config.safety_order_count > 0 else 0
        
        cumulative_deviation = 0
        for i in range(1, config.safety_order_count + 1):
            # Calculate deviation for this safety order
            if i == 1:
                deviation = config.price_deviation_percent
            else:
                deviation = config.price_deviation_percent * (config.price_deviation_scale ** (i - 1))
            
            cumulative_deviation += deviation
            
            # Calculate trigger price
            if side == 'long':
                # For long: buy lower
                trigger_price = entry_price * (1 - cumulative_deviation / 100)
            else:
                # For short: sell higher
                trigger_price = entry_price * (1 + cumulative_deviation / 100)
            
            so_quantity = so_value / trigger_price
            
            orders.append({
                'type': f'safety_{i}',
                'number': i,
                'trigger_price': trigger_price,
                'quantity': so_quantity,
                'value': so_value,
                'deviation_percent': cumulative_deviation
            })
        
        # Log order plan
        logger.debug(f"Order plan for {side} position:")
        for o in orders:
            logger.debug(f"  {o['type']}: ${o['value']:.2f} @ ${o['trigger_price']:.2f}")
        
        return orders
    
    async def _execute_base_order(
        self,
        position_id: str,
        symbol: str,
        side: str,
        order_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the base order (market order)."""
        try:
            # Determine order side
            order_side = 'buy' if side == 'long' else 'sell'
            
            # Place market order
            order_result = await self.exchange.place_order(
                symbol=symbol,
                side=order_side,
                order_type='market',
                quantity=order_info['quantity']
            )
            
            if not order_result:
                return {'success': False, 'error': 'No order result returned'}
            
            # Extract fill info
            fill_price = order_result.get('average') or order_result.get('price') or order_info['trigger_price']
            fill_quantity = order_result.get('filled') or order_info['quantity']
            fill_value = fill_price * fill_quantity
            
            # Update order in database
            with DatabaseManager.session_scope() as session:
                order = session.query(DCAOrder).filter_by(
                    dca_position_id=position_id,
                    order_type='base'
                ).first()
                
                if order:
                    order.status = 'filled'
                    order.fill_price = fill_price
                    order.fill_quantity = fill_quantity
                    order.fill_value = fill_value
                    order.fill_time = datetime.utcnow()
                    order.exchange_order_id = order_result.get('id')
                    session.commit()
            
            return {
                'success': True,
                'fill_price': fill_price,
                'fill_quantity': fill_quantity,
                'fill_value': fill_value,
                'order_id': order_result.get('id')
            }
            
        except Exception as e:
            logger.error(f"Base order execution failed: {e}")
            return {'success': False, 'error': str(e)}
    
    # ========================================================================
    # Safety Order Execution
    # ========================================================================
    
    async def check_all_safety_orders(self) -> int:
        """
        Check all active DCA positions for safety order triggers.
        
        This is the main method called from trading_cycle to monitor
        all DCA positions and execute any triggered safety orders.
        
        Returns:
            Number of safety orders executed
        """
        total_executed = 0
        
        try:
            # Get all active positions for this user
            with DatabaseManager.session_scope() as session:
                positions = session.query(DCAPosition).filter_by(
                    user_id=self.user_id,
                    status='active'
                ).all()
                
                if not positions:
                    return 0
                
                logger.debug(f"DCA: Checking {len(positions)} active position(s)")
                
                for position in positions:
                    try:
                        # Get current price
                        current_price = await self._get_current_price(position.symbol)
                        
                        if not current_price:
                            continue
                        
                        # Check TP/SL first
                        if self._check_tp_sl_trigger(position, current_price):
                            continue  # Position was closed
                        
                        # Check safety orders
                        triggered = await self.check_and_execute_safety_orders(
                            position.id, 
                            current_price
                        )
                        total_executed += len(triggered)
                        
                    except Exception as e:
                        logger.error(f"Error checking DCA position {position.id[:8]}: {e}")
                        
        except Exception as e:
            logger.error(f"DCA check_all_safety_orders failed: {e}")
        
        return total_executed
    
    async def check_and_execute_safety_orders(
        self,
        position_id: str,
        current_price: float
    ) -> List[SafetyOrderTrigger]:
        """
        Check if any safety orders should trigger and execute them.
        
        Returns list of triggered orders.
        """
        triggered = []
        
        try:
            with DatabaseManager.session_scope() as session:
                # Get position
                position = session.query(DCAPosition).filter_by(
                    id=position_id,
                    status='active'
                ).first()
                
                if not position:
                    return []
                
                # Get pending safety orders
                pending_orders = session.query(DCAOrder).filter_by(
                    dca_position_id=position_id,
                    status='pending'
                ).filter(
                    DCAOrder.order_type.like('safety_%')
                ).order_by(DCAOrder.order_number).all()
                
                for order in pending_orders:
                    should_trigger = self._should_trigger_safety_order(
                        position.side,
                        current_price,
                        order.trigger_price
                    )
                    
                    if should_trigger:
                        # Check minimum time between orders
                        last_fill = session.query(DCAOrder).filter_by(
                            dca_position_id=position_id,
                            status='filled'
                        ).order_by(DCAOrder.fill_time.desc()).first()
                        
                        if last_fill and last_fill.fill_time:
                            time_since_last = (datetime.utcnow() - last_fill.fill_time).total_seconds()
                            if time_since_last < self.config.min_time_between_orders:
                                logger.debug(
                                    f"Skipping SO trigger - too soon ({time_since_last:.0f}s < {self.config.min_time_between_orders}s)"
                                )
                                continue
                        
                        trigger = SafetyOrderTrigger(
                            order_id=order.id,
                            position_id=position_id,
                            order_number=order.order_number,
                            trigger_price=order.trigger_price,
                            current_price=current_price,
                            target_quantity=order.target_quantity,
                            target_value=order.target_value
                        )
                        
                        # Execute the safety order
                        result = await self._execute_safety_order(position, order, current_price)
                        
                        if result['success']:
                            triggered.append(trigger)
                            
                            # Update position aggregates
                            await self._update_position_after_fill(
                                position_id=position_id,
                                fill_price=result['fill_price'],
                                fill_quantity=result['fill_quantity'],
                                fill_value=result['fill_value']
                            )
                            
                            logger.info(
                                f"🎯 Safety order {order.order_number} triggered | "
                                f"{position.symbol} @ ${current_price:.2f} | "
                                f"Filled @ ${result['fill_price']:.2f}"
                            )
                        
                        # Only trigger one SO per check cycle
                        break
            
        except Exception as e:
            logger.error(f"Error checking safety orders: {e}")
        
        return triggered
    
    def _should_trigger_safety_order(
        self,
        side: str,
        current_price: float,
        trigger_price: float
    ) -> bool:
        """Check if safety order should trigger based on current price."""
        if side == 'long':
            # For long: trigger when price drops to/below trigger price
            return current_price <= trigger_price
        else:
            # For short: trigger when price rises to/above trigger price
            return current_price >= trigger_price
    
    async def _execute_safety_order(
        self,
        position: DCAPosition,
        order: DCAOrder,
        current_price: float
    ) -> Dict[str, Any]:
        """Execute a safety order."""
        try:
            order_side = 'buy' if position.side == 'long' else 'sell'
            
            # Place market order
            order_result = await self.exchange.place_order(
                symbol=position.symbol,
                side=order_side,
                order_type='market',
                quantity=order.target_quantity
            )
            
            if not order_result:
                return {'success': False, 'error': 'No order result'}
            
            fill_price = order_result.get('average') or order_result.get('price') or current_price
            fill_quantity = order_result.get('filled') or order.target_quantity
            fill_value = fill_price * fill_quantity
            
            # Update order in database
            with DatabaseManager.session_scope() as session:
                db_order = session.query(DCAOrder).filter_by(id=order.id).first()
                if db_order:
                    db_order.status = 'filled'
                    db_order.fill_price = fill_price
                    db_order.fill_quantity = fill_quantity
                    db_order.fill_value = fill_value
                    db_order.fill_time = datetime.utcnow()
                    db_order.triggered_at = datetime.utcnow()
                    db_order.exchange_order_id = order_result.get('id')
                    session.commit()
            
            return {
                'success': True,
                'fill_price': fill_price,
                'fill_quantity': fill_quantity,
                'fill_value': fill_value
            }
            
        except Exception as e:
            logger.error(f"Safety order execution failed: {e}")
            
            # Mark order as failed
            with DatabaseManager.session_scope() as session:
                db_order = session.query(DCAOrder).filter_by(id=order.id).first()
                if db_order:
                    db_order.status = 'failed'
                    db_order.error_message = str(e)
                    db_order.retry_count += 1
                    session.commit()
            
            return {'success': False, 'error': str(e)}
    
    # ========================================================================
    # Position Updates
    # ========================================================================
    
    async def _update_position_after_fill(
        self,
        position_id: str,
        fill_price: float,
        fill_quantity: float,
        fill_value: float
    ):
        """Update position aggregates after an order fill."""
        with DatabaseManager.session_scope() as session:
            position = session.query(DCAPosition).filter_by(id=position_id).first()
            
            if not position:
                return
            
            # Calculate new average entry price (volume-weighted)
            old_total_qty = position.total_quantity
            old_total_value = position.total_invested
            
            new_total_qty = old_total_qty + fill_quantity
            new_total_value = old_total_value + fill_value
            
            if new_total_qty > 0:
                new_avg_price = new_total_value / new_total_qty
            else:
                new_avg_price = fill_price
            
            # Update position
            position.total_quantity = new_total_qty
            position.total_invested = new_total_value
            position.average_entry_price = new_avg_price
            position.filled_orders_count += 1
            position.updated_at = datetime.utcnow()
            
            # Recalculate TP/SL from new average
            config = DCAConfig(
                take_profit_percent=position.take_profit_percent,
                stop_loss_percent=position.stop_loss_percent
            )
            tp_price, sl_price = self._calculate_tp_sl(new_avg_price, position.side, config)
            
            position.take_profit_price = tp_price
            position.stop_loss_price = sl_price
            
            session.commit()
            
            logger.info(
                f"📊 Position updated | Avg: ${new_avg_price:.2f} | "
                f"Qty: {new_total_qty:.6f} | Invested: ${new_total_value:.2f} | "
                f"New TP: ${tp_price:.2f} | New SL: ${sl_price:.2f}"
            )
    
    def _calculate_tp_sl(
        self,
        avg_price: float,
        side: str,
        config: DCAConfig
    ) -> Tuple[float, float]:
        """Calculate TP and SL prices from average entry price."""
        if side == 'long':
            tp_price = avg_price * (1 + config.take_profit_percent / 100)
            sl_price = avg_price * (1 - config.stop_loss_percent / 100)
        else:
            tp_price = avg_price * (1 - config.take_profit_percent / 100)
            sl_price = avg_price * (1 + config.stop_loss_percent / 100)
        
        return tp_price, sl_price
    
    # ========================================================================
    # Position Closing
    # ========================================================================
    
    async def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_reason: str
    ) -> bool:
        """Close a DCA position."""
        try:
            with DatabaseManager.session_scope() as session:
                position = session.query(DCAPosition).filter_by(id=position_id).first()
                
                if not position or position.status != 'active':
                    return False
                
                # Calculate P&L
                if position.side == 'long':
                    pnl = (exit_price - position.average_entry_price) * position.total_quantity
                    pnl_percent = ((exit_price / position.average_entry_price) - 1) * 100
                else:
                    pnl = (position.average_entry_price - exit_price) * position.total_quantity
                    pnl_percent = ((position.average_entry_price / exit_price) - 1) * 100
                
                # Update position
                position.status = 'completed'
                position.exit_price = exit_price
                position.realized_pnl = pnl
                position.realized_pnl_percent = pnl_percent
                position.exit_reason = exit_reason
                position.closed_at = datetime.utcnow()
                
                # Cancel pending safety orders
                pending_orders = session.query(DCAOrder).filter_by(
                    dca_position_id=position_id,
                    status='pending'
                ).all()
                
                for order in pending_orders:
                    order.status = 'cancelled'
                
                session.commit()
                
                # Remove from active monitoring
                if position_id in self._active_positions:
                    del self._active_positions[position_id]
                
                logger.info(
                    f"{'✅' if pnl > 0 else '❌'} DCA position closed | "
                    f"{position.symbol} | Exit: ${exit_price:.2f} | "
                    f"P&L: ${pnl:.2f} ({pnl_percent:+.2f}%) | Reason: {exit_reason}"
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return False
    
    async def _cancel_position(self, position_id: str, reason: str):
        """Cancel a position (e.g., if base order fails)."""
        with DatabaseManager.session_scope() as session:
            position = session.query(DCAPosition).filter_by(id=position_id).first()
            if position:
                position.status = 'cancelled'
                position.exit_reason = reason
                position.closed_at = datetime.utcnow()
            
            # Cancel all orders
            orders = session.query(DCAOrder).filter_by(dca_position_id=position_id).all()
            for order in orders:
                if order.status == 'pending':
                    order.status = 'cancelled'
            
            session.commit()
        
        logger.warning(f"DCA position cancelled: {reason}")
    
    # ========================================================================
    # Monitoring
    # ========================================================================
    
    async def start_monitoring(self):
        """Start the DCA position monitoring loop."""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("DCA monitoring started")
    
    async def stop_monitoring(self):
        """Stop the DCA position monitoring loop."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("DCA monitoring stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop for DCA positions."""
        while self._running:
            try:
                await self._check_all_positions()
            except Exception as e:
                logger.error(f"DCA monitor loop error: {e}")
            
            await asyncio.sleep(self._check_interval)
    
    async def _check_all_positions(self):
        """Check all active DCA positions."""
        # Load active positions from database
        with DatabaseManager.session_scope() as session:
            positions = session.query(DCAPosition).filter_by(
                user_id=self.user_id,
                status='active'
            ).all()
            
            for position in positions:
                try:
                    # Get current price
                    current_price = await self._get_current_price(position.symbol)
                    
                    if not current_price:
                        continue
                    
                    # Check TP/SL
                    if self._check_tp_sl_trigger(position, current_price):
                        continue  # Position was closed
                    
                    # Check safety orders
                    await self.check_and_execute_safety_orders(position.id, current_price)
                    
                except Exception as e:
                    logger.error(f"Error checking position {position.id[:8]}: {e}")
    
    def _check_tp_sl_trigger(self, position: DCAPosition, current_price: float) -> bool:
        """Check if TP or SL should trigger. Returns True if position closed."""
        if position.side == 'long':
            if position.take_profit_price and current_price >= position.take_profit_price:
                asyncio.create_task(self.close_position(position.id, current_price, 'take_profit'))
                return True
            if position.stop_loss_price and current_price <= position.stop_loss_price:
                asyncio.create_task(self.close_position(position.id, current_price, 'stop_loss'))
                return True
        else:  # short
            if position.take_profit_price and current_price <= position.take_profit_price:
                asyncio.create_task(self.close_position(position.id, current_price, 'take_profit'))
                return True
            if position.stop_loss_price and current_price >= position.stop_loss_price:
                asyncio.create_task(self.close_position(position.id, current_price, 'stop_loss'))
                return True
        
        return False
    
    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        try:
            ticker = await self.exchange.exchange.fetch_ticker(symbol)
            return ticker.get('last')
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            return None
    
    # ========================================================================
    # Queries
    # ========================================================================
    
    def get_active_positions(self) -> List[DCAPosition]:
        """Get all active DCA positions for this user."""
        with DatabaseManager.session_scope() as session:
            return session.query(DCAPosition).filter_by(
                user_id=self.user_id,
                status='active'
            ).all()
    
    def get_position_with_orders(self, position_id: str) -> Optional[Dict[str, Any]]:
        """Get position with all its orders."""
        with DatabaseManager.session_scope() as session:
            position = session.query(DCAPosition).filter_by(id=position_id).first()
            
            if not position:
                return None
            
            orders = session.query(DCAOrder).filter_by(
                dca_position_id=position_id
            ).order_by(DCAOrder.order_number).all()
            
            return {
                'position': position,
                'orders': orders,
                'filled_count': len([o for o in orders if o.status == 'filled']),
                'pending_count': len([o for o in orders if o.status == 'pending'])
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get DCA statistics for this user."""
        with DatabaseManager.session_scope() as session:
            positions = session.query(DCAPosition).filter_by(user_id=self.user_id).all()
            
            completed = [p for p in positions if p.status == 'completed']
            active = [p for p in positions if p.status == 'active']
            
            total_pnl = sum(p.realized_pnl or 0 for p in completed)
            winning = [p for p in completed if (p.realized_pnl or 0) > 0]
            
            return {
                'total_positions': len(positions),
                'active_positions': len(active),
                'completed_positions': len(completed),
                'total_pnl': total_pnl,
                'win_rate': len(winning) / len(completed) if completed else 0,
                'avg_pnl_percent': sum(p.realized_pnl_percent or 0 for p in completed) / len(completed) if completed else 0
            }


# ============================================================================
# Factory Function
# ============================================================================

_dca_managers: Dict[str, DCAManager] = {}


def get_dca_manager(
    exchange_adapter: 'CCXTAdapter',
    user_id: str,
    config: Optional[DCAConfig] = None
) -> DCAManager:
    """Get or create DCA manager for a user."""
    if user_id not in _dca_managers:
        _dca_managers[user_id] = DCAManager(exchange_adapter, user_id, config)
    return _dca_managers[user_id]
