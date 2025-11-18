"""Base broker interface."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class BaseBroker(ABC):
    """Abstract base class for all broker implementations."""
    
    @abstractmethod
    def get_account_info(self) -> Dict:
        """Get account information."""
        pass
    
    @abstractmethod
    async def place_order(self, symbol: str, side: str, quantity: float,
                         order_type: str = "MARKET", price: Optional[float] = None,
                         **kwargs) -> Dict:
        """Place an order."""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """Cancel an order."""
        pass
    
    @abstractmethod
    def get_open_positions(self) -> List[Dict]:
        """Get list of open positions."""
        pass
    
    @abstractmethod
    def get_open_orders(self) -> List[Dict]:
        """Get list of open orders."""
        pass
    
    @abstractmethod
    async def close_position(self, position_id: str) -> bool:
        """Close a position."""
        pass
    
    @abstractmethod
    def get_order_book(self, symbol: str) -> Dict:
        """Get order book for a symbol."""
        pass
