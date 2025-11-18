"""Content Security Policy middleware for enhanced security."""

import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.infrastructure.logging.logger import get_logger


logger = get_logger(__name__)


class CSPMiddleware(BaseHTTPMiddleware):
    """Middleware to add Content Security Policy headers."""

    def __init__(self, app, config: dict[str, list[str]] | None = None):
        """Initialize CSP middleware with configuration."""
        super().__init__(app)
        self.config = config or self._get_default_config()

    def _get_default_config(self) -> dict[str, list[str]]:
        """Get default CSP configuration."""
        return {
            "default-src": ["'none'"],
            "script-src": [
                "'self'",
                "'nonce-{nonce}'",
                "'strict-dynamic'",
                "https:",
                "'unsafe-inline'"  # Fallback for older browsers, ignored with strict-dynamic
            ],
            "style-src": ["'self'", "'nonce-{nonce}'"],
            "img-src": ["'self'", "data:", "https:"],
            "font-src": ["'self'", "https://fonts.gstatic.com"],
            "connect-src": ["'self'", "wss://stream.binance.com", "https://*.hcaptcha.com"],
            "frame-src": [
                "https://hcaptcha.com",
                "https://*.hcaptcha.com",
                "https://s3.tradingview.com",
            ],
            "frame-ancestors": ["'none'"],
            "base-uri": ["'self'"],
            "form-action": ["'self'"],
            "object-src": ["'none'"],
            "upgrade-insecure-requests": [],
            "block-all-mixed-content": [],
            "require-trusted-types-for": ["'script'"],
        }

    async def dispatch(self, request: Request, call_next):
        """Add CSP headers to response."""
        # Generate nonce for this request
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)

        # Build CSP header
        csp_parts = []
        for directive, sources in self.config.items():
            if sources:
                sources_str = " ".join(s.replace("{nonce}", nonce) for s in sources)
                csp_parts.append(f"{directive} {sources_str}")
            else:
                csp_parts.append(directive)

        csp_header = "; ".join(csp_parts)

        # Add security headers
        response.headers["Content-Security-Policy"] = csp_header
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # Additional security headers
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-DNS-Prefetch-Control"] = "off"
        response.headers["X-Download-Options"] = "noopen"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting to prevent DoS attacks."""

    def __init__(self, app, redis_client, max_requests: int = 100, window: int = 60):
        """Initialize rate limit middleware."""
        super().__init__(app)
        self.redis = redis_client
        self.max_requests = max_requests
        self.window = window

    async def dispatch(self, request: Request, call_next):
        """Check rate limits before processing request."""
        # Get client IP
        client = request.client
        client_ip = client.host if client else "127.0.0.1"
        if request.headers.get("X-Forwarded-For"):
            client_ip = request.headers["X-Forwarded-For"].split(",")[0].strip()

        # Rate limit key
        key = f"rate_limit:{client_ip}:{request.url.path}"

        apply_headers = True
        try:
            current = await self.redis.get(key)
            if current and int(current) >= self.max_requests:
                return Response(
                    content="Rate limit exceeded",
                    status_code=429,
                    headers={"Retry-After": str(self.window)},
                )

            await self.redis.incr(key)
            await self.redis.expire(key, self.window)
        except Exception as exc:  # noqa: BLE001 - graceful degradation
            logger.warning(
                "Rate limiting middleware degraded to noop due to Redis error: %s",
                exc,
            )
            apply_headers = False

        response = await call_next(request)

        if apply_headers:
            response.headers["X-RateLimit-Limit"] = str(self.max_requests)
            response.headers["X-RateLimit-Window"] = str(self.window)

        return response
