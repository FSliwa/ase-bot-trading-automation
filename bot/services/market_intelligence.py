"""
Market Intelligence Service - Advanced market analysis and risk assessment.

Addresses critical gaps in bot's trading logic:
1. Liquidity verification before trades
2. Market sentiment analysis (Fear & Greed)
3. Volatility-adjusted SL/TP
4. Correlation matrix for portfolio risk
5. Market regime detection (bull/bear/sideways)
6. News & macro event awareness
7. Kill switch for black swan events

FIX 2025-12-16: Added CircuitBreaker integration for external API calls
FIX 2025-12-16: Added Emergency Cache Invalidation for flash crashes
"""

import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import time

logger = logging.getLogger(__name__)


# ============================================================================
# CIRCUIT BREAKER FOR EXTERNAL APIs (FIX 2025-12-16)
# ============================================================================

@dataclass
class CircuitBreakerState:
    """State for a circuit breaker."""
    failures: int = 0
    last_failure_time: float = 0.0
    state: str = "closed"  # closed, open, half_open
    last_success_time: float = 0.0


class APICircuitBreaker:
    """
    Circuit Breaker for external API calls.
    
    Prevents repeated calls to failing APIs, allowing fast-fail instead of timeout.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Requests fail immediately (circuit tripped)
    - HALF_OPEN: Allow one request to test if service recovered
    """
    
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,  # seconds before trying again
        timeout_per_request: float = 5.0  # max time per request (reduced from 10s)
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.timeout_per_request = timeout_per_request
        self._breakers: Dict[str, CircuitBreakerState] = {}
        self._lock = asyncio.Lock()
    
    def _get_breaker(self, name: str) -> CircuitBreakerState:
        """Get or create circuit breaker for a service."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreakerState()
        return self._breakers[name]
    
    def is_open(self, name: str) -> bool:
        """Check if circuit is open (blocking requests)."""
        breaker = self._get_breaker(name)
        
        if breaker.state == "closed":
            return False
        
        if breaker.state == "open":
            # Check if recovery timeout has passed
            if time.time() - breaker.last_failure_time > self.recovery_timeout:
                breaker.state = "half_open"
                logger.info(f"🔄 Circuit breaker '{name}' entering HALF_OPEN state")
                return False
            return True
        
        # half_open - allow one request
        return False
    
    def record_success(self, name: str):
        """Record successful API call."""
        breaker = self._get_breaker(name)
        breaker.failures = 0
        breaker.state = "closed"
        breaker.last_success_time = time.time()
        
        if breaker.state == "half_open":
            logger.info(f"✅ Circuit breaker '{name}' recovered - CLOSED")
    
    def record_failure(self, name: str):
        """Record failed API call."""
        breaker = self._get_breaker(name)
        breaker.failures += 1
        breaker.last_failure_time = time.time()
        
        if breaker.failures >= self.failure_threshold:
            breaker.state = "open"
            logger.warning(
                f"🚨 Circuit breaker '{name}' OPEN after {breaker.failures} failures. "
                f"Will retry in {self.recovery_timeout}s"
            )
    
    async def call(
        self,
        name: str,
        func: Callable,
        *args,
        fallback_value: Any = None,
        **kwargs
    ) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            name: Circuit breaker name (e.g., "fear_greed_api")
            func: Async function to call
            fallback_value: Value to return if circuit is open
            
        Returns:
            Function result or fallback_value
        """
        # Check if circuit is open
        if self.is_open(name):
            logger.debug(f"⚡ Circuit breaker '{name}' is OPEN - returning fallback")
            return fallback_value
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.timeout_per_request
            )
            self.record_success(name)
            return result
            
        except asyncio.TimeoutError:
            self.record_failure(name)
            logger.warning(f"⏱️ Timeout calling '{name}' ({self.timeout_per_request}s)")
            return fallback_value
            
        except Exception as e:
            self.record_failure(name)
            logger.warning(f"❌ Error calling '{name}': {e}")
            return fallback_value
    
    def get_status(self) -> Dict[str, Dict]:
        """Get status of all circuit breakers."""
        return {
            name: {
                "state": breaker.state,
                "failures": breaker.failures,
                "last_failure": datetime.fromtimestamp(breaker.last_failure_time).isoformat() 
                    if breaker.last_failure_time > 0 else None
            }
            for name, breaker in self._breakers.items()
        }


