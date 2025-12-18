"""
API Package for Trading Platform
Contains all API route modules for the FastAPI backend
"""

__version__ = "1.0.0"
__author__ = "Trading Platform Team"

# Import all route modules for easy access
from .auth_routes import auth_router
from .portfolio_routes import portfolio_router  
from .trading_routes import trading_router
from .ai_routes import ai_router

__all__ = [
    "auth_router",
    "portfolio_router", 
    "trading_routes",
    "ai_router"
]
