"""
Advanced AI Analysis Engine with Multi-Model Support
Integrates multiple AI models for comprehensive market analysis and trading signals.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import numpy as np
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class AIModel(str, Enum):
    """Available AI models"""
    GPT_4 = "gpt-4"
    GPT_4_TURBO = "gpt-4-turbo"
    GPT_5_PRO = "gpt-5-pro"
    CLAUDE_3 = "claude-3"
    GEMINI_PRO = "gemini-pro"
    LOCAL_LLAMA = "local-llama"

class AnalysisType(str, Enum):
    """Types of AI analysis"""
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    SENTIMENT = "sentiment"
    NEWS = "news"
    PATTERN = "pattern"
    RISK = "risk"
    PORTFOLIO = "portfolio"

class SignalStrength(str, Enum):
    """Signal strength levels"""
    VERY_WEAK = "very_weak"
    WEAK = "weak"
    NEUTRAL = "neutral"
    STRONG = "strong"
    VERY_STRONG = "very_strong"

@dataclass
class AISignal:
    """AI trading signal structure"""
    symbol: str
    action: str  # buy, sell, hold
    strength: SignalStrength
    confidence: float  # 0-100
    price_target: Optional[float]
    stop_loss: Optional[float]
    time_horizon: str  # short, medium, long
    reasoning: str
    model_used: AIModel
    analysis_type: AnalysisType
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "strength": self.strength.value,
            "confidence": self.confidence,
            "price_target": self.price_target,
            "stop_loss": self.stop_loss,
            "time_horizon": self.time_horizon,
            "reasoning": self.reasoning,
            "model_used": self.model_used.value,
            "analysis_type": self.analysis_type.value,
            "timestamp": self.timestamp.isoformat()
        }

class MarketDataProcessor:
    """Processes and prepares market data for AI analysis"""
    
    def __init__(self):
        self.data_cache = {}
        self.cache_duration = 300  # 5 minutes
    
    def get_technical_indicators(self, symbol: str, timeframe: str = "1h") -> Dict[str, Any]:
        """Calculate technical indicators for AI analysis"""
        # This would integrate with your existing technical analysis
        # For now, returning mock data
        return {
            "rsi": 65.5,
            "macd": {"value": 0.5, "signal": 0.3, "histogram": 0.2},
            "bollinger_bands": {"upper": 52000, "middle": 50000, "lower": 48000},
            "moving_averages": {
                "sma_20": 49500,
                "sma_50": 48800,
                "ema_12": 50200,
                "ema_26": 49100
            },
            "volume": {
                "current": 150000,
                "average_20": 120000,
                "trend": "increasing"
            },
            "support_resistance": {
                "support": [48500, 47000, 45500],
                "resistance": [52000, 53500, 55000]
            }
        }
    
    def get_market_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Get market sentiment data"""
        return {
            "fear_greed_index": 45,
            "social_sentiment": 0.65,
            "news_sentiment": 0.55,
            "whale_activity": "moderate",
            "funding_rates": -0.001,
            "open_interest": "increasing"
        }
    
    def get_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """Get fundamental analysis data"""
        return {
            "market_cap": 1200000000000,
            "trading_volume_24h": 25000000000,
            "price_change_24h": 2.5,
            "price_change_7d": -1.2,
            "price_change_30d": 15.8,
            "dominance": 45.2,
            "correlation_sp500": 0.65,
            "network_activity": "high"
        }

