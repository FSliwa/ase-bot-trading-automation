"""
ADVANCED ANALYTICS ENGINE - METRYKI I ANALITYKA
System zaawansowanej analityki dla platform tradingowych
"""

# ==================================================================================
# 📊 ADVANCED ANALYTICS ENGINE
# ==================================================================================

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import logging
from collections import defaultdict
import json
import math
from scipy import stats
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AnalyticsType(Enum):
    """Typy analityki"""
    PERFORMANCE = "performance"
    RISK = "risk"
    PORTFOLIO = "portfolio"
    MARKET = "market"
    PREDICTIVE = "predictive"
    BEHAVIORAL = "behavioral"

@dataclass
class AnalyticsResult:
    """Rezultat analizy"""
    metric_name: str
    value: float
    confidence: Optional[float] = None
    percentile: Optional[float] = None
    benchmark_comparison: Optional[float] = None
    time_period: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None
    calculated_at: datetime = None
    
    def __post_init__(self):
        if self.calculated_at is None:
            self.calculated_at = datetime.now(timezone.utc)

class PerformanceAnalytics:
    """Analityka wydajności tradingowej"""
    
    def __init__(self):
        self.risk_free_rate = 0.02  # 2% annual risk-free rate
        
    def calculate_sharpe_ratio(self, returns: List[float], risk_free_rate: Optional[float] = None) -> AnalyticsResult:
        """Oblicza współczynnik Sharpe'a"""
        if not returns or len(returns) < 2:
            return AnalyticsResult("sharpe_ratio", 0.0)
        
        rf_rate = risk_free_rate or self.risk_free_rate
        returns_array = np.array(returns)
        
        # Convert to excess returns
        excess_returns = returns_array - (rf_rate / 252)  # Daily risk-free rate
        
        if np.std(excess_returns) == 0:
            sharpe = 0.0
        else:
            sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)
        
        # Calculate percentile against typical range (-2 to 3)
        percentile = self._calculate_percentile(sharpe, -2, 3)
        
        return AnalyticsResult(
            metric_name="sharpe_ratio",
            value=round(sharpe, 4),
            percentile=percentile,
            additional_data={
                "mean_excess_return": float(np.mean(excess_returns)),
                "volatility": float(np.std(excess_returns) * np.sqrt(252)),
                "annualized": True
            }
        )
    
    def calculate_sortino_ratio(self, returns: List[float], target_return: float = 0.0) -> AnalyticsResult:
        """Oblicza współczynnik Sortino"""
        if not returns or len(returns) < 2:
            return AnalyticsResult("sortino_ratio", 0.0)
        
        returns_array = np.array(returns)
        excess_returns = returns_array - target_return
        
        # Calculate downside deviation
        negative_returns = excess_returns[excess_returns < 0]
        if len(negative_returns) == 0:
            downside_deviation = 0.001  # Small value to avoid division by zero
        else:
            downside_deviation = np.sqrt(np.mean(negative_returns ** 2))
        
        sortino = np.mean(excess_returns) / downside_deviation * np.sqrt(252)
        
        return AnalyticsResult(
            metric_name="sortino_ratio",
            value=round(sortino, 4),
            additional_data={
                "downside_deviation": float(downside_deviation),
                "target_return": target_return,
                "negative_periods": len(negative_returns)
            }
        )
    
    def calculate_maximum_drawdown(self, equity_curve: List[float]) -> AnalyticsResult:
        """Oblicza maksymalny drawdown"""
        if not equity_curve or len(equity_curve) < 2:
            return AnalyticsResult("maximum_drawdown", 0.0)
        
        equity_array = np.array(equity_curve)
        running_max = np.maximum.accumulate(equity_array)
        drawdowns = (equity_array - running_max) / running_max
        
        max_dd = float(np.min(drawdowns))
        max_dd_idx = np.argmin(drawdowns)
        
        # Find the peak before the max drawdown
        peak_idx = np.argmax(running_max[:max_dd_idx + 1]) if max_dd_idx > 0 else 0
        
        # Calculate duration
        drawdown_duration = max_dd_idx - peak_idx
        
        return AnalyticsResult(
            metric_name="maximum_drawdown",
            value=round(abs(max_dd) * 100, 2),  # Convert to percentage
            additional_data={
                "drawdown_start_idx": int(peak_idx),
                "drawdown_end_idx": int(max_dd_idx),
                "duration_periods": int(drawdown_duration),
                "peak_value": float(equity_array[peak_idx]),
                "trough_value": float(equity_array[max_dd_idx])
            }
        )
    
    def calculate_calmar_ratio(self, returns: List[float], equity_curve: List[float]) -> AnalyticsResult:
        """Oblicza współczynnik Calmar"""
        if not returns or not equity_curve:
            return AnalyticsResult("calmar_ratio", 0.0)
        
        # Annual return
        annual_return = np.mean(returns) * 252
        
        # Maximum drawdown
        max_dd_result = self.calculate_maximum_drawdown(equity_curve)
        max_dd = max_dd_result.value / 100  # Convert back to decimal
        
        if max_dd == 0:
            calmar = float('inf') if annual_return > 0 else 0.0
        else:
            calmar = annual_return / max_dd
        
        return AnalyticsResult(
            metric_name="calmar_ratio",
            value=round(calmar, 4),
            additional_data={
                "annual_return": float(annual_return),
                "maximum_drawdown": float(max_dd),
                "periods_analyzed": len(returns)
            }
        )
    
    def calculate_win_rate(self, trade_results: List[float]) -> AnalyticsResult:
        """Oblicza wskaźnik wygranych transakcji"""
        if not trade_results:
            return AnalyticsResult("win_rate", 0.0)
        
        winning_trades = sum(1 for result in trade_results if result > 0)
        total_trades = len(trade_results)
        win_rate = winning_trades / total_trades * 100
        
        # Calculate confidence interval
        confidence_interval = self._calculate_binomial_confidence_interval(winning_trades, total_trades)
        
        return AnalyticsResult(
            metric_name="win_rate",
            value=round(win_rate, 2),
            confidence=95.0,
            additional_data={
                "winning_trades": winning_trades,
                "total_trades": total_trades,
                "losing_trades": total_trades - winning_trades,
                "confidence_interval": confidence_interval
            }
        )
    
    def calculate_profit_factor(self, trade_results: List[float]) -> AnalyticsResult:
        """Oblicza współczynnik zysku"""
        if not trade_results:
            return AnalyticsResult("profit_factor", 0.0)
        
        gross_profit = sum(result for result in trade_results if result > 0)
        gross_loss = abs(sum(result for result in trade_results if result < 0))
        
        if gross_loss == 0:
            profit_factor = float('inf') if gross_profit > 0 else 1.0
        else:
            profit_factor = gross_profit / gross_loss
        
        return AnalyticsResult(
            metric_name="profit_factor",
            value=round(profit_factor, 4),
            additional_data={
                "gross_profit": float(gross_profit),
                "gross_loss": float(gross_loss),
                "net_profit": float(gross_profit - gross_loss)
            }
        )
    
    def calculate_average_trade_metrics(self, trade_results: List[float]) -> Dict[str, AnalyticsResult]:
        """Oblicza średnie metryki transakcji"""
        if not trade_results:
            return {}
        
        winning_trades = [r for r in trade_results if r > 0]
        losing_trades = [r for r in trade_results if r < 0]
        
        results = {}
        
        # Average trade
        results["average_trade"] = AnalyticsResult(
            metric_name="average_trade",
            value=round(np.mean(trade_results), 4),
            additional_data={
                "median_trade": float(np.median(trade_results)),
                "std_dev": float(np.std(trade_results))
            }
        )
        
        # Average winning trade
        if winning_trades:
            results["average_winning_trade"] = AnalyticsResult(
                metric_name="average_winning_trade",
                value=round(np.mean(winning_trades), 4),
                additional_data={
                    "largest_win": float(max(winning_trades)),
                    "median_win": float(np.median(winning_trades))
                }
            )
        
        # Average losing trade
        if losing_trades:
            results["average_losing_trade"] = AnalyticsResult(
                metric_name="average_losing_trade",
                value=round(np.mean(losing_trades), 4),
                additional_data={
                    "largest_loss": float(min(losing_trades)),
                    "median_loss": float(np.median(losing_trades))
                }
            )
        
        return results
    
    def _calculate_percentile(self, value: float, min_val: float, max_val: float) -> float:
        """Oblicza percentyl wartości w zakresie"""
        if max_val == min_val:
            return 50.0
        
        percentile = (value - min_val) / (max_val - min_val) * 100
        return max(0, min(100, percentile))
    
    def _calculate_binomial_confidence_interval(self, successes: int, trials: int, confidence: float = 0.95) -> Tuple[float, float]:
        """Oblicza przedział ufności dla proporcji"""
        if trials == 0:
            return (0.0, 0.0)
        
        p = successes / trials
        z = stats.norm.ppf((1 + confidence) / 2)
        
        # Wilson score interval
        denominator = 1 + z**2 / trials
        center = (p + z**2 / (2 * trials)) / denominator
        margin = z * np.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2)) / denominator
        
        lower = max(0, center - margin)
        upper = min(1, center + margin)
        
        return (round(lower * 100, 2), round(upper * 100, 2))

