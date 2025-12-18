"""SLO (Service Level Objectives) monitoring and alerting."""

import time
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import json

from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class SLOType(Enum):
    AVAILABILITY = "availability"
    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"


@dataclass
class SLOConfig:
    name: str
    slo_type: SLOType
    target: float  # e.g., 0.999 for 99.9% availability
    window_minutes: int = 60
    alert_threshold: float = 0.95  # Alert when SLO drops below 95% of target


class SLOMonitor:
    """Monitor and track SLO metrics."""
    
    def __init__(self):
        self.cache = RedisCache()
        self.slos: Dict[str, SLOConfig] = {}
        self.setup_default_slos()
        
    def setup_default_slos(self):
        """Setup default SLO configurations."""
        self.slos = {
            "api_availability": SLOConfig(
                name="API Availability",
                slo_type=SLOType.AVAILABILITY,
                target=0.999,  # 99.9%
                window_minutes=60
            ),
            "api_latency_p95": SLOConfig(
                name="API Latency P95",
                slo_type=SLOType.LATENCY,
                target=2.0,  # 2 seconds
                window_minutes=60
            ),
            "error_rate": SLOConfig(
                name="Error Rate",
                slo_type=SLOType.ERROR_RATE,
                target=0.005,  # 0.5%
                window_minutes=60
            ),
            "login_success_rate": SLOConfig(
                name="Login Success Rate",
                slo_type=SLOType.AVAILABILITY,
                target=0.995,  # 99.5%
                window_minutes=60
            )
        }
    
    async def record_request(self, endpoint: str, status_code: int, duration: float):
        """Record request metrics for SLO tracking."""
        timestamp = int(time.time())
        minute_bucket = timestamp // 60
        
        # Record for availability SLO
        await self._record_availability(minute_bucket, endpoint, status_code)
        
        # Record for latency SLO
        await self._record_latency(minute_bucket, endpoint, duration)
        
        # Record for error rate SLO
        await self._record_error_rate(minute_bucket, endpoint, status_code)
        
        # Check SLOs periodically
        if timestamp % 300 == 0:  # Every 5 minutes
            asyncio.create_task(self.check_all_slos())
    
    async def _record_availability(self, minute_bucket: int, endpoint: str, status_code: int):
        """Record availability metrics."""
        key = f"slo:availability:{minute_bucket}"
        
        # Increment total requests
        await self.cache.increment(f"{key}:total")
        
        # Increment successful requests (2xx, 3xx)
        if 200 <= status_code < 400:
            await self.cache.increment(f"{key}:success")
        
        # Set expiration (keep data for 24 hours)
        await self.cache.redis.expire(f"{key}:total", 86400)
        await self.cache.redis.expire(f"{key}:success", 86400)
    
    async def _record_latency(self, minute_bucket: int, endpoint: str, duration: float):
        """Record latency metrics."""
        key = f"slo:latency:{minute_bucket}"
        
        # Store latency values for percentile calculation
        await self.cache.redis.lpush(f"{key}:durations", duration)
        await self.cache.redis.ltrim(f"{key}:durations", 0, 999)  # Keep last 1000
        await self.cache.redis.expire(f"{key}:durations", 86400)
    
    async def _record_error_rate(self, minute_bucket: int, endpoint: str, status_code: int):
        """Record error rate metrics."""
        key = f"slo:errors:{minute_bucket}"
        
        # Increment total requests
        await self.cache.increment(f"{key}:total")
        
        # Increment errors (4xx, 5xx)
        if status_code >= 400:
            await self.cache.increment(f"{key}:errors")
        
        # Set expiration
        await self.cache.redis.expire(f"{key}:total", 86400)
        await self.cache.redis.expire(f"{key}:errors", 86400)
    
    async def check_all_slos(self):
        """Check all SLOs and trigger alerts if needed."""
        for slo_name, slo_config in self.slos.items():
            current_value = await self.calculate_slo(slo_config)
            
            if current_value is not None:
                await self.check_slo_violation(slo_config, current_value)
    
    async def calculate_slo(self, slo_config: SLOConfig) -> Optional[float]:
        """Calculate current SLO value."""
        current_time = int(time.time())
        window_start = current_time - (slo_config.window_minutes * 60)
        
        if slo_config.slo_type == SLOType.AVAILABILITY:
            return await self._calculate_availability(window_start, current_time)
        elif slo_config.slo_type == SLOType.LATENCY:
            return await self._calculate_latency_p95(window_start, current_time)
        elif slo_config.slo_type == SLOType.ERROR_RATE:
            return await self._calculate_error_rate(window_start, current_time)
        
        return None
    
    async def _calculate_availability(self, start_time: int, end_time: int) -> Optional[float]:
        """Calculate availability percentage."""
        total_requests = 0
        successful_requests = 0
        
        for timestamp in range(start_time // 60, end_time // 60 + 1):
            key = f"slo:availability:{timestamp}"
            total = await self.cache.get(f"{key}:total") or 0
            success = await self.cache.get(f"{key}:success") or 0
            
            total_requests += int(total)
            successful_requests += int(success)
        
        if total_requests == 0:
            return None
            
        return successful_requests / total_requests
    
    async def _calculate_latency_p95(self, start_time: int, end_time: int) -> Optional[float]:
        """Calculate P95 latency."""
        all_durations = []
        
        for timestamp in range(start_time // 60, end_time // 60 + 1):
            key = f"slo:latency:{timestamp}:durations"
            durations = await self.cache.redis.lrange(key, 0, -1)
            all_durations.extend([float(d) for d in durations])
        
        if not all_durations:
            return None
            
        all_durations.sort()
        p95_index = int(len(all_durations) * 0.95)
        return all_durations[p95_index] if p95_index < len(all_durations) else all_durations[-1]
    
    async def _calculate_error_rate(self, start_time: int, end_time: int) -> Optional[float]:
        """Calculate error rate percentage."""
        total_requests = 0
        error_requests = 0
        
        for timestamp in range(start_time // 60, end_time // 60 + 1):
            key = f"slo:errors:{timestamp}"
            total = await self.cache.get(f"{key}:total") or 0
            errors = await self.cache.get(f"{key}:errors") or 0
            
            total_requests += int(total)
            error_requests += int(errors)
        
        if total_requests == 0:
            return None
            
        return error_requests / total_requests
    
    async def check_slo_violation(self, slo_config: SLOConfig, current_value: float):
        """Check if SLO is violated and trigger alerts."""
        if slo_config.slo_type == SLOType.LATENCY:
            # For latency, higher is worse
            violation = current_value > slo_config.target
            severity = "HIGH" if current_value > slo_config.target * 2 else "MEDIUM"
        else:
            # For availability/error rate, lower is worse
            threshold = slo_config.target * slo_config.alert_threshold
            violation = current_value < threshold
            severity = "HIGH" if current_value < threshold * 0.9 else "MEDIUM"
        
        if violation:
            await self.trigger_alert(slo_config, current_value, severity)
    
    async def trigger_alert(self, slo_config: SLOConfig, current_value: float, severity: str):
        """Trigger SLO violation alert."""
        alert_data = {
            "slo_name": slo_config.name,
            "slo_type": slo_config.slo_type.value,
            "target": slo_config.target,
            "current_value": current_value,
            "severity": severity,
            "timestamp": time.time(),
            "window_minutes": slo_config.window_minutes
        }
        
        # Log alert
        logger.error(f"SLO VIOLATION: {slo_config.name} - Current: {current_value}, Target: {slo_config.target}")
        
        # Store alert for dashboard
        alert_key = f"alerts:slo:{int(time.time())}"
        await self.cache.set(alert_key, alert_data, ttl=86400)
        
        # In production, send to external alerting system
        await self.send_external_alert(alert_data)
    
    async def send_external_alert(self, alert_data: Dict[str, Any]):
        """Send alert to external system (Slack, PagerDuty, etc.)."""
        # Implementation for external alerting
        # e.g., Slack webhook, PagerDuty API, email
        pass
    
    async def get_slo_dashboard_data(self) -> Dict[str, Any]:
        """Get SLO data for dashboard display."""
        dashboard_data = {}
        
        for slo_name, slo_config in self.slos.items():
            current_value = await self.calculate_slo(slo_config)
            
            dashboard_data[slo_name] = {
                "name": slo_config.name,
                "type": slo_config.slo_type.value,
                "target": slo_config.target,
                "current": current_value,
                "status": "OK" if current_value and current_value >= (slo_config.target * slo_config.alert_threshold) else "VIOLATION"
            }
        
        return dashboard_data


# Global SLO monitor
slo_monitor = SLOMonitor()
