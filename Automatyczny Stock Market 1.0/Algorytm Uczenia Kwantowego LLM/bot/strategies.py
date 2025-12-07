from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .broker.paper import PaperBroker
from .config import AppConfig
from .parser import TradeIntent


@dataclass
class Signal:
    """Trading signal from a strategy."""
    action: str  # "buy", "sell", "close", "hold"
    symbol: str
    quantity: float
    order_type: str  # "market", "limit"
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    leverage: Optional[float] = None
    reason: str = ""
    confidence: float = 0.5  # 0-1


@dataclass
class MarketData:
    """Simplified market data for strategies."""
    symbol: str
    current_price: float
    high_24h: float
    low_24h: float
    volume_24h: float
    change_24h_percent: float
    timestamp: datetime


class TradingStrategy(ABC):
    """Base class for all trading strategies."""
    
    def __init__(self, name: str, symbols: List[str], config: AppConfig):
        self.name = name
        self.symbols = symbols
        self.config = config
        self.active = True
        
    @abstractmethod
    def analyze(self, market_data: Dict[str, MarketData], positions: Dict) -> List[Signal]:
        """Analyze market and return trading signals."""
        pass
        
    def validate_signal(self, signal: Signal) -> bool:
        """Basic signal validation."""
        if signal.quantity <= 0:
            return False
        if signal.order_type == "limit" and signal.price is None:
            return False
        return True


class MomentumStrategy(TradingStrategy):
    """Simple momentum strategy - buy on uptrend, sell on downtrend."""
    
    def __init__(self, symbols: List[str], config: AppConfig, threshold: float = 2.0):
        super().__init__("Momentum", symbols, config)
        self.threshold = threshold  # % change threshold
        
    def analyze(self, market_data: Dict[str, MarketData], positions: Dict) -> List[Signal]:
        signals = []
        
        for symbol in self.symbols:
            if symbol not in market_data:
                continue
                
            data = market_data[symbol]
            has_position = symbol in positions
            
            # Buy signal: positive momentum above threshold
            if data.change_24h_percent > self.threshold and not has_position:
                signal = Signal(
                    action="buy",
                    symbol=symbol,
                    quantity=0.01,  # Fixed small size for MVP
                    order_type="market",
                    stop_loss=data.current_price * 0.97,  # 3% stop loss
                    take_profit=data.current_price * 1.05,  # 5% take profit
                    leverage=2.0,
                    reason=f"Momentum up {data.change_24h_percent:.1f}%",
                    confidence=min(0.5 + (data.change_24h_percent / 10), 0.9)
                )
                signals.append(signal)
                
            # Sell signal: negative momentum below threshold
            elif data.change_24h_percent < -self.threshold and has_position:
                signal = Signal(
                    action="close",
                    symbol=symbol,
                    quantity=positions[symbol].quantity,
                    order_type="market",
                    reason=f"Momentum down {data.change_24h_percent:.1f}%",
                    confidence=min(0.5 + (abs(data.change_24h_percent) / 10), 0.9)
                )
                signals.append(signal)
                
        return [s for s in signals if self.validate_signal(s)]


class MeanReversionStrategy(TradingStrategy):
    """Mean reversion - buy oversold, sell overbought."""
    
    def __init__(self, symbols: List[str], config: AppConfig, band_width: float = 0.02):
        super().__init__("MeanReversion", symbols, config)
        self.band_width = band_width  # 2% bands
        
    def analyze(self, market_data: Dict[str, MarketData], positions: Dict) -> List[Signal]:
        signals = []
        
        for symbol in self.symbols:
            if symbol not in market_data:
                continue
                
            data = market_data[symbol]
            has_position = symbol in positions
            
            # Calculate simple bands
            mid_price = (data.high_24h + data.low_24h) / 2
            lower_band = mid_price * (1 - self.band_width)
            upper_band = mid_price * (1 + self.band_width)
            
            # Buy at lower band
            if data.current_price <= lower_band and not has_position:
                signal = Signal(
                    action="buy",
                    symbol=symbol,
                    quantity=0.01,
                    order_type="limit",
                    price=data.current_price,
                    stop_loss=data.current_price * 0.98,
                    take_profit=mid_price,
                    leverage=1.5,
                    reason=f"Oversold at lower band",
                    confidence=0.6
                )
                signals.append(signal)
                
            # Sell at upper band
            elif data.current_price >= upper_band and has_position:
                signal = Signal(
                    action="close",
                    symbol=symbol,
                    quantity=positions[symbol].quantity,
                    order_type="market",
                    reason=f"Overbought at upper band",
                    confidence=0.6
                )
                signals.append(signal)
                
        return [s for s in signals if self.validate_signal(s)]


