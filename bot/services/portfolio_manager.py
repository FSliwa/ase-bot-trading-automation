"""
Portfolio Manager Service - Portfolio Awareness for intelligent position decisions.

This service provides:
1. Real-time portfolio composition analysis
2. Sector/category exposure tracking (L1, L2, DeFi, etc.)
3. Concentration risk detection
4. Position sizing recommendations based on existing holdings
5. Rebalancing suggestions
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AssetCategory(Enum):
    """Crypto asset categories for exposure tracking."""
    L1 = "layer1"           # BTC, ETH, SOL, AVAX, etc.
    L2 = "layer2"           # ARB, OP, MATIC, etc.
    DEFI = "defi"           # UNI, AAVE, COMP, etc.
    MEME = "meme"           # DOGE, SHIB, PEPE, etc.
    AI = "ai"               # FET, RNDR, AGIX, etc.
    GAMING = "gaming"       # AXS, SAND, MANA, etc.
    STABLECOIN = "stable"   # USDT, USDC, DAI, etc.
    EXCHANGE = "exchange"   # BNB, FTT, etc.
    PRIVACY = "privacy"     # XMR, ZEC, etc.
    UNKNOWN = "unknown"


# Asset category mapping
ASSET_CATEGORIES: Dict[str, AssetCategory] = {
    # Layer 1
    "BTC": AssetCategory.L1,
    "ETH": AssetCategory.L1,
    "SOL": AssetCategory.L1,
    "AVAX": AssetCategory.L1,
    "ADA": AssetCategory.L1,
    "DOT": AssetCategory.L1,
    "ATOM": AssetCategory.L1,
    "NEAR": AssetCategory.L1,
    "SUI": AssetCategory.L1,
    "APT": AssetCategory.L1,
    "TON": AssetCategory.L1,
    "TRX": AssetCategory.L1,
    "XRP": AssetCategory.L1,
    "LTC": AssetCategory.L1,
    "BCH": AssetCategory.L1,
    
    # Layer 2
    "ARB": AssetCategory.L2,
    "OP": AssetCategory.L2,
    "MATIC": AssetCategory.L2,
    "IMX": AssetCategory.L2,
    "STRK": AssetCategory.L2,
    
    # DeFi
    "UNI": AssetCategory.DEFI,
    "AAVE": AssetCategory.DEFI,
    "LINK": AssetCategory.DEFI,
    "MKR": AssetCategory.DEFI,
    "SNX": AssetCategory.DEFI,
    "CRV": AssetCategory.DEFI,
    "COMP": AssetCategory.DEFI,
    "LDO": AssetCategory.DEFI,
    "SUSHI": AssetCategory.DEFI,
    "1INCH": AssetCategory.DEFI,
    "YFI": AssetCategory.DEFI,
    "BAL": AssetCategory.DEFI,
    
    # Meme
    "DOGE": AssetCategory.MEME,
    "SHIB": AssetCategory.MEME,
    "PEPE": AssetCategory.MEME,
    "BONK": AssetCategory.MEME,
    "FLOKI": AssetCategory.MEME,
    "WIF": AssetCategory.MEME,
    
    # AI
    "FET": AssetCategory.AI,
    "RNDR": AssetCategory.AI,
    "AGIX": AssetCategory.AI,
    "OCEAN": AssetCategory.AI,
    "TAO": AssetCategory.AI,
    "ARKM": AssetCategory.AI,
    
    # Gaming
    "AXS": AssetCategory.GAMING,
    "SAND": AssetCategory.GAMING,
    "MANA": AssetCategory.GAMING,
    "GALA": AssetCategory.GAMING,
    "ENJ": AssetCategory.GAMING,
    "ILV": AssetCategory.GAMING,
    
    # Exchange
    "BNB": AssetCategory.EXCHANGE,
    "CRO": AssetCategory.EXCHANGE,
    "OKB": AssetCategory.EXCHANGE,
    "KCS": AssetCategory.EXCHANGE,
    
    # Stablecoins
    "USDT": AssetCategory.STABLECOIN,
    "USDC": AssetCategory.STABLECOIN,
    "DAI": AssetCategory.STABLECOIN,
    "BUSD": AssetCategory.STABLECOIN,
    
    # Privacy
    "XMR": AssetCategory.PRIVACY,
    "ZEC": AssetCategory.PRIVACY,
}


@dataclass
class PortfolioPosition:
    """Single position in portfolio."""
    symbol: str
    base_asset: str
    quantity: float
    entry_price: float
    current_price: float
    value_usd: float
    pnl_usd: float
    pnl_percent: float
    category: AssetCategory
    weight_percent: float = 0.0  # Portfolio weight


@dataclass
class CategoryExposure:
    """Exposure to a specific asset category."""
    category: AssetCategory
    value_usd: float
    weight_percent: float
    positions: List[str]  # List of symbols
    is_overweight: bool = False
    recommendation: str = ""


@dataclass
class PortfolioAnalysis:
    """Complete portfolio analysis result."""
    total_value_usd: float
    available_balance_usd: float
    positions: List[PortfolioPosition]
    category_exposures: Dict[str, CategoryExposure]
    concentration_risk: float  # 0-1, higher = more concentrated
    largest_position_weight: float
    diversification_score: float  # 0-100
    recommendations: List[str]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TradeDecision:
    """Decision recommendation for a potential trade."""
    symbol: str
    original_action: str  # buy/sell from signal
    recommended_action: str  # adjusted action
    should_execute: bool
    position_size_multiplier: float  # 0.0 to 1.5 (can increase or decrease)
    reasons: List[str]
    portfolio_context: str
    current_exposure: float  # Current % of portfolio in this category
    max_allowed_exposure: float  # Max recommended %


class PortfolioManagerService:
    """
    Service for portfolio-aware trading decisions.
    Ensures trades consider existing portfolio composition.
    """
    
    # Default limits (can be overridden) - RELAXED FOR MORE TRADES
    DEFAULT_LIMITS = {
        "max_single_position_pct": 40.0,      # Max 40% in single asset (raised from 25%)
        "max_category_exposure_pct": 60.0,    # Max 60% in single category (raised from 40%)
        "max_l1_exposure_pct": 400.0,         # Max 400% in L1 (aggressive allocation)
        "max_meme_exposure_pct": 20.0,        # Max 20% in meme coins (raised from 10%)
        "max_defi_exposure_pct": 50.0,        # Max 50% in DeFi (raised from 30%)
        "min_stable_reserve_pct": 0.0,        # No minimum stable reserve (was 10%)
        "concentration_warning_threshold": 0.7,  # Warn if HHI > 0.7 (raised from 0.5)
    }
    
    def __init__(
        self,
        exchange_adapter=None,
        custom_limits: Optional[Dict[str, float]] = None
    ):
        self.exchange = exchange_adapter
        self.limits = {**self.DEFAULT_LIMITS, **(custom_limits or {})}
        self._cached_analysis: Optional[PortfolioAnalysis] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 30  # Refresh every 30 seconds
        
        logger.info(f"PortfolioManager initialized with limits: {self.limits}")
    
    def get_asset_category(self, symbol: str) -> AssetCategory:
        """Get category for an asset."""
        # Extract base asset from symbol (e.g., "BTC/USDC" -> "BTC")
        base = symbol.split('/')[0] if '/' in symbol else symbol
        base = base.replace('USDT', '').replace('USDC', '').replace('USD', '')
        return ASSET_CATEGORIES.get(base.upper(), AssetCategory.UNKNOWN)
    
    async def analyze_portfolio(self, force_refresh: bool = False) -> PortfolioAnalysis:
        """
        Analyze current portfolio composition.
        Returns cached result if fresh, otherwise fetches new data.
        """
        # Check cache
        if (not force_refresh and 
            self._cached_analysis and 
            self._cache_timestamp and
            (datetime.now() - self._cache_timestamp).seconds < self._cache_ttl_seconds):
            return self._cached_analysis
        
        if not self.exchange:
            logger.warning("No exchange adapter, returning empty analysis")
            return self._empty_analysis()
        
        try:
            # Fetch balances and positions
            balance = await self._fetch_balance()
            positions = await self._fetch_positions()
            
            # Calculate total portfolio value
            total_value = balance.get('total_usd', 0.0)
            available = balance.get('available_usd', 0.0)
            
            # Build position list with categories
            portfolio_positions = []
            category_values: Dict[str, float] = {}
            category_positions: Dict[str, List[str]] = {}
            
            for pos in positions:
                category = self.get_asset_category(pos['symbol'])
                cat_key = category.value
                
                position = PortfolioPosition(
                    symbol=pos['symbol'],
                    base_asset=pos['symbol'].split('/')[0] if '/' in pos['symbol'] else pos['symbol'],
                    quantity=pos['quantity'],
                    entry_price=pos['entry_price'],
                    current_price=pos['current_price'],
                    value_usd=pos['value_usd'],
                    pnl_usd=pos['pnl_usd'],
                    pnl_percent=pos['pnl_percent'],
                    category=category,
                    weight_percent=(pos['value_usd'] / total_value * 100) if total_value > 0 else 0
                )
                portfolio_positions.append(position)
                
                # Accumulate category values
                category_values[cat_key] = category_values.get(cat_key, 0) + pos['value_usd']
                if cat_key not in category_positions:
                    category_positions[cat_key] = []
                category_positions[cat_key].append(pos['symbol'])
            
            # Build category exposures
            category_exposures = {}
            for cat_key, value in category_values.items():
                weight = (value / total_value * 100) if total_value > 0 else 0
                category = AssetCategory(cat_key)
                
                # Determine if overweight
                max_exposure = self._get_max_exposure_for_category(category)
                is_overweight = weight > max_exposure
                
                recommendation = ""
                if is_overweight:
                    excess = weight - max_exposure
                    recommendation = f"Reduce {cat_key} exposure by {excess:.1f}%"
                
                category_exposures[cat_key] = CategoryExposure(
                    category=category,
                    value_usd=value,
                    weight_percent=weight,
                    positions=category_positions.get(cat_key, []),
                    is_overweight=is_overweight,
                    recommendation=recommendation
                )
            
            # Calculate concentration risk (HHI - Herfindahl-Hirschman Index)
            weights = [(p.value_usd / total_value) ** 2 for p in portfolio_positions] if total_value > 0 else []
            hhi = sum(weights) if weights else 0
            
            # Find largest position
            largest_weight = max((p.weight_percent for p in portfolio_positions), default=0)
            
            # Calculate diversification score (inverse of concentration)
            diversification = max(0, 100 - (hhi * 100))
            
            # Generate recommendations
            recommendations = self._generate_recommendations(
                portfolio_positions, 
                category_exposures,
                hhi,
                largest_weight,
                available,
                total_value
            )
            
            analysis = PortfolioAnalysis(
                total_value_usd=total_value,
                available_balance_usd=available,
                positions=portfolio_positions,
                category_exposures=category_exposures,
                concentration_risk=hhi,
                largest_position_weight=largest_weight,
                diversification_score=diversification,
                recommendations=recommendations
            )
            
            # Cache result
            self._cached_analysis = analysis
            self._cache_timestamp = datetime.now()
            
            logger.info(
                f"📊 Portfolio Analysis: ${total_value:.2f} total, "
                f"{len(portfolio_positions)} positions, "
                f"diversification: {diversification:.1f}%"
            )
            
            return analysis
            
        except Exception as e:
            logger.error(f"Portfolio analysis failed: {e}")
            return self._empty_analysis()
    
    async def evaluate_trade(
        self,
        symbol: str,
        action: str,  # "buy" or "sell"
        proposed_size_usd: float = 0,
        confidence: float = 0.5
    ) -> TradeDecision:
        """
        Evaluate a proposed trade against portfolio context.
        Returns recommendation on whether to execute and at what size.
        """
        analysis = await self.analyze_portfolio()
        
        base_asset = symbol.split('/')[0] if '/' in symbol else symbol
        category = self.get_asset_category(symbol)
        cat_key = category.value
        
        reasons = []
        position_multiplier = 1.0
        should_execute = True
        
        # Get current exposures
        current_position = next(
            (p for p in analysis.positions if p.symbol == symbol or p.base_asset == base_asset), 
            None
        )
        current_asset_weight = current_position.weight_percent if current_position else 0
        current_category_weight = analysis.category_exposures.get(cat_key, CategoryExposure(
            category=category, value_usd=0, weight_percent=0, positions=[]
        )).weight_percent
        
        max_category_exposure = self._get_max_exposure_for_category(category)
        max_single_position = self.limits["max_single_position_pct"]
        
        # ===== BUY DECISION LOGIC =====
        if action.lower() == "buy":
            
            # Check 1: Already have too much of this asset
            if current_asset_weight >= max_single_position:
                reasons.append(f"❌ Already {current_asset_weight:.1f}% in {base_asset} (max: {max_single_position}%)")
                should_execute = False
                position_multiplier = 0
                
            elif current_asset_weight >= max_single_position * 0.7:
                reduction = 0.5  # Reduce size by 50%
                position_multiplier = reduction
                reasons.append(
                    f"⚠️ High exposure to {base_asset} ({current_asset_weight:.1f}%), "
                    f"reducing position size by {(1-reduction)*100:.0f}%"
                )
            
            # Check 2: Category exposure too high
            if current_category_weight >= max_category_exposure:
                reasons.append(
                    f"❌ {cat_key.upper()} exposure at {current_category_weight:.1f}% "
                    f"(max: {max_category_exposure}%)"
                )
                should_execute = False
                position_multiplier = 0
                
            elif current_category_weight >= max_category_exposure * 0.8:
                reduction = 0.3  # Reduce size by 70%
                position_multiplier = min(position_multiplier, reduction)
                reasons.append(
                    f"⚠️ High {cat_key.upper()} exposure ({current_category_weight:.1f}%), "
                    f"limiting position size"
                )
            
            # Check 3: Portfolio concentration risk
            if analysis.concentration_risk > self.limits["concentration_warning_threshold"]:
                # Only add to underweight categories
                underweight_categories = [
                    k for k, v in analysis.category_exposures.items() 
                    if v.weight_percent < self._get_max_exposure_for_category(v.category) * 0.5
                ]
                
                if cat_key not in underweight_categories and len(underweight_categories) > 0:
                    reasons.append(
                        f"⚠️ Portfolio concentrated. Consider diversifying into: "
                        f"{', '.join(underweight_categories)}"
                    )
                    position_multiplier = min(position_multiplier, 0.5)
            
            # Check 4: Reserve requirement (keep stables)
            stable_weight = analysis.category_exposures.get('stable', CategoryExposure(
                category=AssetCategory.STABLECOIN, value_usd=0, weight_percent=0, positions=[]
            )).weight_percent
            
            if stable_weight < self.limits["min_stable_reserve_pct"]:
                reasons.append(
                    f"⚠️ Stable reserve low ({stable_weight:.1f}%), "
                    f"limiting new positions"
                )
                position_multiplier = min(position_multiplier, 0.5)
            
            # Check 5: Confidence-based sizing
            if confidence < 0.4:
                position_multiplier = min(position_multiplier, 0.3)
                reasons.append(f"Low confidence ({confidence:.2f}), reducing size")
            elif confidence > 0.8:
                position_multiplier = min(position_multiplier * 1.2, 1.5)
                reasons.append(f"High confidence ({confidence:.2f}), allowing larger size")
        
        # ===== SELL DECISION LOGIC =====
        elif action.lower() == "sell":
            
            # Check 1: Do we even have this position?
            if not current_position:
                reasons.append(f"⚠️ No position in {base_asset} to sell")
                should_execute = False
                position_multiplier = 0
            
            # Check 2: Should we reduce overweight position?
            elif current_asset_weight > max_single_position:
                reasons.append(
                    f"✅ {base_asset} overweight ({current_asset_weight:.1f}%), "
                    f"sell recommended"
                )
                # Calculate how much to sell to get back to target
                target_weight = max_single_position * 0.8  # 80% of max
                excess_pct = current_asset_weight - target_weight
                position_multiplier = min(1.5, excess_pct / current_asset_weight + 1)
            
            # Check 3: Category rebalancing opportunity
            elif current_category_weight > max_category_exposure:
                reasons.append(
                    f"✅ {cat_key.upper()} overweight, partial reduction beneficial"
                )
        
        # Build context string
        portfolio_context = (
            f"Portfolio: ${analysis.total_value_usd:.0f} | "
            f"{base_asset}: {current_asset_weight:.1f}% | "
            f"{cat_key.upper()}: {current_category_weight:.1f}% | "
            f"Diversification: {analysis.diversification_score:.0f}%"
        )
        
        # Default reason if none
        if not reasons:
            if should_execute:
                reasons.append(f"✅ Trade within portfolio limits")
            else:
                reasons.append(f"Trade blocked by portfolio rules")
        
        decision = TradeDecision(
            symbol=symbol,
            original_action=action,
            recommended_action=action if should_execute else "hold",
            should_execute=should_execute,
            position_size_multiplier=position_multiplier,
            reasons=reasons,
            portfolio_context=portfolio_context,
            current_exposure=current_category_weight,
            max_allowed_exposure=max_category_exposure
        )
        
        logger.info(
            f"📊 Trade Decision for {symbol} {action.upper()}: "
            f"execute={should_execute}, multiplier={position_multiplier:.2f}, "
            f"reasons={reasons}"
        )
        
        return decision
    
    async def get_rebalancing_suggestions(self) -> List[Dict]:
        """
        Generate suggestions for portfolio rebalancing.
        Returns list of suggested trades.
        """
        analysis = await self.analyze_portfolio()
        suggestions = []
        
        for cat_key, exposure in analysis.category_exposures.items():
            max_exp = self._get_max_exposure_for_category(exposure.category)
            
            if exposure.is_overweight:
                # Suggest reducing largest position in this category
                cat_positions = [
                    p for p in analysis.positions 
                    if p.category.value == cat_key
                ]
                if cat_positions:
                    largest = max(cat_positions, key=lambda p: p.weight_percent)
                    excess = exposure.weight_percent - max_exp
                    
                    suggestions.append({
                        "action": "sell",
                        "symbol": largest.symbol,
                        "reason": f"Reduce {cat_key} exposure by {excess:.1f}%",
                        "priority": "high" if excess > 10 else "medium",
                        "suggested_reduction_pct": min(50, excess / largest.weight_percent * 100)
                    })
        
        # Check for underweight categories (diversification opportunity)
        for cat_key, exposure in analysis.category_exposures.items():
            target = self._get_max_exposure_for_category(exposure.category) * 0.3  # 30% of max as target
            if exposure.weight_percent < target and exposure.category not in [AssetCategory.MEME, AssetCategory.UNKNOWN]:
                suggestions.append({
                    "action": "buy",
                    "category": cat_key,
                    "reason": f"Consider increasing {cat_key} exposure (currently {exposure.weight_percent:.1f}%)",
                    "priority": "low"
                })
        
        return suggestions
    
    def _get_max_exposure_for_category(self, category: AssetCategory) -> float:
        """Get maximum allowed exposure for a category."""
        if category == AssetCategory.L1:
            return self.limits["max_l1_exposure_pct"]
        elif category == AssetCategory.MEME:
            return self.limits["max_meme_exposure_pct"]
        elif category == AssetCategory.DEFI:
            return self.limits["max_defi_exposure_pct"]
        elif category == AssetCategory.STABLECOIN:
            return 100.0  # No limit on stables
        else:
            return self.limits["max_category_exposure_pct"]
    
    def _generate_recommendations(
        self,
        positions: List[PortfolioPosition],
        category_exposures: Dict[str, CategoryExposure],
        hhi: float,
        largest_weight: float,
        available: float,
        total: float
    ) -> List[str]:
        """Generate portfolio recommendations."""
        recommendations = []
        
        # Concentration warning
        if hhi > self.limits["concentration_warning_threshold"]:
            recommendations.append(
                f"⚠️ Portfolio highly concentrated (HHI: {hhi:.2f}). "
                f"Consider diversifying."
            )
        
        # Single position warning
        if largest_weight > self.limits["max_single_position_pct"]:
            largest = max(positions, key=lambda p: p.weight_percent)
            recommendations.append(
                f"⚠️ {largest.base_asset} is {largest_weight:.1f}% of portfolio. "
                f"Consider reducing."
            )
        
        # Category warnings
        for cat_key, exposure in category_exposures.items():
            if exposure.is_overweight:
                recommendations.append(exposure.recommendation)
        
        # Low diversification
        if len(positions) < 3 and total > 1000:
            recommendations.append(
                "💡 Consider adding more positions for better diversification."
            )
        
        # Cash reserve
        if total > 0:
            cash_pct = (available / total) * 100
            if cash_pct < 5:
                recommendations.append(
                    f"💡 Low available cash ({cash_pct:.1f}%). "
                    f"Consider keeping some reserve."
                )
        
        return recommendations
    
    async def _fetch_balance(self) -> Dict:
        """Fetch balance from exchange."""
        try:
            if hasattr(self.exchange, 'exchange'):
                # CCXT adapter
                balance = await self.exchange.exchange.fetch_balance()
                
                total_usd = 0
                available_usd = 0
                
                # Sum up all balances in USD terms
                for currency, amounts in balance.items():
                    if isinstance(amounts, dict) and 'total' in amounts:
                        if currency in ['USDT', 'USDC', 'USD', 'BUSD', 'DAI']:
                            total_usd += amounts.get('total', 0) or 0
                            available_usd += amounts.get('free', 0) or 0
                
                return {
                    'total_usd': total_usd,
                    'available_usd': available_usd,
                    'raw': balance
                }
            
            return {'total_usd': 0, 'available_usd': 0}
            
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return {'total_usd': 0, 'available_usd': 0}
    
    async def _fetch_positions(self) -> List[Dict]:
        """Fetch positions from exchange."""
        try:
            positions = []
            
            if hasattr(self.exchange, 'exchange'):
                # CCXT adapter - fetch balance for spot
                balance = await self.exchange.exchange.fetch_balance()
                
                for currency, amounts in balance.items():
                    if isinstance(amounts, dict):
                        total = amounts.get('total', 0) or 0
                        if total > 0 and currency not in ['USDT', 'USDC', 'USD', 'BUSD', 'DAI', 'info']:
                            try:
                                # Get current price
                                symbol = f"{currency}/USDC"
                                ticker = await self.exchange.exchange.fetch_ticker(symbol)
                                current_price = ticker['last']
                                value_usd = total * current_price
                                
                                if value_usd > 1:  # Only count positions > $1
                                    positions.append({
                                        'symbol': symbol,
                                        'quantity': total,
                                        'entry_price': current_price,  # Approximate
                                        'current_price': current_price,
                                        'value_usd': value_usd,
                                        'pnl_usd': 0,  # Can't know without entry
                                        'pnl_percent': 0
                                    })
                            except:
                                # Symbol might not exist
                                pass
            
            return positions
            
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return []
    
    def _empty_analysis(self) -> PortfolioAnalysis:
        """Return empty analysis."""
        return PortfolioAnalysis(
            total_value_usd=0,
            available_balance_usd=0,
            positions=[],
            category_exposures={},
            concentration_risk=0,
            largest_position_weight=0,
            diversification_score=100,
            recommendations=["No portfolio data available"]
        )


# Singleton instance for easy access
_portfolio_manager: Optional[PortfolioManagerService] = None


def get_portfolio_manager(exchange_adapter=None) -> PortfolioManagerService:
    """Get or create portfolio manager instance."""
    global _portfolio_manager
    
    if _portfolio_manager is None:
        _portfolio_manager = PortfolioManagerService(exchange_adapter)
    elif exchange_adapter and _portfolio_manager.exchange is None:
        _portfolio_manager.exchange = exchange_adapter
    
    return _portfolio_manager
