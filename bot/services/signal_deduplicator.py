"""
Signal Deduplicator Service - Intelligent signal deduplication.

Addresses the gap: "Deduplication by time - seen_symbols may skip newer signals"

Old logic flaw:
- Bot tracked seen_symbols and skipped if seen before
- This caused NEWER signals to be skipped if an old signal was seen first
- Result: Stale signals executed, fresh signals ignored

New logic:
- For each symbol, always prefer the NEWEST signal
- Track signal_id to avoid re-executing same signal
- Allow signal refresh if new signal is significantly different
- Consider signal quality score

v2.0: Added file persistence for crash recovery.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

# Persistence directory
PERSISTENCE_DIR = Path.home() / ".ase_bot" / "signal_dedup"


@dataclass
class SignalRecord:
    """Record of a processed signal."""
    signal_id: str
    symbol: str
    action: str  # BUY/SELL
    price: float
    confidence: float
    created_at: datetime
    processed_at: datetime
    was_executed: bool
    
    def to_dict(self) -> dict:
        """Convert to serializable dict."""
        return {
            'signal_id': self.signal_id,
            'symbol': self.symbol,
            'action': self.action,
            'price': self.price,
            'confidence': self.confidence,
            'created_at': self.created_at.isoformat(),
            'processed_at': self.processed_at.isoformat(),
            'was_executed': self.was_executed,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SignalRecord':
        """Create from dict."""
        return cls(
            signal_id=data['signal_id'],
            symbol=data['symbol'],
            action=data['action'],
            price=float(data['price']),
            confidence=float(data['confidence']),
            created_at=datetime.fromisoformat(data['created_at']),
            processed_at=datetime.fromisoformat(data['processed_at']),
            was_executed=bool(data['was_executed']),
        )


@dataclass
class DeduplicationResult:
    """Result of signal deduplication."""
    unique_signals: List[Dict]
    duplicates_removed: int
    stale_removed: int
    upgraded_signals: int  # Signals that replaced older versions
    reasons: Dict[str, str]  # symbol -> reason for removal


class SignalDeduplicator:
    """
    Intelligent signal deduplication that prefers newer signals.
    
    v2.0: Added file persistence for crash recovery.
    """
    
    def __init__(
        self,
        signal_window_hours: float = 6.0,      # Shorter than before (was 24h)
        stale_threshold_hours: float = 2.0,    # Consider signal stale after this
        price_change_threshold_pct: float = 1.0,  # Re-allow if price moved >1%
        confidence_upgrade_threshold: float = 0.1  # Re-allow if confidence +10%
    ):
        self.signal_window_hours = signal_window_hours
        self.stale_threshold_hours = stale_threshold_hours
        self.price_change_threshold_pct = price_change_threshold_pct
        self.confidence_upgrade_threshold = confidence_upgrade_threshold
        
        # Track processed signals {user_id: {signal_id: SignalRecord}}
        self._processed_signals: Dict[str, Dict[str, SignalRecord]] = defaultdict(dict)
        
        # Track last processed signal per symbol {user_id: {symbol: SignalRecord}}
        self._last_signal_by_symbol: Dict[str, Dict[str, SignalRecord]] = defaultdict(dict)
        
        # Ensure persistence directory exists
        PERSISTENCE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Load persisted state
        self._load_persisted_state()
        
        logger.info(f"🔍 Signal Deduplicator initialized: window={signal_window_hours}h, "
                   f"stale={stale_threshold_hours}h")
    
    def _get_persistence_path(self, user_id: str) -> Path:
        """Get persistence file path for user."""
        safe_user_id = user_id.replace('/', '_').replace('\\', '_')[:50]
        return PERSISTENCE_DIR / f"signals_{safe_user_id}.json"
    
    def _persist_state(self, user_id: str) -> None:
        """Persist state to file for crash recovery."""
        try:
            state = {
                'processed_signals': {
                    sid: rec.to_dict() 
                    for sid, rec in self._processed_signals[user_id].items()
                },
                'last_signal_by_symbol': {
                    sym: rec.to_dict() 
                    for sym, rec in self._last_signal_by_symbol[user_id].items()
                },
                'persisted_at': datetime.now().isoformat(),
            }
            
            file_path = self._get_persistence_path(user_id)
            with open(file_path, 'w') as f:
                json.dump(state, f, indent=2)
                
            logger.debug(f"Persisted signal dedup state for {user_id[:8]}...")
            
        except Exception as e:
            logger.warning(f"Failed to persist signal dedup state: {e}")
    
    def _load_persisted_state(self) -> None:
        """Load persisted state from files."""
        try:
            if not PERSISTENCE_DIR.exists():
                return
            
            now = datetime.now()
            window = timedelta(hours=self.signal_window_hours)
            loaded_count = 0
            
            for file_path in PERSISTENCE_DIR.glob("signals_*.json"):
                try:
                    with open(file_path, 'r') as f:
                        state = json.load(f)
                    
                    # Check if state is too old
                    persisted_at = datetime.fromisoformat(state.get('persisted_at', '2000-01-01'))
                    if now - persisted_at > window:
                        # Old state - delete file
                        file_path.unlink()
                        continue
                    
                    # Extract user_id from filename
                    user_id = file_path.stem.replace('signals_', '')
                    
                    # Load processed signals (only non-stale ones)
                    for sid, rec_data in state.get('processed_signals', {}).items():
                        try:
                            record = SignalRecord.from_dict(rec_data)
                            # Only load if not stale
                            if now - record.processed_at < window:
                                self._processed_signals[user_id][sid] = record
                        except Exception:
                            pass
                    
                    # Load last signal by symbol
                    for sym, rec_data in state.get('last_signal_by_symbol', {}).items():
                        try:
                            record = SignalRecord.from_dict(rec_data)
                            if now - record.processed_at < window:
                                self._last_signal_by_symbol[user_id][sym] = record
                        except Exception:
                            pass
                    
                    loaded_count += 1
                    logger.info(
                        f"✅ Restored signal dedup state for {user_id[:8]}... | "
                        f"Signals: {len(self._processed_signals[user_id])}"
                    )
                    
                except Exception as e:
                    logger.warning(f"Failed to load state from {file_path}: {e}")
            
            if loaded_count > 0:
                logger.info(f"📂 Loaded {loaded_count} persisted signal dedup states")
                
        except Exception as e:
            logger.warning(f"Failed to load persisted signal dedup states: {e}")
    
    def deduplicate_signals(
        self, 
        user_id: str,
        signals: List[Dict],
        current_time: Optional[datetime] = None
    ) -> DeduplicationResult:
        """
        Deduplicate signals, preferring the newest and highest quality.
        
        Logic:
        1. Remove stale signals (older than stale_threshold)
        2. For each symbol, keep only the newest signal
        3. Skip signals that were already processed (by signal_id)
        4. Allow refresh if significant price/confidence change
        """
        now = current_time or datetime.now()
        
        unique_signals = []
        duplicates_removed = 0
        stale_removed = 0
        upgraded = 0
        reasons = {}
        
        # Clean old processed signals
        self._cleanup_old_records(user_id, now)
        
        # Group signals by symbol, keeping newest
        signals_by_symbol: Dict[str, Dict] = {}
        
        for signal in signals:
            symbol = signal.get('symbol', '')
            signal_id = signal.get('id') or signal.get('signal_id', '')
            
            # Parse created_at
            created_at = self._parse_datetime(signal.get('created_at'))
            if not created_at:
                logger.warning(f"Signal missing created_at: {signal}")
                continue
            
            # 1. Check if signal is too old (outside window)
            age_hours = (now - created_at).total_seconds() / 3600
            if age_hours > self.signal_window_hours:
                stale_removed += 1
                reasons[f"{symbol}_{signal_id}"] = f"Too old ({age_hours:.1f}h > {self.signal_window_hours}h)"
                continue
            
            # 2. Check if stale (but still within window)
            is_stale = age_hours > self.stale_threshold_hours
            
            # 3. Check if already processed this exact signal
            if signal_id and signal_id in self._processed_signals[user_id]:
                old_record = self._processed_signals[user_id][signal_id]
                if old_record.was_executed:
                    duplicates_removed += 1
                    reasons[symbol] = f"Already executed (signal_id={signal_id[:8]})"
                    continue
            
            # 4. Compare with any signal for this symbol in current batch
            if symbol in signals_by_symbol:
                existing = signals_by_symbol[symbol]
                existing_time = self._parse_datetime(existing.get('created_at'))
                
                # Keep the newer one
                if created_at > existing_time:
                    signals_by_symbol[symbol] = signal
                    duplicates_removed += 1
                else:
                    duplicates_removed += 1
                    continue
            else:
                # 5. Check against last processed signal for this symbol
                if symbol in self._last_signal_by_symbol[user_id]:
                    last = self._last_signal_by_symbol[user_id][symbol]
                    
                    # Allow if significantly different
                    should_upgrade = self._should_upgrade_signal(signal, last, now)
                    
                    if not should_upgrade:
                        if is_stale:
                            stale_removed += 1
                            reasons[symbol] = f"Stale duplicate ({age_hours:.1f}h old)"
                        else:
                            duplicates_removed += 1
                            reasons[symbol] = f"Recent duplicate of {last.signal_id[:8] if last.signal_id else 'unknown'}"
                        continue
                    else:
                        upgraded += 1
                        logger.info(f"♻️ Upgrading signal for {symbol} (newer/better)")
                
                signals_by_symbol[symbol] = signal
        
        # Convert back to list, sorted by confidence (highest first)
        unique_signals = sorted(
            signals_by_symbol.values(),
            key=lambda s: s.get('confidence', 0.5),
            reverse=True
        )
        
        return DeduplicationResult(
            unique_signals=unique_signals,
            duplicates_removed=duplicates_removed,
            stale_removed=stale_removed,
            upgraded_signals=upgraded,
            reasons=reasons
        )
    
    def _should_upgrade_signal(
        self, 
        new_signal: Dict, 
        old_record: SignalRecord,
        now: datetime
    ) -> bool:
        """
        Check if new signal should replace the old one.
        
        Returns True if:
        - New signal has significantly higher confidence
        - Price has changed significantly since old signal
        - Old signal is stale
        - Action changed (e.g., BUY -> SELL)
        """
        # Different action = always upgrade
        new_action = new_signal.get('action', '').upper()
        if new_action and new_action != old_record.action:
            return True
        
        # Old signal is stale
        old_age = (now - old_record.created_at).total_seconds() / 3600
        if old_age > self.stale_threshold_hours:
            return True
        
        # Confidence significantly higher
        new_confidence = new_signal.get('confidence', 0.5)
        if new_confidence - old_record.confidence > self.confidence_upgrade_threshold:
            return True
        
        # Price changed significantly (would need current price - not checking here)
        # This would require market data access
        
        return False
    
    def record_processed(
        self, 
        user_id: str, 
        signal: Dict, 
        was_executed: bool
    ):
        """Record that a signal was processed."""
        now = datetime.now()
        
        signal_id = signal.get('id') or signal.get('signal_id', f"gen_{now.timestamp()}")
        symbol = signal.get('symbol', '')
        
        record = SignalRecord(
            signal_id=signal_id,
            symbol=symbol,
            action=signal.get('action', 'BUY').upper(),
            price=signal.get('entry_price', 0.0),
            confidence=signal.get('confidence', 0.5),
            created_at=self._parse_datetime(signal.get('created_at')) or now,
            processed_at=now,
            was_executed=was_executed
        )
        
        # Store by signal_id
        self._processed_signals[user_id][signal_id] = record
        
        # Store as last signal for symbol (only if executed)
        if was_executed:
            self._last_signal_by_symbol[user_id][symbol] = record
            logger.debug(f"Recorded executed signal: {symbol} ({signal_id[:8]})")
        
        # Persist state after recording
        self._persist_state(user_id)
    
    def _cleanup_old_records(self, user_id: str, now: datetime):
        """Remove records older than signal window."""
        cutoff = now - timedelta(hours=self.signal_window_hours * 2)
        
        # Clean processed signals
        old_ids = [
            sid for sid, rec in self._processed_signals[user_id].items()
            if rec.processed_at < cutoff
        ]
        for sid in old_ids:
            del self._processed_signals[user_id][sid]
        
        # Clean last signal by symbol
        old_symbols = [
            sym for sym, rec in self._last_signal_by_symbol[user_id].items()
            if rec.processed_at < cutoff
        ]
        for sym in old_symbols:
            del self._last_signal_by_symbol[user_id][sym]
        
        if old_ids or old_symbols:
            logger.debug(f"Cleaned up {len(old_ids)} signal records, {len(old_symbols)} symbol records")
    
    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            # Try common formats
            for fmt in [
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
            ]:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
            # Try parsing with timezone
            try:
                # Handle +00:00 timezone
                if '+' in value or value.endswith('Z'):
                    value = value.replace('Z', '+00:00')
                    if '+' in value:
                        value = value.rsplit('+', 1)[0]
                return datetime.fromisoformat(value)
            except:
                pass
        return None
    
    def get_stats(self, user_id: str) -> Dict:
        """Get deduplication stats for a user."""
        return {
            "processed_signals": len(self._processed_signals[user_id]),
            "symbols_tracked": len(self._last_signal_by_symbol[user_id]),
            "signal_window_hours": self.signal_window_hours,
            "stale_threshold_hours": self.stale_threshold_hours
        }
    
    def clear_user(self, user_id: str):
        """Clear all records for a user (e.g., on restart)."""
        self._processed_signals[user_id].clear()
        self._last_signal_by_symbol[user_id].clear()
        logger.info(f"Cleared deduplication records for {user_id[:8]}")


# Default instance
_deduplicator: Optional[SignalDeduplicator] = None


def get_signal_deduplicator(
    signal_window_hours: float = 6.0,
    stale_threshold_hours: float = 2.0
) -> SignalDeduplicator:
    """Get or create the global SignalDeduplicator instance."""
    global _deduplicator
    if _deduplicator is None:
        _deduplicator = SignalDeduplicator(
            signal_window_hours=signal_window_hours,
            stale_threshold_hours=stale_threshold_hours
        )
    return _deduplicator
