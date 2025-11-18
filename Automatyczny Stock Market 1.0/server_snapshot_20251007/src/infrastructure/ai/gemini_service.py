"""Google Gemini AI service integration."""

import os
import asyncio
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
try:
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.config import get_settings

logger = get_logger(__name__)
settings = get_settings()


class GeminiService:
    """Google Gemini AI service for trading insights."""
    
    def __init__(self):
        self.cache = RedisCache()
        self.daily_budget = settings.ai_daily_budget_usd
        self.daily_usage = 0
        self.model_name = "gemini-1.5-pro"
        self.setup_client()
        
    def setup_client(self):
        """Initialize Gemini client."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not found - AI features disabled")
            self.client = None
            return
            
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                }
            )
            # Test the API key with a simple request
            test_response = self.model.generate_content("Test")
            logger.info(f"Gemini API key validated successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self.model = None
        logger.info("Gemini AI client initialized")

    async def get_trading_insights(self, symbol: str, timeframe: str = "1d") -> Dict[str, Any]:
        """Get AI-powered trading insights for a symbol."""
        if not self.model:
            return {"error": "AI service not available"}
            
        # Check cache first
        cache_key = f"ai:insights:{symbol}:{timeframe}"
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            logger.info(f"Cache hit for AI insights: {symbol}")
            return cached_result
            
        # Check daily budget
        if not await self.check_budget():
            return {"error": "Daily AI budget exceeded"}
            
        try:
            # Prepare market data context (would fetch real data in production)
            market_context = await self.get_market_context(symbol)
            
            prompt = self.build_trading_prompt(symbol, market_context, timeframe)
            
            # Generate insights
            response = await self.generate_content(prompt)
            
            if response:
                # Parse and structure response
                insights = self.parse_trading_response(response)
                
                # Cache for 15 minutes
                await self.cache.set(cache_key, insights, ttl=900)
                
                # Track usage
                await self.track_usage(len(prompt) + len(response))
                
                return insights
            else:
                return {"error": "Failed to generate insights"}
                
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return {"error": "AI service temporarily unavailable"}

    async def analyze_market_sentiment(self, news_data: List[str]) -> Dict[str, Any]:
        """Analyze market sentiment from news data."""
        if not self.model or not news_data:
            return {"sentiment": "neutral", "confidence": 0.5}
            
        # Check cache
        news_hash = hash(str(sorted(news_data)))
        cache_key = f"ai:sentiment:{news_hash}"
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            return cached_result
            
        if not await self.check_budget():
            return {"error": "Daily AI budget exceeded"}
            
        try:
            prompt = f"""
            Analyze the market sentiment from the following cryptocurrency news headlines.
            Provide a JSON response with sentiment (bullish/bearish/neutral) and confidence (0-1).
            
            News headlines:
            {json.dumps(news_data, indent=2)}
            
            Response format:
            {{
                "sentiment": "bullish|bearish|neutral",
                "confidence": 0.85,
                "key_factors": ["factor1", "factor2"],
                "summary": "Brief explanation"
            }}
            """
            
            response = await self.generate_content(prompt)
            
            if response:
                try:
                    sentiment_data = json.loads(response)
                    # Cache for 30 minutes
                    await self.cache.set(cache_key, sentiment_data, ttl=1800)
                    await self.track_usage(len(prompt) + len(response))
                    return sentiment_data
                except json.JSONDecodeError:
                    logger.error("Failed to parse sentiment response")
                    return {"sentiment": "neutral", "confidence": 0.5}
            
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            
        return {"sentiment": "neutral", "confidence": 0.5}

    async def generate_trading_strategy(self, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        """Generate personalized trading strategy."""
        if not self.model:
            return {"error": "AI service not available"}
            
        cache_key = f"ai:strategy:{user_profile.get('id', 'anonymous')}"
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            return cached_result
            
        if not await self.check_budget():
            return {"error": "Daily AI budget exceeded"}
            
        try:
            # Sanitize user data (remove PII)
            safe_profile = self.sanitize_user_data(user_profile)
            
            prompt = f"""
            Generate a personalized cryptocurrency trading strategy based on user profile.
            Focus on risk management and realistic expectations.
            
            User Profile (anonymized):
            - Experience Level: {safe_profile.get('experience', 'beginner')}
            - Risk Tolerance: {safe_profile.get('risk_tolerance', 'medium')}
            - Investment Horizon: {safe_profile.get('horizon', 'medium-term')}
            - Portfolio Size Category: {safe_profile.get('portfolio_size', 'small')}
            
            Provide strategy in JSON format with specific, actionable recommendations.
            """
            
            response = await self.generate_content(prompt)
            
            if response:
                try:
                    strategy = json.loads(response)
                    # Cache for 24 hours
                    await self.cache.set(cache_key, strategy, ttl=86400)
                    await self.track_usage(len(prompt) + len(response))
                    return strategy
                except json.JSONDecodeError:
                    logger.error("Failed to parse strategy response")
                    
        except Exception as e:
            logger.error(f"Strategy generation error: {e}")
            
        return {"error": "Failed to generate strategy"}

    async def generate_content(self, prompt: str) -> Optional[str]:
        """Generate content using Gemini API with safety measures."""
        try:
            # Add safety preamble
            safe_prompt = f"""
            You are a professional financial advisor AI. Provide helpful, accurate information while:
            - Never giving specific financial advice
            - Always recommending users consult financial advisors
            - Focusing on education and general market analysis
            - Being transparent about limitations and risks
            
            User Query: {prompt}
            """
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                safe_prompt,
                generation_config={
                    "temperature": settings.ai_temperature,
                    "max_output_tokens": settings.ai_max_tokens,
                }
            )
            
            return response.text if response else None
            
        except Exception as e:
            logger.error(f"Content generation error: {e}")
            return None

    def build_trading_prompt(self, symbol: str, market_data: Dict, timeframe: str) -> str:
        """Build trading analysis prompt."""
        return f"""
        Analyze the cryptocurrency {symbol} for trading insights.
        
        Market Data:
        - Current Price: ${market_data.get('price', 'N/A')}
        - 24h Change: {market_data.get('change_24h', 'N/A')}%
        - Volume: ${market_data.get('volume', 'N/A')}
        - Market Cap: ${market_data.get('market_cap', 'N/A')}
        - Timeframe: {timeframe}
        
        Provide analysis in JSON format:
        {{
            "trend": "bullish|bearish|neutral",
            "confidence": 0.75,
            "support_levels": [price1, price2],
            "resistance_levels": [price3, price4],
            "risk_assessment": "low|medium|high",
            "key_factors": ["factor1", "factor2"],
            "disclaimer": "Educational purposes only"
        }}
        """

    async def get_market_context(self, symbol: str) -> Dict[str, Any]:
        """Get market context for the symbol."""
        # In production, this would fetch real market data
        return {
            "price": 43250.00,
            "change_24h": 2.34,
            "volume": 28500000000,
            "market_cap": 850000000000
        }

    def parse_trading_response(self, response: str) -> Dict[str, Any]:
        """Parse and validate trading response."""
        try:
            data = json.loads(response)
            
            # Validate required fields
            required_fields = ["trend", "confidence", "risk_assessment"]
            for field in required_fields:
                if field not in data:
                    data[field] = "unknown"
                    
            # Ensure confidence is between 0 and 1
            if "confidence" in data:
                data["confidence"] = max(0, min(1, float(data["confidence"])))
                
            # Add timestamp
            data["generated_at"] = datetime.utcnow().isoformat()
            data["model"] = self.model_name
            
            return data
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse trading response: {e}")
            return {
                "trend": "neutral",
                "confidence": 0.5,
                "risk_assessment": "medium",
                "error": "Failed to parse AI response"
            }

    def sanitize_user_data(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove PII from user data before sending to AI."""
        safe_data = {}
        
        # Only include non-PII fields
        safe_fields = [
            'experience_level', 'risk_tolerance', 'investment_horizon',
            'portfolio_size_category', 'trading_style', 'preferred_assets'
        ]
        
        for field in safe_fields:
            if field in user_data:
                safe_data[field] = user_data[field]
                
        return safe_data

    async def check_budget(self) -> bool:
        """Check if daily AI budget is not exceeded."""
        today = datetime.utcnow().date().isoformat()
        usage_key = f"ai:usage:{today}"
        
        daily_usage = await self.cache.get(usage_key) or 0
        return float(daily_usage) < self.daily_budget

    async def track_usage(self, tokens_used: int):
        """Track AI usage for budget management."""
        today = datetime.utcnow().date().isoformat()
        usage_key = f"ai:usage:{today}"
        
        # Estimate cost (rough approximation)
        estimated_cost = tokens_used * 0.00001  # $0.00001 per token
        
        current_usage = await self.cache.get(usage_key) or 0
        new_usage = float(current_usage) + estimated_cost
        
        # Cache until end of day
        await self.cache.set(usage_key, new_usage, ttl=86400)
        
        logger.info(f"AI usage: ${new_usage:.4f} / ${self.daily_budget} daily budget")

    async def get_usage_stats(self) -> Dict[str, Any]:
        """Get current AI usage statistics."""
        today = datetime.utcnow().date().isoformat()
        usage_key = f"ai:usage:{today}"
        
        daily_usage = await self.cache.get(usage_key) or 0
        
        return {
            "daily_usage_usd": float(daily_usage),
            "daily_budget_usd": self.daily_budget,
            "budget_remaining": self.daily_budget - float(daily_usage),
            "usage_percentage": (float(daily_usage) / self.daily_budget) * 100
        }
