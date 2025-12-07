from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .broker.paper import OrderFill, Position


@dataclass
class Trade:
    """Completed trade with entry and exit."""
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    side: str  # "buy" or "sell"
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_percent: float


@dataclass
class TradingStats:
    """Professional trading statistics."""
    # Basic metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # P&L metrics
    total_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    
    # Risk metrics
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    
    # Average metrics
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_trade_duration: float = 0.0  # minutes
    avg_win_percent: float = 0.0
    avg_loss_percent: float = 0.0
    
    # Position metrics
    largest_win: float = 0.0
    largest_loss: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    
    # Portfolio metrics
    starting_balance: float = 10000.0
    current_balance: float = 10000.0
    roi: float = 0.0
    roi_percent: float = 0.0
    
    # Risk/Reward
    avg_risk_reward_ratio: float = 0.0
    expectancy: float = 0.0
    
    # Activity
    total_volume: float = 0.0
    active_days: int = 0
    trades_per_day: float = 0.0


class StatsCalculator:
    def __init__(self, starting_balance: float = 10000.0):
        self.starting_balance = starting_balance
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = [starting_balance]
        
    def add_closed_trade(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        side: str,
        entry_time: Optional[datetime] = None,
        exit_time: Optional[datetime] = None,
    ) -> None:
        """Record a completed trade."""
        entry_time = entry_time or datetime.now()
        exit_time = exit_time or datetime.now()
        
        # Calculate P&L
        if side == "buy":
            pnl = (exit_price - entry_price) * quantity
            pnl_percent = ((exit_price - entry_price) / entry_price) * 100
        else:  # sell/short
            pnl = (entry_price - exit_price) * quantity
            pnl_percent = ((entry_price - exit_price) / exit_price) * 100
            
        trade = Trade(
            symbol=symbol,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            side=side,
            entry_time=entry_time,
            exit_time=exit_time,
            pnl=pnl,
            pnl_percent=pnl_percent,
        )
        
        self.trades.append(trade)
        self.equity_curve.append(self.equity_curve[-1] + pnl)
        
    def calculate_stats(self) -> TradingStats:
        """Calculate comprehensive trading statistics."""
        stats = TradingStats(starting_balance=self.starting_balance)
        
        if not self.trades:
            return stats
            
        # Basic counts
        stats.total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t.realized_pnl > 0]
        losing_trades = [t for t in self.trades if t.realized_pnl < 0]
        
        stats.winning_trades = len(winning_trades)
        stats.losing_trades = len(losing_trades)
        stats.win_rate = (stats.winning_trades / stats.total_trades * 100) if stats.total_trades > 0 else 0
        
        # P&L calculations
        stats.total_pnl = sum(t.realized_pnl for t in self.trades)
        stats.net_pnl = stats.total_pnl - stats.total_fees
        stats.current_balance = self.starting_balance + stats.net_pnl
        stats.roi = stats.net_pnl
        stats.roi_percent = (stats.net_pnl / self.starting_balance * 100) if self.starting_balance > 0 else 0
        
        # Win/Loss averages
        if winning_trades:
            stats.avg_win = sum(t.realized_pnl for t in winning_trades) / len(winning_trades)
            stats.avg_win_percent = sum(t.pnl_percent for t in winning_trades) / len(winning_trades)
            stats.largest_win = max(t.realized_pnl for t in winning_trades)
            
        if losing_trades:
            stats.avg_loss = sum(t.realized_pnl for t in losing_trades) / len(losing_trades)
            stats.avg_loss_percent = sum(t.pnl_percent for t in losing_trades) / len(losing_trades)
            stats.largest_loss = min(t.realized_pnl for t in losing_trades)
            
        # Profit factor
        total_wins = sum(t.realized_pnl for t in winning_trades) if winning_trades else 0
        total_losses = abs(sum(t.realized_pnl for t in losing_trades)) if losing_trades else 1
        stats.profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Expectancy
        if stats.total_trades > 0:
            win_prob = stats.win_rate / 100
            loss_prob = 1 - win_prob
            stats.expectancy = (win_prob * stats.avg_win) + (loss_prob * stats.avg_loss)
            
        # Risk/Reward ratio
        if stats.avg_loss < 0:
            stats.avg_risk_reward_ratio = abs(stats.avg_win / stats.avg_loss)
            
        # Consecutive wins/losses
        current_wins = 0
        current_losses = 0
        
        for trade in self.trades:
            if trade.realized_pnl > 0:
                current_wins += 1
                current_losses = 0
                stats.max_consecutive_wins = max(stats.max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                stats.max_consecutive_losses = max(stats.max_consecutive_losses, current_losses)
                
        # Drawdown calculation
        peak = self.starting_balance
        max_dd = 0
        max_dd_percent = 0
        
        for equity in self.equity_curve:
            if equity > peak:
                peak = equity
            dd = peak - equity
            dd_percent = (dd / peak * 100) if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                max_dd_percent = dd_percent
                
        stats.max_drawdown = max_dd
        stats.max_drawdown_percent = max_dd_percent
        
        # Sharpe ratio (simplified - assumes 0% risk-free rate)
        if len(self.equity_curve) > 1:
            returns = []
            for i in range(1, len(self.equity_curve)):
                ret = (self.equity_curve[i] - self.equity_curve[i-1]) / self.equity_curve[i-1]
                returns.append(ret)
                
            if returns:
                avg_return = sum(returns) / len(returns)
                std_dev = math.sqrt(sum((r - avg_return) ** 2 for r in returns) / len(returns))
                # Annualized Sharpe (assuming 252 trading days)
                stats.sharpe_ratio = (avg_return / std_dev * math.sqrt(252)) if std_dev > 0 else 0
                
        # Volume and activity
        stats.total_volume = sum(t.quantity * t.entry_price for t in self.trades)
        
        # Trade duration
        durations = [(t.exit_time - t.entry_time).total_seconds() / 60 for t in self.trades]
        stats.avg_trade_duration = sum(durations) / len(durations) if durations else 0
        
        return stats
        
    def get_equity_curve(self) -> List[float]:
        """Get the equity curve for charting."""
        return self.equity_curve.copy()
