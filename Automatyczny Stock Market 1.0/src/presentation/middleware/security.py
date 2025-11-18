import secrets
from typing import Any, Dict, List, Optional


class CSPMiddleware(BaseHTTPMiddleware):
    """Middleware to add Content Security Policy headers."""
    
    def __init__(self, app: Any, config: Optional[Dict[str, List[str]]] = None):
        """Initialize CSP middleware with configuration."""
        super().__init__(app)
        self.config = config or self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, List[str]]:
        """Get default CSP configuration."""
        return {
            'default-src': [],
            'script-src': [],
            'style-src': [],
            'img-src': [],
            'font-src': [],
            'connect-src': [],
            'object-src': [],
            'media-src': [],
            'frame-src': [],
            'sandbox': [],
            'report-uri': [],
            'upgrade-insecure-requests': []
        }
    
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Add CSP headers to response."""
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce
        
        response = await call_next(request)
        
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting to prevent DoS attacks."""
    
    def __init__(self, app: Any, redis_client: Any, max_requests: int = 100, window: int = 60):
        """Initialize rate limit middleware."""
        super().__init__(app)
        self.redis = redis_client
        self.max_requests = max_requests
        self.window = window
    
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Check rate limits before processing request."""
        client_ip = request.client.host if request.client else "127.0.0.1"
        if request.headers.get("X-Forwarded-For"):
            client_ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        
        key = f"rate_limit:{client_ip}:{request.url.path}"
        
        # Rate limit key