class RiskAnalytics:
    """Analityka ryzyka"""
    
    def calculate_value_at_risk(self, returns: List[float], confidence_level: float = 0.95, 
                               method: str = "historical") -> AnalyticsResult:
        """Oblicza Value at Risk (VaR)"""
        if not returns or len(returns) < 2:
            return AnalyticsResult("value_at_risk", 0.0)
        
        returns_array = np.array(returns)
        
        if method == "historical":
            var = np.percentile(returns_array, (1 - confidence_level) * 100)
        elif method == "parametric":
            var = np.mean(returns_array) - stats.norm.ppf(confidence_level) * np.std(returns_array)
        else:
            var = np.percentile(returns_array, (1 - confidence_level) * 100)
        
        return AnalyticsResult(
            metric_name="value_at_risk",
            value=round(float(var) * 100, 4),  # Convert to percentage
            confidence=confidence_level * 100,
            additional_data={
                "method": method,
                "daily_var": float(var),
                "annualized_var": float(var * np.sqrt(252))
            }
        )
    
    def calculate_conditional_var(self, returns: List[float], confidence_level: float = 0.95) -> AnalyticsResult:
        """Oblicza Conditional Value at Risk (CVaR/Expected Shortfall)"""
        if not returns or len(returns) < 2:
            return AnalyticsResult("conditional_var", 0.0)
        
        returns_array = np.array(returns)
        var_threshold = np.percentile(returns_array, (1 - confidence_level) * 100)
        
        # Calculate expected value of returns below VaR threshold
        tail_returns = returns_array[returns_array <= var_threshold]
        cvar = np.mean(tail_returns) if len(tail_returns) > 0 else var_threshold
        
        return AnalyticsResult(
            metric_name="conditional_var",
            value=round(float(cvar) * 100, 4),
            confidence=confidence_level * 100,
            additional_data={
                "var_threshold": float(var_threshold),
                "tail_observations": len(tail_returns),
                "tail_percentage": float(len(tail_returns) / len(returns_array) * 100)
            }
        )
    
    def calculate_beta(self, asset_returns: List[float], market_returns: List[float]) -> AnalyticsResult:
        """Oblicza beta względem rynku"""
        if not asset_returns or not market_returns or len(asset_returns) != len(market_returns):
            return AnalyticsResult("beta", 1.0)
        
        if len(asset_returns) < 2:
            return AnalyticsResult("beta", 1.0)
        
        # Calculate covariance and variance
        covariance = np.cov(asset_returns, market_returns)[0, 1]
        market_variance = np.var(market_returns)
        
        if market_variance == 0:
            beta = 1.0
        else:
            beta = covariance / market_variance
        
        # Calculate R-squared
        correlation = np.corrcoef(asset_returns, market_returns)[0, 1]
        r_squared = correlation ** 2 if not np.isnan(correlation) else 0
        
        return AnalyticsResult(
            metric_name="beta",
            value=round(float(beta), 4),
            additional_data={
                "correlation": float(correlation) if not np.isnan(correlation) else 0,
                "r_squared": float(r_squared),
                "covariance": float(covariance),
                "market_variance": float(market_variance)
            }
        )
    
    def calculate_tracking_error(self, portfolio_returns: List[float], 
                               benchmark_returns: List[float]) -> AnalyticsResult:
        """Oblicza błąd śledzenia względem benchmarku"""
        if (not portfolio_returns or not benchmark_returns or 
            len(portfolio_returns) != len(benchmark_returns)):
            return AnalyticsResult("tracking_error", 0.0)
        
        excess_returns = np.array(portfolio_returns) - np.array(benchmark_returns)
        tracking_error = np.std(excess_returns) * np.sqrt(252)  # Annualized
        
        return AnalyticsResult(
            metric_name="tracking_error",
            value=round(float(tracking_error) * 100, 4),
            additional_data={
                "daily_tracking_error": float(np.std(excess_returns)),
                "mean_excess_return": float(np.mean(excess_returns)),
                "excess_return_volatility": float(np.std(excess_returns))
            }
        )

