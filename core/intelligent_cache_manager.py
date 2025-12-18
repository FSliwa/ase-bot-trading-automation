"""
Intelligent Redis Cache Management System
Multi-level caching with TTL, cache warming, intelligent invalidation
"""

import asyncio
import json
import logging
import time
import hashlib
import zlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Callable
from dataclasses import dataclass, asdict
from enum import Enum

import redis.asyncio as redis

logger = logging.getLogger(__name__)

class CacheLevel(str, Enum):
    """Cache levels with different TTL strategies"""
    L1_REALTIME = "l1_realtime"      # 1-5 seconds
    L2_FREQUENT = "l2_frequent"      # 30-60 seconds  
    L3_MODERATE = "l3_moderate"      # 5-15 minutes
    L4_PERSISTENT = "l4_persistent"  # 1-24 hours

@dataclass
class CacheConfig:
    """Cache configuration for different data types"""
    level: CacheLevel
    ttl_seconds: int
    compression: bool = False
    serialization: str = "json"  # json, pickle, msgpack
    max_size_mb: float = 10.0
    warming_enabled: bool = False

class CacheKeyBuilder:
    """Intelligent cache key construction"""
    
    @staticmethod
    def build_key(namespace: str, *args, **kwargs) -> str:
        """Build cache key from arguments"""
        key_parts = [namespace]
        
        # Add positional arguments
        for arg in args:
            if isinstance(arg, (str, int, float)):
                key_parts.append(str(arg))
            else:
                # Hash complex objects
                key_parts.append(hashlib.md5(str(arg).encode()).hexdigest()[:8])
        
        # Add keyword arguments (sorted for consistency)
        if kwargs:
            for k, v in sorted(kwargs.items()):
                key_parts.append(f"{k}:{v}")
        
        return ":".join(key_parts)
    
    @staticmethod
    def build_pattern(namespace: str, pattern: str = "*") -> str:
        """Build cache key pattern for bulk operations"""
        return f"{namespace}:{pattern}"

