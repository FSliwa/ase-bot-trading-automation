"""
Signal Validator Service - Validates trading signals using historical data.

ISOLATION: This service is stateless and does not affect global application state.
IMMUTABILITY: All operations return new objects, never mutate input data.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging

from bot.db import extract_base_symbol

# Import DB timeout utilities
try:
    from bot.core.db_timeout import (
        safe_db_query,
        DBTimeoutError,
        DEFAULT_DB_TIMEOUT_SHORT
    )
    DB_TIMEOUT_AVAILABLE = True
except ImportError:
    DB_TIMEOUT_AVAILABLE = False
    DEFAULT_DB_TIMEOUT_SHORT = 10

logger = logging.getLogger(__name__)


@dataclass(frozen=True)  # Immutable by design
class SignalValidation:
    """Immutable validation result for a trading signal."""
    symbol: str
    action: str
    should_execute: bool
    confidence_adjusted: float
    consensus_score: float
    reasons: Tuple[str, ...]  # Tuple for immutability
    recent_signals_count: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


class SignalValidatorService:
    """
    Service to validate trading signals using historical data from trading_signals table.
    
    Design Principles:
    - ISOLATION: Does not modify any external state
    - IMMUTABILITY: Returns new objects, never mutates
    - NO SIDE EFFECTS: Only reads from database
    
    Enhanced with:
    - ADAPTIVE CONFIDENCE THRESHOLD: Adjusts based on market conditions
    """
    
    # Configuration constants (base values)
    MIN_CONSENSUS_SIGNALS = 2
    MAX_CONSENSUS_SIGNALS = 5
    CONSENSUS_WINDOW_HOURS = 1
    DUPLICATE_WINDOW_MINUTES = 5
    DB_QUERY_TIMEOUT = DEFAULT_DB_TIMEOUT_SHORT  # 10 seconds timeout for queries
    
    # ADAPTIVE CONFIDENCE THRESHOLDS - LOWERED FOR MORE TRADES
    BASE_CONFIDENCE_THRESHOLD = 0.40   # Lowered from 0.6 for more trades
    HIGH_VOLATILITY_THRESHOLD = 0.50   # Lowered from 0.7
    LOW_VOLATILITY_THRESHOLD = 0.35    # Lowered from 0.5
    STRONG_TREND_THRESHOLD = 0.30      # Lowered from 0.45 for aggressive trading
    
    def __init__(self, db_manager_class, volatility_mode: str = 'normal'):
        """
        Initialize with database manager class (not instance).
        This ensures no shared state between validations.
        
        Args:
            db_manager_class: Database manager class
            volatility_mode: 'high', 'low', or 'normal' (default)
        """
        self._db_manager_class = db_manager_class
        self._volatility_mode = volatility_mode
        self._confidence_threshold = self._calculate_threshold(volatility_mode)
    
    @property
    def MIN_CONFIDENCE_THRESHOLD(self):
        """Dynamic confidence threshold based on market conditions."""
        return self._confidence_threshold
    
    def _calculate_threshold(self, mode: str) -> float:
        """Calculate confidence threshold based on volatility mode."""
        if mode == 'high':
            return self.HIGH_VOLATILITY_THRESHOLD
        elif mode == 'low':
            return self.LOW_VOLATILITY_THRESHOLD
        elif mode == 'trend':
            return self.STRONG_TREND_THRESHOLD
        return self.BASE_CONFIDENCE_THRESHOLD
    
    def set_volatility_mode(self, mode: str):
        """Update volatility mode and recalculate threshold."""
        self._volatility_mode = mode
        self._confidence_threshold = self._calculate_threshold(mode)
        logger.info(f"📊 Signal validator threshold updated: {self._confidence_threshold:.2f} (mode: {mode})")
    
    def validate_signal(
        self, 
        new_signal: Dict, 
        symbol: str
    ) -> SignalValidation:
        """
        Validate a new signal against historical signals.
        
        Args:
            new_signal: New signal dict with 'action' and 'confidence' keys
            symbol: Trading pair symbol
            
        Returns:
            Immutable SignalValidation result
        """
        # Extract signal data (defensive copy)
        action = str(new_signal.get('action', 'HOLD')).upper()
        confidence = float(new_signal.get('confidence', 0.5))
        
        # Get historical signals (isolated database read)
        recent_signals = self._fetch_recent_signals(symbol)
        
        # Calculate consensus (pure function)
        consensus_score, signal_counts = self._calculate_consensus(
            recent_signals, action
        )
        
        # Determine execution decision (pure function)
        should_execute, reasons = self._evaluate_execution(
            action=action,
            confidence=confidence,
            consensus_score=consensus_score,
            signal_counts=signal_counts,
            total_signals=len(recent_signals)
        )
        
        # Adjust confidence based on consensus (pure calculation)
        confidence_adjusted = self._adjust_confidence(
            base_confidence=confidence,
            consensus_score=consensus_score
        )
        
        # Return immutable result
        return SignalValidation(
            symbol=symbol,
            action=action,
            should_execute=should_execute,
            confidence_adjusted=confidence_adjusted,
            consensus_score=consensus_score,
            reasons=tuple(reasons),  # Convert to tuple for immutability
            recent_signals_count=len(recent_signals)
        )
    
    def _fetch_recent_signals(self, symbol: str) -> List[Dict]:
        """
        Fetch recent signals from database with timeout protection.
        Returns a NEW list (no reference sharing).
        Uses base symbol (BTC, ETH) for querying since signals are stored as base symbols.
        """
        try:
            # Normalize to base symbol (BTC/USDC -> BTC)
            base_symbol = extract_base_symbol(symbol)
            
            def do_query():
                with self._db_manager_class() as db:
                    from bot.db import TradingSignal
                    
                    cutoff = datetime.utcnow() - timedelta(hours=self.CONSENSUS_WINDOW_HOURS)
                    
                    signals = (
                        db.session.query(TradingSignal)
                        .filter(TradingSignal.symbol == base_symbol)
                        .filter(TradingSignal.created_at > cutoff)
                        .order_by(TradingSignal.created_at.desc())
                        .limit(self.MAX_CONSENSUS_SIGNALS)
                        .all()
                    )
                    
                    # Create NEW list of dicts (no ORM reference leaks)
                    return [
                        {
                            'signal_type': str(s.signal_type).upper(),
                            'confidence_score': float(s.confidence_score or 0.5),
                            'created_at': s.created_at
                        }
                        for s in signals
                    ]
            
            # Execute with timeout protection
            if DB_TIMEOUT_AVAILABLE:
                return safe_db_query(
                    query_func=do_query,
                    default_value=[],
                    timeout_seconds=self.DB_QUERY_TIMEOUT,
                    operation_name=f"fetch_signals_{base_symbol}"
                )
            else:
                return do_query()
                
        except Exception as e:
            logger.error(f"Failed to fetch recent signals for {symbol}: {e}")
            return []  # Safe fallback - empty list
    
    def _calculate_consensus(
        self, 
        signals: List[Dict], 
        target_action: str
    ) -> Tuple[float, Dict[str, int]]:
        """
        Calculate consensus score (pure function - no side effects).
        
        Returns:
            Tuple of (consensus_score, signal_counts_dict)
        """
        if not signals:
            return 0.0, {'BUY': 0, 'SELL': 0, 'HOLD': 0}
        
        # Count signals by type (immutable operations)
        counts = {'BUY': 0, 'SELL': 0, 'HOLD': 0}
        weighted_sum = 0.0
        
        for signal in signals:
            signal_type = signal.get('signal_type', 'HOLD')
            confidence = signal.get('confidence_score', 0.5)
            
            if signal_type in counts:
                counts[signal_type] += 1
                
                # Weight matching signals positively
                if signal_type == target_action:
                    weighted_sum += confidence
                elif signal_type != 'HOLD':
                    weighted_sum -= confidence * 0.5  # Opposing signals reduce score
        
        # Calculate consensus (0.0 to 1.0)
        total = len(signals)
        matching = counts.get(target_action, 0)
        
        raw_consensus = matching / total if total > 0 else 0.0
        weighted_consensus = weighted_sum / total if total > 0 else 0.0
        
        # Blend raw and weighted (pure calculation)
        final_consensus = (raw_consensus * 0.6) + (max(0, weighted_consensus) * 0.4)
        
        return min(1.0, max(0.0, final_consensus)), dict(counts)  # Return copy
    
    def _evaluate_execution(
        self,
        action: str,
        confidence: float,
        consensus_score: float,
        signal_counts: Dict[str, int],
        total_signals: int
    ) -> Tuple[bool, List[str]]:
        """
        Evaluate whether signal should be executed (pure function).
        
        Returns:
            Tuple of (should_execute, list_of_reasons)
        """
        reasons = []  # Collect reasons (will be converted to tuple)
        
        # Rule 1: Skip HOLD signals
        if action == 'HOLD':
            reasons.append("HOLD signal - no action required")
            return False, reasons
        
        # Rule 2: Minimum confidence threshold
        if confidence < self.MIN_CONFIDENCE_THRESHOLD:
            reasons.append(f"Confidence {confidence:.2f} below threshold {self.MIN_CONFIDENCE_THRESHOLD}")
            return False, reasons
        
        # Rule 3: Check for consensus (if enough historical data)
        if total_signals >= self.MIN_CONSENSUS_SIGNALS:
            matching_count = signal_counts.get(action, 0)
            
            if consensus_score >= 0.5:
                reasons.append(f"Consensus achieved: {matching_count}/{total_signals} signals match {action}")
            else:
                # Strong opposing signal
                opposing = 'SELL' if action == 'BUY' else 'BUY'
                opposing_count = signal_counts.get(opposing, 0)
                
                if opposing_count > matching_count:
                    reasons.append(f"Opposing signals ({opposing_count}) > matching ({matching_count})")
                    return False, reasons
                    
                reasons.append(f"Weak consensus: {matching_count}/{total_signals} match, proceeding with caution")
        else:
            reasons.append(f"Insufficient history ({total_signals} signals), using signal confidence only")
        
        # Rule 4: High confidence override
        if confidence >= 0.8:
            reasons.append(f"High confidence signal ({confidence:.2f})")
            return True, reasons
        
        # Rule 5: Combined score check
        # FIX 2025-12-16: Lowered threshold from 0.55 to 0.35 for more trades
        # 63% confidence + 0 history = 0.378 -> will pass with 0.35 threshold
        combined_score = (confidence * 0.6) + (consensus_score * 0.4)
        if combined_score >= 0.35:
            reasons.append(f"Combined score {combined_score:.2f} meets threshold (0.35)")
            return True, reasons
        
        reasons.append(f"Combined score {combined_score:.2f} below threshold (0.35)")
        return False, reasons
    
    def _adjust_confidence(
        self, 
        base_confidence: float, 
        consensus_score: float
    ) -> float:
        """
        Adjust confidence based on consensus (pure function).
        """
        # Blend base confidence with consensus
        adjusted = (base_confidence * 0.7) + (consensus_score * 0.3)
        
        # Clamp to valid range
        return min(1.0, max(0.0, adjusted))
    
    def is_duplicate_signal(
        self, 
        symbol: str, 
        signal_type: str
    ) -> bool:
        """
        Check if a similar signal was recently saved (prevents spam).
        Uses base symbol (BTC, ETH) for querying since signals are stored as base symbols.
        Includes timeout protection.
        """
        try:
            # Normalize to base symbol (BTC/USDC -> BTC)
            base_symbol = extract_base_symbol(symbol)
            
            def do_query():
                with self._db_manager_class() as db:
                    from bot.db import TradingSignal
                    
                    cutoff = datetime.utcnow() - timedelta(minutes=self.DUPLICATE_WINDOW_MINUTES)
                    
                    existing = (
                        db.session.query(TradingSignal)
                        .filter(TradingSignal.symbol == base_symbol)
                        .filter(TradingSignal.signal_type == signal_type.upper())
                        .filter(TradingSignal.created_at > cutoff)
                        .first()
                    )
                    
                    return existing is not None
            
            # Execute with timeout protection
            if DB_TIMEOUT_AVAILABLE:
                return safe_db_query(
                    query_func=do_query,
                    default_value=False,  # On timeout, allow signal
                    timeout_seconds=self.DB_QUERY_TIMEOUT,
                    operation_name=f"check_duplicate_{base_symbol}"
                )
            else:
                return do_query()
                
        except Exception as e:
            logger.error(f"Error checking duplicate signal: {e}")
            return False  # Safe fallback - allow signal


# Factory function for clean instantiation
def create_signal_validator():
    """Create a new SignalValidatorService instance."""
    from bot.db import DatabaseManager
    return SignalValidatorService(DatabaseManager)