class PortfolioAnalytics:
    """Analityka portfolio"""
    
    def calculate_diversification_metrics(self, positions: List[Dict[str, Any]]) -> Dict[str, AnalyticsResult]:
        """Oblicza metryki dywersyfikacji"""
        if not positions:
            return {}
        
        results = {}
        
        # Calculate weights
        total_value = sum(abs(pos.get('market_value', 0)) for pos in positions)
        if total_value == 0:
            return {}
        
        weights = [abs(pos.get('market_value', 0)) / total_value for pos in positions]
        
        # Concentration metrics
        results["concentration_hhi"] = self._calculate_hhi(weights)
        results["effective_positions"] = self._calculate_effective_positions(weights)
        
        # Sector/Symbol diversification
        sector_weights = self._group_weights_by_key(positions, 'sector', weights)
        if len(sector_weights) > 1:
            results["sector_concentration"] = self._calculate_hhi(list(sector_weights.values()))
        
        exchange_weights = self._group_weights_by_key(positions, 'exchange', weights)
        if len(exchange_weights) > 1:
            results["exchange_concentration"] = self._calculate_hhi(list(exchange_weights.values()))
        
        return results
    
    def calculate_portfolio_risk_metrics(self, positions: List[Dict[str, Any]], 
                                       correlation_matrix: Optional[np.ndarray] = None) -> Dict[str, AnalyticsResult]:
        """Oblicza metryki ryzyka portfolio"""
        if not positions:
            return {}
        
        results = {}
        
        # Calculate position sizes and volatilities
        total_value = sum(abs(pos.get('market_value', 0)) for pos in positions)
        if total_value == 0:
            return {}
        
        weights = np.array([pos.get('market_value', 0) / total_value for pos in positions])
        volatilities = np.array([pos.get('volatility', 0.2) for pos in positions])  # Default 20% volatility
        
        # Portfolio volatility (if correlation matrix provided)
        if correlation_matrix is not None and correlation_matrix.shape == (len(positions), len(positions)):
            # Covariance matrix = correlation * vol_i * vol_j
            cov_matrix = correlation_matrix * np.outer(volatilities, volatilities)
            portfolio_variance = np.dot(weights, np.dot(cov_matrix, weights))
            portfolio_volatility = np.sqrt(portfolio_variance)
            
            results["portfolio_volatility"] = AnalyticsResult(
                metric_name="portfolio_volatility",
                value=round(float(portfolio_volatility) * 100, 2),
                additional_data={
                    "annualized": True,
                    "diversification_ratio": float(np.sum(weights * volatilities) / portfolio_volatility)
                }
            )
        
        # Individual risk contributions
        risk_contributions = weights * volatilities
        total_risk = np.sum(risk_contributions)
        
        if total_risk > 0:
            risk_percentages = risk_contributions / total_risk * 100
            max_risk_contribution = np.max(risk_percentages)
            
            results["max_position_risk"] = AnalyticsResult(
                metric_name="max_position_risk",
                value=round(float(max_risk_contribution), 2),
                additional_data={
                    "risk_contributions": risk_percentages.tolist(),
                    "top_risk_position_idx": int(np.argmax(risk_percentages))
                }
            )
        
        return results
    
    def _calculate_hhi(self, weights: List[float]) -> AnalyticsResult:
        """Oblicza Herfindahl-Hirschman Index"""
        if not weights:
            return AnalyticsResult("hhi", 0.0)
        
        hhi = sum(w**2 for w in weights) * 10000  # Multiply by 10000 for standard HHI scale
        
        return AnalyticsResult(
            metric_name="hhi",
            value=round(float(hhi), 2),
            additional_data={
                "interpretation": self._interpret_hhi(hhi),
                "max_possible": 10000,
                "positions_count": len(weights)
            }
        )
    
    def _calculate_effective_positions(self, weights: List[float]) -> AnalyticsResult:
        """Oblicza efektywną liczbę pozycji"""
        if not weights:
            return AnalyticsResult("effective_positions", 0.0)
        
        # Effective number of positions = 1 / sum(wi^2)
        effective_n = 1.0 / sum(w**2 for w in weights) if weights else 0
        
        return AnalyticsResult(
            metric_name="effective_positions",
            value=round(float(effective_n), 2),
            additional_data={
                "actual_positions": len(weights),
                "concentration_ratio": float(effective_n / len(weights)) if len(weights) > 0 else 0
            }
        )
    
    def _group_weights_by_key(self, positions: List[Dict[str, Any]], 
                            key: str, weights: List[float]) -> Dict[str, float]:
        """Grupuje wagi według klucza"""
        grouped = defaultdict(float)
        
        for pos, weight in zip(positions, weights):
            group_key = pos.get(key, 'unknown')
            grouped[group_key] += weight
        
        return dict(grouped)
    
    def _interpret_hhi(self, hhi: float) -> str:
        """Interpretuje wartość HHI"""
        if hhi < 1500:
            return "highly_diversified"
        elif hhi < 2500:
            return "moderately_diversified"
        else:
            return "concentrated"

