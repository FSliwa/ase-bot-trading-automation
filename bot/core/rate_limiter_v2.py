"""
Component Rate Limiter V2 - Per-component rate limiting.

Different components have different rate limits:
- Trading Engine: 5 trades/hour
- Position Monitor: 100 checks/minute  
- Market Data: 60 requests/minute
- AI Analysis: 10 requests/minute
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from enum import Enum
from functools import wraps
import time

logger = logging.getLogger(__name__)


class Component(Enum):
    """Trading system components with different rate limits."""
    TRADING_ENGINE = "trading_engine"
    POSITION_MONITOR = "position_monitor"
    MARKET_DATA = "market_data"
    AI_ANALYSIS = "ai_analysis"
    EXCHANGE_API = "exchange_api"
    DATABASE = "database"


@dataclass
class RateLimitConfig:
    """Configuration for a component's rate limits."""
    max_requests_per_minute: int = 60
    max_requests_per_hour: int = 1000
    max_requests_per_day: int = 10000
    burst_limit: int = 10  # Max requests in 1 second
    cooldown_after_limit: float = 60.0  # Seconds to wait after hitting limit
    
    
# Default configs per component
DEFAULT_RATE_LIMITS: Dict[Component, RateLimitConfig] = {
    Component.TRADING_ENGINE: RateLimitConfig(
        max_requests_per_minute=10,
        max_requests_per_hour=60,
        max_requests_per_day=200,
        burst_limit=3,
        cooldown_after_limit=120.0
    ),
    Component.POSITION_MONITOR: RateLimitConfig(
        max_requests_per_minute=100,
        max_requests_per_hour=3000,
        max_requests_per_day=50000,
        burst_limit=20,
        cooldown_after_limit=10.0
    ),
    Component.MARKET_DATA: RateLimitConfig(
        max_requests_per_minute=60,
        max_requests_per_hour=1000,
        max_requests_per_day=20000,
        burst_limit=10,
        cooldown_after_limit=30.0
    ),
    Component.AI_ANALYSIS: RateLimitConfig(
        max_requests_per_minute=10,
        max_requests_per_hour=100,
        max_requests_per_day=500,
        burst_limit=2,
        cooldown_after_limit=60.0
    ),
    Component.EXCHANGE_API: RateLimitConfig(
        max_requests_per_minute=30,
        max_requests_per_hour=500,
        max_requests_per_day=5000,
        burst_limit=5,
        cooldown_after_limit=60.0
    ),
    Component.DATABASE: RateLimitConfig(
        max_requests_per_minute=200,
        max_requests_per_hour=5000,
        max_requests_per_day=100000,
        burst_limit=50,
        cooldown_after_limit=5.0
    ),
}


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    def __init__(self, component: str, limit_type: str, retry_after: float):
        self.component = component
        self.limit_type = limit_type
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded for {component}: {limit_type}. "
            f"Retry after {retry_after:.1f}s"
        )


@dataclass
class RequestLog:
    """Log of requests for rate limiting."""
    timestamps: List[float] = field(default_factory=list)
    
    def add(self, timestamp: float = None):
        self.timestamps.append(timestamp or time.time())
    
    def count_since(self, since: float) -> int:
        """Count requests since timestamp."""
        return sum(1 for ts in self.timestamps if ts >= since)
    
    def cleanup(self, before: float):
        """Remove entries older than timestamp."""
        self.timestamps = [ts for ts in self.timestamps if ts >= before]


