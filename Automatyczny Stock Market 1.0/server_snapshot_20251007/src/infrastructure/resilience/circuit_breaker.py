"""Circuit Breaker pattern implementation for resilience."""

import asyncio
import time
from enum import Enum
from typing import Callable, Any, Optional, Dict
from dataclasses import dataclass
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, blocking calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5          # Failures before opening
    recovery_timeout: int = 60          # Seconds before trying again
    expected_exception: type = Exception
    timeout: int = 30                   # Request timeout in seconds


class CircuitBreaker:
    """Circuit breaker for external service calls."""
    
    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.success_count = 0
        
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        
        # Check if circuit is open
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time < self.config.recovery_timeout:
                raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is OPEN")
            else:
                # Try to recover
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info(f"Circuit breaker {self.name} entering HALF_OPEN state")
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.timeout
            )
            
            # Success - reset failure count
            await self.on_success()
            return result
            
        except self.config.expected_exception as e:
            await self.on_failure()
            raise
        except asyncio.TimeoutError:
            await self.on_failure()
            raise CircuitBreakerTimeoutError(f"Circuit breaker {self.name} timeout")
    
    async def on_success(self):
        """Handle successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= 3:  # 3 successful calls to close
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info(f"Circuit breaker {self.name} CLOSED - service recovered")
        else:
            self.failure_count = 0
    
    async def on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            logger.error(f"Circuit breaker {self.name} OPENED - service failing")
    
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "success_count": self.success_count
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreakerTimeoutError(Exception):
    """Raised when circuit breaker times out."""
    pass


class CircuitBreakerManager:
    """Manage multiple circuit breakers."""
    
    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
    
    def get_breaker(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get or create circuit breaker."""
        if name not in self.breakers:
            config = config or CircuitBreakerConfig()
            self.breakers[name] = CircuitBreaker(name, config)
        return self.breakers[name]
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get states of all circuit breakers."""
        return {name: breaker.get_state() for name, breaker in self.breakers.items()}


# Global circuit breaker manager
circuit_manager = CircuitBreakerManager()


# Decorator for easy circuit breaker usage
def circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None):
    """Decorator to add circuit breaker to async functions."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            breaker = circuit_manager.get_breaker(name, config)
            return await breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator


# Pre-configured circuit breakers for common services
database_breaker = circuit_manager.get_breaker(
    "database",
    CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30)
)

redis_breaker = circuit_manager.get_breaker(
    "redis", 
    CircuitBreakerConfig(failure_threshold=5, recovery_timeout=15)
)

ai_breaker = circuit_manager.get_breaker(
    "ai_service",
    CircuitBreakerConfig(failure_threshold=3, recovery_timeout=120, timeout=45)
)
