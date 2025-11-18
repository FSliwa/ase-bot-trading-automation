"""Redis cache implementation."""

import json
from typing import Any, Optional

import redis.asyncio as redis

from src.infrastructure.logging.logger import get_logger
from src.infrastructure.config import get_settings

logger = get_logger(__name__)


class RedisCache:
    """Redis cache implementation with async support."""

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize Redis cache."""
        settings = get_settings()
        url = redis_url or settings.redis_url.get_secret_value()
        self.redis = redis.from_url(
            url, 
            encoding="utf-8", 
            decode_responses=True,
            max_connections=settings.redis_max_connections
        )

    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        try:
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set value in cache with TTL."""
        try:
            serialized = json.dumps(value, default=str)
            return await self.redis.set(key, serialized, ex=ttl)
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        try:
            return await self.redis.delete(key) > 0
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False

    async def increment(self, key: str, amount: int = 1) -> int | None:
        """Increment counter in cache."""
        try:
            return await self.redis.incrby(key, amount)
        except Exception as e:
            logger.error(f"Cache increment error for key {key}: {e}")
            return None

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from cache."""
        try:
            values = await self.redis.mget(keys)
            result = {}
            for key, value in zip(keys, values, strict=False):
                if value:
                    result[key] = json.loads(value)
            return result
        except Exception as e:
            logger.error(f"Cache get_many error: {e}")
            return {}

    async def set_many(self, mapping: dict[str, Any], ttl: int = 3600) -> bool:
        """Set multiple values in cache."""
        try:
            pipeline = self.redis.pipeline()
            for key, value in mapping.items():
                serialized = json.dumps(value, default=str)
                pipeline.set(key, serialized, ex=ttl)
            await pipeline.execute()
            return True
        except Exception as e:
            logger.error(f"Cache set_many error: {e}")
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern."""
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                return await self.redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Cache clear_pattern error for {pattern}: {e}")
            return 0
