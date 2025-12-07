"""Live trading broker implementation using CCXT."""

from typing import Dict, List, Optional
from datetime import datetime
import logging

from bot.http.ccxt_adapter import CCXTAdapter
from bot.broker.base import BaseBroker

logger = logging.getLogger(__name__)


class LiveBroker(BaseBroker):
    """Live trading broker using real exchange connections."""
    
    def __init__(self, exchange_name: str, api_key: str, api_secret: str, testnet: bool = False):
        """Initialize live broker with exchange credentials."""
        self.exchange_name = exchange_name
        self.testnet = testnet
        
        # Initialize CCXT adapter
        self.client = CCXTAdapter(
            exchange_name=exchange_name,
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet
        )
        
        logger.info(f"Initialized LiveBroker for {exchange_name} {'testnet' if testnet else 'live'}")
    
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
        """Get account balance."""
        try:
            balance = await self.client.exchange.fetch_balance()
            
            # Calculate total balance in USDT
            total_usdt = 0
            for currency, amounts in balance['total'].items():
                if amounts > 0:
                    if currency == 'USDT':
                        total_usdt += amounts
                    else:
                        # Try to get conversion rate
                        try:
                            ticker = await self.client.exchange.fetch_ticker(f"{currency}/USDT")
                            total_usdt += amounts * ticker['last']
                        except:
                            # Skip if can't convert
                            pass
            
            return {
                'total_balance': total_usdt,
                'available_balance': balance['free'].get('USDT', 0),
                'currencies': balance['total']
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
                         **kwargs) -> Dict:
        """Place order on exchange."""
        try:
            # Convert order type to CCXT format
            ccxt_type = order_type.lower()
            ccxt_side = side.lower()
            
            # Place order
            if ccxt_type == 'market':
                order = await self.client.exchange.create_order(
                    symbol=symbol,
                    type=ccxt_type,
                    side=ccxt_side,
                    amount=quantity
                )
            else:
                order = await self.client.exchange.create_order(
                    symbol=symbol,
                    type=ccxt_type,
                    side=ccxt_side,
                    amount=quantity,
                    price=price
                )
            
            return {
                'success': True,
                'order_id': order['id'],
                'status': order['status'],
                'filled_quantity': order.get('filled', 0),
                'average_price': order.get('average', price or 0)
            }
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
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
    
    async def close_position(self, position_id: str) -> bool:
        """Close a position."""
        # Implementation depends on exchange
        # For futures, this would place a reduce-only order
        logger.warning("Close position not implemented for live broker")
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