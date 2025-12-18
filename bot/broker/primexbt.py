"""PrimeXBT broker implementation."""

from typing import Dict, List, Optional
from datetime import datetime
import logging
import hmac
import hashlib
import time
import requests
import json

from bot.broker.base import BaseBroker

logger = logging.getLogger(__name__)


class PrimeXBTBroker(BaseBroker):
    """PrimeXBT trading broker implementation."""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """Initialize PrimeXBT broker."""
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # Set base URL
        if testnet:
            self.base_url = "https://api.testnet.primexbt.com"
        else:
            self.base_url = "https://api.primexbt.com"
            
        self.session = requests.Session()
        self.account_info = {}
        
        logger.info(f"Initialized PrimeXBT broker ({'testnet' if testnet else 'live'})")
    
    def _generate_signature(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        """Generate authentication headers for PrimeXBT API."""
        timestamp = str(int(time.time() * 1000))
        message = timestamp + method.upper() + path + body
        
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return {
            'X-API-KEY': self.api_key,
            'X-API-TIMESTAMP': timestamp,
            'X-API-SIGNATURE': signature,
            'Content-Type': 'application/json'
        }
    
    async def connect(self):
        """Test connection to PrimeXBT."""
        try:
            # Test with account info endpoint
            path = "/v1/account"
            headers = self._generate_signature("GET", path)
            
            response = self.session.get(
                f"{self.base_url}{path}",
                headers=headers
            )
            
            if response.status_code == 200:
                self.account_info = response.json()
                logger.info("Successfully connected to PrimeXBT")
                return True
            else:
                raise Exception(f"Connection failed: {response.text}")
                
        except Exception as e:
            logger.error(f"Failed to connect to PrimeXBT: {e}")
            raise
    
    async def get_balance(self) -> Dict:
        """Get account balance from PrimeXBT."""
        try:
            path = "/v1/account/balance"
            headers = self._generate_signature("GET", path)
            
            response = self.session.get(
                f"{self.base_url}{path}",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # PrimeXBT returns balance in BTC
                btc_balance = float(data.get('balance', 0))
                
                # Get BTC price to convert to USDT
                btc_price = await self._get_btc_price()
                usdt_balance = btc_balance * btc_price
                
                return {
                    'total_balance': usdt_balance,
                    'available_balance': usdt_balance * 0.9,  # Assume 90% available
                    'btc_balance': btc_balance,
                    'currencies': {'BTC': btc_balance}
                }
            else:
                raise Exception(f"Failed to get balance: {response.text}")
                
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            raise
    
    async def _get_btc_price(self) -> float:
        """Get current BTC price."""
        try:
            path = "/v1/market/ticker?symbol=BTC/USD"
            headers = self._generate_signature("GET", path)
            
            response = self.session.get(
                f"{self.base_url}{path}",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                return float(data.get('last', 50000))
            else:
                return 50000  # Default fallback
                
        except:
            return 50000
    
    def get_account_info(self) -> Dict:
        """Get account information."""
        # Return cached info or default
        if self.account_info:
            return {
                'total_balance': self.account_info.get('balance', 0) * 50000,  # Convert BTC to USDT estimate
                'available_balance': self.account_info.get('available', 0) * 50000,
                'margin_used': self.account_info.get('margin_used', 0) * 50000,
                'unrealized_pnl': 0,
                'positions_count': len(self.account_info.get('positions', [])),
                'orders_count': len(self.account_info.get('orders', []))
            }
        else:
            return {
                'total_balance': 10000,
                'available_balance': 10000,
                'margin_used': 0,
                'unrealized_pnl': 0,
                'positions_count': 0,
                'orders_count': 0
            }
    
    async def place_order(self, symbol: str, side: str, quantity: float,
                         order_type: str = "MARKET", price: Optional[float] = None,
                         leverage: int = 1, **kwargs) -> Dict:
        """Place order on PrimeXBT."""
        try:
            path = "/v1/order"
            
            # Convert symbol format (BTC/USDT -> BTCUSD)
            primexbt_symbol = symbol.replace('/', '').replace('USDT', 'USD')
            
            order_data = {
                'symbol': primexbt_symbol,
                'side': side.lower(),
                'type': order_type.lower(),
                'quantity': quantity,
                'leverage': leverage
            }
            
            if order_type.upper() == 'LIMIT':
                order_data['price'] = price
                
            body = json.dumps(order_data)
            headers = self._generate_signature("POST", path, body)
            
            response = self.session.post(
                f"{self.base_url}{path}",
                headers=headers,
                data=body
            )
            
            if response.status_code == 200:
                order = response.json()
                return {
                    'success': True,
                    'order_id': order.get('id'),
                    'status': order.get('status'),
                    'filled_quantity': order.get('filled', 0),
                    'average_price': order.get('avg_price', price or 0)
                }
            else:
                return {
                    'success': False,
                    'error': response.text
                }
                
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def cancel_order(self, order_id: str, symbol: str = None) -> Dict:
        """Cancel order on PrimeXBT."""
        try:
            path = f"/v1/order/{order_id}"
            headers = self._generate_signature("DELETE", path)
            
            response = self.session.delete(
                f"{self.base_url}{path}",
                headers=headers
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'message': 'Order cancelled'
                }
            else:
                return {
                    'success': False,
                    'error': response.text
                }
                
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_open_positions(self) -> List[Dict]:
        """Get open positions from PrimeXBT."""
        try:
            path = "/v1/positions"
            headers = self._generate_signature("GET", path)
            
            response = self.session.get(
                f"{self.base_url}{path}",
                headers=headers
            )
            
            if response.status_code == 200:
                positions = response.json()
                
                # Convert to standard format
                formatted_positions = []
                for pos in positions:
                    formatted_positions.append({
                        'id': pos.get('id'),
                        'symbol': pos.get('symbol'),
                        'side': pos.get('side'),
                        'size': pos.get('quantity'),
                        'entry_price': pos.get('entry_price'),
                        'current_price': pos.get('mark_price'),
                        'unrealized_pnl': pos.get('unrealized_pnl'),
                        'margin_used': pos.get('margin'),
                        'leverage': pos.get('leverage')
                    })
                
                return formatted_positions
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def get_open_orders(self) -> List[Dict]:
        """Get open orders from PrimeXBT."""
        try:
            path = "/v1/orders"
            headers = self._generate_signature("GET", path)
            
            response = self.session.get(
                f"{self.base_url}{path}",
                headers=headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            return []
    
    async def close_position(self, position_id: str) -> bool:
        """Close a position on PrimeXBT."""
        try:
            path = f"/v1/position/{position_id}/close"
            headers = self._generate_signature("POST", path)
            
            response = self.session.post(
                f"{self.base_url}{path}",
                headers=headers
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False
    
    def get_order_book(self, symbol: str) -> Dict:
        """Get order book from PrimeXBT."""
        try:
            # Convert symbol format
            primexbt_symbol = symbol.replace('/', '').replace('USDT', 'USD')
            
            path = f"/v1/market/orderbook?symbol={primexbt_symbol}"
            headers = self._generate_signature("GET", path)
            
            response = self.session.get(
                f"{self.base_url}{path}",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'bids': data.get('bids', []),
                    'asks': data.get('asks', []),
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return {
                    'bids': [],
                    'asks': [],
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting order book: {e}")
            return {
                'bids': [],
                'asks': [],
                'timestamp': datetime.now().isoformat()
            }