# Global circuit breaker instance
_api_circuit_breaker: Optional['APICircuitBreaker'] = None

def get_api_circuit_breaker() -> APICircuitBreaker:
    """Get or create global API circuit breaker."""
    global _api_circuit_breaker
    if _api_circuit_breaker is None:
        _api_circuit_breaker = APICircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60.0,
            timeout_per_request=5.0
        )
    return _api_circuit_breaker


class MarketRegime(Enum):
    """Market regime classification."""
    STRONG_BULL = "strong_bull"      # >20% monthly gain
    BULL = "bull"                     # 5-20% monthly gain
    SIDEWAYS = "sideways"             # -5% to +5%
    BEAR = "bear"                     # -5% to -20%
    STRONG_BEAR = "strong_bear"       # <-20% monthly loss
    CRISIS = "crisis"                 # Black swan event


@dataclass
class LiquidityCheck:
    """Result of liquidity verification."""
    symbol: str
    is_liquid: bool
    bid_ask_spread_pct: float
    order_book_depth_usd: float
    estimated_slippage_pct: float
    max_safe_order_usd: float
    warnings: List[str] = field(default_factory=list)


@dataclass
class VolatilityProfile:
    """Asset volatility profile for dynamic SL/TP."""
    symbol: str
    atr_percent: float           # Average True Range as % of price
    daily_volatility: float      # Standard deviation of daily returns
    suggested_sl_pct: float      # Volatility-adjusted stop loss
    suggested_tp_pct: float      # Volatility-adjusted take profit
    risk_multiplier: float       # 1.0 = normal, >1 = more volatile


@dataclass
class MarketSentiment:
    """Overall market sentiment indicators."""
    fear_greed_index: int        # 0-100 (0=Extreme Fear, 100=Extreme Greed)
    fear_greed_label: str        # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    btc_dominance: float         # BTC market dominance %
    total_market_cap_change_24h: float
    funding_rate_avg: float      # Average perpetual funding rate
    regime: MarketRegime
    is_safe_to_trade: bool
    warnings: List[str] = field(default_factory=list)


@dataclass
class CorrelationRisk:
    """Portfolio correlation risk assessment."""
    avg_correlation: float
    highly_correlated_pairs: List[Tuple[str, str, float]]
    diversification_score: float  # 0-100
    concentration_risk: str       # "low", "medium", "high"


