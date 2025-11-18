"""Trading API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import random

from src.domain.entities.user import User
from src.presentation.api.dependencies import get_current_user
from src.infrastructure.audit import audit_logger, AuditAction
from src.infrastructure.ai.gemini_service import GeminiService
from src.infrastructure.external import web_search_service

router = APIRouter(prefix="/api/v2/trading", tags=["trading"])


class PortfolioSummary(BaseModel):
    total_balance: float
    daily_pnl: float
    daily_pnl_percent: float
    active_trades: int
    win_rate: float
    total_trades: int


class TradePosition(BaseModel):
    id: int
    symbol: str
    side: str  # LONG/SHORT
    size: float
    entry_price: float
    current_price: float
    pnl: float
    pnl_percent: float
    status: str
    created_at: datetime


class MarketData(BaseModel):
    symbol: str
    price: float
    change_24h: float
    change_percent: float
    volume: float
    timestamp: datetime


class TradingSettings(BaseModel):
    risk_level: str
    max_position_size: float
    stop_loss_percent: float
    take_profit_percent: float
    auto_trading_enabled: bool
    preferred_pairs: List[str]


class AIInsight(BaseModel):
    symbol: str
    trend: str
    confidence: float
    support_levels: List[float]
    resistance_levels: List[float]
    recommendation: str
    generated_at: datetime


@router.get("/portfolio", response_model=PortfolioSummary)
async def get_portfolio_summary(current_user: User = Depends(get_current_user)):
    """Get user's portfolio summary."""
    
    # Log audit event
    await audit_logger.log_audit_event(
        action=AuditAction.API_ACCESS,
        user_id=current_user.id,
        resource="portfolio_summary"
    )
    
    # In production, this would fetch real data from database
    # For now, return mock data
    return PortfolioSummary(
        total_balance=10000.0 + random.uniform(-500, 1500),
        daily_pnl=random.uniform(-200, 500),
        daily_pnl_percent=random.uniform(-2.0, 5.0),
        active_trades=random.randint(0, 8),
        win_rate=random.uniform(65, 85),
        total_trades=random.randint(50, 200)
    )


@router.get("/positions", response_model=List[TradePosition])
async def get_active_positions(current_user: User = Depends(get_current_user)):
    """Get user's active trading positions."""
    
    await audit_logger.log_audit_event(
        action=AuditAction.API_ACCESS,
        user_id=current_user.id,
        resource="trading_positions"
    )
    
    # Mock data - in production, fetch from database
    symbols = ["BTC/USDT", "ETH/USDT", "ADA/USDT", "DOT/USDT"]
    positions = []
    
    for i, symbol in enumerate(symbols[:random.randint(1, 4)]):
        entry_price = random.uniform(30000, 50000) if "BTC" in symbol else random.uniform(2000, 3000)
        current_price = entry_price * random.uniform(0.95, 1.08)
        size = random.uniform(0.1, 2.0)
        pnl = (current_price - entry_price) * size
        
        positions.append(TradePosition(
            id=i + 1,
            symbol=symbol,
            side=random.choice(["LONG", "SHORT"]),
            size=size,
            entry_price=entry_price,
            current_price=current_price,
            pnl=pnl,
            pnl_percent=(pnl / (entry_price * size)) * 100,
            status="OPEN",
            created_at=datetime.utcnow() - timedelta(hours=random.randint(1, 48))
        ))
    
    return positions


@router.get("/market-data", response_model=List[MarketData])
async def get_market_data(symbols: str = "BTC/USDT,ETH/USDT,ADA/USDT"):
    """Get real-time market data for specified symbols."""
    
    symbol_list = symbols.split(",")
    market_data = []
    
    # Mock market data - in production, fetch from exchange APIs
    base_prices = {
        "BTC/USDT": 43250.0,
        "ETH/USDT": 2650.0,
        "ADA/USDT": 0.45,
        "DOT/USDT": 7.25,
        "LINK/USDT": 14.50,
        "MATIC/USDT": 0.85
    }
    
    for symbol in symbol_list:
        if symbol in base_prices:
            base_price = base_prices[symbol]
            change = random.uniform(-5, 5)
            current_price = base_price * (1 + change / 100)
            
            market_data.append(MarketData(
                symbol=symbol,
                price=current_price,
                change_24h=change,
                change_percent=change,
                volume=random.uniform(1000000, 50000000),
                timestamp=datetime.utcnow()
            ))
    
    return market_data


@router.get("/settings", response_model=TradingSettings)
async def get_trading_settings(current_user: User = Depends(get_current_user)):
    """Get user's trading settings."""
    
    await audit_logger.log_audit_event(
        action=AuditAction.API_ACCESS,
        user_id=current_user.id,
        resource="trading_settings"
    )
    
    # Mock settings - in production, fetch from database
    return TradingSettings(
        risk_level="medium",
        max_position_size=1000.0,
        stop_loss_percent=5.0,
        take_profit_percent=10.0,
        auto_trading_enabled=True,
        preferred_pairs=["BTC/USDT", "ETH/USDT", "ADA/USDT"]
    )


@router.post("/settings")
async def update_trading_settings(
    settings: TradingSettings,
    current_user: User = Depends(get_current_user)
):
    """Update user's trading settings."""
    
    await audit_logger.log_audit_event(
        action=AuditAction.SETTINGS_CHANGE,
        user_id=current_user.id,
        resource="trading_settings",
        details=settings.dict()
    )
    
    # In production, save to database
    # For now, return success
    return {"message": "Settings updated successfully", "settings": settings}


