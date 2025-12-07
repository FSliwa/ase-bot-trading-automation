import aiohttp
import json
from typing import Dict, Optional, List, Any
from bot.config import load_supabase_config
from bot.logging_setup import get_logger

logger = get_logger("supabase_analysis")

class SupabaseAnalysisService:
    """Service to interact with Supabase Edge Functions for AI analysis."""
    
    def __init__(self):
        self.config = load_supabase_config()
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.key}",
            "apikey": self.config.key
        }
        self.url = f"{self.config.url}/{self.config.function_name}"
        
    async def generate_signals_batch(self, symbols: List[str], market_data_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Call the Edge Function to generate trading signals for multiple symbols.
        
        Args:
            symbols: List of trading pair symbols (e.g., ["BTC/USDT", "ETH/USDT"])
            market_data_map: Dictionary mapping symbol to market metrics
            
        Returns:
            List of dictionaries with signal details
        """
        # Clean symbols for the API
        clean_symbols = [s.replace("/USDT", "").replace("/USD", "") for s in symbols]
        
        # Prepare market data with clean keys
        clean_market_data = {}
        for s, data in market_data_map.items():
            clean_key = s.replace("/USDT", "").replace("/USD", "")
            clean_market_data[clean_key] = data
            
        payload = {
            "symbols": clean_symbols,
            "marketData": clean_market_data,
            "takeProfitPercent": 3.0,
            "stopLossPercent": 5.0
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                logger.info(f"Calling Supabase Edge Function for {len(symbols)} symbols: {self.url}")
                async with session.post(self.url, headers=self.headers, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Edge Function failed with status {response.status}: {error_text}")
                        return []
                        
                    data = await response.json()
                    
                    if "error" in data and data["error"]:
                        logger.error(f"Edge Function returned error: {data['error']}")
                        return []
                        
                    signals = data.get("signals", [])
                    if not signals:
                        logger.info(f"No signals returned")
                        return []
                        
                    # Map signals to expected format
                    mapped_signals = []
                    for signal in signals:
                        mapped_signals.append({
                            "symbol": f"{signal['symbol']}/USDT", # Restore /USDT for bot consistency
                            "action": signal["action"].upper(),
                            "confidence": signal["confidence"] / 100.0,
                            "reasoning": signal["reasoning"],
                            "marketSentiment": signal.get("marketSentiment", "NEUTRAL"),
                            "targets": [signal.get("takeProfitPrice", 0)],
                            "stop_loss": signal.get("stopLossPrice", 0)
                        })
                        
                    return mapped_signals
                    
        except Exception as e:
            logger.error(f"Error calling Supabase Edge Function: {e}")
            return []

    async def generate_signal(self, symbol: str, market_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Legacy single signal generation (wraps batch)"""
        signals = await self.generate_signals_batch([symbol], {symbol: market_data})
        return signals[0] if signals else None
