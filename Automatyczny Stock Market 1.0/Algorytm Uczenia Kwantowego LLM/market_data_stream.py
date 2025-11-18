import asyncio
import json
import os
import time
from typing import Dict, List, Optional

import websockets
import redis
from tenacity import retry, wait_fixed, stop_after_attempt

BINANCE_WS = "wss://stream.binance.com:9443/stream"


class MarketDataStreamer:
    """
    Streams miniTicker data from Binance WebSocket for given symbols.
    Publishes last ticks to Redis (TTL) and keeps a local fallback cache.
    """

    def __init__(self, symbols: List[str], redis_url: Optional[str] = None):
        self.symbols = [s.lower().replace("/", "") for s in symbols if s]
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        # Decode responses to str; if Redis is not available, operations will raise which we handle.
        self.r = redis.Redis.from_url(self.redis_url, decode_responses=True)
        self.local_cache: Dict[str, dict] = {}
        self.stop_event = asyncio.Event()

    def _stream_url(self) -> str:
        # Use miniTicker for lightweight stream
        streams = "/".join([f"{sym}@miniTicker" for sym in self.symbols])
        return f"{BINANCE_WS}?streams={streams}"

    @retry(wait=wait_fixed(2), stop=stop_after_attempt(20))
    async def run(self):
        url = self._stream_url()
        # Persistently reconnect on disconnects
        async for ws in websockets.connect(url, ping_interval=15, ping_timeout=10):
            try:
                while not self.stop_event.is_set():
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    data = json.loads(msg)
                    payload = data.get("data", {})
                    sym = str(payload.get("s", "")).lower()
                    if not sym:
                        continue
                    def _to_float(x):
                        try:
                            return float(x) if x is not None else None
                        except Exception:
                            return None
                    tick = {
                        "symbol": sym,
                        "price": _to_float(payload.get("c")),
                        "high": _to_float(payload.get("h")),
                        "low": _to_float(payload.get("l")),
                        "volume": _to_float(payload.get("v")),
                        "ts": time.time(),
                    }
                    # Update local cache always
                    self.local_cache[sym] = tick
                    # Best-effort Redis publish
                    try:
                        self.r.setex(f"md:tick:{sym}", 3, json.dumps(tick))
                    except Exception:
                        # Ignore Redis errors; rely on local cache
                        pass
            except (asyncio.TimeoutError, websockets.ConnectionClosedError, websockets.ConnectionClosedOK):
                # Reconnect handled by async for loop
                continue
            except Exception:
                # Small backoff, then reconnect
                await asyncio.sleep(1)

    async def stop(self):
        self.stop_event.set()

    def get_tick(self, symbol: str) -> Optional[dict]:
        key = f"md:tick:{symbol.lower().replace('/','')}"
        # Try Redis first
        try:
            v = self.r.get(key)
            if v:
                return json.loads(v)
        except Exception:
            # Fallback to local cache
            pass
        return self.local_cache.get(symbol.lower().replace("/", ""))