class IntelligentCacheManager:
    """Advanced Redis cache management with multi-level caching"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        
        # Cache configurations for different data types
        self.cache_configs = {
            # Real-time trading data
            "market_prices": CacheConfig(
                level=CacheLevel.L1_REALTIME,
                ttl_seconds=5,
                compression=True,
                warming_enabled=True
            ),
            "account_balance": CacheConfig(
                level=CacheLevel.L1_REALTIME,
                ttl_seconds=2,
                compression=False
            ),
            "open_positions": CacheConfig(
                level=CacheLevel.L1_REALTIME,
                ttl_seconds=1,
                compression=False
            ),
            
            # Frequent updates
            "user_portfolio": CacheConfig(
                level=CacheLevel.L2_FREQUENT,
                ttl_seconds=30,
                compression=True
            ),
            "exchange_connections": CacheConfig(
                level=CacheLevel.L2_FREQUENT,
                ttl_seconds=60,
                compression=False
            ),
            "trading_signals": CacheConfig(
                level=CacheLevel.L2_FREQUENT,
                ttl_seconds=45,
                compression=True
            ),
            
            # Moderate updates  
            "trading_stats": CacheConfig(
                level=CacheLevel.L3_MODERATE,
                ttl_seconds=300,  # 5 minutes
                compression=True,
                warming_enabled=True
            ),
            "ai_analysis": CacheConfig(
                level=CacheLevel.L3_MODERATE,
                ttl_seconds=600,  # 10 minutes
                compression=True
            ),
            "market_analysis": CacheConfig(
                level=CacheLevel.L3_MODERATE,
                ttl_seconds=900,  # 15 minutes
                compression=True,
                warming_enabled=True
            ),
            
            # Persistent data
            "user_preferences": CacheConfig(
                level=CacheLevel.L4_PERSISTENT,
                ttl_seconds=3600,  # 1 hour
                compression=False
            ),
            "exchange_metadata": CacheConfig(
                level=CacheLevel.L4_PERSISTENT,
                ttl_seconds=86400,  # 24 hours
                compression=True
            ),
            "system_config": CacheConfig(
                level=CacheLevel.L4_PERSISTENT,
                ttl_seconds=3600,
                compression=False
            )
        }
        
        # Cache statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0,
            "total_size_mb": 0.0
        }
        
        # Cache warming functions
        self.warming_functions: Dict[str, Callable] = {}

    async def initialize(self):
        """Initialize Redis connection and cache system"""
        logger.info("🚀 Initializing Intelligent Cache Manager...")
        
        try:
            # Connect to Redis
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=False,  # We'll handle encoding ourselves
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
                max_connections=20
            )
            
            # Test connection
            await self.redis_client.ping()
            
            # Get Redis info
            info = await self.redis_client.info()
            redis_version = info.get('redis_version', 'unknown')
            memory_usage = info.get('used_memory_human', 'unknown')
            
            logger.info(f"✅ Redis connected - Version: {redis_version}, Memory: {memory_usage}")
            
            # Setup cache warming
            await self._setup_cache_warming()
            
            # Start maintenance task
            asyncio.create_task(self._cache_maintenance_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            logger.warning("⚠️ Running without cache - performance may be degraded")
            self.redis_client = None
            return False

    async def get(
        self, 
        namespace: str, 
        *args, 
        default: Any = None, 
        **kwargs
    ) -> Any:
        """Get cached value with intelligent deserialization"""
        if not self.redis_client:
            return default
        
        try:
            # Build cache key
            cache_key = CacheKeyBuilder.build_key(namespace, *args, **kwargs)
            config = self.cache_configs.get(namespace)
            
            if not config:
                logger.warning(f"No cache config for namespace: {namespace}")
                return default
            
            # Get from Redis
            start_time = time.time()
            cached_data = await self.redis_client.get(cache_key)
            
            if cached_data is None:
                self.stats["misses"] += 1
                logger.debug(f"Cache MISS: {cache_key}")
                return default
            
            # Deserialize data
            try:
                # Decompress if needed
                if config.compression:
                    cached_data = zlib.decompress(cached_data)
                
                # Decode
                if config.serialization == "json":
                    result = json.loads(cached_data.decode('utf-8'))
                else:
                    # Handle other serialization methods
                    result = json.loads(cached_data.decode('utf-8'))
                
                self.stats["hits"] += 1
                duration_ms = (time.time() - start_time) * 1000
                logger.debug(f"Cache HIT: {cache_key} ({duration_ms:.1f}ms)")
                
                return result
                
            except Exception as e:
                logger.error(f"Cache deserialization error for {cache_key}: {e}")
                # Remove corrupted cache
                await self.delete(namespace, *args, **kwargs)
                return default
                
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self.stats["errors"] += 1
            return default

    async def set(
        self, 
        namespace: str, 
        value: Any, 
        *args, 
        ttl_override: Optional[int] = None,
        **kwargs
    ) -> bool:
        """Set cached value with intelligent serialization"""
        if not self.redis_client:
            return False
        
        try:
            # Get configuration
            config = self.cache_configs.get(namespace)
            if not config:
                logger.warning(f"No cache config for namespace: {namespace}")
                return False
            
            # Build cache key
            cache_key = CacheKeyBuilder.build_key(namespace, *args, **kwargs)
            
            # Serialize data
            if config.serialization == "json":
                serialized_data = json.dumps(value, default=str).encode('utf-8')
            else:
                serialized_data = json.dumps(value, default=str).encode('utf-8')
            
            # Check size limit
            size_mb = len(serialized_data) / 1024 / 1024
            if size_mb > config.max_size_mb:
                logger.warning(f"Cache value too large: {size_mb:.2f}MB > {config.max_size_mb}MB")
                return False
            
            # Compress if needed
            if config.compression:
                serialized_data = zlib.compress(serialized_data)
            
            # Set TTL
            ttl = ttl_override or config.ttl_seconds
            
            # Store in Redis
            start_time = time.time()
            await self.redis_client.setex(cache_key, ttl, serialized_data)
            
            self.stats["sets"] += 1
            self.stats["total_size_mb"] += size_mb
            
            duration_ms = (time.time() - start_time) * 1000
            logger.debug(f"Cache SET: {cache_key} (TTL: {ttl}s, Size: {size_mb:.2f}MB, {duration_ms:.1f}ms)")
            
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            self.stats["errors"] += 1
            return False

    async def delete(self, namespace: str, *args, **kwargs) -> bool:
        """Delete cached value"""
        if not self.redis_client:
            return False
        
        try:
            cache_key = CacheKeyBuilder.build_key(namespace, *args, **kwargs)
            result = await self.redis_client.delete(cache_key)
            
            self.stats["deletes"] += 1
            logger.debug(f"Cache DELETE: {cache_key}")
            
            return result > 0
            
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            self.stats["errors"] += 1
            return False

    async def delete_pattern(self, namespace: str, pattern: str = "*") -> int:
        """Delete all keys matching pattern"""
        if not self.redis_client:
            return 0
        
        try:
            key_pattern = CacheKeyBuilder.build_pattern(namespace, pattern)
            keys = await self.redis_client.keys(key_pattern)
            
            if keys:
                deleted = await self.redis_client.delete(*keys)
                self.stats["deletes"] += deleted
                logger.debug(f"Cache DELETE PATTERN: {key_pattern} ({deleted} keys)")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Cache delete pattern error: {e}")
            self.stats["errors"] += 1
            return 0

    async def exists(self, namespace: str, *args, **kwargs) -> bool:
        """Check if cached value exists"""
        if not self.redis_client:
            return False
        
        try:
            cache_key = CacheKeyBuilder.build_key(namespace, *args, **kwargs)
            result = await self.redis_client.exists(cache_key)
            return result > 0
            
        except Exception as e:
            logger.error(f"Cache exists error: {e}")
            return False

    async def get_ttl(self, namespace: str, *args, **kwargs) -> int:
        """Get TTL for cached value"""
        if not self.redis_client:
            return -1
        
        try:
            cache_key = CacheKeyBuilder.build_key(namespace, *args, **kwargs)
            return await self.redis_client.ttl(cache_key)
            
        except Exception as e:
            logger.error(f"Cache TTL error: {e}")
            return -1

    async def extend_ttl(self, namespace: str, additional_seconds: int, *args, **kwargs) -> bool:
        """Extend TTL for cached value"""
        if not self.redis_client:
            return False
        
        try:
            cache_key = CacheKeyBuilder.build_key(namespace, *args, **kwargs)
            current_ttl = await self.redis_client.ttl(cache_key)
            
            if current_ttl > 0:
                new_ttl = current_ttl + additional_seconds
                result = await self.redis_client.expire(cache_key, new_ttl)
                return result
            
            return False
            
        except Exception as e:
            logger.error(f"Cache extend TTL error: {e}")
            return False

    # Cache warming methods
    
    def register_warming_function(self, namespace: str, func: Callable):
        """Register function for cache warming"""
        self.warming_functions[namespace] = func
        logger.info(f"📝 Registered cache warming function for: {namespace}")

    async def warm_cache(self, namespace: str, *args, **kwargs):
        """Warm cache for specific namespace"""
        if namespace not in self.warming_functions:
            logger.warning(f"No warming function for: {namespace}")
            return
        
        try:
            func = self.warming_functions[namespace]
            data = await func(*args, **kwargs)
            
            if data is not None:
                await self.set(namespace, data, *args, **kwargs)
                logger.info(f"🔥 Cache warmed: {namespace}")
            
        except Exception as e:
            logger.error(f"Cache warming error for {namespace}: {e}")

    async def _setup_cache_warming(self):
        """Setup automatic cache warming for critical data"""
        warming_configs = {
            namespace: config 
            for namespace, config in self.cache_configs.items() 
            if config.warming_enabled
        }
        
        if warming_configs:
            logger.info(f"🔥 Setting up cache warming for {len(warming_configs)} namespaces")
            
            # Schedule warming tasks
            asyncio.create_task(self._cache_warming_loop(warming_configs))

    async def _cache_warming_loop(self, warming_configs: Dict[str, CacheConfig]):
        """Background cache warming loop"""
        while self.redis_client:
            try:
                for namespace, config in warming_configs.items():
                    # Check if cache needs warming (expired or close to expiring)
                    await self.warm_cache(namespace)
                    await asyncio.sleep(1)  # Prevent overwhelming
                
                # Wait before next warming cycle
                await asyncio.sleep(30)  # Run every 30 seconds
                
            except Exception as e:
                logger.error(f"Cache warming loop error: {e}")
                await asyncio.sleep(60)

    # Cache maintenance and monitoring
    
    async def _cache_maintenance_loop(self):
        """Background cache maintenance"""
        while self.redis_client:
            try:
                # Update statistics
                info = await self.redis_client.info()
                self.stats["total_size_mb"] = info.get('used_memory', 0) / 1024 / 1024
                
                # Log cache statistics periodically
                if self.stats["hits"] + self.stats["misses"] > 0:
                    hit_rate = self.stats["hits"] / (self.stats["hits"] + self.stats["misses"]) * 100
                    logger.info(
                        f"📊 Cache Stats - Hit Rate: {hit_rate:.1f}%, "
                        f"Size: {self.stats['total_size_mb']:.1f}MB, "
                        f"Errors: {self.stats['errors']}"
                    )
                
                # Reset statistics counters periodically
                if (self.stats["hits"] + self.stats["misses"]) > 10000:
                    self.stats.update({
                        "hits": int(self.stats["hits"] * 0.1),  # Keep 10% for trending
                        "misses": int(self.stats["misses"] * 0.1),
                        "sets": 0,
                        "deletes": 0,
                        "errors": 0
                    })
                
                await asyncio.sleep(300)  # Run every 5 minutes
                
            except Exception as e:
                logger.error(f"Cache maintenance error: {e}")
                await asyncio.sleep(600)

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        if not self.redis_client:
            return {"status": "disconnected"}
        
        try:
            # Redis info
            info = await self.redis_client.info()
            
            # Calculate hit rate
            total_requests = self.stats["hits"] + self.stats["misses"]
            hit_rate = (self.stats["hits"] / total_requests * 100) if total_requests > 0 else 0
            
            # Get cache sizes by namespace
            namespace_stats = {}
            for namespace in self.cache_configs.keys():
                pattern = CacheKeyBuilder.build_pattern(namespace, "*")
                keys = await self.redis_client.keys(pattern)
                namespace_stats[namespace] = len(keys)
            
            return {
                "status": "connected",
                "redis_version": info.get('redis_version'),
                "memory_usage_mb": info.get('used_memory', 0) / 1024 / 1024,
                "connected_clients": info.get('connected_clients'),
                "hit_rate_percent": round(hit_rate, 2),
                "total_requests": total_requests,
                "hits": self.stats["hits"],
                "misses": self.stats["misses"],
                "sets": self.stats["sets"],
                "deletes": self.stats["deletes"],
                "errors": self.stats["errors"],
                "namespace_counts": namespace_stats,
                "cache_levels": {
                    level.value: [
                        namespace for namespace, config in self.cache_configs.items() 
                        if config.level == level
                    ]
                    for level in CacheLevel
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"status": "error", "error": str(e)}

    async def clear_all_cache(self) -> bool:
        """Clear all cache (use with caution)"""
        if not self.redis_client:
            return False
        
        try:
            await self.redis_client.flushdb()
            logger.warning("🧹 All cache cleared")
            
            # Reset stats
            self.stats = {
                "hits": 0,
                "misses": 0,
                "sets": 0,
                "deletes": 0,
                "errors": 0,
                "total_size_mb": 0.0
            }
            
            return True
            
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return False

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("🔒 Cache manager closed")

# Global instance
cache_manager = IntelligentCacheManager()

# Convenience functions and decorators
def cache_result(namespace: str, ttl_seconds: Optional[int] = None):
    """Decorator for caching function results"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Try to get from cache first
            cached_result = await cache_manager.get(namespace, *args, **kwargs)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            await cache_manager.set(namespace, result, *args, ttl_override=ttl_seconds, **kwargs)
            
            return result
        return wrapper
    return decorator

async def get_cache_manager():
    """Get cache manager instance for FastAPI dependency"""
    return cache_manager
