"""
Correlation Manager - Limits exposure to correlated assets.

Prevents over-concentration in highly correlated positions
(e.g., BTC + ETH + SOL all moving together).

v2.0: Added dynamic correlation calculation from price data.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class CorrelationConfig:
    """Configuration for correlation-based limits."""
    max_correlated_exposure_pct: float = 50.0  # Max % of portfolio in correlated assets
    correlation_threshold: float = 0.7         # Above this = considered correlated
    max_positions_per_category: int = 3        # Max positions in same category
    max_single_asset_pct: float = 30.0         # Max % in single asset


# Asset categories and their correlations
ASSET_CATEGORIES = {
    'large_cap': ['BTC', 'ETH'],
    'alt_l1': ['SOL', 'ADA', 'AVAX', 'DOT', 'ATOM', 'NEAR', 'APT', 'SUI'],
    'defi': ['UNI', 'AAVE', 'MKR', 'CRV', 'LINK', 'SNX', 'COMP'],
    'meme': ['DOGE', 'SHIB', 'PEPE', 'FLOKI', 'BONK', 'WIF'],
    'gaming': ['AXS', 'SAND', 'MANA', 'GALA', 'IMX', 'ENJ'],
    'layer2': ['MATIC', 'ARB', 'OP', 'STRK'],
    'exchange': ['BNB', 'FTT', 'OKB', 'CRO', 'KCS'],
    'ai': ['FET', 'AGIX', 'OCEAN', 'RNDR', 'TAO'],
    'privacy': ['XMR', 'ZEC', 'DASH'],
    'stable': ['USDT', 'USDC', 'DAI', 'BUSD'],
}

# Pre-computed correlation matrix (simplified - based on historical data)
# In production, this should be calculated from actual price data
# v3.0 ENHANCED: Added full matrix with XRP and more pairs
CORRELATION_MATRIX: Dict[Tuple[str, str], float] = {
    # BTC correlations (market leader)
    ('BTC', 'ETH'): 0.85,
    ('BTC', 'SOL'): 0.75,
    ('BTC', 'XRP'): 0.72,
    ('BTC', 'ADA'): 0.70,
    ('BTC', 'AVAX'): 0.72,
    ('BTC', 'DOT'): 0.70,
    ('BTC', 'LINK'): 0.65,
    ('BTC', 'BNB'): 0.60,
    ('BTC', 'DOGE'): 0.55,
    ('BTC', 'SHIB'): 0.45,
    ('BTC', 'MATIC'): 0.68,
    ('BTC', 'ATOM'): 0.65,
    ('BTC', 'NEAR'): 0.67,
    ('BTC', 'APT'): 0.63,
    ('BTC', 'SUI'): 0.60,
    ('BTC', 'ARB'): 0.72,
    ('BTC', 'OP'): 0.70,
    
    # ETH correlations (L2 leader)
    ('ETH', 'SOL'): 0.80,
    ('ETH', 'XRP'): 0.68,
    ('ETH', 'ADA'): 0.75,
    ('ETH', 'AVAX'): 0.78,
    ('ETH', 'MATIC'): 0.75,
    ('ETH', 'ARB'): 0.82,
    ('ETH', 'OP'): 0.80,
    ('ETH', 'UNI'): 0.70,
    ('ETH', 'AAVE'): 0.72,
    ('ETH', 'LINK'): 0.68,
    ('ETH', 'DOT'): 0.72,
    ('ETH', 'ATOM'): 0.65,
    ('ETH', 'NEAR'): 0.70,
    ('ETH', 'APT'): 0.68,
    ('ETH', 'SUI'): 0.65,
    
    # XRP correlations (payments focus)
    ('XRP', 'SOL'): 0.65,
    ('XRP', 'ADA'): 0.70,
    ('XRP', 'DOT'): 0.62,
    ('XRP', 'LINK'): 0.55,
    ('XRP', 'AVAX'): 0.58,
    ('XRP', 'MATIC'): 0.60,
    ('XRP', 'ATOM'): 0.58,
    ('XRP', 'DOGE'): 0.50,
    
    # Alt L1 inter-correlations
    ('SOL', 'AVAX'): 0.75,
    ('SOL', 'ADA'): 0.70,
    ('SOL', 'DOT'): 0.68,
    ('SOL', 'NEAR'): 0.72,
    ('SOL', 'APT'): 0.75,
    ('SOL', 'SUI'): 0.78,
    ('SOL', 'ATOM'): 0.65,
    ('ADA', 'DOT'): 0.72,
    ('ADA', 'AVAX'): 0.68,
    ('ADA', 'ATOM'): 0.63,
    ('AVAX', 'DOT'): 0.70,
    ('AVAX', 'NEAR'): 0.68,
    ('APT', 'SUI'): 0.80,
    ('NEAR', 'APT'): 0.68,
    
    # Meme coin correlations (high volatility)
    ('DOGE', 'SHIB'): 0.85,
    ('DOGE', 'PEPE'): 0.75,
    ('SHIB', 'PEPE'): 0.80,
    ('PEPE', 'BONK'): 0.78,
    ('DOGE', 'FLOKI'): 0.70,
    ('BONK', 'WIF'): 0.82,
    ('PEPE', 'WIF'): 0.75,
    ('SHIB', 'FLOKI'): 0.72,
    
    # DeFi correlations
    ('UNI', 'AAVE'): 0.72,
    ('UNI', 'MKR'): 0.65,
    ('AAVE', 'MKR'): 0.68,
    ('CRV', 'SNX'): 0.60,
    ('UNI', 'CRV'): 0.65,
    ('AAVE', 'COMP'): 0.70,
    ('LINK', 'UNI'): 0.58,
    ('LINK', 'AAVE'): 0.60,
    
    # Layer 2 correlations
    ('MATIC', 'ARB'): 0.75,
    ('MATIC', 'OP'): 0.78,
    ('ARB', 'OP'): 0.85,
    ('ARB', 'STRK'): 0.72,
    ('OP', 'STRK'): 0.70,
    
    # AI tokens correlations
    ('FET', 'AGIX'): 0.82,
    ('FET', 'OCEAN'): 0.75,
    ('AGIX', 'OCEAN'): 0.78,
    ('RNDR', 'TAO'): 0.65,
    ('FET', 'RNDR'): 0.60,
    
    # Gaming correlations
    ('AXS', 'SAND'): 0.75,
    ('AXS', 'MANA'): 0.72,
    ('SAND', 'MANA'): 0.78,
    ('GALA', 'IMX'): 0.70,
    ('AXS', 'GALA'): 0.68,
    
    # Exchange tokens
    ('BNB', 'CRO'): 0.55,
    ('BNB', 'OKB'): 0.58,
}


@dataclass
class Position:
    """Simplified position for correlation check."""
    symbol: str
    base_asset: str
    value_usd: float
    side: str  # 'long' or 'short'


@dataclass 
class CorrelationCheckResult:
    """Result of correlation check."""
    can_open: bool
    reason: Optional[str] = None
    correlated_positions: List[str] = None
    total_correlated_exposure_pct: float = 0.0
    category_exposure: Dict[str, float] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.correlated_positions is None:
            self.correlated_positions = []
        if self.category_exposure is None:
            self.category_exposure = {}
        if self.warnings is None:
            self.warnings = []


class CorrelationManager:
    """
    Manages correlation-based position limits.
    
    Prevents:
    1. Too much exposure to correlated assets
    2. Over-concentration in one category
    3. Portfolio becoming effectively a single bet
    
    v2.0: Dynamic correlation calculation from price data.
    
    Usage:
        manager = CorrelationManager()
        
        # Before opening new position
        result = manager.can_open_position(
            new_symbol="SOL/USDT",
            proposed_size_usd=1000,
            current_positions=[...],
            portfolio_value_usd=10000
        )
        
        if not result.can_open:
            logger.warning(f"Blocked: {result.reason}")
    """
    
    def __init__(self, config: CorrelationConfig = None, exchange_adapter=None,
                 max_correlation_exposure: float = None, correlation_threshold: float = None):
        """
        Initialize CorrelationManager.
        
        P1-8 FIX: Added legacy-compatible constructor parameters.
        
        Args:
            config: CorrelationConfig object
            exchange_adapter: Exchange adapter for dynamic correlation
            max_correlation_exposure: Legacy param - max % in correlated assets
            correlation_threshold: Legacy param - correlation threshold
        """
        # P1-8 FIX: Support both new and legacy initialization
        if config:
            self.config = config
        else:
            self.config = CorrelationConfig()
            if max_correlation_exposure is not None:
                self.config.max_correlated_exposure_pct = max_correlation_exposure * 100  # Convert to %
            if correlation_threshold is not None:
                self.config.correlation_threshold = correlation_threshold
                
        self._static_correlation_matrix = CORRELATION_MATRIX
        self._asset_categories = ASSET_CATEGORIES
        self._exchange = exchange_adapter
        
        # Dynamic correlation cache
        self._dynamic_correlations: Dict[Tuple[str, str], float] = {}
        self._correlation_cache_time: Dict[Tuple[str, str], datetime] = {}
        self._cache_ttl = timedelta(hours=1)  # Refresh correlations hourly
        
        # P1-8 FIX: Track open positions for correlation checking
        self._tracked_positions: Dict[str, Position] = {}
        self._portfolio_value_usd: float = 0.0
        
        # Build reverse lookup: asset -> category
        self._asset_to_category: Dict[str, str] = {}
        for category, assets in self._asset_categories.items():
            for asset in assets:
                self._asset_to_category[asset] = category
    
    def set_exchange(self, exchange_adapter) -> None:
        """Set exchange adapter for dynamic correlation calculation."""
        self._exchange = exchange_adapter
        logger.info("📊 Correlation Manager: Exchange adapter connected for dynamic correlations")
    
    # ========== P1-8 FIX: Missing methods used by auto_trader.py ==========
    
    def set_portfolio_value(self, value_usd: float) -> None:
        """Update tracked portfolio value."""
        self._portfolio_value_usd = value_usd
    
    def add_position(
        self,
        symbol: str,
        side: str,
        value_usd: float
    ) -> None:
        """
        Add position to internal tracking.
        
        P1-8 FIX: Method used by auto_trader but was missing.
        """
        base_asset = self._extract_base_asset(symbol)
        self._tracked_positions[symbol] = Position(
            symbol=symbol,
            base_asset=base_asset,
            value_usd=value_usd,
            side=side.lower()
        )
        logger.debug(f"📊 Correlation: Added position {symbol} ({side}) ${value_usd:.2f}")
    
    def remove_position(self, symbol: str) -> None:
        """
        Remove position from internal tracking.
        
        P1-8 FIX: Method used by auto_trader but was missing.
        """
        if symbol in self._tracked_positions:
            del self._tracked_positions[symbol]
            logger.debug(f"📊 Correlation: Removed position {symbol}")
    
    def check_correlation_limit(
        self,
        symbol: str,
        side: str,
        proposed_value_usd: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if new position would exceed correlation limits.
        
        P1-8 FIX: Method used by auto_trader but was missing.
        
        Args:
            symbol: Trading pair symbol
            side: 'long' or 'short'
            proposed_value_usd: Value of proposed position
            
        Returns:
            Tuple of (can_open, reason_if_blocked)
        """
        # Get current positions as list
        current_positions = list(self._tracked_positions.values())
        
        # Use tracked portfolio value or estimate from positions
        portfolio_value = self._portfolio_value_usd
        if portfolio_value <= 0:
            portfolio_value = sum(p.value_usd for p in current_positions) + proposed_value_usd
            if portfolio_value <= 0:
                portfolio_value = proposed_value_usd * 10  # Estimate as 10% of portfolio
        
        # Use existing can_open_position method
        result = self.can_open_position(
            new_symbol=symbol,
            proposed_size_usd=proposed_value_usd,
            current_positions=current_positions,
            portfolio_value_usd=portfolio_value
        )
        
        if result.can_open:
            # Log warnings if any
            for warning in result.warnings:
                logger.warning(f"⚠️ Correlation warning: {warning}")
            return True, None
        else:
            return False, result.reason
    
    def get_tracked_positions(self) -> List[Position]:
        """Get list of currently tracked positions."""
        return list(self._tracked_positions.values())
    
    async def calculate_dynamic_correlation(
        self,
        asset1: str,
        asset2: str,
        period_days: int = 30,
        timeframe: str = '1h'
    ) -> Optional[float]:
        """
        Calculate actual correlation between two assets using price data.
        
        Uses Pearson correlation coefficient on returns.
        
        Args:
            asset1: First asset symbol (e.g., 'BTC')
            asset2: Second asset symbol (e.g., 'ETH')
            period_days: Number of days of historical data
            timeframe: Candle timeframe ('1h', '4h', '1d')
            
        Returns:
            Correlation coefficient (-1 to 1) or None if calculation fails
        """
        if not self._exchange:
            return None
        
        # Check cache first
        cache_key = (asset1.upper(), asset2.upper())
        cache_key_rev = (asset2.upper(), asset1.upper())
        
        for key in [cache_key, cache_key_rev]:
            if key in self._dynamic_correlations:
                cache_time = self._correlation_cache_time.get(key)
                if cache_time and datetime.now() - cache_time < self._cache_ttl:
                    return self._dynamic_correlations[key]
        
        try:
            # Fetch OHLCV data for both assets
            symbol1 = f"{asset1.upper()}/USDT"
            symbol2 = f"{asset2.upper()}/USDT"
            
            # Calculate number of candles needed
            hours_per_candle = {'1h': 1, '4h': 4, '1d': 24}.get(timeframe, 1)
            limit = int((period_days * 24) / hours_per_candle)
            
            ohlcv1 = await self._exchange.exchange.fetch_ohlcv(symbol1, timeframe, limit=limit)
            ohlcv2 = await self._exchange.exchange.fetch_ohlcv(symbol2, timeframe, limit=limit)
            
            if not ohlcv1 or not ohlcv2:
                logger.debug(f"No OHLCV data for {asset1}/{asset2}")
                return None
            
            # Extract closing prices
            closes1 = [candle[4] for candle in ohlcv1]
            closes2 = [candle[4] for candle in ohlcv2]
            
            # Ensure same length
            min_len = min(len(closes1), len(closes2))
            closes1 = closes1[-min_len:]
            closes2 = closes2[-min_len:]
            
            if min_len < 10:
                logger.debug(f"Insufficient data for correlation: {min_len} candles")
                return None
            
            # Calculate returns
            returns1 = [(closes1[i] - closes1[i-1]) / closes1[i-1] 
                       for i in range(1, len(closes1)) if closes1[i-1] > 0]
            returns2 = [(closes2[i] - closes2[i-1]) / closes2[i-1] 
                       for i in range(1, len(closes2)) if closes2[i-1] > 0]
            
            # Ensure same length after returns calculation
            min_len = min(len(returns1), len(returns2))
            returns1 = returns1[:min_len]
            returns2 = returns2[:min_len]
            
            if min_len < 5:
                return None
            
            # Calculate Pearson correlation
            n = len(returns1)
            mean1 = sum(returns1) / n
            mean2 = sum(returns2) / n
            
            numerator = sum((returns1[i] - mean1) * (returns2[i] - mean2) for i in range(n))
            std1 = (sum((r - mean1) ** 2 for r in returns1) / n) ** 0.5
            std2 = (sum((r - mean2) ** 2 for r in returns2) / n) ** 0.5
            
            if std1 == 0 or std2 == 0:
                return None
            
            correlation = numerator / (n * std1 * std2)
            
            # Cache result
            self._dynamic_correlations[cache_key] = correlation
            self._correlation_cache_time[cache_key] = datetime.now()
            
            logger.debug(
                f"📊 Dynamic correlation {asset1}/{asset2}: {correlation:.2f} "
                f"(from {min_len} {timeframe} candles)"
            )
            
            return correlation
            
        except Exception as e:
            logger.debug(f"Failed to calculate dynamic correlation: {e}")
            return None
    
    async def get_correlation_async(self, asset1: str, asset2: str) -> float:
        """
        Get correlation between two assets, preferring dynamic calculation.
        Falls back to static matrix if dynamic calculation fails.
        """
        if asset1 == asset2:
            return 1.0
        
        # Try dynamic calculation first
        if self._exchange:
            dynamic_corr = await self.calculate_dynamic_correlation(asset1, asset2)
            if dynamic_corr is not None:
                return dynamic_corr
        
        # Fallback to static matrix
        return self.get_correlation(asset1, asset2)
    
    def get_correlation(self, asset1: str, asset2: str) -> float:
        """
        Get correlation between two assets from static matrix.
        Use get_correlation_async for dynamic calculation.
        
        Returns:
            Correlation coefficient (0-1)
        """
        if asset1 == asset2:
            return 1.0
        
        # Check both orders in static matrix
        key = (asset1, asset2)
        if key in self._static_correlation_matrix:
            return self._static_correlation_matrix[key]
        
        key_rev = (asset2, asset1)
        if key_rev in self._static_correlation_matrix:
            return self._static_correlation_matrix[key_rev]
        
        # Check dynamic cache
        for k in [key, key_rev]:
            if k in self._dynamic_correlations:
                return self._dynamic_correlations[k]
        
        # Check if same category
        cat1 = self._asset_to_category.get(asset1)
        cat2 = self._asset_to_category.get(asset2)
        
        if cat1 and cat1 == cat2:
            # Same category = moderate correlation
            return 0.6
        
        # Default low correlation for unknown pairs
        return 0.3
    
    def get_category(self, asset: str) -> Optional[str]:
        """Get category for an asset."""
        return self._asset_to_category.get(asset.upper())
    
    def _extract_base_asset(self, symbol: str) -> str:
        """Extract base asset from symbol."""
        if '/' in symbol:
            return symbol.split('/')[0].upper()
        
        # Handle concatenated format
        for quote in ['USDT', 'USDC', 'USD', 'EUR', 'BUSD']:
            if symbol.upper().endswith(quote):
                return symbol.upper()[:-len(quote)]
        
        return symbol.upper()
    
    def can_open_position(
        self,
        new_symbol: str,
        proposed_size_usd: float,
        current_positions: List[Position],
        portfolio_value_usd: float
    ) -> CorrelationCheckResult:
        """
        Check if new position can be opened based on correlation limits.
        
        Args:
            new_symbol: Symbol to open (e.g., "SOL/USDT")
            proposed_size_usd: Size of proposed position in USD
            current_positions: List of current positions
            portfolio_value_usd: Total portfolio value in USD
            
        Returns:
            CorrelationCheckResult with decision and details
        """
        if portfolio_value_usd <= 0:
            return CorrelationCheckResult(can_open=True)
        
        new_asset = self._extract_base_asset(new_symbol)
        new_category = self.get_category(new_asset)
        
        warnings = []
        correlated_positions = []
        
        # Calculate existing exposure by category
        category_exposure: Dict[str, float] = {}
        for pos in current_positions:
            cat = self.get_category(pos.base_asset)
            if cat:
                category_exposure[cat] = category_exposure.get(cat, 0) + pos.value_usd
        
        # Add proposed position to category
        if new_category:
            category_exposure[new_category] = category_exposure.get(new_category, 0) + proposed_size_usd
        
        # Check 1: Single asset concentration
        new_asset_total = proposed_size_usd
        for pos in current_positions:
            if pos.base_asset == new_asset:
                new_asset_total += pos.value_usd
        
        single_asset_pct = (new_asset_total / portfolio_value_usd) * 100
        if single_asset_pct > self.config.max_single_asset_pct:
            return CorrelationCheckResult(
                can_open=False,
                reason=f"{new_asset} exposure would be {single_asset_pct:.1f}% "
                       f"(max: {self.config.max_single_asset_pct}%)",
                total_correlated_exposure_pct=single_asset_pct,
                category_exposure=category_exposure
            )
        
        # Check 2: Category concentration
        if new_category:
            category_count = sum(
                1 for pos in current_positions 
                if self.get_category(pos.base_asset) == new_category
            ) + 1  # +1 for new position
            
            if category_count > self.config.max_positions_per_category:
                return CorrelationCheckResult(
                    can_open=False,
                    reason=f"Too many {new_category} positions ({category_count}), "
                           f"max: {self.config.max_positions_per_category}",
                    category_exposure=category_exposure
                )
        
        # Check 3: Correlated exposure
        total_correlated_value = proposed_size_usd
        
        for pos in current_positions:
            correlation = self.get_correlation(new_asset, pos.base_asset)
            
            if correlation >= self.config.correlation_threshold:
                correlated_positions.append(f"{pos.base_asset} (r={correlation:.2f})")
                # Weight by correlation
                total_correlated_value += pos.value_usd * correlation
        
        correlated_pct = (total_correlated_value / portfolio_value_usd) * 100
        
        if correlated_pct > self.config.max_correlated_exposure_pct:
            return CorrelationCheckResult(
                can_open=False,
                reason=f"Correlated exposure would be {correlated_pct:.1f}% "
                       f"(max: {self.config.max_correlated_exposure_pct}%)",
                correlated_positions=correlated_positions,
                total_correlated_exposure_pct=correlated_pct,
                category_exposure=category_exposure
            )
        
        # Warnings
        if correlated_pct > self.config.max_correlated_exposure_pct * 0.7:
            warnings.append(
                f"Approaching correlated exposure limit: {correlated_pct:.1f}% "
                f"of {self.config.max_correlated_exposure_pct}%"
            )
        
        if single_asset_pct > self.config.max_single_asset_pct * 0.7:
            warnings.append(
                f"High {new_asset} concentration: {single_asset_pct:.1f}%"
            )
        
        if correlated_positions:
            warnings.append(
                f"Position correlated with: {', '.join(correlated_positions)}"
            )
        
        return CorrelationCheckResult(
            can_open=True,
            correlated_positions=correlated_positions,
            total_correlated_exposure_pct=correlated_pct,
            category_exposure=category_exposure,
            warnings=warnings
        )
    
    def get_portfolio_correlation_risk(
        self,
        positions: List[Position],
        portfolio_value_usd: float
    ) -> Dict:
        """
        Analyze overall portfolio correlation risk.
        
        Returns dict with:
        - effective_positions: number of truly independent positions
        - correlation_risk_score: 0-100 (higher = more correlated)
        - category_breakdown: exposure by category
        - recommendations: list of suggestions
        """
        if not positions or portfolio_value_usd <= 0:
            return {
                'effective_positions': 0,
                'correlation_risk_score': 0,
                'category_breakdown': {},
                'recommendations': []
            }
        
        # Calculate pairwise correlations
        total_correlation = 0
        pair_count = 0
        
        for i, pos1 in enumerate(positions):
            for pos2 in positions[i+1:]:
                corr = self.get_correlation(pos1.base_asset, pos2.base_asset)
                total_correlation += corr
                pair_count += 1
        
        avg_correlation = total_correlation / pair_count if pair_count > 0 else 0
        
        # Effective positions (adjusted for correlation)
        # If all perfectly correlated, effective = 1
        # If all uncorrelated, effective = len(positions)
        effective_positions = len(positions) * (1 - avg_correlation * 0.7)
        
        # Correlation risk score (0-100)
        risk_score = avg_correlation * 100
        
        # Category breakdown
        category_breakdown = {}
        for pos in positions:
            cat = self.get_category(pos.base_asset) or 'other'
            if cat not in category_breakdown:
                category_breakdown[cat] = {'count': 0, 'value_usd': 0, 'pct': 0}
            category_breakdown[cat]['count'] += 1
            category_breakdown[cat]['value_usd'] += pos.value_usd
        
        for cat in category_breakdown:
            category_breakdown[cat]['pct'] = (
                category_breakdown[cat]['value_usd'] / portfolio_value_usd * 100
            )
        
        # Recommendations
        recommendations = []
        
        if risk_score > 70:
            recommendations.append(
                "High correlation risk - consider diversifying into different categories"
            )
        
        if effective_positions < 2:
            recommendations.append(
                "Portfolio effectively concentrated - acts like single position"
            )
        
        # Check category concentration
        for cat, data in category_breakdown.items():
            if data['pct'] > 50:
                recommendations.append(
                    f"Over 50% in {cat} category - consider rebalancing"
                )
        
        return {
            'effective_positions': round(effective_positions, 1),
            'correlation_risk_score': round(risk_score, 1),
            'avg_correlation': round(avg_correlation, 2),
            'category_breakdown': category_breakdown,
            'recommendations': recommendations
        }


# Global singleton
_correlation_manager: Optional[CorrelationManager] = None


def get_correlation_manager(config: CorrelationConfig = None) -> CorrelationManager:
    """Get or create the global correlation manager."""
    global _correlation_manager
    if _correlation_manager is None:
        _correlation_manager = CorrelationManager(config)
    return _correlation_manager