class GridTradingStrategy(TradingStrategy):
    """Grid trading - place orders at regular intervals."""
    
    def __init__(self, symbols: List[str], config: AppConfig, grid_size: float = 0.01, levels: int = 5):
        super().__init__("GridTrading", symbols, config)
        self.grid_size = grid_size  # 1% between levels
        self.levels = levels
        self.grids: Dict[str, List[float]] = {}
        
    def analyze(self, market_data: Dict[str, MarketData], positions: Dict) -> List[Signal]:
        signals = []
        
        for symbol in self.symbols:
            if symbol not in market_data:
                continue
                
            data = market_data[symbol]
            
            # Initialize grid if needed
            if symbol not in self.grids:
                self.grids[symbol] = self._create_grid(data.current_price)
                
            # Check each grid level
            for i, level in enumerate(self.grids[symbol]):
                # Buy below current price
                if level < data.current_price * 0.99:
                    signal = Signal(
                        action="buy",
                        symbol=symbol,
                        quantity=0.005,  # Smaller size for grid
                        order_type="limit",
                        price=level,
                        stop_loss=level * 0.98,
                        leverage=1.0,
                        reason=f"Grid buy level {i+1}",
                        confidence=0.5
                    )
                    signals.append(signal)
                    
        return [s for s in signals if self.validate_signal(s)][:3]  # Limit orders per cycle
        
    def _create_grid(self, current_price: float) -> List[float]:
        """Create grid levels around current price."""
        levels = []
        for i in range(1, self.levels + 1):
            levels.append(current_price * (1 - self.grid_size * i))
            levels.append(current_price * (1 + self.grid_size * i))
        return sorted(levels)


class AIStrategy(TradingStrategy):
    """Strategy that executes signals from AI analysis."""
    
    def __init__(self, symbols: List[str], config: AppConfig):
        super().__init__("AIStrategy", symbols, config)
        self.latest_signals: Dict[str, Dict] = {}
        
    def update_signals(self, ai_analyses: List[Dict]):
        """Update the latest AI signals."""
        self.latest_signals.clear()
        if not ai_analyses:
            return
            
        for analysis in ai_analyses:
            symbol = analysis.get('symbol')
            if symbol:
                self.latest_signals[symbol] = analysis
                
    def analyze(self, market_data: Dict[str, MarketData], positions: Dict) -> List[Signal]:
        signals = []
        
        for symbol in self.symbols:
            # Skip if no AI analysis for this symbol
            if symbol not in self.latest_signals:
                continue
                
            analysis = self.latest_signals[symbol]
            action = analysis.get('action', 'hold').lower()
            
            # Skip HOLD signals
            if action == 'hold':
                continue
                
            has_position = symbol in positions
            
            # Map AI action to Signal action
            signal_action = None
            if action == 'buy' and not has_position:
                signal_action = 'buy'
            elif action == 'sell' and has_position:
                signal_action = 'close' # or 'sell' if shorting supported
            
            if signal_action:
                # Use confidence to determine quantity or leverage if desired
                confidence = float(analysis.get('confidence', 0.5))
                
                # Default quantity logic (can be enhanced)
                quantity = 0.01 # Base quantity
                
                signal = Signal(
                    action=signal_action,
                    symbol=symbol,
                    quantity=quantity,
                    order_type="market",
                    reason=f"AI Signal: {analysis.get('reasoning', 'No reasoning')}",
                    confidence=confidence
                )
                
                # Add targets if available
                targets = analysis.get('targets', [])
                if targets:
                    signal.take_profit = float(targets[0])
                    
                signals.append(signal)
                
        return [s for s in signals if self.validate_signal(s)]


