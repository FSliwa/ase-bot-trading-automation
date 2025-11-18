"""Cache Configuration with optimized TTL values"""

from typing import Dict

# Cache TTL configuration in seconds
CACHE_TTL_CONFIG: Dict[str, int] = {
    # User data - longer TTL as it changes infrequently
    "user_data": 3600,          # 1 hour (was 30 minutes)
    "user_email_mapping": 7200,  # 2 hours (was 1 hour)
    "user_session": 1800,        # 30 minutes
    
    # Trading data - increased TTL for better performance
    "portfolio_data": 300,       # 5 minutes (was likely uncached)
    "trading_positions": 60,     # 1 minute for real-time data
    "market_data": 30,          # 30 seconds for price updates
    "trading_settings": 3600,    # 1 hour (rarely changes)
    
    # AI insights - expensive to compute, cache longer
    "ai_insights": 1800,         # 30 minutes (was 15 minutes)
    "ai_sentiment": 3600,        # 1 hour (was 30 minutes)
    "ai_strategy": 86400,        # 24 hours (personalized strategies)
    
    # External API data
    "crypto_news": 1800,         # 30 minutes (was 15 minutes)
    "market_overview": 600,      # 10 minutes (was 5 minutes)
    "trading_signals": 900,      # 15 minutes (was 10 minutes)
    "social_sentiment": 2400,    # 40 minutes (was 20 minutes)
    
    # System data
    "audit_logs": 3600,          # 1 hour
    "security_alerts": 86400,    # 24 hours
    "slo_metrics": 300,          # 5 minutes
    
    # Default TTL
    "default": 3600              # 1 hour default
}

def get_cache_ttl(cache_type: str) -> int:
    """Get TTL for specific cache type."""
    return CACHE_TTL_CONFIG.get(cache_type, CACHE_TTL_CONFIG["default"])

# Cache warming configuration
CACHE_WARM_ON_STARTUP = [
    "market_overview",
    "crypto_news",
    "trading_signals"
]

# Cache invalidation patterns
CACHE_INVALIDATION_PATTERNS = {
    "user_update": ["user_data", "user_session"],
    "trade_execution": ["portfolio_data", "trading_positions"],
    "settings_update": ["trading_settings", "ai_strategy"]
}
