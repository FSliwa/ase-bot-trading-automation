"""
Binance WebSocket Live Data Feed
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Callable, Dict, List, Optional

import aiohttp
import websockets
from asyncio_throttle import Throttler

from bot.broker.enhanced_paper import EnhancedPaperBroker


class BinanceFeed:
    """Binance WebSocket data feed"""
    
    def __init__(self, symbols: List[str], broker: Optional[EnhancedPaperBroker] = None):
        self.symbols = [s.lower() for s in symbols]  # Binance uses lowercase
        self.broker = broker
        self.ws_url = "wss://stream.binance.com:9443/ws/"
        self.rest_url = "https://api.binance.com/api/v3"
        self.websocket = None
        self.running = False
        self.callbacks: Dict[str, List[Callable]] = {
            "ticker": [],
            "kline": [],
            "trade": [],
            "orderbook": []
        }
        
        # Rate limiting
        self.throttler = Throttler(rate_limit=10, period=1.0)  # 10 requests per second
        
        self.logger = logging.getLogger(__name__)
    
    def add_callback(self, event_type: str, callback: Callable):
        """Add callback for specific event type"""
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)
    
    async def start(self):
        """Start the WebSocket feed"""
        if self.running:
            return
        
        self.running = True
        self.logger.info(f"Starting Binance feed for symbols: {self.symbols}")
        
        # Get initial market data
        await self._fetch_initial_data()
        
        # Start WebSocket connection
        await self._connect_websocket()
    
    async def stop(self):
        """Stop the WebSocket feed"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
        self.logger.info("Binance feed stopped")
    
    async def _fetch_initial_data(self):
        """Fetch initial market data via REST API"""
        try:
            async with aiohttp.ClientSession() as session:
                # Get 24hr ticker statistics
                url = f"{self.rest_url}/ticker/24hr"
                async with session.get(url) as response:
                    if response.status == 200:
                        tickers = await response.json()
                        
                        for ticker in tickers:
                            symbol = ticker["symbol"].lower()
                            if symbol in self.symbols:
                                await self._process_ticker_data({
                                    "symbol": symbol,
                                    "price": float(ticker["lastPrice"]),
                                    "bid": float(ticker["bidPrice"]),
                                    "ask": float(ticker["askPrice"]),
                                    "volume": float(ticker["volume"]),
                                    "change_24h": float(ticker["priceChangePercent"]),
                                    "high_24h": float(ticker["highPrice"]),
                                    "low_24h": float(ticker["lowPrice"])
                                })
                
                self.logger.info(f"Fetched initial data for {len(self.symbols)} symbols")
        
        except Exception as e:
            self.logger.error(f"Error fetching initial data: {e}")
    
    async def _connect_websocket(self):
        """Connect to Binance WebSocket"""
        # Create stream names
        streams = []
        for symbol in self.symbols:
            streams.extend([
                f"{symbol}@ticker",      # 24hr ticker
                f"{symbol}@kline_1m",    # 1-minute klines
                f"{symbol}@trade",       # Individual trades
                f"{symbol}@depth20"      # Order book depth
            ])
        
        stream_url = self.ws_url + "/".join(streams)
        
        while self.running:
            try:
                self.logger.info("Connecting to Binance WebSocket...")
                
                async with websockets.connect(stream_url) as websocket:
                    self.websocket = websocket
                    self.logger.info("Connected to Binance WebSocket")
                    
                    async for message in websocket:
                        if not self.running:
                            break
                        
                        try:
                            data = json.loads(message)
                            await self._process_websocket_message(data)
                        
                        except json.JSONDecodeError as e:
                            self.logger.warning(f"Invalid JSON received: {e}")
                        except Exception as e:
                            self.logger.error(f"Error processing message: {e}")
            
            except websockets.exceptions.ConnectionClosed:
                if self.running:
                    self.logger.warning("WebSocket connection closed, reconnecting...")
                    await asyncio.sleep(5)
            except Exception as e:
                if self.running:
                    self.logger.error(f"WebSocket error: {e}")
                    await asyncio.sleep(10)
    
    async def _process_websocket_message(self, data: dict):
        """Process incoming WebSocket message"""
        if "stream" not in data or "data" not in data:
            return
        
        stream = data["stream"]
        message_data = data["data"]
        
        # Parse stream name
        parts = stream.split("@")
        if len(parts) != 2:
            return
        
        symbol = parts[0]
        stream_type = parts[1]
        
        try:
            if stream_type == "ticker":
                await self._process_ticker_update(symbol, message_data)
            elif stream_type.startswith("kline"):
                await self._process_kline_update(symbol, message_data)
            elif stream_type == "trade":
                await self._process_trade_update(symbol, message_data)
            elif stream_type.startswith("depth"):
                await self._process_orderbook_update(symbol, message_data)
        
        except Exception as e:
            self.logger.error(f"Error processing {stream_type} for {symbol}: {e}")
    
    async def _process_ticker_update(self, symbol: str, data: dict):
        """Process ticker update"""
        ticker_data = {
            "symbol": symbol,
            "price": float(data["c"]),  # Close price
            "bid": float(data["b"]),    # Best bid
            "ask": float(data["a"]),    # Best ask
            "volume": float(data["v"]), # Volume
            "change_24h": float(data["P"]),  # Price change percent
            "high_24h": float(data["h"]),    # High price
            "low_24h": float(data["l"]),     # Low price
            "timestamp": datetime.utcnow()
        }
        
        await self._process_ticker_data(ticker_data)
    
    async def _process_ticker_data(self, ticker_data: dict):
        """Process ticker data (common for REST and WebSocket)"""
        symbol = ticker_data["symbol"].upper()
        
        # Update broker if available
        if self.broker:
            await self.throttler.acquire()
            self.broker.update_market_price(
                symbol=symbol,
                price=ticker_data["price"],
                bid=ticker_data["bid"],
                ask=ticker_data["ask"]
            )
        
        # Call callbacks
        for callback in self.callbacks["ticker"]:
            try:
                await callback(ticker_data)
            except Exception as e:
                self.logger.error(f"Error in ticker callback: {e}")
    
    async def _process_kline_update(self, symbol: str, data: dict):
        """Process kline (candlestick) update"""
        kline = data["k"]
        
        kline_data = {
            "symbol": symbol.upper(),
            "interval": kline["i"],
            "open_time": kline["t"],
            "close_time": kline["T"],
            "open": float(kline["o"]),
            "high": float(kline["h"]),
            "low": float(kline["l"]),
            "close": float(kline["c"]),
            "volume": float(kline["v"]),
            "is_closed": kline["x"],  # Whether this kline is closed
            "timestamp": datetime.utcnow()
        }
        
        # Call callbacks
        for callback in self.callbacks["kline"]:
            try:
                await callback(kline_data)
            except Exception as e:
                self.logger.error(f"Error in kline callback: {e}")
    
    async def _process_trade_update(self, symbol: str, data: dict):
        """Process individual trade update"""
        trade_data = {
            "symbol": symbol.upper(),
            "trade_id": data["t"],
            "price": float(data["p"]),
            "quantity": float(data["q"]),
            "buyer_order_id": data["b"],
            "seller_order_id": data["a"],
            "trade_time": data["T"],
            "is_buyer_maker": data["m"],
            "timestamp": datetime.utcnow()
        }
        
        # Call callbacks
        for callback in self.callbacks["trade"]:
            try:
                await callback(trade_data)
            except Exception as e:
                self.logger.error(f"Error in trade callback: {e}")
    
    async def _process_orderbook_update(self, symbol: str, data: dict):
        """Process order book update"""
        orderbook_data = {
            "symbol": symbol.upper(),
            "bids": [[float(price), float(qty)] for price, qty in data["bids"]],
            "asks": [[float(price), float(qty)] for price, qty in data["asks"]],
            "timestamp": datetime.utcnow()
        }
        
        # Call callbacks
        for callback in self.callbacks["orderbook"]:
            try:
                await callback(orderbook_data)
            except Exception as e:
                self.logger.error(f"Error in orderbook callback: {e}")
    
    async def get_historical_klines(self, symbol: str, interval: str = "1m", 
                                   limit: int = 100) -> List[dict]:
        """Get historical kline data"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.rest_url}/klines"
                params = {
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "limit": limit
                }
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        klines = await response.json()
                        
                        processed_klines = []
                        for kline in klines:
                            processed_klines.append({
                                "open_time": kline[0],
                                "open": float(kline[1]),
                                "high": float(kline[2]),
                                "low": float(kline[3]),
                                "close": float(kline[4]),
                                "volume": float(kline[5]),
                                "close_time": kline[6],
                                "quote_volume": float(kline[7]),
                                "trades_count": kline[8]
                            })
                        
                        return processed_klines
                    else:
                        self.logger.error(f"Error fetching klines: {response.status}")
                        return []
        
        except Exception as e:
            self.logger.error(f"Error fetching historical klines: {e}")
            return []


class FeedManager:
    """Manages multiple data feeds"""
    
    def __init__(self, broker: Optional[EnhancedPaperBroker] = None):
        self.broker = broker
        self.feeds: Dict[str, BinanceFeed] = {}
        self.running = False
        self.logger = logging.getLogger(__name__)
    
    def add_binance_feed(self, name: str, symbols: List[str]) -> BinanceFeed:
        """Add Binance feed"""
        feed = BinanceFeed(symbols, self.broker)
        self.feeds[name] = feed
        return feed
    
    async def start_all(self):
        """Start all feeds"""
        if self.running:
            return
        
        self.running = True
        self.logger.info("Starting all data feeds...")
        
        tasks = []
        for name, feed in self.feeds.items():
            task = asyncio.create_task(feed.start())
            tasks.append(task)
            self.logger.info(f"Started feed: {name}")
        
        # Wait for all feeds to start
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop_all(self):
        """Stop all feeds"""
        self.running = False
        self.logger.info("Stopping all data feeds...")
        
        tasks = []
        for name, feed in self.feeds.items():
            task = asyncio.create_task(feed.stop())
            tasks.append(task)
            self.logger.info(f"Stopping feed: {name}")
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_feed(self, name: str) -> Optional[BinanceFeed]:
        """Get feed by name"""
        return self.feeds.get(name)


# Global feed manager instance
feed_manager = FeedManager()