class AutoTradingEngine:
    """Automatic trading engine that runs strategies."""
    
    def __init__(self, broker: PaperBroker, config: AppConfig):
        self.broker = broker
        self.config = config
        self.strategies: List[TradingStrategy] = []
        self.active = False
        self.last_run = datetime.now()
        self.trade_history: List[Tuple[datetime, Signal]] = []
        
    def add_strategy(self, strategy: TradingStrategy) -> None:
        """Add a strategy to the engine."""
        self.strategies.append(strategy)
        
    def remove_strategy(self, name: str) -> None:
        """Remove a strategy by name."""
        self.strategies = [s for s in self.strategies if s.name != name]
        
    def get_mock_market_data(self) -> Dict[str, MarketData]:
        """Generate mock market data for testing."""
        # In production, this would fetch real market data
        symbols = ["BTCUSDT", "ETHUSD", "BNBUSDT"]
        market_data = {}
        
        for symbol in symbols:
            base_price = {
                "BTCUSDT": 60000,
                "ETHUSD": 3000,
                "BNBUSDT": 400
            }.get(symbol, 100)
            
            # Simulate price movements
            change = random.uniform(-5, 5)
            current = base_price * (1 + change / 100)
            
            market_data[symbol] = MarketData(
                symbol=symbol,
                current_price=current,
                high_24h=current * 1.02,
                low_24h=current * 0.98,
                volume_24h=random.uniform(1000000, 10000000),
                change_24h_percent=change,
                timestamp=datetime.now()
            )
            
        return market_data
        
    async def run_cycle(self) -> List[Signal]:
        """Run one trading cycle - analyze and execute signals."""
        if not self.active:
            return []
            
        executed_signals = []
        market_data = self.get_mock_market_data()
        
        # Handle async vs sync broker
        if hasattr(self.broker, 'client'):
             positions = await self.broker.get_positions()
        else:
             positions = self.broker.get_positions()
        
        # Collect signals from all strategies
        all_signals = []
        for strategy in self.strategies:
            if strategy.active:
                signals = strategy.analyze(market_data, positions)
                all_signals.extend(signals)
                
        # Sort by confidence and execute top signals
        all_signals.sort(key=lambda s: s.confidence, reverse=True)
        
        for signal in all_signals[:5]:  # Limit concurrent trades
            try:
                if signal.action == "buy":
                    # Check if it's LiveBroker (async) or PaperBroker (sync)
                    if hasattr(self.broker, 'client'):
                        # LiveBroker - run async method
                        await self.broker.place_order(
                            side="buy",
                            symbol=signal.symbol,
                            order_type=signal.order_type,
                            quantity=signal.quantity,
                            market_price=market_data[signal.symbol].current_price,
                            price=signal.price,
                            stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit,
                            leverage=signal.leverage
                        )
                    else:
                        # PaperBroker - sync method
                        self.broker.place_order(
                            side="buy",
                            symbol=signal.symbol,
                            order_type=signal.order_type,
                            quantity=signal.quantity,
                            market_price=market_data[signal.symbol].current_price,
                            price=signal.price,
                            stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit,
                            leverage=signal.leverage
                        )
                    executed_signals.append(signal)
                    self.trade_history.append((datetime.now(), signal))
                    
                elif signal.action == "close":
                    if hasattr(self.broker, 'client'):
                        await self.broker.close_position(symbol=signal.symbol)
                    else:
                        self.broker.close_position(symbol=signal.symbol)
                    executed_signals.append(signal)
                    self.trade_history.append((datetime.now(), signal))
                    
            except Exception as e:
                print(f"Failed to execute signal: {e}")
                
        self.last_run = datetime.now()
        return executed_signals
        
    def get_status(self) -> Dict:
        """Get engine status."""
        return {
            "active": self.active,
            "strategies": [s.name for s in self.strategies],
            "last_run": self.last_run.isoformat(),
            "trade_count": len(self.trade_history)
        }
