"""Comprehensive audit logging service."""

import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

from src.infrastructure.logging.logger import get_logger
from src.infrastructure.cache.redis_cache import RedisCache

logger = get_logger(__name__)


class AuditAction(Enum):
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_REGISTER = "user_register"
    PASSWORD_CHANGE = "password_change"
    ROLE_CHANGE = "role_change"
    TRADE_EXECUTE = "trade_execute"
    SETTINGS_CHANGE = "settings_change"
    API_ACCESS = "api_access"
    SECURITY_VIOLATION = "security_violation"
    DATA_EXPORT = "data_export"


class AuditSeverity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuditLogger:
    """Comprehensive audit logging for compliance and security."""
    
    def __init__(self):
        self.cache = RedisCache()
        
    async def log_audit_event(
        self,
        action: AuditAction,
        user_id: Optional[int] = None,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        severity: AuditSeverity = AuditSeverity.INFO
    ):
        """Log comprehensive audit event."""
        
        # Sanitize details to remove sensitive data
        safe_details = self._sanitize_details(details or {})
        
        audit_event = {
            "action": action.value,
            "user_id": user_id,
            "resource": resource,
            "timestamp": datetime.utcnow().isoformat(),
            "ip_address": ip_address,
            "user_agent": user_agent,
            "details": safe_details,
            "success": success,
            "severity": severity.value,
            "trace_id": self._get_trace_id()
        }
        
        # Log to application logs
        log_message = f"AUDIT: {action.value} - User: {user_id} - Success: {success}"
        if severity == AuditSeverity.CRITICAL:
            logger.critical(log_message, extra={"audit_event": audit_event})
        elif severity == AuditSeverity.ERROR:
            logger.error(log_message, extra={"audit_event": audit_event})
        elif severity == AuditSeverity.WARNING:
            logger.warning(log_message, extra={"audit_event": audit_event})
        else:
            logger.info(log_message, extra={"audit_event": audit_event})
        
        # Store in cache for real-time monitoring
        cache_key = f"audit:recent:{int(time.time())}"
        await self.cache.set(cache_key, audit_event, ttl=3600)  # Keep for 1 hour
        
        # Store in database (in production, this would be async queue)
        await self._store_in_database(audit_event)
        
        # Trigger real-time alerts for critical events
        if severity in [AuditSeverity.ERROR, AuditSeverity.CRITICAL]:
            await self._trigger_security_alert(audit_event)
    
    def _sanitize_details(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive information from audit details."""
        sensitive_fields = [
            'password', 'password_hash', 'token', 'secret', 'key',
            'api_key', 'private_key', 'credit_card', 'ssn'
        ]
        
        sanitized = {}
        for key, value in details.items():
            if any(sensitive in key.lower() for sensitive in sensitive_fields):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_details(value)
            else:
                sanitized[key] = value
                
        return sanitized
    
    def _get_trace_id(self) -> Optional[str]:
        """Get current OpenTelemetry trace ID."""
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            if span and span.is_recording():
                return format(span.get_span_context().trace_id, '032x')
        except ImportError:
            pass
        return None
    
    async def _store_in_database(self, audit_event: Dict[str, Any]):
        """Store audit event in database."""
        # In production, this would use a message queue for async processing
        # For now, we'll store directly (should be made async with Celery/RQ)
        try:
            # This would be implemented with the audit_log table
            pass
        except Exception as e:
            logger.error(f"Failed to store audit event in database: {e}")
    
    async def _trigger_security_alert(self, audit_event: Dict[str, Any]):
        """Trigger security alert for critical events."""
        alert_data = {
            "type": "security_alert",
            "event": audit_event,
            "timestamp": time.time(),
            "requires_immediate_attention": audit_event["severity"] == AuditSeverity.CRITICAL.value
        }
        
        # Store alert
        alert_key = f"security_alerts:{int(time.time())}"
        await self.cache.set(alert_key, alert_data, ttl=86400)
        
        # In production: send to SIEM, Slack, PagerDuty
        logger.critical(f"SECURITY ALERT: {audit_event['action']} - {audit_event.get('details', {})}")
    
    async def get_recent_audit_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent audit events for dashboard."""
        # Get recent events from cache
        pattern = "audit:recent:*"
        keys = await self.cache.redis.keys(pattern)
        
        events = []
        for key in sorted(keys, reverse=True)[:limit]:
            event = await self.cache.get(key)
            if event:
                events.append(event)
        
        return events
    
    async def get_security_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent security alerts."""
        pattern = "security_alerts:*"
        keys = await self.cache.redis.keys(pattern)
        
        alerts = []
        for key in sorted(keys, reverse=True)[:limit]:
            alert = await self.cache.get(key)
            if alert:
                alerts.append(alert)
        
        return alerts


# Global audit logger instance
audit_logger = AuditLogger()


# Decorator for automatic audit logging
def audit_log(action: AuditAction, resource: Optional[str] = None, severity: AuditSeverity = AuditSeverity.INFO):
    """Decorator to automatically log function calls."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            error = None
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                # Extract user context if available
                user_id = None
                if hasattr(args[0], 'user') and args[0].user:
                    user_id = args[0].user.id
                
                # Log audit event
                await audit_logger.log_audit_event(
                    action=action,
                    user_id=user_id,
                    resource=resource,
                    details={
                        "function": func.__name__,
                        "duration_ms": round((time.time() - start_time) * 1000, 2),
                        "error": error
                    },
                    success=success,
                    severity=severity if success else AuditSeverity.ERROR
                )
        
        return wrapper
    return decorator
