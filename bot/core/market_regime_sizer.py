"""
Market Regime Position Sizer - Adjusts position sizes based on market conditions.

Dynamically scales position sizes based on:
1. Market volatility regime
2. Trend strength
3. Sentiment indicators
4. Correlation regime
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classification."""
    TRENDING_BULLISH = "trending_bullish"
    TRENDING_BEARISH = "trending_bearish"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CRISIS = "crisis"
    RECOVERY = "recovery"
    EUPHORIA = "euphoria"
    CAPITULATION = "capitulation"


class TrendStrength(Enum):
    """Trend strength classification."""
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NO_TREND = "no_trend"


@dataclass
class RegimeIndicators:
    """Indicators for regime detection."""
    volatility_percentile: float  # 0-100, where >80 is high vol
    trend_direction: int          # 1 = up, -1 = down, 0 = sideways
    trend_strength: float         # 0-100
    fear_greed_index: int         # 0-100
    correlation_with_btc: float   # -1 to 1
    volume_percentile: float      # 0-100
    timestamp: datetime = None


@dataclass
class PositionSizeMultiplier:
    """Position size adjustment factors."""
    base_multiplier: float = 1.0
    volatility_adj: float = 1.0
    trend_adj: float = 1.0
    sentiment_adj: float = 1.0
    correlation_adj: float = 1.0
    
    @property
    def final_multiplier(self) -> float:
        """Combined multiplier."""
        combined = (
            self.base_multiplier *
            self.volatility_adj *
            self.trend_adj *
            self.sentiment_adj *
            self.correlation_adj
        )
        # Clamp between 0.1 and 2.0
        return max(0.1, min(2.0, combined))
    
    def to_dict(self) -> dict:
        return {
            "base_multiplier": self.base_multiplier,
            "volatility_adj": self.volatility_adj,
            "trend_adj": self.trend_adj,
            "sentiment_adj": self.sentiment_adj,
            "correlation_adj": self.correlation_adj,
            "final_multiplier": self.final_multiplier
        }


class MarketRegimeDetector:
    """
    Detects current market regime from indicators.
    """
    
    def __init__(self):
        self._last_regime: Optional[MarketRegime] = None
        self._regime_duration: int = 0
    
    def detect_regime(self, indicators: RegimeIndicators) -> MarketRegime:
        """Detect current market regime from indicators."""
        vol = indicators.volatility_percentile
        trend_dir = indicators.trend_direction
        trend_str = indicators.trend_strength
        fgi = indicators.fear_greed_index
        
        # Crisis detection (highest priority)
        if vol > 90 and fgi < 20:
            regime = MarketRegime.CRISIS
        # Capitulation
        elif vol > 80 and fgi < 15 and trend_dir < 0:
            regime = MarketRegime.CAPITULATION
        # Euphoria
        elif fgi > 85 and trend_dir > 0 and trend_str > 70:
            regime = MarketRegime.EUPHORIA
        # High volatility regime
        elif vol > 75:
            regime = MarketRegime.HIGH_VOLATILITY
        # Low volatility regime
        elif vol < 25:
            regime = MarketRegime.LOW_VOLATILITY
        # Trending bullish
        elif trend_dir > 0 and trend_str > 50:
            regime = MarketRegime.TRENDING_BULLISH
        # Trending bearish
        elif trend_dir < 0 and trend_str > 50:
            regime = MarketRegime.TRENDING_BEARISH
        # Recovery (after crisis/capitulation)
        elif self._last_regime in [MarketRegime.CRISIS, MarketRegime.CAPITULATION] \
                and fgi > 30 and vol < 70:
            regime = MarketRegime.RECOVERY
        # Default: ranging market
        else:
            regime = MarketRegime.RANGING
        
        # Track regime duration
        if regime == self._last_regime:
            self._regime_duration += 1
        else:
            self._regime_duration = 0
            self._last_regime = regime
        
        return regime
    
    def get_trend_strength(self, indicators: RegimeIndicators) -> TrendStrength:
        """Classify trend strength."""
        strength = indicators.trend_strength
        
        if strength > 70:
            return TrendStrength.STRONG
        elif strength > 40:
            return TrendStrength.MODERATE
        elif strength > 20:
            return TrendStrength.WEAK
        else:
            return TrendStrength.NO_TREND


