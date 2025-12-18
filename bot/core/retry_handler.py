"""
Retry Handler - Robust retry logic for critical operations.

Provides:
1. Configurable retry with exponential backoff
2. Jitter to prevent thundering herd
3. Circuit breaker pattern
4. Per-operation type retry policies
"""

import asyncio
import functools
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import (
    Any, Callable, Dict, List, Optional, 
    Set, Type, TypeVar, Union
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryPolicy(Enum):
    """Predefined retry policies for different operation types."""
    AGGRESSIVE = "aggressive"      # Many retries, short delays
    CONSERVATIVE = "conservative"  # Few retries, longer delays
    CRITICAL = "critical"          # Many retries with exponential backoff
    QUICK = "quick"                # Few retries, minimal delays


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0        # Base delay in seconds
    max_delay: float = 60.0        # Maximum delay cap
    exponential_base: float = 2.0  # Exponential backoff multiplier
    jitter: bool = True            # Add randomness to prevent thundering herd
    jitter_factor: float = 0.3     # Jitter range (±30%)
    
    # Retryable exceptions (empty = retry all)
    retryable_exceptions: Set[Type[Exception]] = field(default_factory=set)
    
    # Non-retryable exceptions (always fail immediately)
    non_retryable_exceptions: Set[Type[Exception]] = field(default_factory=set)
    
    @classmethod
    def for_policy(cls, policy: RetryPolicy) -> 'RetryConfig':
        """Create config from predefined policy."""
        policies = {
            RetryPolicy.AGGRESSIVE: cls(
                max_retries=5,
                base_delay=0.5,
                max_delay=30.0,
                exponential_base=1.5
            ),
            RetryPolicy.CONSERVATIVE: cls(
                max_retries=2,
                base_delay=2.0,
                max_delay=60.0,
                exponential_base=3.0
            ),
            RetryPolicy.CRITICAL: cls(
                max_retries=10,
                base_delay=1.0,
                max_delay=120.0,
                exponential_base=2.0
            ),
            RetryPolicy.QUICK: cls(
                max_retries=2,
                base_delay=0.2,
                max_delay=5.0,
                exponential_base=2.0
            ),
        }
        return policies.get(policy, cls())


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5     # Failures before opening
    success_threshold: int = 3     # Successes before closing
    timeout: float = 60.0          # Time before half-open state


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class RetryStats:
    """Statistics for retry operations."""
    operation: str
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_delay: float = 0.0
    last_error: Optional[str] = None
    last_attempt: Optional[datetime] = None


class CircuitBreaker:
    """
    Circuit breaker pattern to prevent cascading failures.
    """
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
    
    def can_execute(self) -> bool:
        """Check if operation can be executed."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.config.timeout:
                    self.state = CircuitState.HALF_OPEN
                    logger.info(f"Circuit breaker {self.name}: OPEN -> HALF_OPEN")
                    return True
            return False
        
        # HALF_OPEN: allow single request to test
        return True
    
    def record_success(self):
        """Record successful operation."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info(f"Circuit breaker {self.name}: HALF_OPEN -> CLOSED")
        else:
            self.failure_count = 0
    
    def record_failure(self):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        self.success_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker {self.name}: HALF_OPEN -> OPEN")
        elif self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker {self.name}: CLOSED -> OPEN")


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class RetryHandler:
    """
    Handles retry logic with exponential backoff and circuit breaker.
    
    Usage:
        handler = RetryHandler()
        
        # Simple retry
        result = await handler.execute(
            operation=fetch_data,
            args=(url,),
            operation_name="fetch_data"
        )
        
        # With circuit breaker
        result = await handler.execute_with_circuit_breaker(
            operation=api_call,
            circuit_name="api",
            args=(params,)
        )
    """
    
    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.stats: Dict[str, RetryStats] = {}
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter."""
        delay = min(
            self.config.base_delay * (self.config.exponential_base ** attempt),
            self.config.max_delay
        )
        
        if self.config.jitter:
            jitter_range = delay * self.config.jitter_factor
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0.1, delay)  # Minimum 100ms
    
    def _should_retry(self, exception: Exception) -> bool:
        """Determine if exception is retryable."""
        exc_type = type(exception)
        error_str = str(exception).lower()
        
        # P0 FIX: Exchange-specific non-retryable errors
        # These errors won't be fixed by retrying - fail immediately
        NON_RETRYABLE_ERROR_PATTERNS = [
            'margin level too low',      # Kraken: insufficient margin
            'insufficient balance',       # Generic: not enough funds
            'insufficient funds',         # Generic: not enough funds
            'insufficient margin',        # Generic: margin too low
            'eorder:margin',              # Kraken margin errors
            'eorder:insufficient',        # Kraken insufficient errors
            'account has insufficient',   # Binance insufficient
            'notional must be',           # Binance min notional
            'min notional',               # Min order value
            'invalid api-key',            # Auth errors
            'invalid signature',          # Auth errors
            'permission denied',          # Auth errors
            'api key expired',            # Auth errors
        ]
        
        for pattern in NON_RETRYABLE_ERROR_PATTERNS:
            if pattern in error_str:
                logger.warning(f"🚫 Non-retryable error detected: {pattern}")
                return False
        
        # Check non-retryable first
        if self.config.non_retryable_exceptions:
            for non_retry_type in self.config.non_retryable_exceptions:
                if isinstance(exception, non_retry_type):
                    return False
        
        # If retryable list is specified, only retry those
        if self.config.retryable_exceptions:
            for retry_type in self.config.retryable_exceptions:
                if isinstance(exception, retry_type):
                    return True
            return False
        
        # Default: retry all except some common non-retryable
        non_retryable = (
            ValueError, TypeError, KeyError, 
            AttributeError, NotImplementedError
        )
        return not isinstance(exception, non_retryable)
    
    async def execute(
        self,
        operation: Callable,
        args: tuple = (),
        kwargs: dict = None,
        operation_name: str = None,
        config: RetryConfig = None
    ) -> Any:
        """
        Execute operation with retry logic.
        
        Args:
            operation: Callable to execute (can be async)
            args: Positional arguments
            kwargs: Keyword arguments
            operation_name: Name for logging
            config: Override default retry config
            
        Returns:
            Operation result
            
        Raises:
            Last exception if all retries fail
        """
        kwargs = kwargs or {}
        config = config or self.config
        op_name = operation_name or operation.__name__
        
        # Initialize stats
        if op_name not in self.stats:
            self.stats[op_name] = RetryStats(operation=op_name)
        stats = self.stats[op_name]
        
        last_exception = None
        total_delay = 0.0
        
        for attempt in range(config.max_retries + 1):
            stats.attempts += 1
            stats.last_attempt = datetime.now()
            
            try:
                # Execute operation
                if asyncio.iscoroutinefunction(operation):
                    result = await operation(*args, **kwargs)
                else:
                    result = operation(*args, **kwargs)
                
                stats.successes += 1
                
                if attempt > 0:
                    logger.info(
                        f"Operation {op_name} succeeded after {attempt + 1} attempts"
                    )
                
                return result
                
            except Exception as e:
                last_exception = e
                stats.failures += 1
                stats.last_error = str(e)
                
                # Check if we should retry
                if not self._should_retry(e):
                    logger.error(
                        f"Operation {op_name} failed with non-retryable error: {e}"
                    )
                    raise
                
                if attempt >= config.max_retries:
                    logger.error(
                        f"Operation {op_name} failed after {attempt + 1} attempts: {e}"
                    )
                    raise
                
                # Calculate and apply delay
                delay = self._calculate_delay(attempt)
                total_delay += delay
                stats.total_delay = total_delay
                
                logger.warning(
                    f"Operation {op_name} attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                
                await asyncio.sleep(delay)
        
        raise last_exception
    
    def get_or_create_circuit_breaker(
        self,
        name: str,
        config: CircuitBreakerConfig = None
    ) -> CircuitBreaker:
        """Get or create a circuit breaker."""
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(name, config)
        return self.circuit_breakers[name]
    
    async def execute_with_circuit_breaker(
        self,
        operation: Callable,
        circuit_name: str,
        args: tuple = (),
        kwargs: dict = None,
        operation_name: str = None,
        retry_config: RetryConfig = None,
        circuit_config: CircuitBreakerConfig = None
    ) -> Any:
        """
        Execute operation with circuit breaker and retry logic.
        
        Args:
            operation: Callable to execute
            circuit_name: Name of circuit breaker
            args: Positional arguments
            kwargs: Keyword arguments
            operation_name: Name for logging
            retry_config: Retry configuration
            circuit_config: Circuit breaker configuration
            
        Returns:
            Operation result
            
        Raises:
            CircuitBreakerOpenError if circuit is open
            Last exception if all retries fail
        """
        circuit = self.get_or_create_circuit_breaker(circuit_name, circuit_config)
        
        if not circuit.can_execute():
            raise CircuitBreakerOpenError(
                f"Circuit breaker {circuit_name} is open"
            )
        
        try:
            result = await self.execute(
                operation=operation,
                args=args,
                kwargs=kwargs,
                operation_name=operation_name,
                config=retry_config
            )
            circuit.record_success()
            return result
            
        except Exception as e:
            circuit.record_failure()
            raise
    
    def get_stats(self) -> Dict[str, dict]:
        """Get retry statistics."""
        return {
            name: {
                "operation": stats.operation,
                "attempts": stats.attempts,
                "successes": stats.successes,
                "failures": stats.failures,
                "success_rate": (
                    stats.successes / stats.attempts * 100 
                    if stats.attempts > 0 else 0
                ),
                "total_delay": round(stats.total_delay, 2),
                "last_error": stats.last_error,
                "last_attempt": stats.last_attempt.isoformat() if stats.last_attempt else None
            }
            for name, stats in self.stats.items()
        }


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    policy: RetryPolicy = None,
    circuit_breaker: str = None
):
    """
    Decorator for retry logic.
    
    Usage:
        @with_retry(max_retries=3)
        async def fetch_data(url):
            return await http_client.get(url)
        
        @with_retry(policy=RetryPolicy.CRITICAL, circuit_breaker="api")
        async def critical_operation():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Create config
        if policy:
            config = RetryConfig.for_policy(policy)
        else:
            config = RetryConfig(max_retries=max_retries, base_delay=base_delay)
        
        handler = RetryHandler(config)
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if circuit_breaker:
                return await handler.execute_with_circuit_breaker(
                    operation=func,
                    circuit_name=circuit_breaker,
                    args=args,
                    kwargs=kwargs,
                    operation_name=func.__name__
                )
            else:
                return await handler.execute(
                    operation=func,
                    args=args,
                    kwargs=kwargs,
                    operation_name=func.__name__
                )
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return asyncio.run(async_wrapper(*args, **kwargs))
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# Global handler instance
_retry_handler: Optional[RetryHandler] = None


def get_retry_handler(config: RetryConfig = None) -> RetryHandler:
    """Get or create global retry handler."""
    global _retry_handler
    if _retry_handler is None:
        _retry_handler = RetryHandler(config)
    return _retry_handler