class MarketAnalytics:
    """Analityka rynkowa"""
    
    def calculate_volatility_metrics(self, prices: List[float], window: int = 20) -> Dict[str, AnalyticsResult]:
        """Oblicza metryki zmienności"""
        if not prices or len(prices) < window + 1:
            return {}
        
        prices_array = np.array(prices)
        returns = np.diff(np.log(prices_array))
        
        results = {}
        
        # Historical volatility
        historical_vol = np.std(returns) * np.sqrt(252)
        results["historical_volatility"] = AnalyticsResult(
            metric_name="historical_volatility",
            value=round(float(historical_vol) * 100, 4),
            additional_data={
                "annualized": True,
                "sample_size": len(returns)
            }
        )
        
        # Rolling volatility
        if len(returns) >= window:
            rolling_vol = pd.Series(returns).rolling(window).std() * np.sqrt(252)
            current_vol = rolling_vol.iloc[-1]
            avg_vol = rolling_vol.mean()
            
            results["rolling_volatility"] = AnalyticsResult(
                metric_name="rolling_volatility",
                value=round(float(current_vol) * 100, 4),
                additional_data={
                    "window_days": window,
                    "average_rolling_vol": float(avg_vol) * 100,
                    "vol_trend": "increasing" if current_vol > avg_vol else "decreasing"
                }
            )
        
        # Volatility of volatility
        if len(returns) >= window * 2:
            vol_series = pd.Series(returns).rolling(window).std()
            vol_of_vol = vol_series.std() * np.sqrt(252)
            
            results["volatility_of_volatility"] = AnalyticsResult(
                metric_name="volatility_of_volatility",
                value=round(float(vol_of_vol) * 100, 4),
                additional_data={
                    "indicates": "volatility_clustering" if vol_of_vol > historical_vol * 0.5 else "stable_volatility"
                }
            )
        
        return results
    
    def calculate_momentum_indicators(self, prices: List[float]) -> Dict[str, AnalyticsResult]:
        """Oblicza wskaźniki momentum"""
        if not prices or len(prices) < 10:
            return {}
        
        prices_array = np.array(prices)
        results = {}
        
        # Rate of Change (ROC) for different periods
        for period in [5, 10, 20]:
            if len(prices) > period:
                roc = (prices_array[-1] / prices_array[-period-1] - 1) * 100
                results[f"roc_{period}d"] = AnalyticsResult(
                    metric_name=f"roc_{period}d",
                    value=round(float(roc), 4),
                    additional_data={
                        "period_days": period,
                        "start_price": float(prices_array[-period-1]),
                        "end_price": float(prices_array[-1])
                    }
                )
        
        # Moving average trends
        if len(prices) >= 20:
            ma_20 = np.mean(prices_array[-20:])
            current_price = prices_array[-1]
            ma_signal = (current_price / ma_20 - 1) * 100
            
            results["ma_signal_20d"] = AnalyticsResult(
                metric_name="ma_signal_20d",
                value=round(float(ma_signal), 4),
                additional_data={
                    "ma_value": float(ma_20),
                    "current_price": float(current_price),
                    "signal": "bullish" if ma_signal > 0 else "bearish"
                }
            )
        
        return results

