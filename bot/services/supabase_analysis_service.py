import aiohttp
import asyncio
import json
import os
from typing import Dict, Optional, List, Any
from bot.config import load_supabase_config
from bot.logging_setup import get_logger

logger = get_logger("supabase_analysis")

# P2-10 FIX (2025-12-15): Made timeout configurable via environment variable
# K3 FIX: Request configuration - increased timeout and retries for AI processing
# FIX 2025-12-16: Increased timeout to 300s to handle Edge Function cold starts and slow AI responses
REQUEST_TIMEOUT = int(os.getenv('AI_REQUEST_TIMEOUT', 300))  # Default 300s (5 min), configurable
MAX_RETRIES = int(os.getenv('AI_MAX_RETRIES', 3))  # Default 3 retries (reduced to avoid excessive waiting)
RETRY_DELAY_BASE = int(os.getenv('AI_RETRY_DELAY_BASE', 5))  # Base delay 5s (longer for cold start recovery)

# FIX 2025-12-16: Add connection timeout separate from read timeout
CONNECT_TIMEOUT = int(os.getenv('AI_CONNECT_TIMEOUT', 300))  # 300s to establish connection (increased from 60s)

# FIX 2025-12-16: Track last successful call to detect cold starts
_last_successful_call = None

class SupabaseAnalysisService:
    """Service to interact with Supabase Edge Functions for AI analysis."""
    
    def __init__(self):
        self.config = load_supabase_config()
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.key}",
            "apikey": self.config.key
        }
        # K3 FIX: Construct full URL to Edge Function
        # Note: config.url already includes /functions/v1 from load_supabase_config()
        base_url = self.config.url.rstrip('/')
        if '/functions/v1' in base_url:
            # URL already has /functions/v1, just append function name
            self.url = f"{base_url}/{self.config.function_name}"
        else:
            # URL doesn't have /functions/v1, add it
            self.url = f"{base_url}/functions/v1/{self.config.function_name}"
        logger.info(f"📡 Supabase Edge Function URL: {self.url}")
        
    async def _warmup_edge_function(self) -> bool:
        """
        FIX 2025-12-16: Send a lightweight warmup request to wake up cold Edge Function.
        Returns True if warmup succeeded, False otherwise.
        """
        global _last_successful_call
        import time
        
        # Skip warmup if we had a successful call in the last 5 minutes
        if _last_successful_call and (time.time() - _last_successful_call) < 300:
            logger.debug("⏭️ Skipping warmup - recent successful call")
            return True
            
        logger.info("🔥 Sending warmup request to Edge Function (cold start mitigation)...")
        
        try:
            warmup_timeout = aiohttp.ClientTimeout(total=30, connect=15)
            warmup_payload = {"warmup": True, "version": "3.0"}
            
            async with aiohttp.ClientSession(timeout=warmup_timeout) as session:
                async with session.post(self.url, headers=self.headers, json=warmup_payload) as response:
                    if response.status in [200, 400, 500]:  # Any response means function is awake
                        logger.info(f"✅ Edge Function is warm (status: {response.status})")
                        return True
                    else:
                        logger.warning(f"⚠️ Warmup got unexpected status: {response.status}")
                        return False
        except asyncio.TimeoutError:
            logger.warning("⏰ Warmup request timed out - Edge Function may need longer")
            return False
        except Exception as e:
            logger.warning(f"⚠️ Warmup failed: {e}")
            return False
        
    async def generate_signals_batch(self, symbols: List[str], market_data_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Call the Edge Function to generate trading signals for multiple symbols.
        
        K3 FIX: Enhanced with better error handling, logging, and retry logic.
        
        Args:
            symbols: List of trading pair symbols (e.g., ["BTC/USDT", "ETH/USDT"])
            market_data_map: Dictionary mapping symbol to market metrics
            
        Returns:
            List of dictionaries with signal details
        """
        # L8 FIX: Use centralized symbol normalizer
        # LEGACY local function for backward compatibility
        def clean_symbol(s: str) -> str:
            """
            L8 FIX: Delegate to central normalizer if available.
            Fallback to local implementation for backward compatibility.
            """
            try:
                from bot.core.symbol_normalizer import get_base
                return get_base(s)
            except ImportError:
                # Fallback: local implementation
                return s.replace("/USDC", "").replace("/USDT", "").replace("/USD", "")
        
        clean_symbols = [clean_symbol(s) for s in symbols]
        
        # Prepare market data with clean keys (use same clean_symbol function)
        clean_market_data = {}
        for s, data in market_data_map.items():
            clean_key = clean_symbol(s)
            clean_market_data[clean_key] = data
            
        payload = {
            "symbols": clean_symbols,
            "marketData": clean_market_data,
            "takeProfitPercent": 3.0,
            "stopLossPercent": 5.0,
            # K3 FIX: Add request metadata for debugging
            "requestId": f"bot_{asyncio.get_event_loop().time():.0f}",
            "version": "3.0"
        }
        
        logger.info(f"🤖 K3: Calling Edge Function for {len(symbols)} symbols: {clean_symbols}")
        logger.debug(f"📤 Payload: {json.dumps(payload, indent=2)[:500]}...")  # First 500 chars
        
        # FIX 2025-12-16: Warmup Edge Function before main request (cold start mitigation)
        await self._warmup_edge_function()
        
        try:
            # FIX 2025-12-16: Improved timeout configuration for cold starts
            timeout = aiohttp.ClientTimeout(
                total=REQUEST_TIMEOUT,      # Total time for request (300s)
                connect=CONNECT_TIMEOUT,    # Time to establish connection (60s)
                sock_read=REQUEST_TIMEOUT   # Time to read response (300s)
            )
            async with aiohttp.ClientSession(timeout=timeout) as session:
                
                for attempt in range(MAX_RETRIES):
                    retry_delay = RETRY_DELAY_BASE * (2 ** attempt)  # Exponential backoff: 5s, 10s, 20s
                    
                    try:
                        logger.info(f"📡 Edge Function attempt {attempt + 1}/{MAX_RETRIES} (timeout: {REQUEST_TIMEOUT}s, connect: {CONNECT_TIMEOUT}s)")
                        
                        async with session.post(self.url, headers=self.headers, json=payload) as response:
                            response_text = await response.text()
                            
                            # K3 FIX: Log full response for debugging
                            logger.info(f"📥 Response status: {response.status}")
                            logger.debug(f"📥 Response headers: {dict(response.headers)}")
                            
                            if response.status != 200:
                                logger.error(f"❌ Edge Function failed with status {response.status}: {response_text[:500]}")
                                
                                # K3 FIX: Handle specific error codes
                                if response.status == 504:  # Gateway Timeout
                                    logger.warning(f"⏰ Gateway timeout - Edge Function may need more time")
                                elif response.status == 503:  # Service Unavailable
                                    logger.warning(f"🔄 Service temporarily unavailable")
                                elif response.status == 401:  # Unauthorized
                                    logger.error(f"🔑 Authentication failed - check SUPABASE_KEY")
                                    return []  # Don't retry auth errors
                                elif response.status == 429:  # Rate limited
                                    logger.warning(f"⚠️ Rate limited - waiting longer")
                                    retry_delay = retry_delay * 2
                                
                                # FIX 2025-12-17: Log error response to Supabase (User Request)
                                try:
                                    from bot.db import DatabaseManager
                                    with DatabaseManager() as db:
                                        db.record_ai_analysis(
                                            symbol="TITAN_V3_BATCH",
                                            model_used="titan_v3_edge_function",
                                            recommendation="ERROR",
                                            confidence=0.0,
                                            payload={
                                                "request_symbols": clean_symbols,
                                                "error": f"HTTP {response.status}",
                                                "raw_response": response_text[:2000], # Capture more of the error body
                                                "http_status": response.status,
                                                "timestamp_ts": asyncio.get_event_loop().time()
                                            }
                                        )
                                        logger.info(f"📝 Logged Titan V3 error ({response.status}) to Supabase")
                                except Exception as log_err:
                                    logger.error(f"❌ Failed to log Titan V3 error to DB: {log_err}")

                                if attempt < MAX_RETRIES - 1:
                                    logger.info(f"⏳ Retrying in {retry_delay}s...")
                                    await asyncio.sleep(retry_delay)
                                    continue
                                # FIX 2025-12-16: After all retries failed, fall through to DB fallback
                                # (removed: return [])
                                break  # Exit loop to reach DB fallback
                            
                            # Parse JSON response
                            try:
                                data = json.loads(response_text)
                                
                                # FIX 2025-12-17: Log raw Titan V3 response to Supabase (User Request)
                                try:
                                    from bot.db import DatabaseManager
                                    # Note: DatabaseManager is synchronous, but operations are fast enough
                                    with DatabaseManager() as db:
                                        db.record_ai_analysis(
                                            symbol="TITAN_V3_BATCH",
                                            model_used="titan_v3_edge_function",
                                            recommendation="RAW_LOG",
                                            confidence=None,
                                            payload={
                                                "request_symbols": clean_symbols,
                                                "raw_response": data,
                                                "http_status": response.status,
                                                "timestamp_ts": asyncio.get_event_loop().time()
                                            }
                                        )
                                        logger.info("📝 Logged Titan V3 response to Supabase (ai_analyses table)")
                                except Exception as log_err:
                                    logger.error(f"❌ Failed to log Titan V3 response to DB: {log_err}")

                            except json.JSONDecodeError as e:
                                logger.error(f"❌ Failed to parse JSON response: {e}")
                                logger.error(f"📥 Raw response: {response_text[:1000]}")
                                if attempt < MAX_RETRIES - 1:
                                    await asyncio.sleep(retry_delay)
                                    continue
                                return []
                            
                            # K3 FIX: Enhanced response logging
                            logger.info(f"📥 Response data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                            
                            if isinstance(data, dict) and "error" in data and data["error"]:
                                logger.error(f"❌ Edge Function returned error: {data['error']}")
                                # K3 FIX: Log additional error context if available
                                if "details" in data:
                                    logger.error(f"   Details: {data['details']}")
                                if "stack" in data:
                                    logger.debug(f"   Stack: {data['stack']}")
                                return []
                            
                            # K3 FIX: Handle different response formats
                            signals = []
                            if isinstance(data, list):
                                signals = data
                            elif isinstance(data, dict):
                                signals = data.get("signals", data.get("data", data.get("results", [])))
                            
                            if not signals:
                                # K3 FIX: More detailed empty response logging
                                logger.warning(f"⚠️ K3: Empty signals response")
                                logger.warning(f"   Full response: {json.dumps(data, indent=2)[:1000]}")
                                logger.warning(f"   Possible causes:")
                                logger.warning(f"   1. Edge Function returned empty signals[]")
                                logger.warning(f"   2. Market conditions: AI decided HOLD for all symbols")
                                logger.warning(f"   3. Edge Function error not captured in 'error' field")
                                logger.warning(f"   4. Response format changed (expected 'signals' key)")
                                return []
                            
                            logger.info(f"✅ K3: Received {len(signals)} signals from Edge Function")
                            logger.debug(f"📥 Raw signals: {json.dumps(signals, indent=2)[:1500]}")
                                
                            # Map signals to expected format
                            mapped_signals = []
                            for signal in signals:
                                try:
                                    # K3 FIX: Handle various field names
                                    symbol_name = signal.get("symbol") or signal.get("coin") or signal.get("asset", "UNKNOWN")
                                    action = (signal.get("action") or signal.get("signal") or signal.get("recommendation", "HOLD")).upper()
                                    
                                    # Handle confidence in different formats (0-1 or 0-100)
                                    raw_confidence = signal.get("confidence", signal.get("score", 50))
                                    confidence = raw_confidence / 100.0 if raw_confidence > 1 else raw_confidence
                                    
                                    reasoning = signal.get("reasoning") or signal.get("reason") or signal.get("analysis", "AI signal")
                                    
                                    # Extract TP/SL prices (handle None and 0 cases)
                                    tp_price = signal.get("takeProfitPrice") or signal.get("takeProfit") or signal.get("tp")
                                    sl_price = signal.get("stopLossPrice") or signal.get("stopLoss") or signal.get("sl")
                                    entry_price = signal.get("entryPrice") or signal.get("entry") or signal.get("price")
                                    
                                    # Skip HOLD signals with very low confidence
                                    if action == "HOLD" and confidence < 0.1:
                                        logger.debug(f"⏭️ Skipping low-confidence HOLD for {symbol_name}")
                                        continue
                                    
                                    mapped_signal = {
                                        "symbol": f"{symbol_name}/USDT" if "/" not in symbol_name else symbol_name,
                                        "action": action,
                                        "confidence": confidence,
                                        "reasoning": reasoning,
                                        "marketSentiment": signal.get("marketSentiment", signal.get("sentiment", "NEUTRAL")),
                                        "targets": [tp_price] if tp_price and float(tp_price) > 0 else [],
                                        "take_profit": float(tp_price) if tp_price and float(tp_price) > 0 else None,
                                        "stop_loss": float(sl_price) if sl_price and float(sl_price) > 0 else None,
                                        "entry_price": float(entry_price) if entry_price else None,
                                        "source": "edge_function:council_v2"
                                    }
                                    mapped_signals.append(mapped_signal)
                                    logger.info(f"   📊 {symbol_name}: {action} ({confidence*100:.0f}%)")
                                    
                                except Exception as e:
                                    logger.warning(f"⚠️ Failed to parse signal: {e} | Raw: {signal}")
                                    continue
                            
                            logger.info(f"✅ K3: Mapped {len(mapped_signals)} actionable signals")
                            
                            # FIX 2025-12-16: Update last successful call timestamp
                            global _last_successful_call
                            import time
                            _last_successful_call = time.time()
                            
                            return mapped_signals
                            
                    except asyncio.TimeoutError:
                        logger.warning(f"⏰ Request timeout (attempt {attempt + 1}/{MAX_RETRIES}) after {REQUEST_TIMEOUT}s")
                        if attempt < MAX_RETRIES - 1:
                            logger.info(f"⏳ Retrying in {retry_delay}s...")
                            await asyncio.sleep(retry_delay)
                            continue
                        raise
                    except aiohttp.ClientError as e:
                        logger.warning(f"🌐 Network error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(retry_delay)
                            continue
                        raise
                
                # FIX 2025-12-16: If we get here, all retries failed (likely 504s)
                # Try to read signals from Supabase table as fallback
                logger.warning("⚠️ All Edge Function retries exhausted - trying DB fallback...")
                return await self._read_signals_from_db(symbols)
                    
        except asyncio.TimeoutError:
            logger.error(f"❌ K3: Supabase Edge Function timeout after {REQUEST_TIMEOUT}s (all retries exhausted)")
            # FIX 2025-12-16: Try to read signals from Supabase table as fallback
            logger.info("🔄 Attempting to read signals from Supabase table (fallback)...")
            return await self._read_signals_from_db(symbols)
        except aiohttp.ClientError as e:
            logger.error(f"❌ K3: Network error calling Supabase Edge Function: {e}")
            return await self._read_signals_from_db(symbols)
        except Exception as e:
            logger.error(f"❌ K3: Unexpected error calling Supabase Edge Function: {e}")
            import traceback
            traceback.print_exc()
            return await self._read_signals_from_db(symbols)

    async def _read_signals_from_db(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        FIX 2025-12-16: Read recent signals from Supabase trading_signals table.
        This is a fallback when Edge Function times out but still writes to DB.
        """
        try:
            # Get clean symbol names (BTC, ETH, etc.)
            def clean_symbol(s: str) -> str:
                return s.replace("/USDC", "").replace("/USDT", "").replace("/USD", "").replace("/EUR", "")
            
            clean_symbols = [clean_symbol(s) for s in symbols]
            
            # Build Supabase REST API URL for table query
            project_ref = self.config.url.split("//")[1].split(".")[0]
            table_url = f"https://{project_ref}.supabase.co/rest/v1/trading_signals"
            
            # Query for recent signals (last 6 hours) for requested symbols
            # FIX 2025-12-16: Extended from 10 minutes to 6 hours to match get_signals_from_database
            # FIX 2025-12-16: Get signals from ANY user (not just current) - enables cross-user signal sharing
            from datetime import datetime, timedelta
            six_hours_ago = (datetime.utcnow() - timedelta(hours=6)).isoformat()
            
            # Build query params - get newest signals for these symbols from trusted sources
            # Note: We don't filter by user_id - if one user's Edge Function worked, others can use the signal
            symbols_filter = ",".join([f'"{s}"' for s in clean_symbols])
            trusted_sources = "COUNCIL_V2.0_FALLBACK,titan_v3"
            params = {
                "select": "*",
                "symbol": f"in.({symbols_filter})",
                "created_at": f"gte.{six_hours_ago}",
                "is_active": "eq.true",
                "source": f"in.({trusted_sources})",  # Only trusted sources
                "signal_type": "neq.hold",  # Skip HOLD signals
                "order": "created_at.desc",
                "limit": "10"
            }
            
            headers = {
                "apikey": self.config.key,
                "Authorization": f"Bearer {self.config.key}",
                "Content-Type": "application/json"
            }
            
            logger.info(f"📖 Reading signals from DB for symbols: {clean_symbols}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(table_url, headers=headers, params=params) as response:
                    if response.status != 200:
                        logger.warning(f"⚠️ Failed to read from DB: {response.status}")
                        return []
                    
                    data = await response.json()
                    
                    if not data:
                        logger.info("📭 No recent signals found in DB")
                        return []
                    
                    logger.info(f"✅ Found {len(data)} signals in DB")
                    
                    # Map DB format to expected signal format
                    mapped_signals = []
                    for row in data:
                        try:
                            symbol_name = row.get("symbol", "UNKNOWN")
                            action = (row.get("signal_type") or "HOLD").upper()
                            confidence = float(row.get("confidence_score", 50)) / 100.0
                            
                            mapped_signal = {
                                "symbol": f"{symbol_name}/USDT" if "/" not in symbol_name else symbol_name,
                                "action": action,
                                "confidence": confidence,
                                "reasoning": row.get("ai_analysis", "Signal from DB"),
                                "marketSentiment": row.get("market_sentiment", "NEUTRAL"),
                                "take_profit": float(row["take_profit"]) if row.get("take_profit") else None,
                                "stop_loss": float(row["stop_loss"]) if row.get("stop_loss") else None,
                                "entry_price": float(row["entry_price"]) if row.get("entry_price") else None,
                                "source": f"db_fallback:{row.get('source', 'unknown')}"
                            }
                            mapped_signals.append(mapped_signal)
                            logger.info(f"   📊 {symbol_name}: {action} ({confidence*100:.0f}%) [from DB]")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to parse DB signal: {e}")
                            continue
                    
                    return mapped_signals
                    
        except Exception as e:
            logger.error(f"❌ Failed to read signals from DB: {e}")
            return []

    async def generate_signal(self, symbol: str, market_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Legacy single signal generation (wraps batch)"""
        signals = await self.generate_signals_batch([symbol], {symbol: market_data})
        return signals[0] if signals else None

