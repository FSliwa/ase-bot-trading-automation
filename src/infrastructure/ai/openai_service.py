"""OpenAI Service as Alternative to Gemini"""

import os
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime

from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class OpenAIService:
    """OpenAI service for AI insights - fallback when Gemini is not available."""
    
    def __init__(self):
        self.cache = RedisCache()
        self.model_name = "gpt-3.5-turbo"
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.daily_budget_usd = 10.0
        self.cost_per_1k_tokens = 0.002  # GPT-3.5 pricing
        
    async def get_trading_insights(self, symbol: str, timeframe: str = "1d") -> Dict[str, Any]:
        """Get trading insights using mock data (OpenAI integration placeholder)."""
        
        # Check cache first
        cache_key = f"ai:insights:{symbol}:{timeframe}"
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            return cached_result
            
        # Generate mock insights
        insights = {
            "symbol": symbol,
            "timeframe": timeframe,
            "trend": self._analyze_trend(symbol),
            "confidence": 0.75,
            "support_levels": self._calculate_support_levels(symbol),
            "resistance_levels": self._calculate_resistance_levels(symbol),
            "indicators": {
                "rsi": 55.2,
                "macd": {"signal": "bullish", "strength": 0.6},
                "moving_averages": {
                    "ma20": 45200,
                    "ma50": 44800,
                    "ma200": 43500
                }
            },
            "sentiment": {
                "overall": "neutral-positive",
                "news_sentiment": 0.2,
                "social_sentiment": 0.4,
                "technical_sentiment": 0.1
            },
            "recommendation": self._generate_recommendation(symbol),
            "risk_assessment": {
                "volatility": "medium",
                "risk_score": 6.5,
                "stop_loss_suggestion": -3.5,
                "take_profit_suggestion": 7.0
            },
            "generated_at": datetime.utcnow().isoformat()
        }
        
        # Cache for 15 minutes
        await self.cache.set(cache_key, insights, ttl=900)
        
        return insights
        
    def _analyze_trend(self, symbol: str) -> str:
        """Analyze trend based on symbol (mock implementation)."""
        trends = ["bullish", "bearish", "neutral", "consolidating"]
        # Simple hash-based selection for consistency
        index = hash(symbol + str(datetime.utcnow().date())) % len(trends)
        return trends[index]
        
    def _calculate_support_levels(self, symbol: str) -> List[float]:
        """Calculate support levels (mock implementation)."""
        base_price = 45000 if "BTC" in symbol else 3000 if "ETH" in symbol else 100
        return [
            base_price * 0.95,
            base_price * 0.92,
            base_price * 0.88
        ]
        
    def _calculate_resistance_levels(self, symbol: str) -> List[float]:
        """Calculate resistance levels (mock implementation)."""
        base_price = 45000 if "BTC" in symbol else 3000 if "ETH" in symbol else 100
        return [
            base_price * 1.03,
            base_price * 1.06,
            base_price * 1.10
        ]
        
    def _generate_recommendation(self, symbol: str) -> str:
        """Generate trading recommendation (mock implementation)."""
        recommendations = [
            f"Consider taking partial profits on {symbol} as it approaches resistance levels.",
            f"Hold {symbol} position. Current trend shows healthy consolidation.",
            f"Monitor {symbol} closely. Key support levels are being tested.",
            f"Accumulate {symbol} on dips. Long-term trend remains positive.",
            f"Reduce exposure to {symbol}. Short-term weakness detected."
        ]
        index = hash(symbol + str(datetime.utcnow().hour)) % len(recommendations)
        return recommendations[index]
        
    async def analyze_sentiment(self, news_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze sentiment from news items."""
        if not news_items:
            return {
                "overall_sentiment": 0,
                "sentiment_label": "neutral",
                "confidence": 0.5,
                "summary": "No news data available for analysis."
            }
            
        # Mock sentiment analysis
        positive_keywords = ["surge", "bullish", "growth", "adoption", "institutional", "breakthrough"]
        negative_keywords = ["crash", "bearish", "decline", "regulatory", "ban", "hack"]
        
        positive_count = 0
        negative_count = 0
        
        for item in news_items:
            text = (item.get("title", "") + " " + item.get("summary", "")).lower()
            positive_count += sum(1 for keyword in positive_keywords if keyword in text)
            negative_count += sum(1 for keyword in negative_keywords if keyword in text)
            
        total = positive_count + negative_count
        if total == 0:
            sentiment_score = 0
        else:
            sentiment_score = (positive_count - negative_count) / total
            
        sentiment_label = "positive" if sentiment_score > 0.2 else "negative" if sentiment_score < -0.2 else "neutral"
        
        return {
            "overall_sentiment": sentiment_score,
            "sentiment_label": sentiment_label,
            "confidence": min(0.9, 0.5 + (total / 20)),  # Confidence increases with more data
            "summary": f"Analysis of {len(news_items)} news items shows {sentiment_label} market sentiment.",
            "positive_mentions": positive_count,
            "negative_mentions": negative_count
        }
        
    async def generate_trading_strategy(self, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        """Generate personalized trading strategy."""
        risk_level = user_profile.get("risk_level", "medium")
        preferred_pairs = user_profile.get("preferred_pairs", ["BTC/USDT"])
        
        strategies = {
            "low": {
                "name": "Conservative Portfolio",
                "allocation": {"BTC": 0.6, "ETH": 0.3, "Stablecoins": 0.1},
                "rebalance_frequency": "monthly",
                "stop_loss": -5,
                "take_profit": 10,
                "max_position_size": 0.1
            },
            "medium": {
                "name": "Balanced Growth",
                "allocation": {"BTC": 0.4, "ETH": 0.3, "Altcoins": 0.2, "Stablecoins": 0.1},
                "rebalance_frequency": "bi-weekly",
                "stop_loss": -7,
                "take_profit": 15,
                "max_position_size": 0.15
            },
            "high": {
                "name": "Aggressive Trading",
                "allocation": {"BTC": 0.3, "ETH": 0.3, "Altcoins": 0.35, "Stablecoins": 0.05},
                "rebalance_frequency": "weekly",
                "stop_loss": -10,
                "take_profit": 25,
                "max_position_size": 0.25
            }
        }
        
        strategy = strategies.get(risk_level, strategies["medium"])
        strategy["preferred_pairs"] = preferred_pairs
        strategy["generated_at"] = datetime.utcnow().isoformat()
        
        return strategy


# Singleton instance
openai_service = OpenAIService()
