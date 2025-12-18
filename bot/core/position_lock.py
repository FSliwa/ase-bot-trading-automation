"""
Position Lock Manager - Mutex for position operations.

Prevents race conditions when multiple components try to modify
the same position simultaneously (e.g., bot and position monitor).
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
from functools import wraps

logger = logging.getLogger(__name__)


@dataclass
class LockInfo:
    """Information about a held lock."""
    symbol: str
    holder: str  # Component that holds the lock
    acquired_at: datetime
    expires_at: datetime
    
    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


class PositionLockManager:
    """
    Manages locks for position operations to prevent race conditions.
    
    Key Features:
    1. Symbol-level locking (multiple positions can be modified in parallel)
    2. Auto-expiring locks (prevents deadlocks)
    3. Lock ownership tracking (for debugging)
    4. Async-safe implementation
    
    Usage:
        lock_manager = PositionLockManager()
        
        async with lock_manager.acquire_lock("BTC/USDT", "position_monitor") as locked:
            if locked:
                # Safe to modify position
                await close_position("BTC/USDT")
            else:
                logger.warning("Could not acquire lock, skipping")
    """
    
    DEFAULT_TIMEOUT = 30.0  # seconds
    DEFAULT_MAX_WAIT = 5.0  # seconds to wait for lock
    CLEANUP_INTERVAL = 60.0  # seconds between cleanup runs
    
    def __init__(self, default_timeout: float = DEFAULT_TIMEOUT):
        self.default_timeout = default_timeout
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_info: Dict[str, LockInfo] = {}
        self._meta_lock = asyncio.Lock()  # Lock for managing _locks dict
        self._pending_operations: Dict[str, Set[str]] = {}  # symbol -> set of waiting holders
        
    async def _get_or_create_lock(self, symbol: str) -> asyncio.Lock:
        """Get or create a lock for a symbol."""
        async with self._meta_lock:
            if symbol not in self._locks:
                self._locks[symbol] = asyncio.Lock()
            return self._locks[symbol]
    
    @asynccontextmanager
    async def acquire_lock(
        self,
        symbol: str,
        holder: str,
        timeout: Optional[float] = None,
        max_wait: Optional[float] = None
    ):
        """
        Acquire a lock for a symbol.
        
        P0-4 FIX: Proper race condition handling with double-check locking.
        
        Args:
            symbol: Trading pair symbol
            holder: Name of component acquiring lock (for debugging)
            timeout: How long the lock is valid (auto-release after this)
            max_wait: Maximum time to wait to acquire lock
            
        Yields:
            True if lock acquired, False otherwise
        """
        timeout = timeout or self.default_timeout
        max_wait = max_wait or self.DEFAULT_MAX_WAIT
        
        lock = await self._get_or_create_lock(symbol)
        acquired = False
        
        try:
            # P0-4 FIX: Check for expired lock BEFORE attempting to acquire
            # This prevents race condition where multiple waiters all try to force-release
            async with self._meta_lock:
                if symbol in self._lock_info and self._lock_info[symbol].is_expired:
                    logger.warning(
                        f"🔓 Pre-emptive release of expired lock for {symbol} "
                        f"(held by {self._lock_info[symbol].holder})"
                    )
                    if lock.locked():
                        try:
                            lock.release()
                        except RuntimeError:
                            pass  # Lock was already released
                    if symbol in self._lock_info:
                        del self._lock_info[symbol]
            
            # Try to acquire with timeout
            try:
                acquired = await asyncio.wait_for(
                    lock.acquire(),
                    timeout=max_wait
                )
            except asyncio.TimeoutError:
                # P0-4 FIX: Double-check pattern - re-check under meta_lock
                async with self._meta_lock:
                    if symbol in self._lock_info and self._lock_info[symbol].is_expired:
                        logger.warning(
                            f"🔓 Force-releasing expired lock for {symbol} "
                            f"(held by {self._lock_info[symbol].holder})"
                        )
                        # Force release and try again
                        if lock.locked():
                            try:
                                lock.release()
                            except RuntimeError:
                                pass
                        if symbol in self._lock_info:
                            del self._lock_info[symbol]
                        
                        # Try one more time after force release
                        try:
                            acquired = await asyncio.wait_for(
                                lock.acquire(),
                                timeout=1.0
                            )
                        except asyncio.TimeoutError:
                            acquired = False
                    else:
                        current_holder = self._lock_info.get(symbol)
                        logger.warning(
                            f"⏳ Could not acquire lock for {symbol} within {max_wait}s | "
                            f"Current holder: {current_holder.holder if current_holder else 'unknown'}"
                        )
                        acquired = False
            
            if acquired:
                # P0-4 FIX: Record lock info under meta_lock to prevent race
                async with self._meta_lock:
                    self._lock_info[symbol] = LockInfo(
                        symbol=symbol,
                        holder=holder,
                        acquired_at=datetime.utcnow(),
                        expires_at=datetime.utcnow() + timedelta(seconds=timeout)
                    )
                logger.debug(f"🔒 Lock acquired: {symbol} by {holder}")
            
            # FIX 2025-12-16: Yield outside try block to fix "generator didn't stop after athrow()"
            # The issue was that yield inside try/except caused improper generator cleanup
            try:
                yield acquired
            except GeneratorExit:
                # Normal cleanup when context manager exits
                pass
            except Exception as inner_err:
                # Log but don't re-yield - let the exception propagate properly
                logger.error(f"Error during lock context for {symbol}: {inner_err}")
                raise
                
        except Exception as e:
            logger.error(f"Error in lock acquisition for {symbol}: {e}")
            # FIX: Don't yield False after exception - just let it propagate
            # yield False  # REMOVED - this caused "generator didn't stop after athrow()"
            raise
            
        finally:
            if acquired:
                # P0-4 FIX: Clean release under meta_lock
                async with self._meta_lock:
                    if lock.locked():
                        try:
                            lock.release()
                        except RuntimeError:
                            pass  # Already released
                    if symbol in self._lock_info and self._lock_info[symbol].holder == holder:
                        del self._lock_info[symbol]
                logger.debug(f"🔓 Lock released: {symbol} by {holder}")
    
    async def try_acquire(
        self,
        symbol: str,
        holder: str,
        timeout: Optional[float] = None
    ) -> bool:
        """
        Try to acquire lock without waiting.
        
        Returns:
            True if lock acquired immediately, False otherwise
        """
        lock = await self._get_or_create_lock(symbol)
        
        if lock.locked():
            # Check if current lock is expired
            if symbol in self._lock_info and self._lock_info[symbol].is_expired:
                logger.warning(f"Force-releasing expired lock for {symbol}")
                lock.release()
            else:
                return False
        
        try:
            # Non-blocking acquire
            acquired = lock.acquire_nowait()
            if acquired:
                self._lock_info[symbol] = LockInfo(
                    symbol=symbol,
                    holder=holder,
                    acquired_at=datetime.utcnow(),
                    expires_at=datetime.utcnow() + timedelta(seconds=timeout or self.default_timeout)
                )
            return acquired
        except:
            return False
    
    def release(self, symbol: str, holder: str) -> bool:
        """
        Explicitly release a lock.
        
        Args:
            symbol: Symbol to unlock
            holder: Must match the holder that acquired the lock
            
        Returns:
            True if released, False if not held or wrong holder
        """
        if symbol not in self._locks:
            return False
        
        lock = self._locks[symbol]
        lock_info = self._lock_info.get(symbol)
        
        # Verify holder
        if lock_info and lock_info.holder != holder:
            logger.warning(
                f"⚠️ Lock release denied: {symbol} held by {lock_info.holder}, "
                f"release attempted by {holder}"
            )
            return False
        
        if lock.locked():
            lock.release()
            if symbol in self._lock_info:
                del self._lock_info[symbol]
            logger.debug(f"🔓 Lock explicitly released: {symbol} by {holder}")
            return True
        
        return False
    
    def is_locked(self, symbol: str) -> bool:
        """Check if a symbol is currently locked."""
        if symbol not in self._locks:
            return False
        
        lock = self._locks[symbol]
        if not lock.locked():
            return False
        
        # Check expiration
        lock_info = self._lock_info.get(symbol)
        if lock_info and lock_info.is_expired:
            return False  # Expired locks don't count as locked
        
        return True
    
    def get_lock_holder(self, symbol: str) -> Optional[str]:
        """Get the holder of a lock."""
        lock_info = self._lock_info.get(symbol)
        if lock_info and not lock_info.is_expired:
            return lock_info.holder
        return None
    
    def get_all_locks(self) -> Dict[str, LockInfo]:
        """Get information about all active locks."""
        return {
            symbol: info 
            for symbol, info in self._lock_info.items() 
            if not info.is_expired
        }
    
    async def cleanup_expired_locks(self):
        """Clean up expired locks (call periodically)."""
        expired = []
        
        for symbol, info in list(self._lock_info.items()):
            if info.is_expired:
                expired.append(symbol)
                if symbol in self._locks and self._locks[symbol].locked():
                    try:
                        self._locks[symbol].release()
                    except:
                        pass
        
        for symbol in expired:
            if symbol in self._lock_info:
                del self._lock_info[symbol]
        
        if expired:
            logger.info(f"🧹 Cleaned up {len(expired)} expired locks: {expired}")


# Global singleton
_lock_manager: Optional[PositionLockManager] = None


def get_position_lock_manager() -> PositionLockManager:
    """Get or create the global lock manager."""
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = PositionLockManager()
    return _lock_manager


def position_lock(symbol_arg: str = 'symbol', holder: str = 'unknown'):
    """
    Decorator to automatically acquire lock for position operations.
    
    Usage:
        @position_lock(symbol_arg='symbol', holder='trading_engine')
        async def close_position(symbol: str):
            # Lock is automatically acquired and released
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract symbol from kwargs or args
            if symbol_arg in kwargs:
                symbol = kwargs[symbol_arg]
            elif args:
                symbol = args[0]  # Assume first arg is symbol
            else:
                raise ValueError(f"Could not find symbol in arguments")
            
            lock_manager = get_position_lock_manager()
            
            async with lock_manager.acquire_lock(symbol, holder) as locked:
                if not locked:
                    raise RuntimeError(f"Could not acquire lock for {symbol}")
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator
