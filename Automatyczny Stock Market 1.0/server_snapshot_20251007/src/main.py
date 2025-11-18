"""Main FastAPI application entrypoint."""

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import time

from src.presentation.api.v2.users import router as user_router
from src.presentation.api.v2.trading import router as trading_router
from src.presentation.api.v2.debug import router as debug_router
from src.presentation.api.v1_compatibility import router as v1_router
from src.presentation.websocket.trading_ws import websocket_endpoint, start_background_tasks
from src.presentation.middleware.security import CSPMiddleware
from src.infrastructure.observability import setup_telemetry, request_counter, request_duration
from src.infrastructure.monitoring import slo_monitor
from opentelemetry import trace

templates = Jinja2Templates(directory="web/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    setup_telemetry(app)
    await start_background_tasks()
    yield
    # Shutdown
    pass


app = FastAPI(
    title="Trading Bot API v2",
    version="2.0.0",
    description="A refactored, secure, and scalable API for the ASE Trading Bot.",
    lifespan=lifespan,
)

# Add Middleware
app.add_middleware(CSPMiddleware)

# Add WAF + Rate Limiting (ACTIVE)
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.security.waf import WAFMiddleware
from src.presentation.middleware.security import RateLimitMiddleware

redis_cache = RedisCache()
app.add_middleware(WAFMiddleware)
app.add_middleware(RateLimitMiddleware, redis_client=redis_cache.redis, max_requests=100, window=60)


@app.middleware("http")
async def track_requests(request: Request, call_next):
    """Track request metrics."""
    start_time = time.time()
    
    # Track request
    request_counter.add(1, {
        "method": request.method,
        "endpoint": request.url.path,
    })
    
    # Process request
    response = await call_next(request)
    
    # Track duration
    duration = time.time() - start_time
    request_duration.record(duration, {
        "method": request.method,
        "endpoint": request.url.path,
        "status_code": response.status_code,
    })
    
    # Record SLO metrics
    await slo_monitor.record_request(
        endpoint=request.url.path,
        status_code=response.status_code,
        duration=duration
    )
    
    # Add trace ID to response headers
    span = trace.get_current_span()
    if span and span.is_recording():
        trace_id = format(span.get_span_context().trace_id, '032x')
        response.headers["X-Trace-ID"] = trace_id
    
    return response
# The RateLimitMiddleware would be added here as well, but requires a Redis client instance.
# Example:
# from src.infrastructure.cache.redis_cache import RedisCache
# from src.presentation.middleware.security import RateLimitMiddleware
# redis_client = RedisCache().redis
# app.add_middleware(RateLimitMiddleware, redis_client=redis_client)


# Mount static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Include API routers
app.include_router(user_router)
app.include_router(trading_router)
app.include_router(debug_router)
app.include_router(v1_router)


@app.get("/health", tags=["health"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}


@app.get("/slo", tags=["monitoring"])
async def slo_dashboard():
    """SLO dashboard endpoint."""
    slo_data = await slo_monitor.get_slo_dashboard_data()
    return slo_data


@app.post("/admin/waf/unblock/{ip}", tags=["admin"])
async def unblock_ip(ip: str):
    """Emergency endpoint to unblock IP (admin only)."""
    # Get WAF instance from middleware stack
    for middleware in app.user_middleware:
        if hasattr(middleware, 'cls') and middleware.cls.__name__ == 'WAFMiddleware':
            waf_instance = middleware.kwargs.get('app') or getattr(middleware, '_instance', None)
            if waf_instance and hasattr(waf_instance, 'unblock_ip'):
                waf_instance.unblock_ip(ip)
                return {"message": f"IP {ip} unblocked successfully"}
    
    return {"error": "WAF middleware not found"}


@app.post("/admin/waf/clear-blocks", tags=["admin"])
async def clear_all_blocks():
    """Emergency endpoint to clear all blocked IPs."""
    # Get WAF instance from middleware stack
    for middleware in app.user_middleware:
        if hasattr(middleware, 'cls') and middleware.cls.__name__ == 'WAFMiddleware':
            waf_instance = getattr(middleware, '_instance', None)
            if waf_instance and hasattr(waf_instance, 'clear_blocked_ips'):
                waf_instance.clear_blocked_ips()
                return {"message": "All blocked IPs cleared"}
    
    return {"error": "WAF middleware not found"}


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the main application page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page."""
    return templates.TemplateResponse("login_dark.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Serve the register page."""
    return templates.TemplateResponse("register_dark.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Serve the dashboard page."""
    return templates.TemplateResponse("dashboard_modern.html", {"request": request})


@app.websocket("/ws")
async def websocket_handler(websocket: WebSocket):
    """WebSocket endpoint for real-time data."""
    await websocket_endpoint(websocket)
