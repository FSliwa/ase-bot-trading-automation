"""
Main FastAPI application powering the ASE trading backend.
Provides programmatic APIs consumed by automation tools and external clients.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
import logging

# Import route modules
from api.auth_routes import auth_router
from api.portfolio_routes import portfolio_router
from api.trading_routes import trading_router
from api.ai_routes import ai_router
from api.api_keys_routes import api_keys_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Trading Platform API",
    description="Backend API for trading automation and external integrations",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS middleware for approved clients
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\\.0\\.0\\.1)(:\\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(portfolio_router)
app.include_router(trading_router)
app.include_router(ai_router)
app.include_router(api_keys_router)

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Trading Platform API",
        "version": "1.0.0",
        "status": "active",
        "timestamp": datetime.now(),
        "docs": "/api/docs",
        "endpoints": {
            "authentication": "/api/auth/*",
            "portfolio": "/api/portfolio/*",
            "trading": "/api/trading/*",
            "ai": "/api/ai/*",
            "api_keys": "/api/keys/*"
        }
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "services": {
            "authentication": "healthy",
            "portfolio": "healthy", 
            "trading": "healthy",
            "ai": "healthy"
        },
        "version": "1.0.0"
    }

# API info endpoint
@app.get("/api")
async def api_info():
    """API information endpoint"""
    return {
        "name": "Trading Platform API",
        "version": "1.0.0",
        "description": "Backend API for trading automation",
        "endpoints": {
            "authentication": {
                "register": "POST /api/register",
                "login": "POST /api/login",
                "logout": "POST /api/logout",
                "profile": "GET /api/users/me",
                "update_profile": "PUT /api/users/me"
            },
            "portfolio": {
                "summary": "GET /api/portfolio/summary",
                "positions": "GET /api/portfolio/positions",
                "transactions": "GET /api/portfolio/transactions",
                "balance": "GET /api/portfolio/balance",
                "performance": "GET /api/portfolio/performance"
            },
            "trading": {
                "market_data": "GET /api/trading/market-data",
                "symbols": "GET /api/trading/symbols",
                "create_order": "POST /api/trading/orders",
                "order_history": "GET /api/trading/orders",
                "order_book": "GET /api/trading/orderbook/{symbol}"
            },
            "ai": {
                "bots": "GET /api/ai/bots",
                "create_bot": "POST /api/ai/bots", 
                "analysis": "GET /api/ai/analysis/{symbol}",
                "predictions": "GET /api/ai/predictions/{symbol}",
                "strategies": "GET /api/ai/strategies"
            }
        },
        "documentation": "/api/docs",
        "timestamp": datetime.now()
    }

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors"""
    logger.error(f"Unhandled exception: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "timestamp": datetime.now().isoformat()
        }
    )

# 404 handler
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 errors"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not found",
            "message": f"Endpoint {request.url.path} not found",
            "timestamp": datetime.now().isoformat()
        }
    )

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting Trading Platform API server...")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8008,
        reload=True,
        access_log=True
    )
