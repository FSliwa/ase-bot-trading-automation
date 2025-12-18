"""
Dead Letter Queue (DLQ) - Persistent storage for failed signals.

FIX 2025-12-16: Added Dead Letter Queue to prevent signal loss.

When a signal fails to execute (network error, exchange rejection, etc.),
it's stored in the DLQ for later retry instead of being silently dropped.

Features:
- Persistent storage (SQLite or Supabase)
- Automatic retry with exponential backoff
- Signal aging/expiration
- Manual review/replay capability
- Metrics and alerting
"""

import asyncio
import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import sqlite3
import uuid

logger = logging.getLogger(__name__)

# Try to import Supabase for cloud persistence
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None


class DLQEntryStatus(Enum):
    """Status of a Dead Letter Queue entry."""
    PENDING = "pending"           # Waiting for retry
    RETRYING = "retrying"         # Currently being retried
    SUCCEEDED = "succeeded"       # Successfully processed on retry
    FAILED_PERMANENT = "failed"   # Permanently failed after max retries
    EXPIRED = "expired"           # Expired due to age
    MANUAL_REVIEW = "manual"      # Flagged for manual review


@dataclass
class DLQEntry:
    """An entry in the Dead Letter Queue."""
    id: str                              # Unique ID
    signal_type: str                     # 'buy', 'sell', 'close'
    signal_data: Dict[str, Any]          # Original signal data
    error_message: str                   # Why it failed
    error_code: Optional[str] = None     # Error code if available
    user_id: Optional[str] = None        # User who owned the signal
    symbol: str = ""                     # Trading pair
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0                 # Number of retry attempts
    max_retries: int = 5                 # Max retries before permanent failure
    next_retry_at: Optional[datetime] = None
    status: DLQEntryStatus = DLQEntryStatus.PENDING
    last_error: Optional[str] = None     # Last error from retry
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        # Set next retry time with exponential backoff
        if self.next_retry_at is None and self.status == DLQEntryStatus.PENDING:
            backoff_seconds = min(300, 30 * (2 ** self.retry_count))  # Max 5 min
            self.next_retry_at = datetime.now() + timedelta(seconds=backoff_seconds)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            'id': self.id,
            'signal_type': self.signal_type,
            'signal_data': json.dumps(self.signal_data),
            'error_message': self.error_message,
            'error_code': self.error_code,
            'user_id': self.user_id,
            'symbol': self.symbol,
            'created_at': self.created_at.isoformat(),
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'next_retry_at': self.next_retry_at.isoformat() if self.next_retry_at else None,
            'status': self.status.value,
            'last_error': self.last_error,
            'metadata': json.dumps(self.metadata),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'DLQEntry':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            signal_type=data['signal_type'],
            signal_data=json.loads(data['signal_data']) if isinstance(data['signal_data'], str) else data['signal_data'],
            error_message=data['error_message'],
            error_code=data.get('error_code'),
            user_id=data.get('user_id'),
            symbol=data.get('symbol', ''),
            created_at=datetime.fromisoformat(data['created_at']) if isinstance(data['created_at'], str) else data['created_at'],
            retry_count=data.get('retry_count', 0),
            max_retries=data.get('max_retries', 5),
            next_retry_at=datetime.fromisoformat(data['next_retry_at']) if data.get('next_retry_at') else None,
            status=DLQEntryStatus(data.get('status', 'pending')),
            last_error=data.get('last_error'),
            metadata=json.loads(data['metadata']) if isinstance(data.get('metadata'), str) else data.get('metadata', {}),
        )


@dataclass
class DLQStats:
    """Statistics for the Dead Letter Queue."""
    total_entries: int = 0
    pending_entries: int = 0
    retrying_entries: int = 0
    succeeded_entries: int = 0
    failed_entries: int = 0
    expired_entries: int = 0
    manual_review_entries: int = 0
    oldest_entry_age_hours: float = 0.0
    avg_retry_count: float = 0.0