@router.get("/ai-insights/{symbol}", response_model=AIInsight)
async def get_ai_insights(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    """Get AI-powered trading insights for a symbol."""
    
    await audit_logger.log_audit_event(
        action=AuditAction.API_ACCESS,
        user_id=current_user.id,
        resource=f"ai_insights_{symbol}"
    )
    
    try:
        # Use Gemini AI service
        ai_service = GeminiService()
        insights = await ai_service.get_trading_insights(symbol)
        
        if "error" in insights:
            raise HTTPException(
                status_code=503,
                detail=f"AI service unavailable: {insights['error']}"
            )
        
        return AIInsight(
            symbol=symbol,
            trend=insights.get("trend", "neutral"),
            confidence=insights.get("confidence", 0.5),
            support_levels=insights.get("support_levels", []),
            resistance_levels=insights.get("resistance_levels", []),
            recommendation=insights.get("summary", "No recommendation available"),
            generated_at=datetime.utcnow()
        )
        
    except Exception as e:
        await audit_logger.log_audit_event(
            action=AuditAction.API_ACCESS,
            user_id=current_user.id,
            resource=f"ai_insights_{symbol}",
            success=False,
            details={"error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to generate AI insights"
        )


@router.post("/execute-trade")
async def execute_trade(
    trade_data: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """Execute a trading order."""
    
    await audit_logger.log_audit_event(
        action=AuditAction.TRADE_EXECUTE,
        user_id=current_user.id,
        resource="trade_execution",
        details=trade_data
    )
    
    # Validate trade data
    required_fields = ["symbol", "side", "quantity", "order_type"]
    for field in required_fields:
        if field not in trade_data:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required field: {field}"
            )
    
    # In production, execute real trade through exchange API
    # For now, return mock execution
    return {
        "order_id": f"order_{int(datetime.utcnow().timestamp())}",
        "status": "FILLED",
        "symbol": trade_data["symbol"],
        "side": trade_data["side"],
        "quantity": trade_data["quantity"],
        "price": random.uniform(40000, 50000),
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/exchange-status")
async def get_exchange_status(current_user: User = Depends(get_current_user)):
    """Get exchange connection status."""
    
    # Mock exchange status - in production, check real API connections
    exchanges = {
        "binance": {
            "connected": True,
            "api_key_valid": True,
            "last_ping": datetime.utcnow().isoformat(),
            "rate_limit_remaining": 1200,
            "testnet": False
        },
        "coinbase": {
            "connected": False,
            "api_key_valid": None,
            "last_ping": None,
            "rate_limit_remaining": 0,
            "testnet": False
        }
    }
    
    return exchanges


@router.get("/news-sentiment/{symbol}")
async def get_news_sentiment(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    """Get news sentiment analysis for a symbol."""
    
    await audit_logger.log_audit_event(
        action=AuditAction.API_ACCESS,
        user_id=current_user.id,
        resource=f"news_sentiment_{symbol}"
    )
    
    try:
        # Mock news data - in production, fetch from news APIs
        mock_news = [
            f"{symbol} shows strong technical indicators",
            f"Institutional adoption of {symbol} continues to grow",
            f"Market analysts bullish on {symbol} long-term prospects"
        ]
        
        # Use AI service for sentiment analysis
        ai_service = GeminiService()
        sentiment = await ai_service.analyze_market_sentiment(mock_news)
        
        return {
            "symbol": symbol,
            "sentiment": sentiment.get("sentiment", "neutral"),
            "confidence": sentiment.get("confidence", 0.5),
            "key_factors": sentiment.get("key_factors", []),
            "summary": sentiment.get("summary", "No sentiment analysis available"),
            "news_count": len(mock_news),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to analyze news sentiment"
        )


@router.get("/news/{symbol}")
async def get_crypto_news(
    symbol: str,
    limit: int = 10,
    current_user: User = Depends(get_current_user)
):
    """Get cryptocurrency news for a symbol."""
    
    await audit_logger.log_audit_event(
        action=AuditAction.API_ACCESS,
        user_id=current_user.id,
        resource=f"crypto_news_{symbol}"
    )
    
    try:
        news = await web_search_service.search_crypto_news(symbol, limit)
        return {
            "symbol": symbol,
            "news": news,
            "count": len(news),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch crypto news"
        )


@router.get("/market-overview")
async def get_market_overview(current_user: User = Depends(get_current_user)):
    """Get general market overview."""
    
    await audit_logger.log_audit_event(
        action=AuditAction.API_ACCESS,
        user_id=current_user.id,
        resource="market_overview"
    )
    
    try:
        overview = await web_search_service.get_market_overview()
        return overview
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch market overview"
        )


@router.get("/signals/{symbol}")
async def get_trading_signals(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    """Get trading signals for a symbol."""
    
    await audit_logger.log_audit_event(
        action=AuditAction.API_ACCESS,
        user_id=current_user.id,
        resource=f"trading_signals_{symbol}"
    )
    
    try:
        signals = await web_search_service.search_trading_signals(symbol)
        return {
            "symbol": symbol,
            "signals": signals,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch trading signals"
        )


@router.get("/social-sentiment/{symbol}")
async def get_social_sentiment(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    """Get social media sentiment for a symbol."""
    
    await audit_logger.log_audit_event(
        action=AuditAction.API_ACCESS,
        user_id=current_user.id,
        resource=f"social_sentiment_{symbol}"
    )
    
    try:
        sentiment = await web_search_service.get_social_sentiment(symbol)
        return sentiment
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch social sentiment"
        )
