#!/usr/bin/env python3
"""
Enhanced Gemini AI Integration Module with Tavily Web Search
Provides Google Gemini Pro integration with real-time market intelligence
"""

import os
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import google.generativeai as genai
from dataclasses import dataclass

try:
    from dotenv import dotenv_values  # type: ignore
except Exception:  # pragma: no cover
    dotenv_values = None  # lazy fallback if python-dotenv unavailable at runtime

from google.generativeai.types import HarmCategory, HarmBlockThreshold
from .tavily_web_search import TavilyWebSearch, SearchResult

logger = logging.getLogger(__name__)

SUPPORTED_FALLBACK_MODEL = "gemini-1.5-pro"

@dataclass
class MarketIntelligence:
    """Structured market intelligence data"""
    timestamp: datetime
    symbol: str
    news_sentiment: str
    key_events: List[str]
    technical_signals: List[str]
    regulatory_updates: List[str]
    market_context: str
    confidence_score: float

class EnhancedGeminiAnalyzer:
    """Enhanced Google Gemini Pro AI analyzer with web search capabilities"""
    
    def __init__(self):
        """Initialize enhanced Gemini analyzer with API key, model, and web search"""
        # Load API keys
        self.api_key = self._get_api_key("GEMINI_API_KEY")
        self.tavily_api_key = self._get_api_key("TAVILY_API_KEY")
        
        # Configuration
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-pro-latest")
        self.temperature = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))
        self.max_tokens = int(os.getenv("GEMINI_MAX_TOKENS", "4096"))
        self._effective_model = None
        self._daily_budget_cents = int(os.getenv("GEMINI_DAILY_BUDGET_CENTS", "0"))
        self._spent_cents_today = 0
        
        # Initialize components
        self.client = None
        self.web_search = None
        
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not configured - AI analysis disabled")
        else:
            self._initialize_gemini()
        
        if not self.tavily_api_key:
            logger.warning("TAVILY_API_KEY not configured - web search disabled")
        else:
            self.web_search = TavilyWebSearch(self.tavily_api_key)
    
    def _get_api_key(self, key_name: str) -> Optional[str]:
        """Get API key from environment or .env files"""
        # Primary source: environment
        api_key = os.getenv(key_name)
        
        # Fallback: read directly from .env if the env var is not visible under systemd
        if not api_key and dotenv_values is not None:
            try:
                # Prefer absolute path used by systemd unit; fallback to CWD .env
                env_map = dotenv_values("/opt/trading-bot/.env") or dotenv_values(".env") or {}
                api_key = env_map.get(key_name)
            except Exception:  # noqa: BLE001
                # Best-effort fallback only
                pass
        
        return api_key
    
    def _initialize_gemini(self):
        """Initialize Gemini AI client"""
        try:
            genai.configure(api_key=self.api_key)
            
            # Test model availability
            available_models = [m.name for m in genai.list_models()]
            logger.info(f"Available Gemini models: {available_models}")
            
            # Choose best available model
            if f"models/{self.model_name}" in available_models:
                self._effective_model = self.model_name
            elif f"models/{SUPPORTED_FALLBACK_MODEL}" in available_models:
                self._effective_model = SUPPORTED_FALLBACK_MODEL
                logger.warning(f"Requested model {self.model_name} not available, using {SUPPORTED_FALLBACK_MODEL}")
            else:
                logger.error("No supported Gemini model available")
                return
            
            # Initialize model with safety settings
            self.client = genai.GenerativeModel(
                model_name=self._effective_model,
                generation_config=genai.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                    top_p=0.95,
                    top_k=40
                ),
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            )
            
            logger.info(f"Gemini AI initialized successfully with model: {self._effective_model}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Gemini AI: {str(e)}")
            self.client = None
    
    async def analyze_market_with_intelligence(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        technical_indicators: Optional[Dict[str, Any]] = None,
        include_news: bool = True,
        include_sentiment: bool = True,
        include_signals: bool = True
    ) -> Dict[str, Any]:
        """
        Analyze market with comprehensive intelligence from web search
        
        Args:
            symbol: Trading symbol (e.g., "BTC/USDT")
            market_data: Current market data
            technical_indicators: Technical analysis indicators
            include_news: Include news analysis
            include_sentiment: Include sentiment analysis
            include_signals: Include trading signals
            
        Returns:
            Comprehensive market analysis with recommendations
        """
        if not self.client:
            return {"error": "Gemini AI not initialized", "analysis": "fallback_basic"}
        
        try:
            # Gather market intelligence
            intelligence = await self._gather_market_intelligence(
                symbol=symbol,
                include_news=include_news,
                include_sentiment=include_sentiment,
                include_signals=include_signals
            )
            
            # Build comprehensive analysis prompt
            analysis_prompt = self._build_comprehensive_analysis_prompt(
                symbol=symbol,
                market_data=market_data,
                technical_indicators=technical_indicators or {},
                intelligence=intelligence
            )
            
            # Get AI analysis
            response = await self._generate_ai_response(analysis_prompt)
            
            # Parse and structure the response
            analysis_result = self._parse_analysis_response(response, intelligence)
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error in enhanced market analysis: {str(e)}")
            return {
                "error": str(e),
                "analysis": "error",
                "recommendation": "HOLD",
                "confidence": 0.0
            }
    
    async def _gather_market_intelligence(
        self,
        symbol: str,
        include_news: bool = True,
        include_sentiment: bool = True,
        include_signals: bool = True
    ) -> Dict[str, Any]:
        """Gather comprehensive market intelligence using web search"""
        intelligence = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "news": [],
            "sentiment": [],
            "signals": [],
            "regulatory": [],
            "error": None
        }
        
        if not self.web_search:
            logger.warning("Web search not available - proceeding without market intelligence")
            return intelligence
        
        try:
            base_symbol = symbol.split('/')[0] if '/' in symbol else symbol
            
            # Gather news
            if include_news:
                news_results = await self.web_search.search_crypto_news(
                    symbol=base_symbol,
                    max_results=10
                )
                intelligence["news"] = [
                    {
                        "title": r.title,
                        "content": r.content[:300] + "..." if len(r.content) > 300 else r.content,
                        "source": r.source_domain,
                        "score": r.score,
                        "url": r.url
                    } for r in news_results[:5]
                ]
            
            # Gather sentiment analysis
            if include_sentiment:
                sentiment_results = await self.web_search.search_market_sentiment(
                    symbols=[base_symbol],
                    max_results=5
                )
                if base_symbol in sentiment_results:
                    intelligence["sentiment"] = [
                        {
                            "title": r.title,
                            "content": r.content[:200] + "..." if len(r.content) > 200 else r.content,
                            "source": r.source_domain,
                            "url": r.url
                        } for r in sentiment_results[base_symbol][:3]
                    ]
            
            # Gather trading signals
            if include_signals:
                signal_results = await self.web_search.search_trading_signals(
                    symbol=base_symbol
                )
                intelligence["signals"] = [
                    {
                        "title": r.title,
                        "content": r.content[:200] + "..." if len(r.content) > 200 else r.content,
                        "source": r.source_domain,
                        "url": r.url
                    } for r in signal_results[:3]
                ]
            
            # Gather regulatory updates
            regulatory_results = await self.web_search.search_regulatory_news(max_results=3)
            intelligence["regulatory"] = [
                {
                    "title": r.title,
                    "content": r.content[:200] + "..." if len(r.content) > 200 else r.content,
                    "source": r.source_domain,
                    "url": r.url,
                    "score": r.score
                } for r in regulatory_results
            ]
            
        except Exception as e:
            logger.error(f"Error gathering market intelligence: {str(e)}")
            intelligence["error"] = str(e)
        
        return intelligence
    
    def _build_comprehensive_analysis_prompt(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        technical_indicators: Dict[str, Any],
        intelligence: Dict[str, Any]
    ) -> str:
        """Build comprehensive analysis prompt with all available data"""
        
        prompt = f"""
You are an advanced cryptocurrency trading analyst with access to real-time market intelligence.

TRADING SYMBOL: {symbol}
ANALYSIS TIMESTAMP: {datetime.now().isoformat()}

=== MARKET DATA ===
Current Price: ${market_data.get('price', 'N/A')}
24h Change: {market_data.get('change_24h', 'N/A')}%
Volume: {market_data.get('volume', 'N/A')}
Market Cap: {market_data.get('market_cap', 'N/A')}
"""
        
        # Add technical indicators if available
        if technical_indicators:
            prompt += f"\n=== TECHNICAL INDICATORS ===\n"
            for indicator, value in technical_indicators.items():
                prompt += f"{indicator}: {value}\n"
        
        # Add market intelligence
        if intelligence.get('news'):
            prompt += f"\n=== RECENT NEWS ({len(intelligence['news'])} articles) ===\n"
            for i, article in enumerate(intelligence['news'], 1):
                prompt += f"{i}. {article['title']} ({article['source']})\n"
                prompt += f"   Content: {article['content']}\n\n"
        
        if intelligence.get('sentiment'):
            prompt += f"\n=== MARKET SENTIMENT ===\n"
            for i, sentiment in enumerate(intelligence['sentiment'], 1):
                prompt += f"{i}. {sentiment['title']} ({sentiment['source']})\n"
                prompt += f"   Analysis: {sentiment['content']}\n\n"
        
        if intelligence.get('signals'):
            prompt += f"\n=== TRADING SIGNALS ===\n"
            for i, signal in enumerate(intelligence['signals'], 1):
                prompt += f"{i}. {signal['title']} ({signal['source']})\n"
                prompt += f"   Signal: {signal['content']}\n\n"
        
        if intelligence.get('regulatory'):
            prompt += f"\n=== REGULATORY UPDATES ===\n"
            for i, reg in enumerate(intelligence['regulatory'], 1):
                prompt += f"{i}. {reg['title']} ({reg['source']})\n"
                prompt += f"   Update: {reg['content']}\n\n"
        
        # Analysis instructions
        prompt += """
=== ANALYSIS REQUIREMENTS ===

Provide a comprehensive trading analysis considering:
1. Technical indicators and price action
2. Market sentiment from news and social media
3. Recent regulatory developments
4. Trading signals from multiple sources
5. Risk assessment and market context

=== OUTPUT FORMAT ===
Respond with a JSON object containing:

{
  "analysis": {
    "market_sentiment": "bullish|bearish|neutral",
    "technical_outlook": "strong_buy|buy|hold|sell|strong_sell", 
    "risk_level": "low|medium|high|very_high",
    "key_factors": ["factor1", "factor2", "factor3"],
    "price_targets": {
      "support": 0.0,
      "resistance": 0.0,
      "target_24h": 0.0
    }
  },
  "recommendation": {
    "action": "BUY|SELL|HOLD",
    "confidence": 0.85,
    "entry_price": 0.0,
    "stop_loss": 0.0,
    "take_profit": 0.0,
    "position_size": 0.25,
    "timeframe": "short|medium|long"
  },
  "intelligence_summary": {
    "news_impact": "positive|negative|neutral",
    "sentiment_score": 0.75,
    "regulatory_risk": "low|medium|high",
    "technical_strength": 0.80
  },
  "reasoning": "Detailed explanation of the analysis and recommendation"
}

Important: Base your analysis on ALL available data including real-time market intelligence, technical indicators, and current market conditions.
"""
        
        return prompt
    
    async def _generate_ai_response(self, prompt: str) -> str:
        """Generate AI response using Gemini"""
        try:
            if self.client is not None:
                response = await asyncio.to_thread(
                    self.client.generate_content,
                    prompt
                )
                
                if hasattr(response, 'text') and response.text:
                    return response.text
                else:
                    logger.error("Empty response from Gemini AI")
                    return "{\"error\": \"Empty AI response\"}"
            else:
                return "{\"error\": \"Gemini client not initialized\"}"
                
        except Exception as e:
            logger.error(f"Error generating AI response: {str(e)}")
            return f"{{\"error\": \"{str(e)}\"}}"
    
    def _parse_analysis_response(
        self,
        response: str,
        intelligence: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse and structure AI analysis response"""
        try:
            # Try to extract JSON from response
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            else:
                # Look for JSON-like structure
                start = response.find('{')
                end = response.rfind('}') + 1
                json_str = response[start:end] if start != -1 and end != 0 else response
            
            # Parse JSON
            analysis = json.loads(json_str)
            
            # Add metadata
            analysis["metadata"] = {
                "timestamp": datetime.now().isoformat(),
                "model_used": self._effective_model,
                "intelligence_sources": {
                    "news_articles": len(intelligence.get('news', [])),
                    "sentiment_sources": len(intelligence.get('sentiment', [])),
                    "trading_signals": len(intelligence.get('signals', [])),
                    "regulatory_updates": len(intelligence.get('regulatory', []))
                },
                "web_search_available": self.web_search is not None
            }
            
            return analysis
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {str(e)}")
            # Return fallback analysis
            return {
                "analysis": {
                    "market_sentiment": "neutral",
                    "technical_outlook": "hold",
                    "risk_level": "medium",
                    "key_factors": ["Unable to parse AI response"],
                    "price_targets": {"support": 0.0, "resistance": 0.0, "target_24h": 0.0}
                },
                "recommendation": {
                    "action": "HOLD",
                    "confidence": 0.5,
                    "reasoning": f"Analysis parsing failed: {str(e)}"
                },
                "error": f"JSON parsing error: {str(e)}",
                "raw_response": response[:500] + "..." if len(response) > 500 else response
            }
        except Exception as e:
            logger.error(f"Error parsing analysis response: {str(e)}")
            return {
                "error": str(e),
                "analysis": "parsing_error",
                "recommendation": "HOLD",
                "confidence": 0.0
            }
    
    async def get_quick_market_summary(self, symbols: List[str]) -> Dict[str, Any]:
        """Get quick market summary for multiple symbols"""
        if not self.web_search:
            return {"error": "Web search not available"}
        
        try:
            # Get market intelligence summary
            intelligence = await self.web_search.get_market_intelligence_summary(
                symbols=symbols,
                include_sentiment=True,
                include_regulatory=True
            )
            
            # Create summary prompt
            prompt = f"""
Based on the following market intelligence, provide a brief market summary:

Symbols analyzed: {', '.join(symbols)}
Timestamp: {intelligence.get('timestamp')}

News Summary: {len(intelligence.get('news_summary', {}).get('general', []))} articles
Regulatory Updates: {len(intelligence.get('regulatory_updates', []))} updates

Provide a JSON response with:
{{
  "market_overview": "Brief market outlook",
  "key_themes": ["theme1", "theme2"],
  "risk_factors": ["risk1", "risk2"],
  "opportunities": ["opp1", "opp2"],
  "overall_sentiment": "bullish|bearish|neutral"
}}
"""
            
            if self.client:
                response = await self._generate_ai_response(prompt)
                try:
                    summary = json.loads(response)
                    summary["intelligence_data"] = intelligence
                    return summary
                except:
                    pass
            
            # Fallback summary
            return {
                "market_overview": "Market intelligence gathered but AI analysis unavailable",
                "intelligence_data": intelligence,
                "web_search_active": True
            }
            
        except Exception as e:
            logger.error(f"Error generating market summary: {str(e)}")
            return {"error": str(e)}
    
    def is_available(self) -> bool:
        """Check if analyzer is properly initialized"""
        return self.client is not None
    
    def has_web_search(self) -> bool:
        """Check if web search is available"""
        return self.web_search is not None

# Convenience instance
enhanced_gemini_analyzer = EnhancedGeminiAnalyzer()

# Backwards compatibility
GeminiAnalyzer = EnhancedGeminiAnalyzer

# Export main functions
async def analyze_market_with_intelligence(
    symbol: str,
    market_data: Dict[str, Any],
    technical_indicators: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Convenience function for enhanced market analysis"""
    return await enhanced_gemini_analyzer.analyze_market_with_intelligence(
        symbol=symbol,
        market_data=market_data,
        technical_indicators=technical_indicators
    )

async def get_market_summary(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """Convenience function for market summary"""
    symbols = symbols or ["BTC", "ETH"]
    return await enhanced_gemini_analyzer.get_quick_market_summary(symbols)

# Example usage
if __name__ == "__main__":
    async def main():
        analyzer = EnhancedGeminiAnalyzer()
        
        if analyzer.is_available():
            # Test market analysis
            market_data = {
                "price": 45000,
                "change_24h": 2.5,
                "volume": 1000000000,
                "market_cap": 900000000000
            }
            
            analysis = await analyzer.analyze_market_with_intelligence(
                symbol="BTC/USDT",
                market_data=market_data
            )
            
            print("Enhanced Market Analysis:")
            print(json.dumps(analysis, indent=2))
            
        # Test market summary
        summary = await analyzer.get_quick_market_summary(["BTC", "ETH"])
        print("\nMarket Summary:")
        print(json.dumps(summary, indent=2))
    
    # Run example
    asyncio.run(main())
