from fastapi import FastAPI

from src.infrastructure.http.rate_limiter import init_rate_limiter
from src.presentation.api.v1 import trial_router
from src.presentation.api.v2.users import router as user_router
from src.presentation.api.v2.trading import router as trading_router
from src.presentation.middleware.security import CSPMiddleware

app = FastAPI(
    title="Trading Bot API v2",
    version="2.0.0",
    description="A refactored, secure, and scalable API for the ASE Trading Bot.",
)

app.add_middleware(CSPMiddleware)
init_rate_limiter(app)

app.include_router(trial_router)
app.include_router(user_router)
app.include_router(trading_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}
