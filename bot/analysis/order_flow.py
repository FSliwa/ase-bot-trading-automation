"""Smart Order Flow Analysis (SOFA) - Whale Detection and Order Flow Analysis."""

import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class WhaleOrder:
    """Represents a detected whale order."""
    symbol: str
    side: str  # buy/sell
    size: float
    price: float
    timestamp: datetime
    impact_score: float  # 0-100
    confidence: float  # 0-1
    exchange: str
    order_type: str  # market/limit
    

@dataclass
class OrderFlowMetrics:
    """Order flow analysis metrics."""
    buy_volume: float
    sell_volume: float
    buy_count: int
    sell_count: int
    avg_buy_size: float
    avg_sell_size: float
    imbalance_ratio: float  # buy/sell ratio
    large_order_ratio: float  # whale orders / total orders
    momentum_score: float  # -100 to +100


class SmartOrderFlowAnalyzer:
    """
    Smart Order Flow Analysis (SOFA) Engine.
    Detects whale activity, hidden orders, and market maker behavior.
    """
    
    def __init__(self, config: Dict = None):
        """Initialize SOFA analyzer."""
        self.config = config or {}
        
        # Whale detection thresholds
        self.whale_thresholds = {
            "BTC/USDT": 10.0,      # 10 BTC
            "ETH/USDT": 100.0,     # 100 ETH
            "default": 50000.0     # $50k USD equivalent
        }
        
        # Detection parameters
        self.min_whale_confidence = 0.7
        self.order_book_depth = 50
        self.time_window = 300  # 5 minutes
        
        # Storage
        self.order_history: Dict[str, List[Dict]] = {}
        self.whale_alerts: List[WhaleOrder] = []
        self.market_maker_patterns: Dict[str, Dict] = {}
        
    async def analyze_order_book(self, symbol: str, order_book: Dict) -> Dict:
        """
        Analyze order book for whale activity and imbalances.
        
        Returns:
            Analysis results with whale detection and flow metrics
        """
        try:
            # Extract bids and asks
            bids = order_book.get('bids', [])
            asks = order_book.get('asks', [])
            
            # Detect whale orders
            whale_orders = self._detect_whale_orders(symbol, bids, asks)
            
            # Calculate order flow metrics
            flow_metrics = self._calculate_flow_metrics(bids, asks)
            
            # Detect hidden/iceberg orders
            hidden_orders = self._detect_hidden_orders(symbol, order_book)
            
            # Analyze market maker activity
            mm_activity = self._analyze_market_maker_activity(symbol, order_book)
            
            # Calculate price impact prediction
            price_impact = self._predict_price_impact(whale_orders, flow_metrics)
            
            # Generate trading signals
            signals = self._generate_signals(
                whale_orders, flow_metrics, hidden_orders, mm_activity
            )
            
            return {
                "whale_orders": whale_orders,
                "flow_metrics": flow_metrics,
                "hidden_orders": hidden_orders,
                "market_maker_activity": mm_activity,
                "price_impact": price_impact,
                "signals": signals,
                "timestamp": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing order book for {symbol}: {e}")
            return {}
    
    def _detect_whale_orders(self, symbol: str, bids: List, asks: List) -> List[WhaleOrder]:
        """Detect whale orders in the order book."""
        whale_orders = []
        threshold = self.whale_thresholds.get(symbol, self.whale_thresholds["default"])
        
        # Analyze bids
        for bid in bids[:self.order_book_depth]:
            price, size = float(bid[0]), float(bid[1])
            value = price * size
            
            if self._is_whale_order(symbol, size, value, threshold):
                whale = WhaleOrder(
                    symbol=symbol,
                    side="buy",
                    size=size,
                    price=price,
                    timestamp=datetime.now(),
                    impact_score=self._calculate_impact_score(value, "buy"),
                    confidence=self._calculate_whale_confidence(size, value, bids),
                    exchange="current",
                    order_type="limit"
                )
                whale_orders.append(whale)
        
        # Analyze asks
        for ask in asks[:self.order_book_depth]:
            price, size = float(ask[0]), float(ask[1])
            value = price * size
            
            if self._is_whale_order(symbol, size, value, threshold):
                whale = WhaleOrder(
                    symbol=symbol,
                    side="sell",
                    size=size,
                    price=price,
                    timestamp=datetime.now(),
                    impact_score=self._calculate_impact_score(value, "sell"),
                    confidence=self._calculate_whale_confidence(size, value, asks),
                    exchange="current",
                    order_type="limit"
                )
                whale_orders.append(whale)
        
        return whale_orders
    
    def _is_whale_order(self, symbol: str, size: float, value: float, threshold: float) -> bool:
        """Check if order qualifies as whale order."""
        if "BTC" in symbol:
            return size >= threshold
        elif "ETH" in symbol:
            return size >= threshold
        else:
            return value >= threshold
    
    def _calculate_impact_score(self, value: float, side: str) -> float:
        """Calculate potential market impact score (0-100)."""
        # Base impact on order value
        if value < 100000:
            base_score = 20
        elif value < 500000:
            base_score = 40
        elif value < 1000000:
            base_score = 60
        elif value < 5000000:
            base_score = 80
        else:
            base_score = 100
            
        # Adjust for side (sells typically have more impact)
        if side == "sell":
            base_score *= 1.2
            
        return min(100, base_score)
    
    def _calculate_whale_confidence(self, size: float, value: float, orders: List) -> float:
        """Calculate confidence that this is a real whale order."""
        # Factors: size relative to other orders, round numbers, positioning
        
        # Check if size is significantly larger than average
        avg_size = np.mean([float(order[1]) for order in orders[:20]])
        size_factor = min(1.0, size / (avg_size * 10))
        
        # Check for round numbers (often real whales)
        round_factor = 1.0 if size % 10 == 0 or size % 100 == 0 else 0.8
        
        # Check positioning (real whales often not at exact market)
        position_factor = 0.9  # Can be refined based on distance from market
        
        confidence = (size_factor * 0.5 + round_factor * 0.3 + position_factor * 0.2)
        return confidence
    
    def _calculate_flow_metrics(self, bids: List, asks: List) -> OrderFlowMetrics:
        """Calculate order flow metrics."""
        # Calculate volumes
        buy_volume = sum(float(bid[0]) * float(bid[1]) for bid in bids[:self.order_book_depth])
        sell_volume = sum(float(ask[0]) * float(ask[1]) for ask in asks[:self.order_book_depth])
        
        # Count orders
        buy_count = len(bids[:self.order_book_depth])
        sell_count = len(asks[:self.order_book_depth])
        
        # Average sizes
        avg_buy_size = buy_volume / buy_count if buy_count > 0 else 0
        avg_sell_size = sell_volume / sell_count if sell_count > 0 else 0
        
        # Imbalance ratio
        total_volume = buy_volume + sell_volume
        imbalance_ratio = buy_volume / sell_volume if sell_volume > 0 else 2.0
        
        # Large order ratio (orders > 5x average)
        large_buy_orders = sum(1 for bid in bids if float(bid[1]) > avg_buy_size * 5)
        large_sell_orders = sum(1 for ask in asks if float(ask[1]) > avg_sell_size * 5)
        large_order_ratio = (large_buy_orders + large_sell_orders) / (buy_count + sell_count)
        
        # Momentum score
        momentum_score = ((buy_volume - sell_volume) / total_volume * 100) if total_volume > 0 else 0
        
        return OrderFlowMetrics(
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            buy_count=buy_count,
            sell_count=sell_count,
            avg_buy_size=avg_buy_size,
            avg_sell_size=avg_sell_size,
            imbalance_ratio=imbalance_ratio,
            large_order_ratio=large_order_ratio,
            momentum_score=momentum_score
        )
    
    def _detect_hidden_orders(self, symbol: str, order_book: Dict) -> List[Dict]:
        """Detect potential hidden/iceberg orders."""
        hidden_orders = []
        
        # Look for patterns indicating hidden orders:
        # 1. Consistent refills at same price level
        # 2. Orders that seem to absorb market orders without moving
        # 3. Unusual patterns in order sizes
        
        # This is a simplified detection - real implementation would track
        # order book changes over time
        
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        
        # Check for suspiciously consistent order sizes (potential icebergs)
        for i in range(min(10, len(bids)-1)):
            if abs(float(bids[i][1]) - float(bids[i+1][1])) < 0.01:
                hidden_orders.append({
                    "type": "potential_iceberg",
                    "side": "buy",
                    "price": float(bids[i][0]),
                    "visible_size": float(bids[i][1]),
                    "confidence": 0.6
                })
        
        return hidden_orders
    
    def _analyze_market_maker_activity(self, symbol: str, order_book: Dict) -> Dict:
        """Analyze market maker activity patterns."""
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        
        if not bids or not asks:
            return {}
        
        # Calculate spread
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        spread = best_ask - best_bid
        spread_percentage = (spread / best_bid) * 100
        
        # Look for market maker patterns
        # 1. Tight spreads with balanced volumes
        # 2. Multiple orders at regular intervals
        # 3. Quick order replacements
        
        # Check for regular price intervals (market maker grids)
        bid_intervals = []
        ask_intervals = []
        
        for i in range(min(5, len(bids)-1)):
            interval = float(bids[i][0]) - float(bids[i+1][0])
            bid_intervals.append(interval)
            
        for i in range(min(5, len(asks)-1)):
            interval = float(asks[i+1][0]) - float(asks[i][0])
            ask_intervals.append(interval)
        
        # Regular intervals suggest market maker
        bid_regularity = np.std(bid_intervals) if bid_intervals else float('inf')
        ask_regularity = np.std(ask_intervals) if ask_intervals else float('inf')
        
        is_market_maker_active = (
            spread_percentage < 0.1 and  # Tight spread
            bid_regularity < 0.001 and   # Regular intervals
            ask_regularity < 0.001
        )
        
        return {
            "spread": spread,
            "spread_percentage": spread_percentage,
            "is_active": is_market_maker_active,
            "bid_regularity": bid_regularity,
            "ask_regularity": ask_regularity,
            "confidence": 0.8 if is_market_maker_active else 0.2
        }
    
    def _predict_price_impact(self, whale_orders: List[WhaleOrder], 
                            flow_metrics: OrderFlowMetrics) -> Dict:
        """Predict price impact of detected whale orders."""
        if not whale_orders:
            return {"direction": "neutral", "magnitude": 0, "timeframe": "none"}
        
        # Calculate net whale pressure
        buy_pressure = sum(w.size * w.price for w in whale_orders if w.side == "buy")
        sell_pressure = sum(w.size * w.price for w in whale_orders if w.side == "sell")
        net_pressure = buy_pressure - sell_pressure
        
        # Determine direction and magnitude
        if net_pressure > 0:
            direction = "up"
            magnitude = min(5.0, (net_pressure / (buy_pressure + sell_pressure)) * 10)
        elif net_pressure < 0:
            direction = "down"
            magnitude = min(5.0, abs(net_pressure / (buy_pressure + sell_pressure)) * 10)
        else:
            direction = "neutral"
            magnitude = 0
        
        # Estimate timeframe based on order types and market momentum
        if magnitude > 3:
            timeframe = "immediate"  # Within 5 minutes
        elif magnitude > 1:
            timeframe = "short"      # Within 30 minutes
        else:
            timeframe = "medium"     # Within 2 hours
        
        return {
            "direction": direction,
            "magnitude": magnitude,  # Percentage move expected
            "timeframe": timeframe,
            "confidence": min(whale_orders[0].confidence, 0.85) if whale_orders else 0
        }
    
    def _generate_signals(self, whale_orders: List[WhaleOrder], 
                         flow_metrics: OrderFlowMetrics,
                         hidden_orders: List[Dict], 
                         mm_activity: Dict) -> List[Dict]:
        """Generate trading signals based on order flow analysis."""
        signals = []
        
        # Signal 1: Strong whale accumulation
        buy_whales = [w for w in whale_orders if w.side == "buy" and w.confidence > 0.8]
        if len(buy_whales) >= 2 and flow_metrics.momentum_score > 30:
            signals.append({
                "type": "whale_accumulation",
                "action": "buy",
                "strength": min(100, len(buy_whales) * 30),
                "reason": f"{len(buy_whales)} whale buy orders detected",
                "timeframe": "immediate"
            })
        
        # Signal 2: Whale distribution
        sell_whales = [w for w in whale_orders if w.side == "sell" and w.confidence > 0.8]
        if len(sell_whales) >= 2 and flow_metrics.momentum_score < -30:
            signals.append({
                "type": "whale_distribution", 
                "action": "sell",
                "strength": min(100, len(sell_whales) * 30),
                "reason": f"{len(sell_whales)} whale sell orders detected",
                "timeframe": "immediate"
            })
        
        # Signal 3: Order flow imbalance
        if flow_metrics.imbalance_ratio > 2.0:
            signals.append({
                "type": "flow_imbalance",
                "action": "buy",
                "strength": min(80, flow_metrics.imbalance_ratio * 20),
                "reason": "Strong buy-side order flow imbalance",
                "timeframe": "short"
            })
        elif flow_metrics.imbalance_ratio < 0.5:
            signals.append({
                "type": "flow_imbalance",
                "action": "sell", 
                "strength": min(80, (1/flow_metrics.imbalance_ratio) * 20),
                "reason": "Strong sell-side order flow imbalance",
                "timeframe": "short"
            })
        
        # Signal 4: Hidden accumulation
        if hidden_orders and flow_metrics.momentum_score > 0:
            signals.append({
                "type": "hidden_accumulation",
                "action": "buy",
                "strength": 60,
                "reason": "Hidden orders detected with positive momentum",
                "timeframe": "medium"
            })
        
        return signals
    
    async def track_order_execution(self, symbol: str, trades: List[Dict]) -> Dict:
        """Track order execution to validate whale detection."""
        # Store trade history
        if symbol not in self.order_history:
            self.order_history[symbol] = []
            
        self.order_history[symbol].extend(trades)
        
        # Keep only recent history (last 30 minutes)
        cutoff_time = datetime.now() - timedelta(minutes=30)
        self.order_history[symbol] = [
            t for t in self.order_history[symbol] 
            if datetime.fromisoformat(t.get('timestamp', '')) > cutoff_time
        ]
        
        # Analyze execution patterns
        large_trades = [t for t in trades if float(t.get('amount', 0)) > 10000]
        
        return {
            "large_trades_count": len(large_trades),
            "total_volume": sum(float(t.get('amount', 0)) for t in trades),
            "whale_trades": large_trades
        }
    
    def get_whale_alerts(self, symbol: Optional[str] = None) -> List[WhaleOrder]:
        """Get recent whale alerts."""
        if symbol:
            return [w for w in self.whale_alerts if w.symbol == symbol]
        return self.whale_alerts
    
    def clear_old_alerts(self, minutes: int = 60):
        """Clear whale alerts older than specified minutes."""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        self.whale_alerts = [w for w in self.whale_alerts if w.timestamp > cutoff_time]