class MarketRegimeSizer:
    """
    Adjusts position sizes based on market regime.
    
    Usage:
        sizer = MarketRegimeSizer()
        
        # Get position adjustment for current conditions
        multiplier = sizer.get_size_multiplier(
            regime=MarketRegime.HIGH_VOLATILITY,
            indicators=RegimeIndicators(
                volatility_percentile=80,
                trend_direction=1,
                trend_strength=60,
                fear_greed_index=45,
                correlation_with_btc=0.8,
                volume_percentile=70
            )
        )
        
        adjusted_size = base_size * multiplier.final_multiplier
    """
    
    # Base multipliers per regime
    REGIME_MULTIPLIERS = {
        MarketRegime.TRENDING_BULLISH: 1.2,     # Increase in strong trends
        MarketRegime.TRENDING_BEARISH: 0.8,     # Reduce in downtrends
        MarketRegime.RANGING: 1.0,              # Normal in ranging
        MarketRegime.HIGH_VOLATILITY: 0.5,      # Reduce significantly in high vol
        MarketRegime.LOW_VOLATILITY: 1.1,       # Slight increase in low vol
        MarketRegime.CRISIS: 0.2,               # Minimal in crisis
        MarketRegime.RECOVERY: 0.7,             # Cautious in recovery
        MarketRegime.EUPHORIA: 0.4,             # Reduce in euphoria (reversal risk)
        MarketRegime.CAPITULATION: 0.3,         # Very small in capitulation
    }
    
    # Max allowed position based on volatility percentile
    VOLATILITY_LIMITS = {
        90: 0.3,   # >90% vol: max 30% of normal
        80: 0.5,   # >80% vol: max 50% of normal
        70: 0.7,   # >70% vol: max 70% of normal
        60: 0.85,  # >60% vol: max 85% of normal
        0: 1.0,    # Normal conditions
    }
    
    def __init__(
        self,
        min_multiplier: float = 0.1,
        max_multiplier: float = 2.0,
        use_volatility_scaling: bool = True,
        use_sentiment_scaling: bool = True
    ):
        self.min_multiplier = min_multiplier
        self.max_multiplier = max_multiplier
        self.use_volatility_scaling = use_volatility_scaling
        self.use_sentiment_scaling = use_sentiment_scaling
        self.regime_detector = MarketRegimeDetector()
        
        # History for regime persistence
        self._regime_history: List[MarketRegime] = []
    
    def get_size_multiplier(
        self,
        regime: MarketRegime = None,
        indicators: RegimeIndicators = None,
        signal_direction: str = "long"
    ) -> PositionSizeMultiplier:
        """
        Get position size multiplier based on market conditions.
        
        Args:
            regime: Market regime (will detect if not provided)
            indicators: Market indicators
            signal_direction: 'long' or 'short'
            
        Returns:
            PositionSizeMultiplier with all adjustments
        """
        result = PositionSizeMultiplier()
        
        # Detect regime if not provided
        if regime is None and indicators:
            regime = self.regime_detector.detect_regime(indicators)
        
        # Base regime multiplier
        if regime:
            result.base_multiplier = self.REGIME_MULTIPLIERS.get(regime, 1.0)
            
            # Track regime history
            self._regime_history.append(regime)
            if len(self._regime_history) > 100:
                self._regime_history = self._regime_history[-100:]
        
        if indicators:
            # Volatility adjustment
            if self.use_volatility_scaling:
                result.volatility_adj = self._calculate_volatility_adjustment(
                    indicators.volatility_percentile
                )
            
            # Trend alignment adjustment
            result.trend_adj = self._calculate_trend_adjustment(
                indicators, signal_direction
            )
            
            # Sentiment adjustment
            if self.use_sentiment_scaling:
                result.sentiment_adj = self._calculate_sentiment_adjustment(
                    indicators.fear_greed_index, signal_direction
                )
            
            # Correlation adjustment
            result.correlation_adj = self._calculate_correlation_adjustment(
                indicators.correlation_with_btc
            )
        
        logger.debug(
            f"Position size adjustment: regime={regime}, "
            f"multiplier={result.final_multiplier:.2f}"
        )
        
        return result
    
    def _calculate_volatility_adjustment(
        self,
        volatility_percentile: float
    ) -> float:
        """
        Scale down position in high volatility.
        
        Higher volatility = smaller positions to maintain constant risk.
        """
        for threshold, limit in sorted(self.VOLATILITY_LIMITS.items(), reverse=True):
            if volatility_percentile > threshold:
                return limit
        return 1.0
    
    def _calculate_trend_adjustment(
        self,
        indicators: RegimeIndicators,
        signal_direction: str
    ) -> float:
        """
        Adjust based on trend alignment.
        
        Trading with the trend gets a boost.
        Trading against the trend gets reduced.
        """
        trend_dir = indicators.trend_direction
        trend_str = indicators.trend_strength / 100  # Normalize to 0-1
        
        is_long = signal_direction.lower() == 'long'
        
        # Check alignment
        aligned = (trend_dir > 0 and is_long) or (trend_dir < 0 and not is_long)
        
        if aligned:
            # Boost for trend-aligned trades
            return 1.0 + (trend_str * 0.3)  # Max 1.3x for strong aligned trends
        else:
            # Reduce for counter-trend trades
            return 1.0 - (trend_str * 0.4)  # Min 0.6x for strong counter-trend
    
    def _calculate_sentiment_adjustment(
        self,
        fear_greed_index: int,
        signal_direction: str
    ) -> float:
        """
        Adjust based on sentiment extremes.
        
        Extreme fear while going long: contrarian, slight boost
        Extreme greed while going long: reduce size (reversal risk)
        """
        is_long = signal_direction.lower() == 'long'
        
        if fear_greed_index < 20:  # Extreme fear
            return 1.1 if is_long else 0.9  # Slight contrarian boost for longs
        elif fear_greed_index > 80:  # Extreme greed
            return 0.7 if is_long else 1.1  # Reduce longs, boost shorts
        elif fear_greed_index > 65:  # Greed
            return 0.85 if is_long else 1.0
        elif fear_greed_index < 35:  # Fear
            return 1.0 if is_long else 0.85
        else:
            return 1.0  # Neutral sentiment
    
    def _calculate_correlation_adjustment(
        self,
        correlation_with_btc: float
    ) -> float:
        """
        Adjust based on correlation regime.
        
        High correlation = reduce size to limit portfolio concentration.
        Low/negative correlation = can increase (diversification benefit).
        """
        corr = abs(correlation_with_btc)
        
        if corr > 0.9:
            return 0.7  # High correlation, reduce significantly
        elif corr > 0.7:
            return 0.85  # Moderate-high correlation
        elif corr < 0.3:
            return 1.1  # Low correlation, slight boost
        else:
            return 1.0
    
    def should_reduce_exposure(
        self,
        regime: MarketRegime,
        indicators: RegimeIndicators = None
    ) -> bool:
        """Check if current conditions warrant exposure reduction."""
        # Always reduce in crisis/capitulation
        if regime in [MarketRegime.CRISIS, MarketRegime.CAPITULATION]:
            return True
        
        # Reduce in euphoria (reversal imminent)
        if regime == MarketRegime.EUPHORIA:
            return True
        
        # Reduce in extreme volatility
        if indicators and indicators.volatility_percentile > 85:
            return True
        
        # Check for regime instability
        if len(self._regime_history) >= 5:
            recent = self._regime_history[-5:]
            unique_regimes = len(set(recent))
            if unique_regimes >= 3:  # 3+ different regimes in 5 periods
                return True  # Market is unstable
        
        return False
    
    def get_max_leverage_for_regime(
        self,
        regime: MarketRegime,
        base_max_leverage: float = 5.0
    ) -> float:
        """Get recommended max leverage for current regime."""
        leverage_limits = {
            MarketRegime.CRISIS: 1.0,
            MarketRegime.CAPITULATION: 1.0,
            MarketRegime.EUPHORIA: 1.5,
            MarketRegime.HIGH_VOLATILITY: 2.0,
            MarketRegime.TRENDING_BEARISH: 3.0,
            MarketRegime.RECOVERY: 3.0,
            MarketRegime.TRENDING_BULLISH: 4.0,
            MarketRegime.RANGING: 4.0,
            MarketRegime.LOW_VOLATILITY: 5.0,
        }
        
        regime_limit = leverage_limits.get(regime, 3.0)
        return min(base_max_leverage, regime_limit)


# Global instance
_regime_sizer: Optional[MarketRegimeSizer] = None


def get_regime_sizer(
    min_multiplier: float = 0.1,
    max_multiplier: float = 2.0
) -> MarketRegimeSizer:
    """Get or create global regime sizer."""
    global _regime_sizer
    if _regime_sizer is None:
        _regime_sizer = MarketRegimeSizer(
            min_multiplier=min_multiplier,
            max_multiplier=max_multiplier
        )
    return _regime_sizer
