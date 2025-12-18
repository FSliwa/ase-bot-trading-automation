"""
WebSocket Manager - Real-time market data streaming.
Replaces REST polling with WebSocket connections for low-latency data.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from dataclasses import dataclass, field
import json

try:
    import ccxt.pro as ccxt_pro
    CCXT_PRO_AVAILABLE = True
except ImportError:
    CCXT_PRO_AVAILABLE = False
    import ccxt.async_support as ccxt_async

logger = logging.getLogger(__name__)


@dataclass
class MarketTick:
    """Real-time market tick data."""
    symbol: str
    last_price: float
    bid: float
    ask: float
    volume_24h: float
    change_24h_percent: float
    high_24h: float
    low_24h: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OrderBookUpdate:
    """Real-time order book update."""
    symbol: str
    bids: List[List[float]]  # [[price, quantity], ...]
    asks: List[List[float]]
    timestamp: datetime = field(default_factory=datetime.now)


class WebSocketManager:
    """
    Manages WebSocket connections for real-time market data.
    Uses CCXT Pro if available, falls back to native WebSocket.
    """
    
    SUPPORTED_EXCHANGES = {
        'binance': 'binance',
        'bybit': 'bybit',
        'okx': 'okx',
        'kraken': 'kraken',
        'kucoin': 'kucoin',
        'gateio': 'gateio',
        'bitget': 'bitget',
    }
    
    def __init__(
        self,
        exchange_name: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = False
    ):
        self.exchange_name = exchange_name.lower()
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        self.exchange = None
        self.connected = False
        self.running = False
        
        # Data caches
        self.tickers: Dict[str, MarketTick] = {}
        self.order_books: Dict[str, OrderBookUpdate] = {}
        
        # Callbacks
        self.ticker_callbacks: List[Callable[[MarketTick], Any]] = []
        self.order_book_callbacks: List[Callable[[OrderBookUpdate], Any]] = []
        
        # Tasks
        self._tasks: List[asyncio.Task] = []
        self._subscribed_symbols: List[str] = []
        
        logger.info(f"WebSocketManager initialized for {exchange_name}")
    
    async def connect(self) -> bool:
        """Initialize WebSocket connection."""
        try:
            if not CCXT_PRO_AVAILABLE:
                logger.warning("CCXT Pro not available. Install with: pip install ccxt[pro]")
                return False
            
            exchange_class = getattr(ccxt_pro, self.exchange_name, None)
            if not exchange_class:
                logger.error(f"Exchange {self.exchange_name} not supported by CCXT Pro")
                return False
            
            config = {
                'enableRateLimit': True,
                'options': {
                    'adjustForTimeDifference': True,
                }
            }
            
            if self.api_key and self.api_secret:
                config['apiKey'] = self.api_key
                config['secret'] = self.api_secret
            
            if self.testnet:
                if self.exchange_name == 'binance':
                    config['options']['defaultType'] = 'future'
                    config['sandbox'] = True
                elif self.exchange_name == 'bybit':
                    config['options']['testnet'] = True
            
            self.exchange = exchange_class(config)
            await self.exchange.load_markets()
            
            self.connected = True
            logger.info(f"✅ WebSocket connected to {self.exchange_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect WebSocket: {e}")
            return False
    
    async def disconnect(self):
        """Close WebSocket connection."""
        self.running = False
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._tasks.clear()
        
        if self.exchange:
            await self.exchange.close()
            self.exchange = None
        
        self.connected = False
        logger.info("WebSocket disconnected")
    
    def on_ticker(self, callback: Callable[[MarketTick], Any]):
        """Register callback for ticker updates."""
        self.ticker_callbacks.append(callback)
    
    def on_order_book(self, callback: Callable[[OrderBookUpdate], Any]):
        """Register callback for order book updates."""
        self.order_book_callbacks.append(callback)
    
    async def subscribe_tickers(self, symbols: List[str]):
        """Subscribe to ticker updates for symbols."""
        if not self.connected:
            logger.warning("WebSocket not connected. Call connect() first.")
            return
        
        self._subscribed_symbols = symbols
        self.running = True
        
        task = asyncio.create_task(self._ticker_stream(symbols))
        self._tasks.append(task)
        logger.info(f"Subscribed to tickers: {symbols}")
    
    async def subscribe_order_books(self, symbols: List[str], depth: int = 10):
        """Subscribe to order book updates for symbols."""
        if not self.connected:
            logger.warning("WebSocket not connected. Call connect() first.")
            return
        
        self.running = True
        
        task = asyncio.create_task(self._order_book_stream(symbols, depth))
        self._tasks.append(task)
        logger.info(f"Subscribed to order books: {symbols}")
    
    async def _ticker_stream(self, symbols: List[str]):
        """Stream ticker data via WebSocket."""
        logger.info(f"Starting ticker stream for {len(symbols)} symbols")
        
        # P2-9 FIX: Exponential backoff for reconnection
        reconnect_attempts = 0
        MAX_RECONNECT_DELAY = 60  # Max 60 seconds between reconnects
        
        while self.running:
            try:
                # Watch multiple tickers at once
                tickers = await self.exchange.watch_tickers(symbols)
                
                # Reset reconnect counter on successful connection
                reconnect_attempts = 0
                
                for symbol, data in tickers.items():
                    tick = MarketTick(
                        symbol=symbol,
                        last_price=data.get('last', 0),
                        bid=data.get('bid', 0),
                        ask=data.get('ask', 0),
                        volume_24h=data.get('quoteVolume', data.get('baseVolume', 0)),
                        change_24h_percent=data.get('percentage', 0),
                        high_24h=data.get('high', 0),
                        low_24h=data.get('low', 0),
                        timestamp=datetime.now()
                    )
                    
                    # Update cache
                    self.tickers[symbol] = tick
                    
                    # Notify callbacks
                    for callback in self.ticker_callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(tick)
                            else:
                                callback(tick)
                        except Exception as e:
                            logger.error(f"Ticker callback error: {e}")
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ticker stream error: {e}")
                # P2-9 FIX: Exponential backoff with cap
                delay = min(1 * (2 ** reconnect_attempts), MAX_RECONNECT_DELAY)
                reconnect_attempts += 1
                logger.info(f"🔄 Reconnecting in {delay}s (attempt {reconnect_attempts})...")
                await asyncio.sleep(delay)
    
    async def _order_book_stream(self, symbols: List[str], depth: int):
        """Stream order book data via WebSocket."""
        logger.info(f"Starting order book stream for {len(symbols)} symbols")
        
        # P2-9 FIX: Exponential backoff for reconnection
        reconnect_attempts = 0
        MAX_RECONNECT_DELAY = 60  # Max 60 seconds between reconnects
        
        while self.running:
            try:
                for symbol in symbols:
                    order_book = await self.exchange.watch_order_book(symbol, depth)
                    
                    # Reset reconnect counter on successful connection
                    reconnect_attempts = 0
                    
                    update = OrderBookUpdate(
                        symbol=symbol,
                        bids=order_book.get('bids', [])[:depth],
                        asks=order_book.get('asks', [])[:depth],
                        timestamp=datetime.now()
                    )
                    
                    # Update cache
                    self.order_books[symbol] = update
                    
                    # Notify callbacks
                    for callback in self.order_book_callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(update)
                            else:
                                callback(update)
                        except Exception as e:
                            logger.error(f"Order book callback error: {e}")
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Order book stream error: {e}")
                # P2-9 FIX: Exponential backoff with cap
                delay = min(1 * (2 ** reconnect_attempts), MAX_RECONNECT_DELAY)
                reconnect_attempts += 1
                logger.info(f"🔄 Order book reconnecting in {delay}s (attempt {reconnect_attempts})...")
                await asyncio.sleep(delay)
    
    def get_ticker(self, symbol: str) -> Optional[MarketTick]:
        """Get latest ticker from cache."""
        return self.tickers.get(symbol)
    
    def get_all_tickers(self) -> Dict[str, MarketTick]:
        """Get all cached tickers."""
        return dict(self.tickers)
    
    def get_order_book(self, symbol: str) -> Optional[OrderBookUpdate]:
        """Get latest order book from cache."""
        return self.order_books.get(symbol)
    
    def get_spread(self, symbol: str) -> Optional[float]:
        """Get current spread for symbol."""
        tick = self.tickers.get(symbol)
        if tick and tick.bid and tick.ask:
            return (tick.ask - tick.bid) / tick.bid * 100
        return None
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.connected and self.running


class PositionMonitor:
    """
    Background position monitor that tracks SL/TP levels in real-time.
    Runs independently from main trading cycle.
    """
    
    def __init__(
        self,
        ws_manager: WebSocketManager,
        on_sl_triggered: Optional[Callable] = None,
        on_tp_triggered: Optional[Callable] = None
    ):
        self.ws_manager = ws_manager
        self.on_sl_triggered = on_sl_triggered
        self.on_tp_triggered = on_tp_triggered
        
        # Position tracking: symbol -> {side, entry, sl, tp, quantity}
        self.monitored_positions: Dict[str, Dict] = {}
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
        # Register for ticker updates
        self.ws_manager.on_ticker(self._check_positions)
        
        logger.info("PositionMonitor initialized")
    
    def add_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ):
        """Add a position to monitor."""
        self.monitored_positions[symbol] = {
            'side': side.lower(),
            'entry_price': entry_price,
            'quantity': quantity,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'created_at': datetime.now()
        }
        logger.info(f"📍 Monitoring position: {symbol} {side} @ {entry_price} | SL={stop_loss} TP={take_profit}")
    
    def remove_position(self, symbol: str):
        """Remove a position from monitoring."""
        if symbol in self.monitored_positions:
            del self.monitored_positions[symbol]
            logger.info(f"Removed position monitoring: {symbol}")
    
    def update_sl_tp(self, symbol: str, stop_loss: Optional[float] = None, take_profit: Optional[float] = None):
        """Update SL/TP for a position."""
        if symbol in self.monitored_positions:
            if stop_loss is not None:
                self.monitored_positions[symbol]['stop_loss'] = stop_loss
            if take_profit is not None:
                self.monitored_positions[symbol]['take_profit'] = take_profit
            logger.info(f"Updated SL/TP for {symbol}: SL={stop_loss} TP={take_profit}")
    
    async def _check_positions(self, tick: MarketTick):
        """Check positions against current price (called on each tick)."""
        symbol = tick.symbol
        
        if symbol not in self.monitored_positions:
            return
        
        pos = self.monitored_positions[symbol]
        current_price = tick.last_price
        side = pos['side']
        sl = pos.get('stop_loss')
        tp = pos.get('take_profit')
        
        # Check Stop Loss
        if sl:
            sl_triggered = False
            if side == 'long' and current_price <= sl:
                sl_triggered = True
            elif side == 'short' and current_price >= sl:
                sl_triggered = True
            
            if sl_triggered:
                logger.warning(f"🛑 STOP LOSS TRIGGERED: {symbol} @ {current_price} (SL={sl})")
                if self.on_sl_triggered:
                    await self._call_callback(self.on_sl_triggered, symbol, current_price, pos)
                self.remove_position(symbol)
                return
        
        # Check Take Profit
        if tp:
            tp_triggered = False
            if side == 'long' and current_price >= tp:
                tp_triggered = True
            elif side == 'short' and current_price <= tp:
                tp_triggered = True
            
            if tp_triggered:
                logger.info(f"✅ TAKE PROFIT TRIGGERED: {symbol} @ {current_price} (TP={tp})")
                if self.on_tp_triggered:
                    await self._call_callback(self.on_tp_triggered, symbol, current_price, pos)
                self.remove_position(symbol)
                return
    
    async def _call_callback(self, callback: Callable, symbol: str, price: float, position: Dict):
        """Call callback safely."""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(symbol, price, position)
            else:
                callback(symbol, price, position)
        except Exception as e:
            logger.error(f"Position monitor callback error: {e}")
    
    def get_monitored_positions(self) -> Dict[str, Dict]:
        """Get all monitored positions."""
        return dict(self.monitored_positions)
    
    def start(self):
        """Start the position monitor."""
        self.running = True
        logger.info("Position monitor started")
    
    def stop(self):
        """Stop the position monitor."""
        self.running = False
        logger.info("Position monitor stopped")
