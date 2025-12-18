"""
Spread-Aware P&L Calculator - Accurate P&L with bid/ask spread.

Calculates true P&L by accounting for:
1. Bid/Ask spread
2. Trading fees
3. Slippage estimation
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SpreadData:
    """Bid/Ask spread data for a symbol."""
    symbol: str
    bid: float
    ask: float
    timestamp: datetime = None
    
    @property
    def spread(self) -> float:
        """Absolute spread."""
        return self.ask - self.bid
    
    @property
    def spread_pct(self) -> float:
        """Spread as percentage of mid price."""
        mid = (self.bid + self.ask) / 2
        return (self.spread / mid * 100) if mid > 0 else 0
    
    @property
    def mid_price(self) -> float:
        """Mid price between bid and ask."""
        return (self.bid + self.ask) / 2


@dataclass
class FeeStructure:
    """Trading fee structure."""
    maker_fee_pct: float = 0.1    # 0.1% maker fee
    taker_fee_pct: float = 0.1    # 0.1% taker fee
    funding_rate_pct: float = 0.0  # For perpetuals
    
    @classmethod
    def binance_spot(cls) -> 'FeeStructure':
        return cls(maker_fee_pct=0.1, taker_fee_pct=0.1)
    
    @classmethod
    def binance_futures(cls) -> 'FeeStructure':
        return cls(maker_fee_pct=0.02, taker_fee_pct=0.04)
    
    @classmethod
    def kraken_spot(cls) -> 'FeeStructure':
        return cls(maker_fee_pct=0.16, taker_fee_pct=0.26)


@dataclass
class PnLResult:
    """Comprehensive P&L calculation result."""
    gross_pnl: float           # P&L before fees
    net_pnl: float             # P&L after all fees
    fee_cost: float            # Total fees paid
    spread_cost: float         # Cost from spread
    slippage_cost: float       # Estimated slippage cost
    effective_entry: float     # Effective entry price (with spread)
    effective_exit: float      # Effective exit price (with spread)
    roi_gross_pct: float       # Gross ROI %
    roi_net_pct: float         # Net ROI %
    breakeven_price: float     # Price needed to break even


class SpreadAwarePnL:
    """
    Calculates accurate P&L accounting for spread, fees, and slippage.
    
    Usage:
        calculator = SpreadAwarePnL()
        
        # When opening position, record actual spread
        calculator.record_entry(
            symbol="BTC/USDT",
            side="long",
            quantity=0.1,
            entry_price=50000,
            spread_data=SpreadData(bid=49990, ask=50010)
        )
        
        # Calculate current P&L
        pnl = calculator.calculate_pnl(
            symbol="BTC/USDT",
            current_spread=SpreadData(bid=51000, ask=51020),
            quantity=0.1,
            side="long",
            entry_price=50000
        )
    """
    
    # Default slippage estimates by order size (USD)
    SLIPPAGE_ESTIMATES = {
        1000: 0.01,    # 0.01% for small orders
        10000: 0.03,   # 0.03% for medium orders
        50000: 0.08,   # 0.08% for large orders
        100000: 0.15,  # 0.15% for very large orders
    }
    
    def __init__(self, fee_structure: FeeStructure = None):
        self.fee_structure = fee_structure or FeeStructure.binance_spot()
        self._entry_spreads: Dict[str, SpreadData] = {}
    
    def record_entry(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        spread_data: SpreadData = None
    ):
        """Record entry spread for accurate exit P&L calculation."""
        if spread_data:
            self._entry_spreads[symbol] = spread_data
    
    def estimate_slippage_pct(self, order_size_usd: float) -> float:
        """Estimate slippage percentage based on order size."""
        for size, slippage in sorted(self.SLIPPAGE_ESTIMATES.items()):
            if order_size_usd <= size:
                return slippage
        return 0.2  # Default for very large orders
    
    def calculate_effective_entry_price(
        self,
        entry_price: float,
        spread_data: SpreadData,
        side: str,
        is_market_order: bool = True
    ) -> float:
        """
        Calculate effective entry price accounting for spread.
        
        For market orders:
        - Long: pay the ask (higher price)
        - Short: receive the bid (lower price)
        
        For limit orders (maker):
        - Can get mid price or better
        """
        if not spread_data or not is_market_order:
            return entry_price
        
        if side.lower() == 'long':
            # Buy at ask
            return spread_data.ask
        else:
            # Short: sell at bid
            return spread_data.bid
    
    def calculate_effective_exit_price(
        self,
        current_price: float,
        spread_data: SpreadData,
        side: str,
        is_market_order: bool = True
    ) -> float:
        """
        Calculate effective exit price accounting for spread.
        
        For closing:
        - Close long (sell): receive bid
        - Close short (buy back): pay ask
        """
        if not spread_data or not is_market_order:
            return current_price
        
        if side.lower() == 'long':
            # Close long = sell at bid
            return spread_data.bid
        else:
            # Close short = buy at ask
            return spread_data.ask
    
    def calculate_pnl(
        self,
        side: str,
        quantity: float,
        entry_price: float,
        current_price: float = None,
        entry_spread: SpreadData = None,
        exit_spread: SpreadData = None,
        leverage: float = 1.0,
        is_market_order: bool = True
    ) -> PnLResult:
        """
        Calculate comprehensive P&L with all costs.
        
        Args:
            side: 'long' or 'short'
            quantity: Position size
            entry_price: Recorded entry price
            current_price: Current/exit price (or None to use spread mid)
            entry_spread: Spread data at entry
            exit_spread: Spread data at exit/current
            leverage: Leverage used
            is_market_order: Whether using market orders
            
        Returns:
            PnLResult with all cost breakdowns
        """
        # Determine effective prices
        if entry_spread:
            effective_entry = self.calculate_effective_entry_price(
                entry_price, entry_spread, side, is_market_order
            )
        else:
            effective_entry = entry_price
        
        if exit_spread:
            effective_exit = self.calculate_effective_exit_price(
                current_price or exit_spread.mid_price,
                exit_spread, side, is_market_order
            )
        else:
            effective_exit = current_price or entry_price
        
        # Calculate position value
        entry_value = quantity * effective_entry
        exit_value = quantity * effective_exit
        
        # Calculate gross P&L (before fees)
        if side.lower() == 'long':
            gross_pnl = (effective_exit - effective_entry) * quantity
        else:
            gross_pnl = (effective_entry - effective_exit) * quantity
        
        # Calculate fees
        entry_fee = entry_value * (self.fee_structure.taker_fee_pct / 100)
        exit_fee = exit_value * (self.fee_structure.taker_fee_pct / 100)
        total_fees = entry_fee + exit_fee
        
        # Calculate spread cost
        spread_cost = 0
        if entry_spread:
            spread_cost += entry_spread.spread * quantity / 2  # Half spread at entry
        if exit_spread:
            spread_cost += exit_spread.spread * quantity / 2   # Half spread at exit
        
        # Estimate slippage cost
        slippage_pct = self.estimate_slippage_pct(max(entry_value, exit_value))
        slippage_cost = (entry_value + exit_value) * (slippage_pct / 100) / 2
        
        # Calculate net P&L
        net_pnl = gross_pnl - total_fees
        
        # ROI calculations (on margin/capital used)
        margin_used = entry_value / leverage if leverage > 0 else entry_value
        roi_gross_pct = (gross_pnl / margin_used * 100) if margin_used > 0 else 0
        roi_net_pct = (net_pnl / margin_used * 100) if margin_used > 0 else 0
        
        # Breakeven price calculation
        total_cost_pct = (total_fees / entry_value * 100) if entry_value > 0 else 0
        if side.lower() == 'long':
            breakeven_price = effective_entry * (1 + total_cost_pct / 100)
        else:
            breakeven_price = effective_entry * (1 - total_cost_pct / 100)
        
        return PnLResult(
            gross_pnl=round(gross_pnl, 4),
            net_pnl=round(net_pnl, 4),
            fee_cost=round(total_fees, 4),
            spread_cost=round(spread_cost, 4),
            slippage_cost=round(slippage_cost, 4),
            effective_entry=round(effective_entry, 8),
            effective_exit=round(effective_exit, 8),
            roi_gross_pct=round(roi_gross_pct, 2),
            roi_net_pct=round(roi_net_pct, 2),
            breakeven_price=round(breakeven_price, 8)
        )
    
    def calculate_breakeven_move_pct(
        self,
        entry_price: float,
        leverage: float = 1.0,
        include_spread_estimate: float = 0.1  # Estimated spread %
    ) -> float:
        """
        Calculate minimum price move % needed to break even.
        
        Accounts for:
        - Entry and exit fees
        - Estimated spread
        
        Returns:
            Minimum price move % to break even
        """
        # Round trip fees
        total_fee_pct = self.fee_structure.taker_fee_pct * 2
        
        # Spread cost (entry + exit)
        spread_cost_pct = include_spread_estimate
        
        # Total cost
        total_cost_pct = total_fee_pct + spread_cost_pct
        
        return total_cost_pct
    
    def get_minimum_profitable_move(
        self,
        entry_price: float,
        quantity: float,
        target_profit_usd: float,
        side: str,
        leverage: float = 1.0
    ) -> Tuple[float, float]:
        """
        Calculate minimum price move for target profit.
        
        Returns:
            Tuple of (target_price, required_move_pct)
        """
        entry_value = entry_price * quantity
        
        # Calculate fees at current price
        round_trip_fee = entry_value * (self.fee_structure.taker_fee_pct / 100) * 2
        
        # Required gross profit
        required_gross = target_profit_usd + round_trip_fee
        
        # Required price change
        required_change = required_gross / quantity
        
        if side.lower() == 'long':
            target_price = entry_price + required_change
        else:
            target_price = entry_price - required_change
        
        move_pct = abs(required_change / entry_price * 100)
        
        return target_price, move_pct


# Global instance
_pnl_calculator: Optional[SpreadAwarePnL] = None


def get_spread_aware_pnl(fee_structure: FeeStructure = None) -> SpreadAwarePnL:
    """Get or create global P&L calculator."""
    global _pnl_calculator
    if _pnl_calculator is None:
        _pnl_calculator = SpreadAwarePnL(fee_structure)
    return _pnl_calculator