class ComponentRateLimiter:
    """
    Per-component rate limiter with sliding window algorithm.
    
    Features:
    1. Separate limits per component
    2. Minute/hour/day windows
    3. Burst protection
    4. Automatic cleanup of old entries
    5. Async-safe
    
    Usage:
        limiter = ComponentRateLimiter()
        
        # Check before making request
        if limiter.can_proceed(Component.TRADING_ENGINE):
            limiter.record_request(Component.TRADING_ENGINE)
            # Make request...
        
        # Or use decorator
        @limiter.rate_limited(Component.MARKET_DATA)
        async def fetch_market_data():
            ...
    """
    
    def __init__(self, configs: Dict[Component, RateLimitConfig] = None):
        self.configs = configs or DEFAULT_RATE_LIMITS
        self._request_logs: Dict[Component, RequestLog] = {
            c: RequestLog() for c in Component
        }
        self._cooldown_until: Dict[Component, float] = {}
        self._lock = asyncio.Lock()
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5 minutes
    
    def _get_config(self, component: Component) -> RateLimitConfig:
        """Get rate limit config for component."""
        return self.configs.get(component, RateLimitConfig())
    
    def can_proceed(self, component: Component, user_id: str = None) -> bool:
        """
        Check if a request can proceed for the given component.
        
        Args:
            component: System component
            user_id: Optional user ID for per-user limits
            
        Returns:
            True if request is allowed
        """
        now = time.time()
        
        # Check cooldown
        if component in self._cooldown_until:
            if now < self._cooldown_until[component]:
                return False
            else:
                del self._cooldown_until[component]
        
        config = self._get_config(component)
        log = self._request_logs[component]
        
        # Check burst limit (last 1 second)
        if log.count_since(now - 1) >= config.burst_limit:
            logger.warning(f"🚫 Burst limit hit for {component.value}")
            return False
        
        # Check minute limit
        if log.count_since(now - 60) >= config.max_requests_per_minute:
            logger.warning(f"🚫 Minute limit hit for {component.value}")
            return False
        
        # Check hour limit
        if log.count_since(now - 3600) >= config.max_requests_per_hour:
            logger.warning(f"🚫 Hour limit hit for {component.value}")
            self._set_cooldown(component, config.cooldown_after_limit)
            return False
        
        # Check day limit
        if log.count_since(now - 86400) >= config.max_requests_per_day:
            logger.warning(f"🚫 Day limit hit for {component.value}")
            self._set_cooldown(component, config.cooldown_after_limit * 2)
            return False
        
        return True
    
    def record_request(self, component: Component, user_id: str = None):
        """Record a request for the component."""
        self._request_logs[component].add()
        
        # Periodic cleanup
        if time.time() - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
    
    def _set_cooldown(self, component: Component, duration: float):
        """Set cooldown for component."""
        self._cooldown_until[component] = time.time() + duration
        logger.warning(f"⏳ Cooldown set for {component.value}: {duration}s")
    
    def _cleanup(self):
        """Clean up old request logs."""
        cutoff = time.time() - 86400  # Keep last 24h
        for log in self._request_logs.values():
            log.cleanup(cutoff)
        self._last_cleanup = time.time()
    
    def get_remaining(self, component: Component) -> Dict[str, int]:
        """Get remaining requests for each window."""
        now = time.time()
        config = self._get_config(component)
        log = self._request_logs[component]
        
        return {
            'per_minute': max(0, config.max_requests_per_minute - log.count_since(now - 60)),
            'per_hour': max(0, config.max_requests_per_hour - log.count_since(now - 3600)),
            'per_day': max(0, config.max_requests_per_day - log.count_since(now - 86400)),
            'burst': max(0, config.burst_limit - log.count_since(now - 1))
        }
    
    def get_retry_after(self, component: Component) -> float:
        """Get seconds until component can make requests again."""
        if component in self._cooldown_until:
            return max(0, self._cooldown_until[component] - time.time())
        return 0
    
    def rate_limited(self, component: Component, raise_on_limit: bool = True):
        """
        Decorator to rate limit a function.
        
        Args:
            component: Component this function belongs to
            raise_on_limit: If True, raise exception; if False, return None
            
        Usage:
            @limiter.rate_limited(Component.MARKET_DATA)
            async def fetch_price(symbol):
                ...
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                if not self.can_proceed(component):
                    retry_after = self.get_retry_after(component)
                    if raise_on_limit:
                        raise RateLimitExceeded(
                            component.value,
                            "rate_limited",
                            retry_after
                        )
                    else:
                        logger.warning(
                            f"Rate limited {component.value}, skipping {func.__name__}"
                        )
                        return None
                
                self.record_request(component)
                return await func(*args, **kwargs)
            
            return wrapper
        return decorator
    
    def reset(self, component: Component = None):
        """Reset rate limits for component or all."""
        if component:
            self._request_logs[component] = RequestLog()
            if component in self._cooldown_until:
                del self._cooldown_until[component]
        else:
            for c in Component:
                self._request_logs[c] = RequestLog()
            self._cooldown_until.clear()


# Global singleton
_rate_limiter: Optional[ComponentRateLimiter] = None


def get_component_rate_limiter() -> ComponentRateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = ComponentRateLimiter()
    return _rate_limiter
