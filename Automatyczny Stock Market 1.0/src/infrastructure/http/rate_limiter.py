from __future__ import annotations

import os
from typing import Iterable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

DEFAULT_STORAGE_CANDIDATES: Iterable[str] = (
    os.getenv("RATE_LIMIT_STORAGE_URI"),
    os.getenv("REDIS_URL"),
    "redis://redis:6379/3",
    "memory://",
)


def _first_valid_uri() -> str:
    for candidate in DEFAULT_STORAGE_CANDIDATES:
        if candidate:
            return candidate
    return "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_first_valid_uri(),
    default_limits=[],
)


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "Rate limit exceeded",
            "limit": exc.detail,
        },
    )


def init_rate_limiter(app: FastAPI) -> None:
    """Attach SlowAPI middleware and exception handler to the app."""

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)