class AdvancedAnalyticsEngine:
    """Główny silnik zaawansowanej analityki"""
    
    def __init__(self):
        self.performance = PerformanceAnalytics()
        self.risk = RiskAnalytics()
        self.portfolio = PortfolioAnalytics()
        self.market = MarketAnalytics()
        
        # Cache for expensive calculations
        self.calculation_cache = {}
        self.cache_ttl = 300  # 5 minutes
        
    async def run_comprehensive_analysis(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Uruchamia kompleksową analizę"""
        
        results = {
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            "performance_metrics": {},
            "risk_metrics": {},
            "portfolio_metrics": {},
            "market_metrics": {}
        }
        
        try:
            # Performance analysis
            if "returns" in data:
                returns = data["returns"]
                
                results["performance_metrics"]["sharpe_ratio"] = self.performance.calculate_sharpe_ratio(returns)
                results["performance_metrics"]["sortino_ratio"] = self.performance.calculate_sortino_ratio(returns)
                
                if "equity_curve" in data:
                    equity_curve = data["equity_curve"]
                    results["performance_metrics"]["maximum_drawdown"] = self.performance.calculate_maximum_drawdown(equity_curve)
                    results["performance_metrics"]["calmar_ratio"] = self.performance.calculate_calmar_ratio(returns, equity_curve)
                
                if "trades" in data:
                    trades = data["trades"]
                    results["performance_metrics"]["win_rate"] = self.performance.calculate_win_rate(trades)
                    results["performance_metrics"]["profit_factor"] = self.performance.calculate_profit_factor(trades)
                    results["performance_metrics"].update(self.performance.calculate_average_trade_metrics(trades))
                
                # Risk analysis
                results["risk_metrics"]["value_at_risk"] = self.risk.calculate_value_at_risk(returns)
                results["risk_metrics"]["conditional_var"] = self.risk.calculate_conditional_var(returns)
                
                if "market_returns" in data:
                    market_returns = data["market_returns"]
                    results["risk_metrics"]["beta"] = self.risk.calculate_beta(returns, market_returns)
                    results["risk_metrics"]["tracking_error"] = self.risk.calculate_tracking_error(returns, market_returns)
            
            # Portfolio analysis
            if "positions" in data:
                positions = data["positions"]
                results["portfolio_metrics"].update(self.portfolio.calculate_diversification_metrics(positions))
                
                correlation_matrix = data.get("correlation_matrix")
                results["portfolio_metrics"].update(
                    self.portfolio.calculate_portfolio_risk_metrics(positions, correlation_matrix)
                )
            
            # Market analysis
            if "prices" in data:
                prices = data["prices"]
                results["market_metrics"].update(self.market.calculate_volatility_metrics(prices))
                results["market_metrics"].update(self.market.calculate_momentum_indicators(prices))
            
            logger.info("Comprehensive analysis completed successfully")
            
        except Exception as e:
            logger.error(f"Error during comprehensive analysis: {e}")
            results["error"] = str(e)
        
        return results
    
    def serialize_results(self, results: Dict[str, Any]) -> str:
        """Serializuje wyniki do JSON"""
        def serialize_analytics_result(obj):
            if isinstance(obj, AnalyticsResult):
                return {
                    "metric_name": obj.metric_name,
                    "value": obj.value,
                    "confidence": obj.confidence,
                    "percentile": obj.percentile,
                    "benchmark_comparison": obj.benchmark_comparison,
                    "time_period": obj.time_period,
                    "additional_data": obj.additional_data,
                    "calculated_at": obj.calculated_at.isoformat() if obj.calculated_at else None
                }
            elif isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            
            return obj
        
        return json.dumps(results, default=serialize_analytics_result, indent=2)

# ==================================================================================
# 📈 USAGE EXAMPLE
# ==================================================================================

async def example_analytics_usage():
    """Przykład użycia silnika analityki"""
    
    # Sample data
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, 252).tolist()  # Daily returns for 1 year
    equity_curve = np.cumprod(1 + np.array(returns)).tolist()
    market_returns = np.random.normal(0.0008, 0.015, 252).tolist()
    
    # Sample trade data
    trades = np.random.normal(0.002, 0.05, 100).tolist()
    
    # Sample positions
    positions = [
        {"symbol": "BTC/USDT", "market_value": 10000, "volatility": 0.8, "sector": "crypto", "exchange": "binance"},
        {"symbol": "ETH/USDT", "market_value": 8000, "volatility": 0.7, "sector": "crypto", "exchange": "binance"},
        {"symbol": "AAPL", "market_value": 5000, "volatility": 0.3, "sector": "tech", "exchange": "nasdaq"},
        {"symbol": "TSLA", "market_value": 3000, "volatility": 0.6, "sector": "auto", "exchange": "nasdaq"},
    ]
    
    # Sample prices
    prices = np.cumprod(1 + np.array(returns)) * 100
    
    # Create analytics engine
    engine = AdvancedAnalyticsEngine()
    
    # Prepare data
    data = {
        "returns": returns,
        "equity_curve": equity_curve,
        "market_returns": market_returns,
        "trades": trades,
        "positions": positions,
        "prices": prices.tolist()
    }
    
    # Run comprehensive analysis
    results = await engine.run_comprehensive_analysis(data)
    
    # Print results
    print("=== COMPREHENSIVE ANALYTICS RESULTS ===")
    print(engine.serialize_results(results))
    
    # Individual metric examples
    print("\n=== INDIVIDUAL METRIC EXAMPLES ===")
    
    # Sharpe ratio
    sharpe = engine.performance.calculate_sharpe_ratio(returns)
    print(f"Sharpe Ratio: {sharpe.value} (Percentile: {sharpe.percentile}%)")
    
    # Maximum drawdown
    max_dd = engine.performance.calculate_maximum_drawdown(equity_curve)
    print(f"Maximum Drawdown: {max_dd.value}%")
    
    # Value at Risk
    var = engine.risk.calculate_value_at_risk(returns, 0.95)
    print(f"VaR (95%): {var.value}%")
    
    # Portfolio diversification
    div_metrics = engine.portfolio.calculate_diversification_metrics(positions)
    if "concentration_hhi" in div_metrics:
        hhi = div_metrics["concentration_hhi"]
        print(f"Portfolio HHI: {hhi.value} ({hhi.additional_data['interpretation']})")

if __name__ == "__main__":
    asyncio.run(example_analytics_usage())