class AdvancedAIEngine:
    """Advanced AI analysis engine with multi-model support"""
    
    def __init__(self):
        self.data_processor = MarketDataProcessor()
        self.models_config = {
            AIModel.GPT_5_PRO: {
                "api_key": os.getenv("OPENAI_API_KEY"),
                "model_name": "gpt-4o",  # Fallback until GPT-5 is available
                "max_tokens": 2000,
                "temperature": 0.3,
                "specialties": ["technical", "fundamental", "sentiment"]
            },
            AIModel.GPT_4_TURBO: {
                "api_key": os.getenv("OPENAI_API_KEY"),
                "model_name": "gpt-4-turbo",
                "max_tokens": 1500,
                "temperature": 0.2,
                "specialties": ["pattern", "risk"]
            },
            AIModel.CLAUDE_3: {
                "api_key": os.getenv("ANTHROPIC_API_KEY"),
                "model_name": "claude-3-opus",
                "max_tokens": 1500,
                "temperature": 0.3,
                "specialties": ["fundamental", "news"]
            }
        }
        
        # Analysis templates for different models
        self.analysis_prompts = {
            AnalysisType.TECHNICAL: """
            As an expert crypto technical analyst, analyze the following data for {symbol}:
            
            Technical Indicators:
            {technical_data}
            
            Current Price: ${current_price}
            
            Please provide:
            1. Technical analysis summary
            2. Key support/resistance levels
            3. Trading recommendation (buy/sell/hold)
            4. Price targets and stop-loss levels
            5. Confidence level (0-100)
            6. Time horizon (short/medium/long term)
            
            Format your response as JSON with clear reasoning.
            """,
            
            AnalysisType.SENTIMENT: """
            As a market sentiment expert, analyze the following sentiment data for {symbol}:
            
            Sentiment Data:
            {sentiment_data}
            
            Market Data:
            {market_data}
            
            Please provide:
            1. Overall market sentiment assessment
            2. Key sentiment drivers
            3. Impact on price direction
            4. Recommendation based on sentiment
            5. Confidence level (0-100)
            
            Format your response as JSON.
            """,
            
            AnalysisType.FUNDAMENTAL: """
            As a fundamental analyst, evaluate {symbol} based on:
            
            Fundamental Data:
            {fundamental_data}
            
            Technical Context:
            {technical_data}
            
            Please provide:
            1. Fundamental health assessment
            2. Key metrics analysis
            3. Long-term outlook
            4. Fair value estimation
            5. Investment recommendation
            6. Confidence level (0-100)
            
            Format your response as JSON.
            """
        }
    
    async def analyze_symbol(self, symbol: str, analysis_types: List[AnalysisType] = None, models: List[AIModel] = None) -> List[AISignal]:
        """Comprehensive multi-model analysis of a symbol"""
        if analysis_types is None:
            analysis_types = [AnalysisType.TECHNICAL, AnalysisType.SENTIMENT]
        
        if models is None:
            models = [AIModel.GPT_5_PRO]
        
        signals = []
        
        # Gather market data
        technical_data = self.data_processor.get_technical_indicators(symbol)
        sentiment_data = self.data_processor.get_market_sentiment(symbol)
        fundamental_data = self.data_processor.get_fundamental_data(symbol)
        current_price = technical_data.get("current_price", 50000)
        
        # Run analysis with each model and analysis type
        for model in models:
            for analysis_type in analysis_types:
                try:
                    signal = await self._run_analysis(
                        symbol, model, analysis_type,
                        technical_data, sentiment_data, fundamental_data, current_price
                    )
                    if signal:
                        signals.append(signal)
                        
                except Exception as e:
                    logger.error(f"Error in {model.value} {analysis_type.value} analysis: {e}")
        
        return signals
    
    async def _run_analysis(self, symbol: str, model: AIModel, analysis_type: AnalysisType,
                           technical_data: Dict, sentiment_data: Dict, fundamental_data: Dict, current_price: float) -> Optional[AISignal]:
        """Run specific analysis with given model"""
        try:
            # Prepare prompt based on analysis type
            prompt = self._prepare_prompt(analysis_type, symbol, technical_data, sentiment_data, fundamental_data, current_price)
            
            # Get AI response
            response = await self._query_ai_model(model, prompt)
            
            if response:
                # Parse response and create signal
                signal = self._parse_ai_response(response, symbol, model, analysis_type)
                return signal
            
            return None
            
        except Exception as e:
            logger.error(f"Error running {model.value} analysis: {e}")
            return None
    
    def _prepare_prompt(self, analysis_type: AnalysisType, symbol: str,
                       technical_data: Dict, sentiment_data: Dict, fundamental_data: Dict, current_price: float) -> str:
        """Prepare analysis prompt for AI model"""
        prompt_template = self.analysis_prompts.get(analysis_type, "")
        
        if analysis_type == AnalysisType.TECHNICAL:
            return prompt_template.format(
                symbol=symbol,
                technical_data=json.dumps(technical_data, indent=2),
                current_price=current_price
            )
        elif analysis_type == AnalysisType.SENTIMENT:
            return prompt_template.format(
                symbol=symbol,
                sentiment_data=json.dumps(sentiment_data, indent=2),
                market_data=json.dumps({"price": current_price, "volume": technical_data.get("volume", {})}, indent=2)
            )
        elif analysis_type == AnalysisType.FUNDAMENTAL:
            return prompt_template.format(
                symbol=symbol,
                fundamental_data=json.dumps(fundamental_data, indent=2),
                technical_data=json.dumps(technical_data, indent=2)
            )
        
        return prompt_template
    
    async def _query_ai_model(self, model: AIModel, prompt: str) -> Optional[str]:
        """Query specific AI model"""
        try:
            if model in [AIModel.GPT_4, AIModel.GPT_4_TURBO, AIModel.GPT_5_PRO]:
                return await self._query_openai(model, prompt)
            elif model == AIModel.CLAUDE_3:
                return await self._query_claude(prompt)
            elif model == AIModel.GEMINI_PRO:
                return await self._query_gemini(prompt)
            else:
                logger.warning(f"Model {model.value} not implemented")
                return None
                
        except Exception as e:
            logger.error(f"Error querying {model.value}: {e}")
            return None
    
    async def _query_openai(self, model: AIModel, prompt: str) -> Optional[str]:
        """Query OpenAI models"""
        try:
            from openai import AsyncOpenAI
            
            config = self.models_config[model]
            api_key = config["api_key"]
            
            if not api_key:
                logger.warning("OpenAI API key not configured")
                return None
            
            client = AsyncOpenAI(api_key=api_key)
            
            response = await client.chat.completions.create(
                model=config["model_name"],
                messages=[
                    {"role": "system", "content": "You are an expert financial analyst. Provide analysis in JSON format."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=config["max_tokens"],
                temperature=config["temperature"]
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return None
    
    async def _query_claude(self, prompt: str) -> Optional[str]:
        """Query Claude API"""
        # Placeholder for Claude integration
        logger.info("Claude integration not yet implemented")
        return None
    
    async def _query_gemini(self, prompt: str) -> Optional[str]:
        """Query Gemini API"""
        # Placeholder for Gemini integration
        logger.info("Gemini integration not yet implemented")
        return None
    
    def _parse_ai_response(self, response: str, symbol: str, model: AIModel, analysis_type: AnalysisType) -> Optional[AISignal]:
        """Parse AI response and create trading signal"""
        try:
            # Try to parse JSON response
            try:
                data = json.loads(response)
            except:
                # If not JSON, extract key information from text
                data = self._extract_from_text(response)
            
            # Extract signal components
            action = self._extract_action(data)
            confidence = self._extract_confidence(data)
            strength = self._determine_strength(confidence, data)
            price_target = self._extract_price_target(data)
            stop_loss = self._extract_stop_loss(data)
            time_horizon = self._extract_time_horizon(data)
            reasoning = self._extract_reasoning(data, response)
            
            return AISignal(
                symbol=symbol,
                action=action,
                strength=strength,
                confidence=confidence,
                price_target=price_target,
                stop_loss=stop_loss,
                time_horizon=time_horizon,
                reasoning=reasoning,
                model_used=model,
                analysis_type=analysis_type,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Error parsing AI response: {e}")
            return None
    
    def _extract_action(self, data: Dict) -> str:
        """Extract trading action from AI response"""
        action_keywords = {
            "buy": ["buy", "long", "bullish", "purchase"],
            "sell": ["sell", "short", "bearish", "exit"],
            "hold": ["hold", "wait", "neutral", "sideways"]
        }
        
        response_text = str(data).lower()
        
        for action, keywords in action_keywords.items():
            if any(keyword in response_text for keyword in keywords):
                return action
        
        return "hold"  # Default
    
    def _extract_confidence(self, data: Dict) -> float:
        """Extract confidence level from AI response"""
        import re
        
        response_text = str(data)
        
        # Look for confidence patterns
        confidence_patterns = [
            r"confidence[:\s]+(\d+)%?",
            r"(\d+)%?\s+confidence",
            r"certainty[:\s]+(\d+)%?",
            r"probability[:\s]+(\d+)%?"
        ]
        
        for pattern in confidence_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                confidence = float(match.group(1))
                return min(100, max(0, confidence))
        
        return 70.0  # Default moderate confidence
    
    def _determine_strength(self, confidence: float, data: Dict) -> SignalStrength:
        """Determine signal strength based on confidence and other factors"""
        if confidence >= 85:
            return SignalStrength.VERY_STRONG
        elif confidence >= 70:
            return SignalStrength.STRONG
        elif confidence >= 50:
            return SignalStrength.NEUTRAL
        elif confidence >= 30:
            return SignalStrength.WEAK
        else:
            return SignalStrength.VERY_WEAK
    
    def _extract_price_target(self, data: Dict) -> Optional[float]:
        """Extract price target from AI response"""
        import re
        
        response_text = str(data)
        
        # Look for price target patterns
        target_patterns = [
            r"target[:\s]+\$?(\d+,?\d*\.?\d*)",
            r"price target[:\s]+\$?(\d+,?\d*\.?\d*)",
            r"target price[:\s]+\$?(\d+,?\d*\.?\d*)"
        ]
        
        for pattern in target_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1).replace(",", ""))
                except:
                    continue
        
        return None
    
    def _extract_stop_loss(self, data: Dict) -> Optional[float]:
        """Extract stop loss from AI response"""
        import re
        
        response_text = str(data)
        
        # Look for stop loss patterns
        stop_patterns = [
            r"stop[:\s]+\$?(\d+,?\d*\.?\d*)",
            r"stop loss[:\s]+\$?(\d+,?\d*\.?\d*)",
            r"stop-loss[:\s]+\$?(\d+,?\d*\.?\d*)"
        ]
        
        for pattern in stop_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1).replace(",", ""))
                except:
                    continue
        
        return None
    
    def _extract_time_horizon(self, data: Dict) -> str:
        """Extract time horizon from AI response"""
        response_text = str(data).lower()
        
        if any(word in response_text for word in ["long", "months", "year", "years"]):
            return "long"
        elif any(word in response_text for word in ["medium", "weeks", "week"]):
            return "medium"
        else:
            return "short"
    
    def _extract_reasoning(self, data: Dict, full_response: str) -> str:
        """Extract reasoning from AI response"""
        if isinstance(data, dict):
            reasoning = data.get("reasoning") or data.get("analysis") or data.get("summary")
            if reasoning:
                return str(reasoning)
        
        # Fallback to first few sentences of response
        sentences = full_response.split(".")[:3]
        return ". ".join(sentences) + "."
    
    def _extract_from_text(self, text: str) -> Dict:
        """Extract structured data from unstructured text"""
        # Simple extraction for non-JSON responses
        return {
            "text": text,
            "recommendation": text.lower()
        }
    
    async def get_consensus_signal(self, symbol: str) -> Optional[AISignal]:
        """Get consensus signal from multiple models"""
        try:
            # Run analysis with multiple models
            signals = await self.analyze_symbol(
                symbol,
                analysis_types=[AnalysisType.TECHNICAL, AnalysisType.SENTIMENT],
                models=[AIModel.GPT_5_PRO, AIModel.GPT_4_TURBO]
            )
            
            if not signals:
                return None
            
            # Calculate consensus
            buy_signals = sum(1 for s in signals if s.action == "buy")
            sell_signals = sum(1 for s in signals if s.action == "sell")
            hold_signals = sum(1 for s in signals if s.action == "hold")
            
            total_signals = len(signals)
            avg_confidence = sum(s.confidence for s in signals) / total_signals
            
            # Determine consensus action
            if buy_signals > sell_signals and buy_signals > hold_signals:
                consensus_action = "buy"
            elif sell_signals > buy_signals and sell_signals > hold_signals:
                consensus_action = "sell"
            else:
                consensus_action = "hold"
            
            # Create consensus signal
            consensus_signal = AISignal(
                symbol=symbol,
                action=consensus_action,
                strength=self._determine_strength(avg_confidence, {}),
                confidence=avg_confidence,
                price_target=None,
                stop_loss=None,
                time_horizon="medium",
                reasoning=f"Consensus from {total_signals} AI models: {buy_signals} buy, {sell_signals} sell, {hold_signals} hold",
                model_used=AIModel.GPT_5_PRO,  # Representative
                analysis_type=AnalysisType.TECHNICAL,  # Representative
                timestamp=datetime.utcnow()
            )
            
            return consensus_signal
            
        except Exception as e:
            logger.error(f"Error getting consensus signal: {e}")
            return None


# Global instance
_ai_engine: Optional[AdvancedAIEngine] = None

def get_ai_engine() -> AdvancedAIEngine:
    """Get or create global AdvancedAIEngine instance"""
    global _ai_engine
    
    if _ai_engine is None:
        _ai_engine = AdvancedAIEngine()
    
    return _ai_engine
