"""Advanced Market Analyzer - Integration of SOFA, ASAE, and NNMP."""

import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from dataclasses import dataclass
import logging

from .order_flow import SmartOrderFlowAnalyzer, WhaleOrder
from .sentiment import AISentimentAnalyzer, SentimentSignal
from .neural_prediction import NeuralMarketPredictor, PredictionResult

logger = logging.getLogger(__name__)


@dataclass
class AdvancedSignal:
    """Combined signal from all analysis engines."""
    symbol: str
    action: str  # buy/sell/hold
    confidence: float  # 0-1
    strength: float  # 0-100
    timeframe: str  # immediate/short/medium/long
    
    # Component signals
    order_flow_signal: Optional[Dict] = None
    sentiment_signal: Optional[SentimentSignal] = None
    neural_prediction: Optional[PredictionResult] = None
    
    # Risk metrics
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size_percent: float = 1.0
    
    # Metadata
    timestamp: datetime = None
    reasons: List[str] = None


class AdvancedMarketAnalyzer:
    """
    Master analyzer combining SOFA, ASAE, and NNMP.
    Provides unified trading signals with high accuracy.
    """
    
    def __init__(self, config: Dict = None):
        """Initialize advanced analyzer."""
        self.config = config or {}
        
        # Initialize sub-analyzers
        self.order_flow = SmartOrderFlowAnalyzer(config)
        self.sentiment = AISentimentAnalyzer(config)
        self.neural = NeuralMarketPredictor(config)
        
        # Signal combination weights
        self.weights = {
            'order_flow': 0.35,
            'sentiment': 0.25,
            'neural': 0.40
        }
        
        # Signal history
        self.signal_history: Dict[str, List[AdvancedSignal]] = {}
        self.performance_metrics: Dict[str, Dict] = {}
        
    async def analyze_market(self, symbol: str, market_data: Dict) -> AdvancedSignal:
        """
        Perform comprehensive market analysis.
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            market_data: Dict containing:
                - order_book: Current order book
                - ohlcv: Historical OHLCV data (DataFrame)
                - trades: Recent trades
                
        Returns:
            AdvancedSignal with trading recommendation
        """
        try:
            # Run all analyses concurrently
            tasks = [
                self._analyze_order_flow(symbol, market_data.get('order_book', {})),
                self._analyze_sentiment(symbol),
                self._analyze_neural(symbol, market_data.get('ohlcv', pd.DataFrame()))
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            order_flow_result = results[0] if not isinstance(results[0], Exception) else None
            sentiment_result = results[1] if not isinstance(results[1], Exception) else None
            neural_result = results[2] if not isinstance(results[2], Exception) else None
            
            # Combine signals
            signal = self._combine_signals(
                symbol, order_flow_result, sentiment_result, neural_result
            )
            
            # Store signal history
            if symbol not in self.signal_history:
                self.signal_history[symbol] = []
            self.signal_history[symbol].append(signal)
            
            # Log signal
            logger.info(f"""
            Advanced Signal for {symbol}:
            Action: {signal.action} | Confidence: {signal.confidence:.2f}
            Strength: {signal.strength:.0f} | Timeframe: {signal.timeframe}
            Reasons: {', '.join(signal.reasons[:3])}
            """)
            
            return signal
            
        except Exception as e:
            logger.error(f"Error in advanced analysis for {symbol}: {e}")
            return self._create_neutral_signal(symbol)
    
    async def _analyze_order_flow(self, symbol: str, order_book: Dict) -> Optional[Dict]:
        """Analyze order flow."""
        if not order_book:
            return None
            
        try:
            result = await self.order_flow.analyze_order_book(symbol, order_book)
            return result
        except Exception as e:
            logger.error(f"Order flow analysis error: {e}")
            return None
    
    async def _analyze_sentiment(self, symbol: str) -> Optional[Dict]:
        """Analyze market sentiment."""
        try:
            result = await self.sentiment.analyze_sentiment(symbol)
            return result
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            return None
    
    async def _analyze_neural(self, symbol: str, ohlcv_data: pd.DataFrame) -> Optional[PredictionResult]:
        """Get neural network prediction."""
        if ohlcv_data.empty or len(ohlcv_data) < 200:
            return None
            
        try:
            result = await self.neural.predict(symbol, ohlcv_data)
            return result
        except Exception as e:
            logger.error(f"Neural prediction error: {e}")
            return None
    
    def _combine_signals(self, symbol: str, order_flow: Optional[Dict],
                        sentiment: Optional[Dict], 
                        neural: Optional[PredictionResult]) -> AdvancedSignal:
        """Combine all signals into unified trading signal."""
        
        # Initialize scores
        buy_score = 0
        sell_score = 0
        confidence_scores = []
        reasons = []
        
        # Process order flow signals
        if order_flow and 'signals' in order_flow:
            flow_signals = order_flow['signals']
            for signal in flow_signals:
                strength = signal.get('strength', 0) / 100
                if signal.get('action') == 'buy':
                    buy_score += strength * self.weights['order_flow']
                    reasons.append(f"Order Flow: {signal.get('reason', 'Bullish flow')}")
                elif signal.get('action') == 'sell':
                    sell_score += strength * self.weights['order_flow']
                    reasons.append(f"Order Flow: {signal.get('reason', 'Bearish flow')}")
                    
            # Check for whale activity
            if 'whale_orders' in order_flow:
                whale_orders = order_flow['whale_orders']
                buy_whales = len([w for w in whale_orders if w.side == 'buy'])
                sell_whales = len([w for w in whale_orders if w.side == 'sell'])
                
                if buy_whales > sell_whales:
                    buy_score += 0.2
                    reasons.append(f"{buy_whales} whale buy orders detected")
                elif sell_whales > buy_whales:
                    sell_score += 0.2
                    reasons.append(f"{sell_whales} whale sell orders detected")
        
        # Process sentiment signals
        if sentiment and 'signals' in sentiment:
            sent_signals = sentiment['signals']
            sentiment_score = sentiment.get('overall_sentiment', {}).get('score', 0) / 100
            
            if sentiment_score > 0.3:
                buy_score += abs(sentiment_score) * self.weights['sentiment']
                reasons.append(f"Sentiment: {sentiment['overall_sentiment']['mood']}")
            elif sentiment_score < -0.3:
                sell_score += abs(sentiment_score) * self.weights['sentiment']
                reasons.append(f"Sentiment: {sentiment['overall_sentiment']['mood']}")
                
            # Check for FOMO/FUD
            if 'social_metrics' in sentiment:
                metrics = sentiment['social_metrics']
                if metrics.fomo_index > 70:
                    sell_score += 0.1  # FOMO often indicates top
                    reasons.append("High FOMO detected (potential top)")
                elif metrics.fud_index > 70:
                    buy_score += 0.1  # FUD often indicates bottom
                    reasons.append("High FUD detected (potential bottom)")
        
        # Process neural prediction
        if neural:
            neural_confidence = neural.confidence
            if neural.direction == 'up':
                buy_score += neural_confidence * self.weights['neural']
                reasons.append(f"AI Prediction: +{neural.predicted_change_percent:.2f}% ({neural.timeframe})")
                confidence_scores.append(neural_confidence)
            elif neural.direction == 'down':
                sell_score += neural_confidence * self.weights['neural']
                reasons.append(f"AI Prediction: {neural.predicted_change_percent:.2f}% ({neural.timeframe})")
                confidence_scores.append(neural_confidence)
        
        # Determine action
        net_score = buy_score - sell_score
        threshold = 0.3
        
        if net_score > threshold:
            action = 'buy'
            strength = min(100, buy_score * 100)
        elif net_score < -threshold:
            action = 'sell'
            strength = min(100, sell_score * 100)
        else:
            action = 'hold'
            strength = 0
            
        # Calculate overall confidence
        if confidence_scores:
            base_confidence = np.mean(confidence_scores)
        else:
            base_confidence = 0.5
            
        # Adjust confidence based on signal agreement
        agreement_bonus = 0
        if (order_flow and sentiment and neural):
            # Check if all signals agree
            flow_action = self._get_dominant_action(order_flow.get('signals', []))
            sent_mood = sentiment.get('overall_sentiment', {}).get('mood', 'Neutral')
            neural_dir = neural.direction if neural else 'neutral'
            
            if (flow_action == 'buy' and 'Bullish' in sent_mood and neural_dir == 'up'):
                agreement_bonus = 0.2
                reasons.insert(0, "Strong consensus across all indicators")
            elif (flow_action == 'sell' and 'Bearish' in sent_mood and neural_dir == 'down'):
                agreement_bonus = 0.2
                reasons.insert(0, "Strong consensus across all indicators")
        
        final_confidence = min(0.95, base_confidence + agreement_bonus)
        
        # Determine timeframe
        timeframe = self._determine_timeframe(order_flow, sentiment, neural)
        
        # Calculate risk parameters
        stop_loss, take_profit = self._calculate_risk_params(
            symbol, action, neural, order_flow
        )
        
        # Position sizing based on confidence
        position_size = self._calculate_position_size(final_confidence, strength)
        
        return AdvancedSignal(
            symbol=symbol,
            action=action,
            confidence=final_confidence,
            strength=strength,
            timeframe=timeframe,
            order_flow_signal=order_flow,
            sentiment_signal=sentiment.get('signals')[0] if sentiment and sentiment.get('signals') else None,
            neural_prediction=neural,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size_percent=position_size,
            timestamp=datetime.now(),
            reasons=reasons[:5]  # Top 5 reasons
        )
    
    def _get_dominant_action(self, signals: List[Dict]) -> str:
        """Get dominant action from signal list."""
        if not signals:
            return 'hold'
            
        buy_strength = sum(s.get('strength', 0) for s in signals if s.get('action') == 'buy')
        sell_strength = sum(s.get('strength', 0) for s in signals if s.get('action') == 'sell')
        
        if buy_strength > sell_strength:
            return 'buy'
        elif sell_strength > buy_strength:
            return 'sell'
        return 'hold'
    
    def _determine_timeframe(self, order_flow: Optional[Dict],
                           sentiment: Optional[Dict],
                           neural: Optional[PredictionResult]) -> str:
        """Determine signal timeframe."""
        timeframes = []
        
        if order_flow and 'signals' in order_flow:
            for signal in order_flow['signals']:
                timeframes.append(signal.get('timeframe', 'medium'))
                
        if neural:
            timeframes.append(neural.timeframe)
            
        # Most common timeframe
        if not timeframes:
            return 'medium'
            
        timeframe_priority = {'immediate': 0, 'short': 1, 'medium': 2, 'long': 3}
        sorted_timeframes = sorted(timeframes, key=lambda x: timeframe_priority.get(x, 2))
        
        return sorted_timeframes[0]  # Return most urgent timeframe
    
    def _calculate_risk_params(self, symbol: str, action: str,
                             neural: Optional[PredictionResult],
                             order_flow: Optional[Dict]) -> Tuple[float, float]:
        """Calculate stop loss and take profit levels."""
        # Get current price (simplified - in production would get from market data)
        current_price = 50000 if 'BTC' in symbol else 3000 if 'ETH' in symbol else 100
        
        # Base risk parameters
        if action == 'buy':
            base_stop_loss = current_price * 0.98  # 2% stop loss
            base_take_profit = current_price * 1.05  # 5% take profit
        elif action == 'sell':
            base_stop_loss = current_price * 1.02
            base_take_profit = current_price * 0.95
        else:
            return None, None
            
        # Adjust based on neural prediction
        if neural:
            if neural.support_levels and action == 'buy':
                # Place stop below nearest support
                base_stop_loss = min(base_stop_loss, neural.support_levels[-1] * 0.995)
            elif neural.resistance_levels and action == 'sell':
                # Place stop above nearest resistance
                base_stop_loss = max(base_stop_loss, neural.resistance_levels[0] * 1.005)
                
            # Adjust take profit based on prediction magnitude
            if abs(neural.predicted_change_percent) > 3:
                profit_multiplier = 1.5
            else:
                profit_multiplier = 1.0
                
            if action == 'buy':
                base_take_profit = current_price * (1 + 0.05 * profit_multiplier)
            else:
                base_take_profit = current_price * (1 - 0.05 * profit_multiplier)
        
        return base_stop_loss, base_take_profit
    
    def _calculate_position_size(self, confidence: float, strength: float) -> float:
        """Calculate position size as percentage of capital."""
        # Base size
        base_size = 2.0  # 2% base position
        
        # Adjust for confidence
        confidence_multiplier = confidence * 2  # 0-2x
        
        # Adjust for strength
        strength_multiplier = (strength / 100) * 1.5  # 0-1.5x
        
        # Final position size
        position_size = base_size * confidence_multiplier * strength_multiplier
        
        # Cap at 10% max position
        return min(10.0, position_size)
    
    def _create_neutral_signal(self, symbol: str) -> AdvancedSignal:
        """Create neutral signal when analysis fails."""
        return AdvancedSignal(
            symbol=symbol,
            action='hold',
            confidence=0.5,
            strength=0,
            timeframe='medium',
            timestamp=datetime.now(),
            reasons=['Insufficient data for analysis']
        )
    
    async def get_top_opportunities(self, symbols: List[str], 
                                  market_data: Dict[str, Dict]) -> List[AdvancedSignal]:
        """Analyze multiple symbols and return top opportunities."""
        signals = []
        
        # Analyze all symbols concurrently
        tasks = [
            self.analyze_market(symbol, market_data.get(symbol, {}))
            for symbol in symbols
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter valid signals
        for result in results:
            if isinstance(result, AdvancedSignal) and result.action != 'hold':
                signals.append(result)
        
        # Sort by confidence and strength
        signals.sort(key=lambda x: x.confidence * x.strength, reverse=True)
        
        return signals[:5]  # Top 5 opportunities
    
    def get_performance_stats(self, symbol: Optional[str] = None) -> Dict:
        """Get performance statistics for signals."""
        if symbol:
            history = self.signal_history.get(symbol, [])
        else:
            history = []
            for signals in self.signal_history.values():
                history.extend(signals)
        
        if not history:
            return {}
        
        total_signals = len(history)
        buy_signals = len([s for s in history if s.action == 'buy'])
        sell_signals = len([s for s in history if s.action == 'sell'])
        
        avg_confidence = np.mean([s.confidence for s in history])
        avg_strength = np.mean([s.strength for s in history if s.strength > 0])
        
        # Success rate would be calculated by tracking actual outcomes
        # This is a placeholder
        success_rate = 0.65 + (avg_confidence - 0.5) * 0.3  # Simulated
        
        return {
            'total_signals': total_signals,
            'buy_signals': buy_signals,
            'sell_signals': sell_signals,
            'avg_confidence': avg_confidence,
            'avg_strength': avg_strength,
            'estimated_success_rate': success_rate,
            'last_signal': history[-1].timestamp if history else None
        }
    
    async def real_time_monitor(self, symbol: str, callback):
        """Monitor symbol in real-time and call callback on signals."""
        logger.info(f"Starting real-time monitoring for {symbol}")
        
        while True:
            try:
                # In production, this would get real-time data
                # For now, simulate with placeholder
                market_data = {
                    'order_book': {},  # Would be filled with real order book
                    'ohlcv': pd.DataFrame(),  # Would be real OHLCV data
                    'trades': []  # Would be recent trades
                }
                
                # Analyze market
                signal = await self.analyze_market(symbol, market_data)
                
                # Call callback if actionable signal
                if signal.action != 'hold' and signal.confidence > 0.7:
                    await callback(signal)
                
                # Wait before next analysis
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in real-time monitoring: {e}")
                await asyncio.sleep(60)  # Wait longer on error
