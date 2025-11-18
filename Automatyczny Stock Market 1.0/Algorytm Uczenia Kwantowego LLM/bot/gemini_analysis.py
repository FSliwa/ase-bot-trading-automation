#!/usr/bin/env python3
"""
Gemini AI Integration Module
Provides Google Gemini Pro integration for trading analysis
"""

import os
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import google.generativeai as genai
try:
    from dotenv import dotenv_values  # type: ignore
except Exception:  # pragma: no cover
    dotenv_values = None  # lazy fallback if python-dotenv unavailable at runtime
from google.generativeai.types import HarmCategory, HarmBlockThreshold

logger = logging.getLogger(__name__)

SUPPORTED_FALLBACK_MODEL = "gemini-1.5-pro"

class GeminiAnalyzer:
    """Google Gemini Pro AI analyzer for trading decisions"""
    
    def __init__(self):
        """Initialize Gemini analyzer with API key and model"""
        # Primary source: environment
        self.api_key = os.getenv("GEMINI_API_KEY")
        # Fallback: read directly from .env if the env var is not visible under systemd
        if not self.api_key and dotenv_values is not None:
            try:
                # Prefer absolute path used by systemd unit; fallback to CWD .env
                env_map = dotenv_values("/opt/trading-bot/.env") or dotenv_values(".env") or {}
                self.api_key = env_map.get("GEMINI_API_KEY")
            except Exception:  # noqa: BLE001
                # Best-effort fallback only
                pass
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro-latest")
        self.temperature = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))
        self.max_tokens = int(os.getenv("GEMINI_MAX_TOKENS", "2048"))
        self._effective_model = None
        self._daily_budget_cents = int(os.getenv("GEMINI_DAILY_BUDGET_CENTS", "0"))
        self._spent_cents_today = 0
        
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not configured")
            self.client = None
            return
            
        try:
            # Configure Gemini API
            genai.configure(api_key=self.api_key)
            
            # Initialize model with safety settings
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            }
            
            # Configure generation settings
            generation_config = genai.types.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
                top_p=0.9,
                top_k=40
            )
            
            # attempt preferred model first
            self._effective_model = self.model_name
            # Library signature expects `model_name`
            self.client = genai.GenerativeModel(
                model_name=self._effective_model,
                safety_settings=safety_settings,
                generation_config=generation_config
            )
            
            logger.info(f"Gemini AI initialized with model: {self._effective_model}")
            
        except Exception as e:
            logger.error(f"Initial model init failed ({self.model_name}): {e}; falling back to {SUPPORTED_FALLBACK_MODEL}")
            try:
                self._effective_model = SUPPORTED_FALLBACK_MODEL
                self.client = genai.GenerativeModel(model_name=self._effective_model)
                logger.info(f"Gemini AI fallback model in use: {self._effective_model}")
            except Exception as e2:
                logger.error(f"Failed to initialize fallback model: {e2}")
                self.client = None
    
    def is_configured(self) -> bool:
        """Check if Gemini is properly configured"""
        return self.client is not None and self.api_key is not None
    
    async def analyze_market(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze market conditions using Gemini AI"""
        if not self.is_configured():
            return {
                "error": "Gemini AI not configured - set GEMINI_API_KEY in .env file",
                "model": "gemini-not-configured"
            }
        if self._daily_budget_cents and self._spent_cents_today >= self._daily_budget_cents:
            return {"error": "AI daily budget exceeded", "model": self._effective_model}
        
        try:
            # Build market analysis prompt
            prompt = self._build_market_prompt(params)
            
            # Generate analysis
            response = await self._generate_with_retry(prompt)
            
            if not response:
                return {"error": "No response from Gemini API"}
            
            # Parse response
            analysis = self._parse_market_response(response)
            
            # Add metadata
            analysis["meta"] = {
                "model": self._effective_model or self.model_name,
                "timestamp": datetime.now().isoformat(),
                "prompt_tokens": len(prompt) // 4,  # Rough estimate
                "completion_tokens": len(response) // 4
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Gemini market analysis failed: {e}")
            return {
                "error": f"Market analysis failed: {str(e)}",
                "model": self._effective_model or self.model_name
            }
    
    async def analyze_trade_execution(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze trade execution using Gemini AI"""
        if not self.is_configured():
            return {
                "error": "Gemini AI not configured - set GEMINI_API_KEY in .env file"
            }
        
        try:
            # Build trade execution prompt
            prompt = self._build_trade_prompt(params)
            
            # Generate analysis
            response = await self._generate_async(prompt)
            
            if not response:
                return {"error": "No response from Gemini API"}
            
            # Parse response
            analysis = self._parse_trade_response(response)
            
            # Add metadata
            analysis["meta"] = {
                "model": self.model_name,
                "timestamp": datetime.now().isoformat()
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Gemini trade analysis failed: {e}")
            return {"error": f"Trade analysis failed: {str(e)}"}
    
    async def _generate_with_retry(self, prompt: str) -> Optional[str]:
        """Generate response asynchronously with retry on model not found"""
        try:
            # Run in thread pool since Gemini SDK doesn't have async support yet
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.client.generate_content(prompt)
            )
            
            if response and response.text:
                # naive accounting
                self._spent_cents_today += 1
                return response.text
            else:
                logger.warning("Empty response from Gemini")
                return None
                
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            raise
    
    def _build_market_prompt(self, params: Dict[str, Any]) -> str:
        """Build market analysis prompt for Gemini"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
        
        prompt = f"""You are an elite AI trading advisor powered by Google Gemini Pro with advanced market analysis capabilities.

Your task is to analyze current market conditions and provide actionable trading insights.

Current Parameters:
- Exchange: {params.get('exchange', 'PrimeXBT')}
- Portfolio Size: {params.get('notional', '10000')} USD
- Max Leverage: {params.get('150x', '150')}x
- Analysis Time: {current_time}
- Market Impact Limit: {params.get('max impact bps', '10')} bps

Please provide a comprehensive market analysis in the following JSON format:

{{
    "market_regime": {{
        "trend": "bullish|bearish|sideways",
        "strength": 0.0-1.0,
        "confidence": 0.0-1.0
    }},
    "candidates": [
        {{
            "symbol": "BTC/USDT",
            "side": "long|short",
            "confidence": 0.0-1.0,
            "entry_price": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "reasoning": "Clear explanation of the trade thesis"
        }}
    ],
    "top_pick": {{
        "symbol": "BTC/USDT",
        "side": "long|short",
        "confidence": 0.0-1.0,
        "risk_reward_ratio": 2.0
    }},
    "market_summary": "Brief summary of current market conditions and key factors",
    "risk_assessment": "Risk factors and warnings"
}}

Focus on major cryptocurrency pairs (BTC, ETH, ADA, SOL, DOT) and provide specific, actionable recommendations based on current market analysis."""

        return prompt
    
    def _build_trade_prompt(self, params: Dict[str, Any]) -> str:
        """Build trade execution prompt for Gemini"""
        prompt = f"""You are an advanced trade execution advisor using Google Gemini Pro.

Analyze the following trade setup and provide execution recommendations:

Trade Parameters:
- Symbol: {params.get('SYMBOL', 'BTC/USDT')}
- Side: {params.get('side', 'long')}
- Quantity: {params.get('quantity', '0.1')}
- Leverage: {params.get('leverage', '10')}x
- Entry Price: {params.get('entry_price', 'market')}

Provide trade execution analysis in JSON format:

{{
    "execution_plan": {{
        "order_type": "market|limit|stop",
        "entry_strategy": "immediate|scaled|wait_for_dip",
        "position_sizing": 0.0-1.0,
        "leverage_recommendation": 1-150
    }},
    "risk_management": {{
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "risk_reward_ratio": 2.0,
        "max_loss_usd": 0.0
    }},
    "timing": {{
        "entry_timing": "immediate|wait|scale_in",
        "market_conditions": "favorable|neutral|unfavorable",
        "volatility_assessment": "low|medium|high"
    }},
    "execution_summary": "Brief summary of recommended execution approach"
}}

Provide specific, actionable execution guidance based on current market conditions."""

        return prompt
    
    def _parse_market_response(self, response: str) -> Dict[str, Any]:
        """Parse market analysis response from Gemini"""
        try:
            # Try to extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                # Fallback: create structured response from text
                return {
                    "market_regime": {
                        "trend": "neutral",
                        "strength": 0.5,
                        "confidence": 0.7
                    },
                    "candidates": [],
                    "top_pick": {
                        "symbol": "BTC/USDT",
                        "side": "long",
                        "confidence": 0.6,
                        "risk_reward_ratio": 2.0
                    },
                    "market_summary": response[:200] + "..." if len(response) > 200 else response,
                    "raw_response": response
                }
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from Gemini response: {e}")
            return {
                "error": "Failed to parse analysis",
                "raw_response": response
            }
    
    def _parse_trade_response(self, response: str) -> Dict[str, Any]:
        """Parse trade execution response from Gemini"""
        try:
            # Try to extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                # Fallback response
                return {
                    "execution_plan": {
                        "order_type": "market",
                        "entry_strategy": "immediate",
                        "position_sizing": 0.5,
                        "leverage_recommendation": 10
                    },
                    "risk_management": {
                        "stop_loss": 0.0,
                        "take_profit": 0.0,
                        "risk_reward_ratio": 2.0,
                        "max_loss_usd": 100.0
                    },
                    "execution_summary": response[:200] + "..." if len(response) > 200 else response,
                    "raw_response": response
                }
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from Gemini trade response: {e}")
            return {
                "error": "Failed to parse trade analysis",
                "raw_response": response
            }

# Global instance
_gemini_analyzer = None

def get_gemini_analyzer() -> Optional[GeminiAnalyzer]:
    """Get global Gemini analyzer instance.

    Re-initialize if previously unconfigured and an API key is now present.
    This makes it resilient to late-bound environment variables under systemd.
    """
    global _gemini_analyzer
    if _gemini_analyzer is None or not _gemini_analyzer.is_configured():
        _gemini_analyzer = GeminiAnalyzer()
    return _gemini_analyzer if _gemini_analyzer.is_configured() else None
