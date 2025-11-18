from __future__ import annotations

from typing import Any, Optional

import json
import os
import warnings
import redis.asyncio as redis  # type: ignore[import]

from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class RedisCache:
    """Async Redis cache helper with JSON serialization."""

    def __init__(self, redis_url: Optional[str] = None):
        app_env = os.getenv("APP_ENV", "development").lower()
        effective_url = redis_url or os.getenv("REDIS_URL")

        if not effective_url:
            if app_env == "development":
                effective_url = "redis://localhost:6379/0"
                warnings.warn(
                    "REDIS_URL is not configured; using development fallback. "
                    "Ensure REDIS_URL is set in production environments.",
                    RuntimeWarning,
                )
            else:
                raise RuntimeError(
                    "REDIS_URL environment variable must be set when APP_ENV is not development."
                )

        self.redis: redis.Redis = redis.from_url(
            effective_url,
            encoding="utf-8",
            decode_responses=True,
        )

    async def get(self, key: str) -> Optional[Any]:
        try:
            value = await self.redis.get(key)
            return json.loads(value) if value is not None else None
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Redis GET failed", extra={"key": key, "error": str(exc)})
            return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        try:
            payload = json.dumps(value, default=str)
            result = await self.redis.set(key, payload, ex=ttl)
            return result is True
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Redis SET failed", extra={"key": key, "error": str(exc)})
            return False

    async def delete(self, key: str) -> bool:
        try:
            return (await self.redis.delete(key)) > 0
        except Exception as exc:  # pragma: no cover
            logger.error("Redis DELETE failed", extra={"key": key, "error": str(exc)})
            return False

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self.redis.exists(key))
        except Exception as exc:  # pragma: no cover
            logger.error("Redis EXISTS failed", extra={"key": key, "error": str(exc)})
            return False

    async def close(self) -> None:
        await self.redis.close()