class DeadLetterQueue:
    """
    Dead Letter Queue for failed trading signals.
    
    Provides persistent storage and automatic retry for signals that
    failed to execute due to temporary errors.
    """
    
    # Signal expiration time (24 hours)
    SIGNAL_EXPIRY_HOURS = 24
    
    # How often to check for retries (seconds)
    RETRY_CHECK_INTERVAL = 30
    
    def __init__(
        self,
        storage_path: str = "dlq.sqlite",
        use_supabase: bool = False,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        on_retry_success: Optional[callable] = None,
        on_permanent_failure: Optional[callable] = None,
    ):
        self.storage_path = storage_path
        self.use_supabase = use_supabase and SUPABASE_AVAILABLE
        self.on_retry_success = on_retry_success
        self.on_permanent_failure = on_permanent_failure
        
        # In-memory cache for fast access
        self._entries: Dict[str, DLQEntry] = {}
        
        # Retry processor
        self._retry_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Supabase client
        self._supabase: Optional[Client] = None
        
        # Initialize storage
        if self.use_supabase:
            self._init_supabase(supabase_url, supabase_key)
        else:
            self._init_sqlite()
        
        logger.info(
            f"🗃️ Dead Letter Queue initialized | "
            f"Storage: {'Supabase' if self.use_supabase else f'SQLite ({storage_path})'} | "
            f"Expiry: {self.SIGNAL_EXPIRY_HOURS}h"
        )
    
    def _init_sqlite(self):
        """Initialize SQLite storage."""
        conn = sqlite3.connect(self.storage_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id TEXT PRIMARY KEY,
                signal_type TEXT,
                signal_data TEXT,
                error_message TEXT,
                error_code TEXT,
                user_id TEXT,
                symbol TEXT,
                created_at TEXT,
                retry_count INTEGER,
                max_retries INTEGER,
                next_retry_at TEXT,
                status TEXT,
                last_error TEXT,
                metadata TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON dead_letter_queue(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_next_retry ON dead_letter_queue(next_retry_at)')
        conn.commit()
        conn.close()
        
        # Load existing entries
        self._load_entries()
    
    def _init_supabase(self, url: Optional[str], key: Optional[str]):
        """Initialize Supabase storage."""
        url = url or os.getenv('SUPABASE_URL')
        key = key or os.getenv('SUPABASE_KEY')
        
        if url and key:
            try:
                self._supabase = create_client(url, key)
                logger.info("✅ Dead Letter Queue connected to Supabase")
                self._load_entries_from_supabase()
            except Exception as e:
                logger.error(f"Failed to connect to Supabase: {e}")
                self.use_supabase = False
                self._init_sqlite()
        else:
            logger.warning("Supabase credentials not found, falling back to SQLite")
            self.use_supabase = False
            self._init_sqlite()
    
    def _load_entries(self):
        """Load entries from SQLite."""
        try:
            conn = sqlite3.connect(self.storage_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM dead_letter_queue WHERE status IN ('pending', 'retrying', 'manual')"
            )
            rows = cursor.fetchall()
            conn.close()
            
            for row in rows:
                entry = DLQEntry.from_dict(dict(row))
                self._entries[entry.id] = entry
            
            logger.info(f"Loaded {len(self._entries)} DLQ entries from SQLite")
        except Exception as e:
            logger.error(f"Failed to load DLQ entries: {e}")
    
    def _load_entries_from_supabase(self):
        """Load entries from Supabase."""
        try:
            response = self._supabase.table('dead_letter_queue').select('*').in_(
                'status', ['pending', 'retrying', 'manual']
            ).execute()
            
            for row in response.data:
                entry = DLQEntry.from_dict(row)
                self._entries[entry.id] = entry
            
            logger.info(f"Loaded {len(self._entries)} DLQ entries from Supabase")
        except Exception as e:
            logger.error(f"Failed to load DLQ entries from Supabase: {e}")
    
    def add_failed_signal(
        self,
        signal_type: str,
        signal_data: Dict[str, Any],
        error_message: str,
        error_code: Optional[str] = None,
        user_id: Optional[str] = None,
        symbol: str = "",
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Add a failed signal to the Dead Letter Queue.
        
        Returns:
            Entry ID
        """
        entry_id = str(uuid.uuid4())
        
        entry = DLQEntry(
            id=entry_id,
            signal_type=signal_type,
            signal_data=signal_data,
            error_message=error_message,
            error_code=error_code,
            user_id=user_id,
            symbol=symbol or signal_data.get('symbol', ''),
            metadata=metadata or {}
        )
        
        self._entries[entry_id] = entry
        self._persist_entry(entry)
        
        logger.warning(
            f"📥 Signal added to DLQ: {entry_id[:8]} | "
            f"Type: {signal_type} | Symbol: {symbol} | "
            f"Error: {error_message[:50]}... | "
            f"Next retry: {entry.next_retry_at}"
        )
        
        return entry_id
    
    def _persist_entry(self, entry: DLQEntry):
        """Persist entry to storage."""
        if self.use_supabase:
            try:
                self._supabase.table('dead_letter_queue').upsert(entry.to_dict()).execute()
            except Exception as e:
                logger.error(f"Failed to persist DLQ entry to Supabase: {e}")
        else:
            try:
                conn = sqlite3.connect(self.storage_path)
                cursor = conn.cursor()
                data = entry.to_dict()
                cursor.execute('''
                    INSERT OR REPLACE INTO dead_letter_queue 
                    (id, signal_type, signal_data, error_message, error_code, user_id, 
                     symbol, created_at, retry_count, max_retries, next_retry_at, 
                     status, last_error, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data['id'], data['signal_type'], data['signal_data'],
                    data['error_message'], data['error_code'], data['user_id'],
                    data['symbol'], data['created_at'], data['retry_count'],
                    data['max_retries'], data['next_retry_at'], data['status'],
                    data['last_error'], data['metadata']
                ))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to persist DLQ entry to SQLite: {e}")
    
    def get_pending_entries(self) -> List[DLQEntry]:
        """Get all entries ready for retry."""
        now = datetime.now()
        ready = []
        
        for entry in self._entries.values():
            if entry.status == DLQEntryStatus.PENDING:
                if entry.next_retry_at and entry.next_retry_at <= now:
                    ready.append(entry)
        
        return ready
    
    def get_stats(self) -> DLQStats:
        """Get queue statistics."""
        stats = DLQStats()
        
        now = datetime.now()
        total_retries = 0
        oldest_age = 0
        
        for entry in self._entries.values():
            stats.total_entries += 1
            total_retries += entry.retry_count
            
            age_hours = (now - entry.created_at).total_seconds() / 3600
            if age_hours > oldest_age:
                oldest_age = age_hours
            
            if entry.status == DLQEntryStatus.PENDING:
                stats.pending_entries += 1
            elif entry.status == DLQEntryStatus.RETRYING:
                stats.retrying_entries += 1
            elif entry.status == DLQEntryStatus.SUCCEEDED:
                stats.succeeded_entries += 1
            elif entry.status == DLQEntryStatus.FAILED_PERMANENT:
                stats.failed_entries += 1
            elif entry.status == DLQEntryStatus.EXPIRED:
                stats.expired_entries += 1
            elif entry.status == DLQEntryStatus.MANUAL_REVIEW:
                stats.manual_review_entries += 1
        
        stats.oldest_entry_age_hours = oldest_age
        stats.avg_retry_count = total_retries / stats.total_entries if stats.total_entries > 0 else 0
        
        return stats
    
    def mark_succeeded(self, entry_id: str):
        """Mark an entry as successfully processed."""
        if entry_id in self._entries:
            entry = self._entries[entry_id]
            entry.status = DLQEntryStatus.SUCCEEDED
            self._persist_entry(entry)
            
            logger.info(f"✅ DLQ entry succeeded: {entry_id[:8]} | Symbol: {entry.symbol}")
            
            if self.on_retry_success:
                try:
                    self.on_retry_success(entry)
                except Exception as e:
                    logger.error(f"Error in retry success callback: {e}")
    
    def mark_failed(self, entry_id: str, error: str):
        """Mark an entry as failed (will retry or permanent fail)."""
        if entry_id in self._entries:
            entry = self._entries[entry_id]
            entry.retry_count += 1
            entry.last_error = error
            
            if entry.retry_count >= entry.max_retries:
                entry.status = DLQEntryStatus.FAILED_PERMANENT
                logger.error(
                    f"❌ DLQ entry permanently failed after {entry.retry_count} retries: "
                    f"{entry_id[:8]} | Symbol: {entry.symbol} | Last error: {error}"
                )
                
                if self.on_permanent_failure:
                    try:
                        self.on_permanent_failure(entry)
                    except Exception as e:
                        logger.error(f"Error in permanent failure callback: {e}")
            else:
                # Calculate next retry with exponential backoff
                backoff_seconds = min(300, 30 * (2 ** entry.retry_count))
                entry.next_retry_at = datetime.now() + timedelta(seconds=backoff_seconds)
                entry.status = DLQEntryStatus.PENDING
                
                logger.warning(
                    f"🔄 DLQ entry will retry ({entry.retry_count}/{entry.max_retries}): "
                    f"{entry_id[:8]} | Next: {entry.next_retry_at} | Error: {error[:50]}"
                )
            
            self._persist_entry(entry)
    
    def expire_old_entries(self):
        """Expire entries older than SIGNAL_EXPIRY_HOURS."""
        now = datetime.now()
        expired_count = 0
        
        for entry in list(self._entries.values()):
            if entry.status in (DLQEntryStatus.PENDING, DLQEntryStatus.RETRYING):
                age_hours = (now - entry.created_at).total_seconds() / 3600
                if age_hours > self.SIGNAL_EXPIRY_HOURS:
                    entry.status = DLQEntryStatus.EXPIRED
                    self._persist_entry(entry)
                    expired_count += 1
        
        if expired_count > 0:
            logger.info(f"⏰ Expired {expired_count} old DLQ entries")
    
    async def start_retry_processor(self, retry_callback: callable):
        """
        Start background task to process retries.
        
        Args:
            retry_callback: Async function to call for retrying signals.
                            Should accept (signal_type, signal_data) and return (success, error)
        """
        self._running = True
        self._retry_task = asyncio.create_task(
            self._retry_loop(retry_callback)
        )
        logger.info("🔄 DLQ retry processor started")
    
    async def stop_retry_processor(self):
        """Stop the retry processor."""
        self._running = False
        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 DLQ retry processor stopped")
    
    async def _retry_loop(self, retry_callback: callable):
        """Background loop for processing retries."""
        while self._running:
            try:
                # Expire old entries
                self.expire_old_entries()
                
                # Get entries ready for retry
                pending = self.get_pending_entries()
                
                for entry in pending:
                    if not self._running:
                        break
                    
                    logger.info(
                        f"🔄 Retrying DLQ entry: {entry.id[:8]} | "
                        f"Symbol: {entry.symbol} | Attempt: {entry.retry_count + 1}/{entry.max_retries}"
                    )
                    
                    entry.status = DLQEntryStatus.RETRYING
                    self._persist_entry(entry)
                    
                    try:
                        success, error = await retry_callback(
                            entry.signal_type,
                            entry.signal_data
                        )
                        
                        if success:
                            self.mark_succeeded(entry.id)
                        else:
                            self.mark_failed(entry.id, error or "Unknown error")
                    
                    except Exception as e:
                        self.mark_failed(entry.id, str(e))
                    
                    # Small delay between retries
                    await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in DLQ retry loop: {e}")
            
            await asyncio.sleep(self.RETRY_CHECK_INTERVAL)


# Global DLQ instance
_dlq_instance: Optional[DeadLetterQueue] = None


def get_dead_letter_queue() -> DeadLetterQueue:
    """Get or create the global Dead Letter Queue instance."""
    global _dlq_instance
    if _dlq_instance is None:
        _dlq_instance = DeadLetterQueue()
    return _dlq_instance


def add_to_dlq(
    signal_type: str,
    signal_data: Dict,
    error: str,
    **kwargs
) -> str:
    """Convenience function to add a failed signal to the DLQ."""
    dlq = get_dead_letter_queue()
    return dlq.add_failed_signal(
        signal_type=signal_type,
        signal_data=signal_data,
        error_message=error,
        **kwargs
    )
