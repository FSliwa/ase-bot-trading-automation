"""
Enhanced Trading Statistics Calculator with Professional Metrics
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from bot.db import DatabaseManager


@dataclass
class ProfessionalStats:
    """Professional trading statistics"""
    # Basic metrics
    current_balance: float = 0.0
    starting_balance: float = 10000.0
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    
    # Performance metrics
    roi_percent: float = 0.0
    total_return_percent: float = 0.0
    annualized_return_percent: float = 0.0
    
    # Risk metrics
    max_drawdown_percent: float = 0.0
    max_drawdown_duration_days: int = 0
    current_drawdown_percent: float = 0.0
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    
    # Trade metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate_percent: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    
    # Advanced metrics
    average_win: float = 0.0
    average_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    average_trade: float = 0.0
    
    # Volatility metrics
    volatility_annual_percent: float = 0.0
    var_95_percent: float = 0.0  # Value at Risk 95%
    cvar_95_percent: float = 0.0  # Conditional VaR 95%
    
    # Consistency metrics
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    
    # Time-based metrics
    trading_days: int = 0
    avg_trades_per_day: float = 0.0
    avg_holding_time_hours: float = 0.0
    
    # Recovery metrics
    recovery_factor: float = 0.0  # Total return / Max drawdown
    ulcer_index: float = 0.0
    
    # Additional professional metrics
    kelly_percentage: float = 0.0
    optimal_f: float = 0.0
    sterling_ratio: Optional[float] = None
    burke_ratio: Optional[float] = None


class EnhancedStatsCalculator:
    """Enhanced statistics calculator with professional metrics"""
    
    def __init__(self):
        self.db = DatabaseManager()
    
    def calculate_stats(self, start_date: Optional[datetime] = None,
                       end_date: Optional[datetime] = None) -> ProfessionalStats:
        """Calculate comprehensive trading statistics"""
        
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)  # Default to last 30 days
        
        with DatabaseManager() as db:
            # Get closed positions (completed trades)
            closed_positions = db.session.query(db.Position).filter(
                db.Position.status == "CLOSED",
                db.Position.exit_time >= start_date,
                db.Position.exit_time <= end_date
            ).order_by(db.Position.exit_time).all()
            
            # Get current open positions
            open_positions = db.get_open_positions()
            
            # Calculate basic metrics
            stats = self._calculate_basic_metrics(closed_positions, open_positions)
            
            # Calculate performance metrics
            self._calculate_performance_metrics(stats, closed_positions, start_date, end_date)
            
            # Calculate risk metrics
            self._calculate_risk_metrics(stats, closed_positions)
            
            # Calculate trade metrics
            self._calculate_trade_metrics(stats, closed_positions)
            
            # Calculate advanced metrics
            self._calculate_advanced_metrics(stats, closed_positions)
            
            # Calculate volatility metrics
            self._calculate_volatility_metrics(stats, closed_positions, start_date, end_date)
            
            # Calculate consistency metrics
            self._calculate_consistency_metrics(stats, closed_positions)
            
            # Calculate time-based metrics
            self._calculate_time_metrics(stats, closed_positions, start_date, end_date)
            
            # Calculate recovery metrics
            self._calculate_recovery_metrics(stats, closed_positions)
            
            return stats
    
    def _calculate_basic_metrics(self, closed_positions: List, open_positions: List) -> ProfessionalStats:
        """Calculate basic P&L metrics"""
        
        # Calculate realized P&L from closed positions
        realized_pnl = sum(pos.realized_pnl for pos in closed_positions)
        
        # Calculate unrealized P&L from open positions
        unrealized_pnl = sum(pos.unrealized_pnl for pos in open_positions)
        
        # Current balance calculation (simplified)
        starting_balance = 10000.0  # Should be fetched from account history
        current_balance = starting_balance + realized_pnl
        
        total_pnl = realized_pnl + unrealized_pnl
        roi_percent = (total_pnl / starting_balance) * 100 if starting_balance > 0 else 0
        
        return ProfessionalStats(
            current_balance=current_balance,
            starting_balance=starting_balance,
            total_pnl=total_pnl,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            roi_percent=roi_percent
        )
    
    def _calculate_performance_metrics(self, stats: ProfessionalStats, 
                                     closed_positions: List,
                                     start_date: datetime, end_date: datetime):
        """Calculate performance metrics"""
        
        if not closed_positions:
            return
        
        # Total return
        stats.total_return_percent = stats.roi_percent
        
        # Annualized return
        days_elapsed = (end_date - start_date).days
        if days_elapsed > 0:
            years = days_elapsed / 365.25
            if years > 0 and stats.starting_balance > 0:
                final_value = stats.starting_balance + stats.total_pnl
                stats.annualized_return_percent = (
                    (final_value / stats.starting_balance) ** (1 / years) - 1
                ) * 100
    
    def _calculate_risk_metrics(self, stats: ProfessionalStats, closed_positions: List):
        """Calculate risk metrics including drawdown"""
        
        if not closed_positions:
            return
        
        # Calculate equity curve
        equity_curve = [stats.starting_balance]
        running_balance = stats.starting_balance
        
        for pos in closed_positions:
            running_balance += pos.realized_pnl
            equity_curve.append(running_balance)
        
        # Calculate drawdowns
        peak = equity_curve[0]
        max_drawdown = 0
        max_dd_duration = 0
        current_dd_duration = 0
        drawdown_start = None
        
        for i, equity in enumerate(equity_curve):
            if equity > peak:
                peak = equity
                current_dd_duration = 0
                drawdown_start = None
            else:
                if drawdown_start is None:
                    drawdown_start = i
                current_dd_duration = i - drawdown_start
                
                drawdown = (peak - equity) / peak * 100
                max_drawdown = max(max_drawdown, drawdown)
                max_dd_duration = max(max_dd_duration, current_dd_duration)
        
        stats.max_drawdown_percent = max_drawdown
        stats.max_drawdown_duration_days = max_dd_duration
        
        # Current drawdown
        current_equity = equity_curve[-1]
        current_peak = max(equity_curve)
        if current_peak > 0:
            stats.current_drawdown_percent = (current_peak - current_equity) / current_peak * 100
        
        # Calculate Sharpe ratio
        if len(closed_positions) > 1:
            returns = []
            for i in range(1, len(equity_curve)):
                if equity_curve[i-1] > 0:
                    ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
                    returns.append(ret)
            
            if returns:
                mean_return = np.mean(returns)
                std_return = np.std(returns, ddof=1) if len(returns) > 1 else 0
                
                if std_return > 0:
                    # Assuming 2% annual risk-free rate
                    risk_free_daily = 0.02 / 365
                    stats.sharpe_ratio = (mean_return - risk_free_daily) / std_return * np.sqrt(365)
                
                # Sortino ratio (downside deviation)
                downside_returns = [r for r in returns if r < 0]
                if downside_returns:
                    downside_std = np.std(downside_returns, ddof=1)
                    if downside_std > 0:
                        stats.sortino_ratio = (mean_return - risk_free_daily) / downside_std * np.sqrt(365)
                
                # Calmar ratio
                if max_drawdown > 0:
                    stats.calmar_ratio = stats.annualized_return_percent / max_drawdown
    
    def _calculate_trade_metrics(self, stats: ProfessionalStats, closed_positions: List):
        """Calculate trade-specific metrics"""
        
        if not closed_positions:
            return
        
        pnls = [pos.realized_pnl for pos in closed_positions]
        wins = [pnl for pnl in pnls if pnl > 0]
        losses = [pnl for pnl in pnls if pnl < 0]
        
        stats.total_trades = len(closed_positions)
        stats.winning_trades = len(wins)
        stats.losing_trades = len(losses)
        
        if stats.total_trades > 0:
            stats.win_rate_percent = (stats.winning_trades / stats.total_trades) * 100
        
        # Profit factor
        total_wins = sum(wins) if wins else 0
        total_losses = abs(sum(losses)) if losses else 0
        
        if total_losses > 0:
            stats.profit_factor = total_wins / total_losses
        
        # Expectancy
        if stats.total_trades > 0:
            stats.expectancy = sum(pnls) / stats.total_trades
    
    def _calculate_advanced_metrics(self, stats: ProfessionalStats, closed_positions: List):
        """Calculate advanced trade metrics"""
        
        if not closed_positions:
            return
        
        pnls = [pos.realized_pnl for pos in closed_positions]
        wins = [pnl for pnl in pnls if pnl > 0]
        losses = [pnl for pnl in pnls if pnl < 0]
        
        # Average metrics
        if wins:
            stats.average_win = np.mean(wins)
            stats.largest_win = max(wins)
        
        if losses:
            stats.average_loss = np.mean(losses)
            stats.largest_loss = min(losses)  # Most negative
        
        if pnls:
            stats.average_trade = np.mean(pnls)
        
        # Kelly percentage
        if wins and losses and stats.win_rate_percent > 0:
            win_rate = stats.win_rate_percent / 100
            avg_win_abs = abs(stats.average_win)
            avg_loss_abs = abs(stats.average_loss)
            
            if avg_loss_abs > 0:
                kelly = win_rate - ((1 - win_rate) * avg_win_abs / avg_loss_abs)
                stats.kelly_percentage = max(0, kelly * 100)
        
        # Optimal f (simplified)
        if pnls:
            stats.optimal_f = self._calculate_optimal_f(pnls)
    
    def _calculate_optimal_f(self, pnls: List[float]) -> float:
        """Calculate optimal f (simplified version)"""
        if not pnls:
            return 0.0
        
        # Find the largest loss
        largest_loss = min(pnls)
        if largest_loss >= 0:
            return 0.0
        
        # Calculate TWR (Terminal Wealth Relative) for different f values
        best_f = 0.0
        best_twr = 0.0
        
        for f in np.arange(0.01, 1.0, 0.01):
            twr = 1.0
            for pnl in pnls:
                hpr = 1 + (f * pnl / abs(largest_loss))  # Holding Period Return
                if hpr <= 0:
                    twr = 0
                    break
                twr *= hpr
            
            if twr > best_twr:
                best_twr = twr
                best_f = f
        
        return best_f
    
    def _calculate_volatility_metrics(self, stats: ProfessionalStats, 
                                    closed_positions: List,
                                    start_date: datetime, end_date: datetime):
        """Calculate volatility metrics"""
        
        if len(closed_positions) < 2:
            return
        
        # Calculate daily returns from equity curve
        equity_curve = [stats.starting_balance]
        running_balance = stats.starting_balance
        
        for pos in closed_positions:
            running_balance += pos.realized_pnl
            equity_curve.append(running_balance)
        
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i-1] > 0:
                ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
                returns.append(ret)
        
        if returns:
            # Annualized volatility
            daily_vol = np.std(returns, ddof=1)
            stats.volatility_annual_percent = daily_vol * np.sqrt(365) * 100
            
            # VaR and CVaR (95% confidence)
            if len(returns) >= 20:  # Need sufficient data
                sorted_returns = sorted(returns)
                var_index = int(0.05 * len(sorted_returns))
                
                stats.var_95_percent = abs(sorted_returns[var_index] * 100)
                
                # CVaR (Expected Shortfall)
                tail_returns = sorted_returns[:var_index+1]
                if tail_returns:
                    stats.cvar_95_percent = abs(np.mean(tail_returns) * 100)
    
    def _calculate_consistency_metrics(self, stats: ProfessionalStats, closed_positions: List):
        """Calculate consistency metrics"""
        
        if not closed_positions:
            return
        
        # Count consecutive wins/losses
        current_streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        current_is_win = None
        
        for pos in closed_positions:
            is_win = pos.realized_pnl > 0
            
            if current_is_win == is_win:
                current_streak += 1
            else:
                # Streak broken, record if it was a record
                if current_is_win is True:  # Previous was wins
                    max_win_streak = max(max_win_streak, current_streak)
                elif current_is_win is False:  # Previous was losses
                    max_loss_streak = max(max_loss_streak, current_streak)
                
                current_streak = 1
                current_is_win = is_win
        
        # Handle final streak
        if current_is_win is True:
            max_win_streak = max(max_win_streak, current_streak)
            stats.consecutive_wins = current_streak
        elif current_is_win is False:
            max_loss_streak = max(max_loss_streak, current_streak)
            stats.consecutive_losses = current_streak
        
        stats.max_consecutive_wins = max_win_streak
        stats.max_consecutive_losses = max_loss_streak
    
    def _calculate_time_metrics(self, stats: ProfessionalStats, closed_positions: List,
                               start_date: datetime, end_date: datetime):
        """Calculate time-based metrics"""
        
        if not closed_positions:
            return
        
        # Trading days
        days_elapsed = (end_date - start_date).days
        stats.trading_days = max(1, days_elapsed)
        
        # Average trades per day
        stats.avg_trades_per_day = stats.total_trades / stats.trading_days
        
        # Average holding time
        holding_times = []
        for pos in closed_positions:
            if pos.exit_time and pos.entry_time:
                holding_time = (pos.exit_time - pos.entry_time).total_seconds() / 3600  # Hours
                holding_times.append(holding_time)
        
        if holding_times:
            stats.avg_holding_time_hours = np.mean(holding_times)
    
    def _calculate_recovery_metrics(self, stats: ProfessionalStats, closed_positions: List):
        """Calculate recovery and stability metrics"""
        
        if not closed_positions or stats.max_drawdown_percent == 0:
            return
        
        # Recovery factor
        if stats.max_drawdown_percent > 0:
            stats.recovery_factor = stats.total_return_percent / stats.max_drawdown_percent
        
        # Ulcer Index
        equity_curve = [stats.starting_balance]
        running_balance = stats.starting_balance
        
        for pos in closed_positions:
            running_balance += pos.realized_pnl
            equity_curve.append(running_balance)
        
        if len(equity_curve) > 1:
            peak = equity_curve[0]
            squared_drawdowns = []
            
            for equity in equity_curve:
                if equity > peak:
                    peak = equity
                
                if peak > 0:
                    drawdown_pct = ((peak - equity) / peak) * 100
                    squared_drawdowns.append(drawdown_pct ** 2)
            
            if squared_drawdowns:
                stats.ulcer_index = np.sqrt(np.mean(squared_drawdowns))
        
        # Sterling ratio (if enough data)
        if stats.max_drawdown_percent > 0 and len(closed_positions) >= 12:  # At least 12 trades
            stats.sterling_ratio = stats.annualized_return_percent / stats.max_drawdown_percent
    
    def get_daily_stats(self, date: datetime) -> Dict:
        """Get statistics for a specific day"""
        
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        with DatabaseManager() as db:
            # Get trades for the day
            day_positions = db.session.query(db.Position).filter(
                db.Position.status == "CLOSED",
                db.Position.exit_time >= start_of_day,
                db.Position.exit_time < end_of_day
            ).all()
            
            day_pnl = sum(pos.realized_pnl for pos in day_positions)
            day_trades = len(day_positions)
            day_wins = len([pos for pos in day_positions if pos.realized_pnl > 0])
            
            return {
                "date": date.date().isoformat(),
                "trades": day_trades,
                "pnl": day_pnl,
                "wins": day_wins,
                "losses": day_trades - day_wins,
                "win_rate": (day_wins / day_trades * 100) if day_trades > 0 else 0
            }
    
    def get_performance_summary(self, days: int = 30) -> Dict:
        """Get performance summary for the last N days"""
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        stats = self.calculate_stats(start_date, end_date)
        
        return {
            "period_days": days,
            "total_return_pct": stats.total_return_percent,
            "annualized_return_pct": stats.annualized_return_percent,
            "sharpe_ratio": stats.sharpe_ratio,
            "max_drawdown_pct": stats.max_drawdown_percent,
            "win_rate_pct": stats.win_rate_percent,
            "profit_factor": stats.profit_factor,
            "total_trades": stats.total_trades,
            "avg_trades_per_day": stats.avg_trades_per_day,
            "volatility_pct": stats.volatility_annual_percent,
            "var_95_pct": stats.var_95_percent
        }
