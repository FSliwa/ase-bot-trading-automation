"""Live trading broker implementation using CCXT."""

from typing import Dict, List, Optional
from datetime import datetime
import logging

from bot.exchange_adapters.ccxt_adapter import CCXTAdapter
from bot.broker.base import BaseBroker

# NEW v3.0: Import core infrastructure modules
try:
    from bot.core import (
        TransactionManager, 
        PositionLockManager, 
        RetryHandler,
        with_retry,
        ComponentRateLimiter,
        SymbolNormalizer
    )
    CORE_MODULES_AVAILABLE = True
except ImportError:
    CORE_MODULES_AVAILABLE = False

logger = logging.getLogger(__name__)


class LiveBroker(BaseBroker):
    """Live trading broker using real exchange connections."""
    
    def __init__(self, exchange_name: str, api_key: str, api_secret: str, 
                 testnet: bool = False, futures: bool = False, margin: bool = False):
        """Initialize live broker with exchange credentials."""
        self.exchange_name = exchange_name
        self.testnet = testnet
        self.futures = futures
        self.margin = margin
        
        # Initialize CCXT adapter with futures/margin support
        self.client = CCXTAdapter(
            exchange_name=exchange_name,
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
            futures=futures,
            margin=margin
        )
        
        # NEW v3.0: Core infrastructure modules
        self.position_lock_manager = None
        self.transaction_manager = None
        self.retry_handler = None
        self.rate_limiter = None
        self.symbol_normalizer = None
        
        if CORE_MODULES_AVAILABLE:
            self.position_lock_manager = PositionLockManager()
            self.retry_handler = RetryHandler()
            self.rate_limiter = ComponentRateLimiter()
            self.symbol_normalizer = SymbolNormalizer()
            logger.info("✅ Core modules initialized for LiveBroker")
        
        logger.info(f"Initialized LiveBroker for {exchange_name} {'testnet' if testnet else 'live'} {'margin' if margin else 'futures' if futures else 'spot'}")
    
    async def connect(self):
        """Test connection to exchange."""
        try:
            # Load markets
            await self.client.exchange.load_markets()
            logger.info(f"Successfully connected to {self.exchange_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to {self.exchange_name}: {e}")
            raise
    
    async def get_balance(self) -> Dict:
        """Get account balance - enhanced for multiple quote currencies."""
        try:
            balance = await self.client.exchange.fetch_balance()
            
            # Priority list of quote currencies
            quote_currencies = ['USDT', 'USDC', 'USD', 'EUR', 'ZUSD', 'ZEUR']
            
            # Find the best available balance in a quote currency
            available_balance = 0
            used_currency = 'USDT'  # default
            
            # First, try 'free' balances
            for currency in quote_currencies:
                if currency in balance.get('free', {}) and balance['free'][currency] > 0:
                    available_balance = balance['free'][currency]
                    used_currency = currency
                    logger.debug(f"Found available balance in {currency}: {available_balance}")
                    break
            
            # Calculate total balance (convert all to USD equivalent)
            total_usd = 0
            for currency, amounts in balance.get('total', {}).items():
                if amounts > 0:
                    if currency in quote_currencies:
                        # Already in USD-equivalent
                        total_usd += amounts
                    elif currency.upper() in ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOT']:
                        # Try to convert major cryptos
                        try:
                            # Try different quote pairs
                            for quote in ['USDT', 'USDC', 'USD']:
                                try:
                                    ticker = await self.client.exchange.fetch_ticker(f"{currency}/{quote}")
                                    total_usd += amounts * ticker['last']
                                    break
                                except:
                                    continue
                        except:
                            pass  # Skip if can't convert
            
            logger.info(f"💰 LiveBroker balance: available={available_balance:.2f} {used_currency}, total≈${total_usd:.2f}")
            
            return {
                'total_balance': total_usd if total_usd > 0 else available_balance,
                'available_balance': available_balance,
                'currency': used_currency,
                'currencies': balance.get('total', {}),
                'free': balance.get('free', {})
            }
            
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            raise
    
    def get_account_info(self) -> Dict:
        """Get account information synchronously."""
        # For compatibility, return basic info
        # In production, this should cache async results
        return {
            'total_balance': 10000,  # Placeholder
            'available_balance': 10000,
            'margin_used': 0,
            'unrealized_pnl': 0,
            'positions_count': 0,
            'orders_count': 0
        }
    
    async def place_order(self, symbol: str, side: str, quantity: float,
                         order_type: str = "MARKET", price: Optional[float] = None,
                         stop_loss: Optional[float] = None,
                         take_profit: Optional[float] = None,
                         leverage: Optional[float] = None,
                         user_id: Optional[str] = None,
                         position_monitor = None,
                         use_oco: bool = True,  # L1 FIX: Enable OCO by default
                         **kwargs) -> Dict:
        """Place order on exchange with optional SL/TP and save position to DB.
        
        NEW v3.0: Uses position locking and retry logic for safety.
        L1 FIX: Uses OCO orders for hardware SL/TP protection on Binance SPOT.
        L4 FIX: Checks currency availability before trading.
        """
        logger.debug(f"LiveBroker.place_order: SL={stop_loss}, TP={take_profit}, kwargs={kwargs}")
        
        # Normalize symbol if available
        if self.symbol_normalizer:
            normalized = self.symbol_normalizer.normalize(symbol)
            symbol = normalized.internal  # Use internal format "BTC/USDT"
        
        # ========================================================================
        # L4 FIX: Check if user can trade this symbol with available balance
        # ========================================================================
        if hasattr(self.client, 'get_tradeable_balance_for_symbol'):
            try:
                trade_check = await self.client.get_tradeable_balance_for_symbol(symbol)
                if not trade_check.get('can_trade', True):
                    suggestion = trade_check.get('suggestion', 'Insufficient balance')
                    alt_pair = trade_check.get('alternative_pair')
                    
                    if alt_pair:
                        logger.warning(f"⚠️ L4 FIX: Cannot trade {symbol}. Suggestion: Use {alt_pair} instead")
                        # Could auto-switch to alternative pair here
                        # symbol = alt_pair  # Uncomment to auto-switch
                    else:
                        logger.warning(f"⚠️ L4 FIX: Cannot trade {symbol}. {suggestion}")
                        return {
                            'success': False, 
                            'error': f'Currency mismatch: {suggestion}',
                            'suggestion': suggestion,
                            'alternative_pair': alt_pair,
                        }
            except Exception as e:
                logger.debug(f"L4 check failed: {e}, continuing with order")
        
        # Check rate limit (using ComponentRateLimiter's can_proceed method)
        if self.rate_limiter:
            try:
                # Try async check first (legacy), then sync can_proceed
                if hasattr(self.rate_limiter, 'check'):
                    component_allowed = await self.rate_limiter.check("trading_engine")
                elif hasattr(self.rate_limiter, 'can_proceed'):
                    # Import Component enum if using ComponentRateLimiter
                    from bot.core.rate_limiter_v2 import Component
                    component_allowed = self.rate_limiter.can_proceed(Component.TRADING_ENGINE)
                else:
                    component_allowed = True
                    
                if not component_allowed:
                    logger.warning(f"🚫 Rate limit exceeded for trading_engine")
                    return {'success': False, 'error': 'Rate limit exceeded'}
            except Exception as e:
                logger.debug(f"Rate limiter check failed: {e}, allowing request")
                # Don't block trades if rate limiter fails
        
        async def _do_place_order():
            """Inner function for retry logic.
            
            L1 FIX: Uses OCO orders for hardware SL/TP protection on Binance SPOT.
            """
            # Check if we should use OCO (hardware SL/TP)
            is_spot_mode = not self.futures and not getattr(self.client, 'futures', False)
            should_use_oco = (
                use_oco 
                and is_spot_mode 
                and side.lower() == 'buy'  # Only for opening long positions
                and (stop_loss or take_profit)
                and hasattr(self.client, 'place_order_with_oco')
            )
            
            if should_use_oco:
                # L1 FIX: Use OCO for hardware protection
                logger.info(f"🛡️ L1 FIX: Using OCO order for hardware SL/TP protection on {symbol}")
                oco_result = await self.client.place_order_with_oco(
                    symbol=symbol,
                    side=side.lower(),
                    quantity=quantity,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    order_type=order_type.lower(),
                    price=price,
                )
                
                if oco_result.get('success') and oco_result.get('main_order'):
                    main_order = oco_result['main_order']
                    if oco_result.get('oco_order'):
                        logger.info(f"✅ L1 FIX: OCO protection active for {symbol}")
                    return main_order
                elif oco_result.get('main_order'):
                    # Main order succeeded but OCO failed - log warning but return success
                    logger.warning(f"⚠️ L1 FIX: OCO failed but main order succeeded. Position will use software SL/TP.")
                    return oco_result['main_order']
                else:
                    raise Exception(f"OCO order failed: {oco_result.get('error')}")
            
            # Standard order (non-OCO)
            return await self.client.place_order(
                symbol=symbol,
                side=side.lower(),
                order_type=order_type.lower(),
                quantity=quantity,
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                leverage=int(leverage) if leverage else None
            )
        
        try:
            # NEW v3.0: Use position lock to prevent race conditions
            if self.position_lock_manager and CORE_MODULES_AVAILABLE:
                async with self.position_lock_manager.acquire_lock(symbol, f"broker_{user_id or 'system'}", timeout=30.0) as locked:
                    # P0-4 FIX: Block order if lock acquisition fails to prevent race conditions
                    if not locked:
                        logger.error(f"🚫 Could not acquire lock for {symbol}, aborting to prevent race condition")
                        return {'success': False, 'error': f'Position lock acquisition failed for {symbol}'}
                    
                    # Use retry handler for critical order placement
                    if self.retry_handler:
                        order = await self.retry_handler.execute(
                            operation=_do_place_order,
                            operation_name=f"place_order_{symbol}",
                        )
                    else:
                        order = await _do_place_order()
                    
                    return await self._process_order_result(
                        order=order,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        price=price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        leverage=leverage,
                        user_id=user_id,
                        position_monitor=position_monitor
                    )
            else:
                # Fallback without locking
                order = await _do_place_order()
                return await self._process_order_result(
                    order=order,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    leverage=leverage,
                    user_id=user_id,
                    position_monitor=position_monitor
                )
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _process_order_result(self, order, symbol: str, side: str, quantity: float,
                                     price: Optional[float], stop_loss: Optional[float],
                                     take_profit: Optional[float], leverage: Optional[float],
                                     user_id: Optional[str], position_monitor) -> Dict:
        """Process order result and save to DB."""
        # Get executed price
        executed_price = getattr(order, 'average', price or 0) or 0
        if executed_price == 0:
            try:
                ticker = await self.client.exchange.fetch_ticker(symbol)
                executed_price = ticker['last']
            except:
                pass
        
        # Determine position side for DB
        position_side = 'long' if side.lower() == 'buy' else 'short'
        
        # Save position to database
        if executed_price > 0:
            await self._save_position_to_db(
                symbol=symbol,
                side=position_side,
                quantity=quantity,
                entry_price=executed_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                leverage=leverage or 1,
                user_id=user_id
            )
            
            # Also add to position monitor if available
            if position_monitor:
                position_monitor.add_position(
                    symbol=symbol,
                    side=position_side,
                    entry_price=executed_price,
                    quantity=quantity,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    user_id=user_id
                )
                logger.info(f"📍 Added to position monitor: {symbol}")
        
        return {
            'success': True,
            'order_id': order.id,
            'status': order.status,
            'filled_quantity': getattr(order, 'filled', 0) or 0,
            'average_price': executed_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit
        }
    
    async def _save_position_to_db(self, symbol: str, side: str, quantity: float,
                                    entry_price: float, stop_loss: Optional[float],
                                    take_profit: Optional[float], leverage: float,
                                    user_id: Optional[str]):
        """Save opened position to database for tracking."""
        try:
            from bot.db import DatabaseManager, Position
            from datetime import datetime
            
            with DatabaseManager.session_scope() as session:
                # Check if position already exists
                existing = session.query(Position).filter(
                    Position.symbol == symbol,
                    Position.status == 'OPEN'
                )
                if user_id:
                    existing = existing.filter(Position.user_id == user_id)
                existing = existing.first()
                
                if existing:
                    # Update existing position (average entry)
                    old_total = existing.quantity * existing.entry_price
                    new_total = quantity * entry_price
                    new_quantity = existing.quantity + quantity
                    new_entry = (old_total + new_total) / new_quantity if new_quantity > 0 else entry_price
                    
                    existing.quantity = new_quantity
                    existing.entry_price = new_entry
                    existing.stop_loss = stop_loss
                    existing.take_profit = take_profit
                    existing.updated_at = datetime.utcnow()
                    
                    logger.info(f"📊 Updated position in DB: {symbol} | Qty: {new_quantity:.6f} | Avg Entry: {new_entry:.4f}")
                else:
                    # Create new position
                    position = Position(
                        user_id=user_id,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        entry_price=entry_price,
                        current_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        leverage=leverage,
                        status='OPEN',
                        unrealized_pnl=0.0,
                        realized_pnl=0.0,
                        margin_used=quantity * entry_price / leverage if leverage > 0 else quantity * entry_price,
                        strategy='AI_SIGNAL',
                        entry_time=datetime.utcnow()
                    )
                    session.add(position)
                    
                    logger.info(f"💾 Saved position to DB: {symbol} | {side.upper()} | Qty: {quantity:.6f} | Entry: {entry_price:.4f} | SL: {stop_loss} | TP: {take_profit}")
                
                session.commit()
                
        except Exception as e:
            logger.error(f"Failed to save position to DB: {e}")
    
    async def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """Cancel order."""
        try:
            result = await self.client.exchange.cancel_order(order_id, symbol)
            return {
                'success': True,
                'message': 'Order cancelled'
            }
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_open_positions(self) -> List[Dict]:
        """Get open positions."""
        # This needs to be async in production
        # For now return empty list
        return []
    
    def get_open_orders(self) -> List[Dict]:
        """Get open orders."""
        # This needs to be async in production
        # For now return empty list
        return []
    
    async def close_position(self, symbol: str) -> bool:
        """Close a position by placing opposite market order."""
        try:
            # Get current position for symbol
            positions = await self.client.get_positions(symbol)
            
            if not positions:
                logger.warning(f"No position found for {symbol}")
                return False
            
            for pos in positions:
                # Determine opposite side
                close_side = 'sell' if pos.side.lower() == 'long' else 'buy'
                
                # Place reduce-only market order
                logger.info(f"Closing position: {symbol} {pos.side} qty={pos.quantity}")
                
                await self.client.place_order(
                    symbol=symbol,
                    side=close_side,
                    order_type='market',
                    quantity=pos.quantity,
                    reduce_only=True
                )
                
                logger.info(f"✅ Position closed: {symbol}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}")
            return False
    
    def get_order_book(self, symbol: str) -> Dict:
        """Get order book (synchronous for compatibility)."""
        # This should cache async results in production
        return {
            'bids': [],
            'asks': [],
            'timestamp': datetime.now().isoformat()
        }

    async def get_positions(self, symbol: Optional[str] = None):
        """Get open positions (delegates to CCXT adapter)."""
        return await self.client.get_positions(symbol)

    async def get_spot_balances(self) -> List[str]:
        """Get spot balances (delegates to CCXT adapter)."""
        return await self.client.get_spot_balances()