class MarketIntelligenceService:
    """
    Advanced market intelligence for smarter trading decisions.
    """
    
    # Volatility categories for different assets
    ASSET_VOLATILITY = {
        # Major cryptos - lower volatility
        "BTC": {"base_sl": 3.0, "base_tp": 5.0, "vol_mult": 1.0},
        "ETH": {"base_sl": 4.0, "base_tp": 6.0, "vol_mult": 1.2},
        # Mid-cap - medium volatility  
        "SOL": {"base_sl": 5.0, "base_tp": 8.0, "vol_mult": 1.5},
        "XRP": {"base_sl": 5.0, "base_tp": 8.0, "vol_mult": 1.4},
        "ADA": {"base_sl": 5.0, "base_tp": 8.0, "vol_mult": 1.5},
        "AVAX": {"base_sl": 6.0, "base_tp": 9.0, "vol_mult": 1.6},
        "DOT": {"base_sl": 5.0, "base_tp": 8.0, "vol_mult": 1.5},
        "LINK": {"base_sl": 5.0, "base_tp": 8.0, "vol_mult": 1.5},
        # Small-cap/meme - high volatility
        "DOGE": {"base_sl": 7.0, "base_tp": 12.0, "vol_mult": 2.0},
        "SHIB": {"base_sl": 8.0, "base_tp": 15.0, "vol_mult": 2.5},
        "PEPE": {"base_sl": 10.0, "base_tp": 20.0, "vol_mult": 3.0},
        "BONK": {"base_sl": 10.0, "base_tp": 20.0, "vol_mult": 3.0},
        # Default for unknown
        "DEFAULT": {"base_sl": 5.0, "base_tp": 8.0, "vol_mult": 1.5},
    }
    
    # Correlation groups
    CORRELATION_GROUPS = {
        "L1_SMART_CONTRACT": ["ETH", "SOL", "ADA", "AVAX", "DOT"],
        "BTC_CORRELATED": ["BTC", "ETH", "LTC"],
        "MEME_COINS": ["DOGE", "SHIB", "PEPE", "BONK", "WIF"],
        "DEFI": ["UNI", "AAVE", "LINK", "MKR", "CRV"],
        "AI_TOKENS": ["FET", "AGIX", "OCEAN", "RNDR"],
    }
    
    # Kill switch thresholds
    KILL_SWITCH_THRESHOLDS = {
        "btc_drop_1h": -5.0,       # BTC drops >5% in 1h
        "btc_drop_24h": -15.0,     # BTC drops >15% in 24h
        "fear_greed_extreme": 10,  # Fear & Greed below 10
        "funding_rate_extreme": 0.1,  # Funding rate >0.1% (extreme leverage)
    }
    
    def __init__(self, exchange_adapter=None):
        self.exchange = exchange_adapter
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes cache
        self._last_sentiment_fetch = None
        self._cached_sentiment: Optional[MarketSentiment] = None
        
        # FIX 2025-12-16: Emergency cache invalidation support
        self._emergency_mode = False
        self._last_price_snapshot: Dict[str, float] = {}  # {symbol: price}
        self._flash_crash_threshold_pct = 5.0  # 5% drop = flash crash
        
        logger.info("🧠 Market Intelligence Service initialized")
    
    def invalidate_cache(self, reason: str = "manual"):
        """
        FIX 2025-12-16: Emergency cache invalidation.
        
        Call this during flash crashes or extreme volatility to force
        fresh data fetch instead of using stale cached values.
        """
        self._cache.clear()
        self._cached_sentiment = None
        self._last_sentiment_fetch = None
        logger.warning(f"🚨 Market Intelligence cache INVALIDATED: {reason}")
    
    def check_flash_crash(self, symbol: str, current_price: float) -> bool:
        """
        FIX 2025-12-16: Detect flash crash and invalidate cache if needed.
        
        Returns True if flash crash detected.
        """
        last_price = self._last_price_snapshot.get(symbol)
        self._last_price_snapshot[symbol] = current_price
        
        if last_price is None or last_price <= 0:
            return False
        
        price_change_pct = ((current_price - last_price) / last_price) * 100
        
        if abs(price_change_pct) >= self._flash_crash_threshold_pct:
            direction = "🔻 CRASH" if price_change_pct < 0 else "🚀 PUMP"
            logger.warning(
                f"🚨 FLASH {direction} DETECTED: {symbol} moved {price_change_pct:+.2f}% "
                f"({last_price:.4f} → {current_price:.4f}) - INVALIDATING CACHE"
            )
            self.invalidate_cache(reason=f"flash_{'crash' if price_change_pct < 0 else 'pump'}_{symbol}")
            self._emergency_mode = True
            return True
        
        return False
    
    def is_emergency_mode(self) -> bool:
        """Check if in emergency mode (flash crash detected recently)."""
        return self._emergency_mode
    
    def clear_emergency_mode(self):
        """Clear emergency mode after situation stabilizes."""
        self._emergency_mode = False
        logger.info("✅ Emergency mode cleared - market stabilized")
    
    async def check_liquidity(
        self, 
        symbol: str, 
        order_size_usd: float
    ) -> LiquidityCheck:
        """
        Check if there's sufficient liquidity for the order.
        
        Returns LiquidityCheck with:
        - is_liquid: True if safe to trade this size
        - estimated_slippage_pct: Expected slippage
        - max_safe_order_usd: Maximum order size without significant slippage
        """
        warnings = []
        
        try:
            # Fetch order book
            if self.exchange and hasattr(self.exchange, 'fetch_order_book'):
                order_book = await self.exchange.fetch_order_book(symbol, limit=50)
            else:
                # Fallback: assume liquid for major pairs
                base = symbol.split('/')[0] if '/' in symbol else symbol.replace('USDT', '')
                is_major = base in ['BTC', 'ETH', 'SOL', 'XRP']
                return LiquidityCheck(
                    symbol=symbol,
                    is_liquid=is_major or order_size_usd < 5000,
                    bid_ask_spread_pct=0.1 if is_major else 0.3,
                    order_book_depth_usd=1000000 if is_major else 100000,
                    estimated_slippage_pct=0.1 if is_major else 0.5,
                    max_safe_order_usd=50000 if is_major else 10000,
                    warnings=["Order book not available, using estimates"]
                )
            
            bids = order_book.get('bids', [])
            asks = order_book.get('asks', [])
            
            if not bids or not asks:
                return LiquidityCheck(
                    symbol=symbol,
                    is_liquid=False,
                    bid_ask_spread_pct=999,
                    order_book_depth_usd=0,
                    estimated_slippage_pct=999,
                    max_safe_order_usd=0,
                    warnings=["Empty order book - DO NOT TRADE"]
                )
            
            # Calculate bid-ask spread
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            spread_pct = ((best_ask - best_bid) / best_bid) * 100
            
            # Calculate order book depth (within 2% of mid price)
            mid_price = (best_bid + best_ask) / 2
            depth_range = mid_price * 0.02
            
            bid_depth = sum(float(b[0]) * float(b[1]) for b in bids if float(b[0]) >= best_bid - depth_range)
            ask_depth = sum(float(a[0]) * float(a[1]) for a in asks if float(a[0]) <= best_ask + depth_range)
            total_depth = bid_depth + ask_depth
            
            # Estimate slippage for order size
            if order_size_usd > 0:
                # Simple slippage model: slippage increases with order size relative to depth
                depth_ratio = order_size_usd / total_depth if total_depth > 0 else 999
                estimated_slippage = spread_pct / 2 + (depth_ratio * 100)  # Base spread + impact
            else:
                estimated_slippage = spread_pct / 2
            
            # Max safe order (0.5% of depth for minimal impact)
            max_safe = total_depth * 0.005
            
            # Warnings
            if spread_pct > 0.5:
                warnings.append(f"Wide spread: {spread_pct:.2f}%")
            if total_depth < 50000:
                warnings.append(f"Low liquidity: ${total_depth:,.0f} depth")
            if estimated_slippage > 1.0:
                warnings.append(f"High slippage risk: {estimated_slippage:.2f}%")
            if order_size_usd > max_safe:
                warnings.append(f"Order size ${order_size_usd:,.0f} > safe limit ${max_safe:,.0f}")
            
            is_liquid = (
                spread_pct < 1.0 and 
                total_depth > 10000 and 
                estimated_slippage < 2.0 and
                order_size_usd <= max_safe * 2  # Allow up to 2x safe limit with warning
            )
            
            return LiquidityCheck(
                symbol=symbol,
                is_liquid=is_liquid,
                bid_ask_spread_pct=spread_pct,
                order_book_depth_usd=total_depth,
                estimated_slippage_pct=estimated_slippage,
                max_safe_order_usd=max_safe,
                warnings=warnings
            )
            
        except Exception as e:
            logger.warning(f"Liquidity check failed for {symbol}: {e}")
            return LiquidityCheck(
                symbol=symbol,
                is_liquid=False,
                bid_ask_spread_pct=999,
                order_book_depth_usd=0,
                estimated_slippage_pct=999,
                max_safe_order_usd=0,
                warnings=[f"Liquidity check error: {str(e)}"]
            )
    
    def get_volatility_adjusted_sl_tp(
        self, 
        symbol: str,
        market_regime: MarketRegime = MarketRegime.SIDEWAYS
    ) -> VolatilityProfile:
        """
        Get volatility-adjusted SL/TP for a symbol.
        
        Instead of fixed 5% SL / 7% TP, adjusts based on:
        1. Asset volatility category
        2. Current market regime
        """
        base = symbol.split('/')[0] if '/' in symbol else symbol.replace('USDT', '')
        
        # Get asset-specific volatility profile
        profile = self.ASSET_VOLATILITY.get(base, self.ASSET_VOLATILITY["DEFAULT"])
        
        base_sl = profile["base_sl"]
        base_tp = profile["base_tp"]
        vol_mult = profile["vol_mult"]
        
        # Adjust for market regime
        regime_adjustments = {
            MarketRegime.STRONG_BULL: {"sl_mult": 0.8, "tp_mult": 1.5},  # Tighter SL, wider TP
            MarketRegime.BULL: {"sl_mult": 0.9, "tp_mult": 1.2},
            MarketRegime.SIDEWAYS: {"sl_mult": 1.0, "tp_mult": 1.0},
            MarketRegime.BEAR: {"sl_mult": 1.2, "tp_mult": 0.8},  # Wider SL, tighter TP
            MarketRegime.STRONG_BEAR: {"sl_mult": 1.5, "tp_mult": 0.6},
            MarketRegime.CRISIS: {"sl_mult": 2.0, "tp_mult": 0.5},  # Very wide SL
        }
        
        adj = regime_adjustments.get(market_regime, regime_adjustments[MarketRegime.SIDEWAYS])
        
        suggested_sl = base_sl * adj["sl_mult"]
        suggested_tp = base_tp * adj["tp_mult"]
        
        return VolatilityProfile(
            symbol=symbol,
            atr_percent=base_sl,  # Approximation
            daily_volatility=vol_mult * 2,  # Rough estimate
            suggested_sl_pct=round(suggested_sl, 1),
            suggested_tp_pct=round(suggested_tp, 1),
            risk_multiplier=vol_mult
        )
    
    async def get_market_sentiment(self) -> MarketSentiment:
        """
        Fetch overall market sentiment indicators with CircuitBreaker protection.
        
        Sources:
        - Fear & Greed Index (alternative.me)
        - BTC dominance
        - Total market cap change
        
        FIX 2025-12-16: Added CircuitBreaker integration for API resilience
        """
        # Use cache if recent
        now = datetime.now()
        if (self._cached_sentiment and self._last_sentiment_fetch and 
            (now - self._last_sentiment_fetch).seconds < self._cache_ttl):
            return self._cached_sentiment
        
        fear_greed = 50
        fear_greed_label = "Neutral"
        btc_dominance = 50.0
        market_cap_change = 0.0
        funding_rate = 0.0
        warnings = []
        
        # Get circuit breaker instance
        circuit_breaker = get_api_circuit_breaker()
        
        # Helper functions for circuit breaker calls
        async def fetch_fear_greed():
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.alternative.me/fng/",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("data"):
                            return {
                                "value": int(data["data"][0]["value"]),
                                "label": data["data"][0]["value_classification"]
                            }
            return None
        
        async def fetch_coingecko_global():
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.coingecko.com/api/v3/global",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("data"):
                            return {
                                "btc_dominance": data["data"].get("market_cap_percentage", {}).get("btc", 50.0),
                                "market_cap_change": data["data"].get("market_cap_change_percentage_24h_usd", 0.0)
                            }
            return None
        
        try:
            # Fetch Fear & Greed Index with CircuitBreaker
            fg_result = await circuit_breaker.call(
                name="fear_greed_api",
                func=fetch_fear_greed,
                fallback_value=None
            )
            if fg_result:
                fear_greed = fg_result["value"]
                fear_greed_label = fg_result["label"]
            else:
                warnings.append("Fear & Greed data unavailable (circuit breaker or API error)")
            
            # Fetch CoinGecko data with CircuitBreaker
            cg_result = await circuit_breaker.call(
                name="coingecko_api",
                func=fetch_coingecko_global,
                fallback_value=None
            )
            if cg_result:
                btc_dominance = cg_result["btc_dominance"]
                market_cap_change = cg_result["market_cap_change"]
            else:
                warnings.append("Market cap data unavailable (circuit breaker or API error)")
        
        except Exception as e:
            logger.error(f"Sentiment fetch error: {e}")
            warnings.append(f"Sentiment API error: {str(e)}")
        
        # Determine market regime
        regime = self._determine_regime(fear_greed, market_cap_change)
        
        # Safety check
        is_safe = (
            fear_greed >= self.KILL_SWITCH_THRESHOLDS["fear_greed_extreme"] and
            regime != MarketRegime.CRISIS
        )
        
        if fear_greed < 20:
            warnings.append(f"⚠️ EXTREME FEAR ({fear_greed}) - Consider reduced position sizes")
        if fear_greed > 80:
            warnings.append(f"⚠️ EXTREME GREED ({fear_greed}) - Market may be overheated")
        
        sentiment = MarketSentiment(
            fear_greed_index=fear_greed,
            fear_greed_label=fear_greed_label,
            btc_dominance=btc_dominance,
            total_market_cap_change_24h=market_cap_change,
            funding_rate_avg=funding_rate,
            regime=regime,
            is_safe_to_trade=is_safe,
            warnings=warnings
        )
        
        self._cached_sentiment = sentiment
        self._last_sentiment_fetch = now
        
        return sentiment
    
    def _determine_regime(self, fear_greed: int, market_cap_change_24h: float) -> MarketRegime:
        """Determine current market regime."""
        # Crisis detection
        if fear_greed < 10 or market_cap_change_24h < -15:
            return MarketRegime.CRISIS
        
        # Trend detection based on 24h change
        if market_cap_change_24h > 10:
            return MarketRegime.STRONG_BULL
        elif market_cap_change_24h > 3:
            return MarketRegime.BULL
        elif market_cap_change_24h < -10:
            return MarketRegime.STRONG_BEAR
        elif market_cap_change_24h < -3:
            return MarketRegime.BEAR
        else:
            return MarketRegime.SIDEWAYS
    
    def check_correlation_risk(
        self, 
        current_positions: List[str],
        new_symbol: str
    ) -> CorrelationRisk:
        """
        Check if adding a new position increases correlation risk.
        
        Returns CorrelationRisk with:
        - avg_correlation: Average correlation in portfolio
        - highly_correlated_pairs: Pairs with correlation > 0.7
        - diversification_score: 0-100 (higher = more diversified)
        """
        # Extract base symbols
        def get_base(s):
            return s.split('/')[0] if '/' in s else s.replace('USDT', '').replace('USD', '')
        
        positions = [get_base(p) for p in current_positions]
        new_base = get_base(new_symbol)
        
        # Find correlation groups for each position
        def find_group(symbol):
            for group_name, symbols in self.CORRELATION_GROUPS.items():
                if symbol in symbols:
                    return group_name
            return None
        
        # Check correlations
        highly_correlated = []
        
        new_group = find_group(new_base)
        
        for pos in positions:
            pos_group = find_group(pos)
            
            # Same group = high correlation
            if new_group and pos_group and new_group == pos_group:
                highly_correlated.append((pos, new_base, 0.85))
            
            # BTC correlation (everything correlates with BTC)
            if pos == "BTC" or new_base == "BTC":
                highly_correlated.append((pos, new_base, 0.7))
        
        # Calculate metrics
        num_correlated = len(highly_correlated)
        total_positions = len(positions) + 1
        
        avg_correlation = sum(c[2] for c in highly_correlated) / max(num_correlated, 1)
        
        # Diversification score (penalize same-group positions)
        groups_used = set(find_group(p) for p in positions + [new_base] if find_group(p))
        unique_assets = len(set(positions + [new_base]))
        diversification = min(100, (unique_assets * 20) + (len(groups_used) * 15))
        
        # Concentration risk
        if num_correlated >= 3:
            concentration = "high"
        elif num_correlated >= 1:
            concentration = "medium"
        else:
            concentration = "low"
        
        return CorrelationRisk(
            avg_correlation=avg_correlation,
            highly_correlated_pairs=highly_correlated,
            diversification_score=diversification,
            concentration_risk=concentration
        )
    
    async def should_kill_switch(self) -> Tuple[bool, str]:
        """
        Check if emergency kill switch should be activated.
        
        Returns (should_kill, reason)
        """
        try:
            # Get BTC price change
            if self.exchange:
                try:
                    ticker = await self.exchange.get_ticker("BTC/USDT")
                    if ticker:
                        change_24h = getattr(ticker, 'change_percent_24h', None) or ticker.get('percentage', 0)
                        
                        if change_24h and change_24h < self.KILL_SWITCH_THRESHOLDS["btc_drop_24h"]:
                            return True, f"🚨 KILL SWITCH: BTC dropped {change_24h:.1f}% in 24h"
                except Exception as e:
                    logger.warning(f"Could not check BTC price: {e}")
            
            # Check sentiment
            sentiment = await self.get_market_sentiment()
            
            if sentiment.fear_greed_index < self.KILL_SWITCH_THRESHOLDS["fear_greed_extreme"]:
                return True, f"🚨 KILL SWITCH: Extreme Fear ({sentiment.fear_greed_index})"
            
            if sentiment.regime == MarketRegime.CRISIS:
                return True, f"🚨 KILL SWITCH: Market in CRISIS mode"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"Kill switch check error: {e}")
            return False, ""  # Don't kill on error


# Singleton instance
_market_intelligence: Optional[MarketIntelligenceService] = None

def get_market_intelligence(exchange_adapter=None) -> MarketIntelligenceService:
    """Get or create the global MarketIntelligenceService instance."""
    global _market_intelligence
    if _market_intelligence is None:
        _market_intelligence = MarketIntelligenceService(exchange_adapter)
    elif exchange_adapter and not _market_intelligence.exchange:
        _market_intelligence.exchange = exchange_adapter
    return _market_intelligence
