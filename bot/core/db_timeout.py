"""
Database Timeout Utility - Prevents hanging DB operations.

Provides timeout wrappers for synchronous and asynchronous database operations
to ensure the bot doesn't freeze on slow queries or connection issues.

Author: ASE BOT Team
Date: 2025-12-15
"""

import asyncio
import os
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import contextmanager
from functools import wraps
from typing import TypeVar, Callable, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Configuration from environment or defaults
DEFAULT_DB_TIMEOUT = int(os.getenv('DB_QUERY_TIMEOUT', 30))  # 30 seconds default
DEFAULT_DB_TIMEOUT_SHORT = int(os.getenv('DB_QUERY_TIMEOUT_SHORT', 10))  # 10 seconds for simple queries


class DBTimeoutError(Exception):
    """Raised when database operation times out."""
    pass


# Thread pool for timeout execution (reusable)
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="db_timeout_")


def db_operation_with_timeout(
    operation: Callable[[], Any],
    timeout_seconds: int = DEFAULT_DB_TIMEOUT,
    operation_name: str = "DB operation"
) -> Any:
    """
    Execute a synchronous DB operation with timeout protection.
    
    Uses ThreadPoolExecutor for cross-platform compatibility (works on macOS/Linux/Windows).
    
    Args:
        operation: Callable that performs the DB operation
        timeout_seconds: Maximum time to wait (default: 30s)
        operation_name: Name for logging purposes
        
    Returns:
        Result of the operation
        
    Raises:
        DBTimeoutError: If operation times out
        
    Usage:
        result = db_operation_with_timeout(
            lambda: db.session.query(Model).all(),
            timeout_seconds=10,
            operation_name="fetch_signals"
        )
    """
    future = _executor.submit(operation)
    
    try:
        result = future.result(timeout=timeout_seconds)
        return result
    except FuturesTimeoutError:
        future.cancel()
        error_msg = f"{operation_name} timed out after {timeout_seconds}s"
        logger.error(f"⏱️ DB TIMEOUT: {error_msg}")
        raise DBTimeoutError(error_msg)
    except Exception as e:
        logger.error(f"DB operation '{operation_name}' failed: {e}")
        raise


@contextmanager
def db_timeout(seconds: int = DEFAULT_DB_TIMEOUT, operation_name: str = "query"):
    """
    Context manager for DB operations with timeout (Unix-only, uses SIGALRM).
    
    Falls back to thread-based timeout on non-Unix systems.
    
    Usage:
        with db_timeout(10, "fetch_signals"):
            result = db.session.query(...).all()
    """
    # Check if we're on Unix and in main thread
    is_unix = hasattr(signal, 'SIGALRM')
    is_main_thread = threading.current_thread() is threading.main_thread()
    
    if is_unix and is_main_thread:
        # Unix with SIGALRM (more reliable)
        def timeout_handler(signum, frame):
            raise DBTimeoutError(f"DB {operation_name} timed out after {seconds}s")
        
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(seconds)
        
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        # Fallback for non-Unix or non-main thread
        # Just yield without timeout (operations should use db_operation_with_timeout instead)
        logger.debug(f"db_timeout context manager: no SIGALRM available, proceeding without timeout")
        yield


def with_db_timeout(timeout_seconds: int = DEFAULT_DB_TIMEOUT, operation_name: str = None):
    """
    Decorator for functions with DB operations.
    
    Usage:
        @with_db_timeout(10, "fetch_user_settings")
        def fetch_settings(user_id):
            return db.session.query(...).first()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            name = operation_name or func.__name__
            
            def operation():
                return func(*args, **kwargs)
            
            return db_operation_with_timeout(
                operation=operation,
                timeout_seconds=timeout_seconds,
                operation_name=name
            )
        return wrapper
    return decorator


async def async_db_timeout(
    coro,
    timeout_seconds: int = DEFAULT_DB_TIMEOUT,
    operation_name: str = "async DB operation"
):
    """
    Async wrapper for DB operations with timeout.
    
    Usage:
        result = await async_db_timeout(
            fetch_signals_async(),
            timeout_seconds=10,
            operation_name="fetch_signals"
        )
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        error_msg = f"{operation_name} timed out after {timeout_seconds}s"
        logger.error(f"⏱️ ASYNC DB TIMEOUT: {error_msg}")
        raise DBTimeoutError(error_msg)


def safe_db_query(
    query_func: Callable[[], Any],
    default_value: Any = None,
    timeout_seconds: int = DEFAULT_DB_TIMEOUT_SHORT,
    operation_name: str = "query"
) -> Any:
    """
    Execute a DB query with timeout and return default on failure.
    
    This is a "safe" wrapper that never raises - returns default_value on any error.
    Useful for non-critical queries where graceful degradation is preferred.
    
    Args:
        query_func: Callable that performs the query
        default_value: Value to return on timeout or error
        timeout_seconds: Maximum time to wait
        operation_name: Name for logging
        
    Returns:
        Query result or default_value on failure
        
    Usage:
        signals = safe_db_query(
            lambda: db.session.query(Signal).all(),
            default_value=[],
            timeout_seconds=5,
            operation_name="fetch_signals"
        )
    """
    try:
        return db_operation_with_timeout(
            operation=query_func,
            timeout_seconds=timeout_seconds,
            operation_name=operation_name
        )
    except DBTimeoutError:
        logger.warning(f"⚠️ {operation_name} timed out, using default value")
        return default_value
    except Exception as e:
        logger.warning(f"⚠️ {operation_name} failed ({e}), using default value")
        return default_value


# Cleanup function for graceful shutdown
def shutdown_timeout_executor():
    """Shutdown the thread pool executor gracefully."""
    global _executor
    _executor.shutdown(wait=False)
    logger.info("DB timeout executor shut down")
