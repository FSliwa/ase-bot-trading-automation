"""
Enhanced Risk Management System
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Import all database models we'll need
from .db import Position, TradingStats, Fill, RiskEvent
from bot.db import DatabaseManager


@dataclass
class RiskLimits:
    """Risk limits configuration"""
    max_leverage: float = 150.0
    max_position_size_pct: float = 20.0  # % of equity per position
    max_daily_drawdown_pct: float = 5.0
    max_total_exposure_pct: float = 100.0
    require_stop_loss_live: bool = True
    max_correlation_exposure: float = 50.0  # % of equity in correlated positions
    cooldown_after_stop_minutes: int = 30
    max_consecutive_losses: int = 5


@dataclass
class RiskMetrics:
    """Current risk metrics"""
    current_leverage: float = 0.0
    daily_drawdown_pct: float = 0.0
    total_exposure_pct: float = 0.0
    largest_position_pct: float = 0.0
    correlation_exposure_pct: float = 0.0
    consecutive_losses: int = 0
    risk_of_ruin_pct: float = 0.0
    var_1d_pct: float = 0.0  # 1-day VaR
    sharpe_ratio: Optional[float] = None


class RiskManager:
    """Enhanced risk management system"""
    
    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or RiskLimits()
        self.symbol_correlations: Dict[Tuple[str, str], float] = {}
        self.stop_loss_cooldowns: Dict[str, datetime] = {}
        
        # Initialize correlations (simplified)
        self._init_correlations()
    
    def _init_correlations(self):
        """Initialize symbol correlations (simplified)"""
        # Crypto correlations (approximate)
        correlations = {
            ("BTCUSDT", "ETHUSD"): 0.85,
            ("BTCUSDT", "SOLUSDT"): 0.75,
            ("BTCUSDT", "ADAUSDT"): 0.70,
            ("ETHUSD", "SOLUSDT"): 0.80,
            ("ETHUSD", "ADAUSDT"): 0.75,
            ("SOLUSDT", "ADAUSDT"): 0.65,
        }
        
        # Add reverse correlations
        for (s1, s2), corr in list(correlations.items()):
            correlations[(s2, s1)] = corr
        
        self.symbol_correlations = correlations
    
    def get_correlation(self, symbol1: str, symbol2: str) -> float:
        """Get correlation between two symbols"""
        return self.symbol_correlations.get((symbol1, symbol2), 0.0)
    
    def validate_new_order(self, symbol: str, side: str, quantity: float, 
                          price: float, leverage: float, stop_loss: Optional[float] = None,
                          is_live: bool = False, current_equity: float = 10000.0) -> Dict:
        """Validate new order against risk limits"""
        
        violations = []
        warnings = []
        
        # Check leverage limit
        if leverage > self.limits.max_leverage:
            violations.append(f"Leverage {leverage}x exceeds limit {self.limits.max_leverage}x")
        
        # Check stop loss requirement for live trading
        if is_live and self.limits.require_stop_loss_live and not stop_loss:
            violations.append("Stop loss required for live trading")
        
        # Check position size
        position_value = quantity * price
        position_size_pct = (position_value / current_equity) * 100
        
        if position_size_pct > self.limits.max_position_size_pct:
            violations.append(
                f"Position size {position_size_pct:.1f}% exceeds limit {self.limits.max_position_size_pct}%"
            )
        
        # Check cooldown period
        if symbol in self.stop_loss_cooldowns:
            cooldown_end = self.stop_loss_cooldowns[symbol]
            if datetime.utcnow() < cooldown_end:
                remaining_minutes = (cooldown_end - datetime.utcnow()).total_seconds() / 60
                violations.append(
                    f"Symbol {symbol} in cooldown for {remaining_minutes:.0f} more minutes"
                )
        
        # Get current risk metrics
        current_metrics = self.calculate_risk_metrics(current_equity)
        
        # Check daily drawdown
        if current_metrics.daily_drawdown_pct >= self.limits.max_daily_drawdown_pct:
            violations.append(
                f"Daily drawdown {current_metrics.daily_drawdown_pct:.1f}% "
                f"exceeds limit {self.limits.max_daily_drawdown_pct}%"
            )
        
        # Check total exposure
        new_exposure_pct = current_metrics.total_exposure_pct + position_size_pct
        if new_exposure_pct > self.limits.max_total_exposure_pct:
            violations.append(
                f"Total exposure would be {new_exposure_pct:.1f}% "
                f"exceeding limit {self.limits.max_total_exposure_pct}%"
            )
        
        # Check correlation exposure
        correlation_exposure = self._calculate_correlation_exposure(
            symbol, position_value, current_equity
        )
        
        if correlation_exposure > self.limits.max_correlation_exposure:
            violations.append(
                f"Correlated exposure {correlation_exposure:.1f}% "
                f"exceeds limit {self.limits.max_correlation_exposure}%"
            )
        
        # Check consecutive losses
        if current_metrics.consecutive_losses >= self.limits.max_consecutive_losses:
            violations.append(
                f"Too many consecutive losses ({current_metrics.consecutive_losses}), "
                f"trading suspended"
            )
        
        # Risk warnings
        if position_size_pct > self.limits.max_position_size_pct * 0.8:
            warnings.append(f"Large position size: {position_size_pct:.1f}%")
        
        if leverage > 50:
            warnings.append(f"High leverage: {leverage}x")
        
        if stop_loss and price:
            stop_distance_pct = abs(stop_loss - price) / price * 100
            if stop_distance_pct < 1.0:
                warnings.append(f"Very tight stop loss: {stop_distance_pct:.1f}%")
        
        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "risk_metrics": current_metrics
        }
    
    def calculate_risk_metrics(self, current_equity: float) -> RiskMetrics:
        """Calculate current risk metrics"""
        
        with DatabaseManager() as db:
            positions = db.get_open_positions()
            
            # Calculate leverage and exposure
            total_notional = sum(pos.quantity * pos.current_price for pos in positions)
            current_leverage = total_notional / current_equity if current_equity > 0 else 0
            total_exposure_pct = (total_notional / current_equity) * 100 if current_equity > 0 else 0
            
            # Largest position
            largest_position_pct = 0
            if positions:
                largest_notional = max(pos.quantity * pos.current_price for pos in positions)
                largest_position_pct = (largest_notional / current_equity) * 100
            
            # Daily drawdown
            daily_dd_pct = self._calculate_daily_drawdown(current_equity)
            
            # Correlation exposure
            correlation_exposure_pct = self._calculate_total_correlation_exposure(current_equity)
            
            # Consecutive losses
            consecutive_losses = self._count_consecutive_losses()
            
            # Risk of ruin (simplified Kelly criterion based)
            ror_pct = self._calculate_risk_of_ruin()
            
            # VaR (simplified)
            var_1d_pct = self._calculate_var_1d()
            
            # Sharpe ratio (if enough data)
            sharpe = self._calculate_sharpe_ratio()
            
            # Sanitize all float values to avoid JSON serialization issues
            def sanitize_float(value):
                if isinstance(value, float):
                    import math
                    if math.isnan(value) or math.isinf(value):
                        return 0.0
                return value
            
            return RiskMetrics(
                current_leverage=sanitize_float(current_leverage),
                daily_drawdown_pct=sanitize_float(daily_dd_pct),
                total_exposure_pct=sanitize_float(total_exposure_pct),
                largest_position_pct=sanitize_float(largest_position_pct),
                correlation_exposure_pct=sanitize_float(correlation_exposure_pct),
                consecutive_losses=consecutive_losses,
                risk_of_ruin_pct=sanitize_float(ror_pct),
                var_1d_pct=sanitize_float(var_1d_pct),
                sharpe_ratio=sanitize_float(sharpe)
            )
    
    def _calculate_daily_drawdown(self, current_equity: float) -> float:
        """Calculate daily drawdown percentage"""
        
        # Get today's starting balance
        today = datetime.utcnow().date()
        
        with DatabaseManager() as db:
            stats = db.session.query(TradingStats).filter(
                TradingStats.date >= today
            ).first()
            
            if stats:
                starting_balance = stats.starting_balance
                drawdown_pct = max(0, (starting_balance - current_equity) / starting_balance * 100)
                return drawdown_pct
        
        return 0.0
    
    def _calculate_correlation_exposure(self, new_symbol: str, new_position_value: float,
                                      current_equity: float) -> float:
        """Calculate correlation exposure for new position"""
        
        with DatabaseManager() as db:
            positions = db.get_open_positions()
            
            total_correlated_exposure = new_position_value
            
            for pos in positions:
                correlation = self.get_correlation(new_symbol, pos.symbol)
                if correlation > 0.5:  # Significant correlation
                    position_value = pos.quantity * pos.current_price
                    total_correlated_exposure += position_value * correlation
            
            return (total_correlated_exposure / current_equity) * 100
    
    def _calculate_total_correlation_exposure(self, current_equity: float) -> float:
        """Calculate total correlation exposure across all positions"""
        
        with DatabaseManager() as db:
            positions = db.get_open_positions()
            
            if len(positions) < 2:
                return 0.0
            
            max_correlated_exposure = 0
            
            for i, pos1 in enumerate(positions):
                correlated_exposure = pos1.quantity * pos1.current_price
                
                for j, pos2 in enumerate(positions):
                    if i != j:
                        correlation = self.get_correlation(pos1.symbol, pos2.symbol)
                        if correlation > 0.5:
                            correlated_exposure += (pos2.quantity * pos2.current_price) * correlation
                
                exposure_pct = (correlated_exposure / current_equity) * 100
                max_correlated_exposure = max(max_correlated_exposure, exposure_pct)
            
            return max_correlated_exposure
    
    def _count_consecutive_losses(self) -> int:
        """Count consecutive losing trades"""
        
        from bot.db import Position
        
        with DatabaseManager() as db:
            # Get recent closed positions
            recent_positions = db.session.query(Position).filter(
                Position.status == "CLOSED",
                Position.exit_time >= datetime.utcnow() - timedelta(days=7)
            ).order_by(Position.exit_time.desc()).limit(20).all()
            
            consecutive_losses = 0
            for pos in recent_positions:
                if pos.realized_pnl < 0:
                    consecutive_losses += 1
                else:
                    break
            
            return consecutive_losses
    
    def _calculate_risk_of_ruin(self) -> float:
        """Calculate risk of ruin using simplified Kelly criterion"""
        
        with DatabaseManager() as db:
            # Get recent trade statistics
            recent_positions = db.session.query(Position).filter(
                Position.status == "CLOSED",
                Position.exit_time >= datetime.utcnow() - timedelta(days=30)
            ).all()
            
            if len(recent_positions) < 10:
                return 0.0  # Not enough data
            
            pnls = [pos.realized_pnl for pos in recent_positions]
            wins = [pnl for pnl in pnls if pnl > 0]
            losses = [pnl for pnl in pnls if pnl < 0]
            
            if not wins or not losses:
                return 0.0
            
            win_rate = len(wins) / len(pnls)
            avg_win = np.mean(wins)
            avg_loss = abs(np.mean(losses))
            
            if avg_loss == 0:
                return 0.0
            
            payoff_ratio = avg_win / avg_loss
            
            # Simplified risk of ruin calculation
            # RoR = ((1-p)/p)^(Capital/AvgLoss) where p is win rate
            if win_rate >= 0.5:
                ror = 0.0  # Positive expectancy
            else:
                q = 1 - win_rate
                if payoff_ratio <= q / win_rate:
                    ror = 100.0  # Negative expectancy
                else:
                    # Kelly formula approximation
                    kelly_pct = (win_rate * payoff_ratio - q) / payoff_ratio
                    if kelly_pct <= 0:
                        ror = 100.0
                    else:
                        # Simplified RoR based on Kelly percentage
                        ror = max(0, min(100, (1 - kelly_pct) * 100))
            
            return ror
    
    def calculate_risk_of_ruin(self, win_rate: float = None, avg_win_loss_ratio: float = None, 
                               risk_per_trade: float = 0.01) -> float:
        """
        Calculate risk of ruin using Kelly criterion.
        
        Args:
            win_rate: Win rate (0-1). If None, calculated from recent trades
            avg_win_loss_ratio: Average win/loss ratio. If None, calculated from recent trades
            risk_per_trade: Risk per trade as fraction of capital
            
        Returns:
            Risk of ruin as percentage (0-100)
        """
        try:
            # If parameters provided, use them directly
            if win_rate is not None and avg_win_loss_ratio is not None:
                if win_rate >= 0.5 and avg_win_loss_ratio > 1.0:
                    return 0.0  # Positive expectancy system
                
                q = 1 - win_rate
                if avg_win_loss_ratio <= q / win_rate if win_rate > 0 else float('inf'):
                    return 100.0  # Negative expectancy
                
                # Kelly formula
                kelly_pct = (win_rate * avg_win_loss_ratio - q) / avg_win_loss_ratio
                if kelly_pct <= 0:
                    return 100.0
                
                # Risk of ruin approximation
                return max(0, min(100, (1 - kelly_pct / 2) * 100))
            
            # Otherwise use historical data
            return self._calculate_risk_of_ruin()
            
        except Exception as e:
            return 50.0  # Conservative estimate

    def _calculate_var_1d(self) -> float:
        """Calculate 1-day Value at Risk (95% confidence)"""
        
        with DatabaseManager() as db:
            # Get recent daily P&L data
            recent_stats = db.session.query(TradingStats).filter(
                TradingStats.date >= datetime.utcnow() - timedelta(days=30)
            ).order_by(TradingStats.date.desc()).all()
            
            if len(recent_stats) < 10:
                return 0.0
            
            daily_returns = []
            for i in range(len(recent_stats) - 1):
                today_balance = recent_stats[i].ending_balance
                yesterday_balance = recent_stats[i + 1].ending_balance
                
                if yesterday_balance > 0:
                    daily_return = (today_balance - yesterday_balance) / yesterday_balance
                    daily_returns.append(daily_return)
            
            if not daily_returns:
                return 0.0
            
            # 95% VaR (5th percentile)
            var_95 = np.percentile(daily_returns, 5)
            return abs(var_95 * 100)  # Convert to percentage
    
    def _calculate_sharpe_ratio(self) -> Optional[float]:
        """Calculate Sharpe ratio"""
        
        with DatabaseManager() as db:
            recent_stats = db.session.query(TradingStats).filter(
                TradingStats.date >= datetime.utcnow() - timedelta(days=30)
            ).order_by(TradingStats.date.desc()).all()
            
            if len(recent_stats) < 10:
                return None
            
            daily_returns = []
            for i in range(len(recent_stats) - 1):
                today_balance = recent_stats[i].ending_balance
                yesterday_balance = recent_stats[i + 1].ending_balance
                
                if yesterday_balance > 0:
                    daily_return = (today_balance - yesterday_balance) / yesterday_balance
                    daily_returns.append(daily_return)
            
            if not daily_returns:
                return None
            
            mean_return = np.mean(daily_returns)
            std_return = np.std(daily_returns)
            
            if std_return == 0:
                return None
            
            # Annualized Sharpe ratio (assuming 365 trading days)
            risk_free_rate = 0.02 / 365  # 2% annual risk-free rate
            sharpe = (mean_return - risk_free_rate) / std_return * np.sqrt(365)
            
            return sharpe
    
    def handle_stop_loss_hit(self, symbol: str):
        """Handle stop loss hit - start cooldown period"""
        cooldown_end = datetime.utcnow() + timedelta(minutes=self.limits.cooldown_after_stop_minutes)
        self.stop_loss_cooldowns[symbol] = cooldown_end
        
        # Log risk event
        with DatabaseManager() as db:
            db.log_risk_event(
                event_type="STOP_LOSS",
                severity="WARNING",
                message=f"Stop loss hit for {symbol}, cooldown activated",
                symbol=symbol,
                data={"cooldown_until": cooldown_end.isoformat()}
            )
    
    def check_circuit_breakers(self, current_equity: float) -> Dict:
        """Check if circuit breakers should be triggered"""
        
        metrics = self.calculate_risk_metrics(current_equity)
        breakers_triggered = []
        
        # Daily drawdown breaker
        if metrics.daily_drawdown_pct >= self.limits.max_daily_drawdown_pct:
            breakers_triggered.append({
                "type": "DAILY_DRAWDOWN",
                "message": f"Daily drawdown {metrics.daily_drawdown_pct:.1f}% exceeds limit",
                "severity": "CRITICAL"
            })
        
        # Consecutive losses breaker
        if metrics.consecutive_losses >= self.limits.max_consecutive_losses:
            breakers_triggered.append({
                "type": "CONSECUTIVE_LOSSES",
                "message": f"Too many consecutive losses: {metrics.consecutive_losses}",
                "severity": "CRITICAL"
            })
        
        # High risk of ruin
        if metrics.risk_of_ruin_pct > 50:
            breakers_triggered.append({
                "type": "HIGH_RISK_OF_RUIN",
                "message": f"Risk of ruin too high: {metrics.risk_of_ruin_pct:.1f}%",
                "severity": "CRITICAL"
            })
        
        # Log breakers
        if breakers_triggered:
            with DatabaseManager() as db:
                for breaker in breakers_triggered:
                    db.log_risk_event(
                        event_type=breaker["type"],
                        severity=breaker["severity"],
                        message=breaker["message"],
                        data={"metrics": metrics.__dict__}
                    )
        
        return {
            "triggered": len(breakers_triggered) > 0,
            "breakers": breakers_triggered,
            "should_halt_trading": any(b["severity"] == "CRITICAL" for b in breakers_triggered)
        }
    
    def get_position_sizing_recommendation(self, symbol: str, entry_price: float,
                                         stop_loss: float, current_equity: float,
                                         risk_per_trade_pct: float = 1.0) -> Dict:
        """Get position sizing recommendation based on risk"""
        
        if not stop_loss or stop_loss == entry_price:
            return {
                "recommended_quantity": 0,
                "max_quantity": 0,
                "risk_amount": 0,
                "error": "Stop loss required for position sizing"
            }
        
        # Calculate risk per unit
        risk_per_unit = abs(entry_price - stop_loss)
        
        # Calculate risk amount
        risk_amount = current_equity * (risk_per_trade_pct / 100)
        
        # Calculate recommended quantity
        recommended_quantity = risk_amount / risk_per_unit
        
        # Apply position size limits
        max_position_value = current_equity * (self.limits.max_position_size_pct / 100)
        max_quantity_by_size = max_position_value / entry_price
        
        final_quantity = min(recommended_quantity, max_quantity_by_size)
        
        return {
            "recommended_quantity": final_quantity,
            "max_quantity": max_quantity_by_size,
            "risk_amount": risk_amount,
            "risk_per_unit": risk_per_unit,
            "position_size_pct": (final_quantity * entry_price / current_equity) * 100
        }
