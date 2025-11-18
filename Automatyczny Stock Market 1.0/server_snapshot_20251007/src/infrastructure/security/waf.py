"""Web Application Firewall implementation."""

import re
import ipaddress
from typing import Set, List, Dict, Any
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import json
import time
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class WAFMiddleware(BaseHTTPMiddleware):
    """Web Application Firewall middleware."""
    
    def __init__(self, app):
        super().__init__(app)
        self.blocked_ips: Set[str] = set()
        self.allowed_ips: Set[str] = set()
        
        # Add internal Docker network IPs to allowed list
        self.internal_networks = [
            "172.18.0.0/16",  # Docker bridge network
            "172.17.0.0/16",  # Default Docker network
            "10.0.0.0/8",     # Private network
            "192.168.0.0/16", # Private network
            "127.0.0.1",      # Localhost
            "::1"             # IPv6 localhost
        ]
        self.sql_injection_patterns = [
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
            r"(\b(OR|AND)\s+\d+\s*=\s*\d+)",
            r"(--|#|/\*|\*/)",
            r"(\b(SCRIPT|JAVASCRIPT|VBSCRIPT)\b)",
            r"(\b(ONLOAD|ONERROR|ONCLICK)\b)",
        ]
        self.xss_patterns = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"vbscript:",
            r"onload\s*=",
            r"onerror\s*=",
            r"onclick\s*=",
        ]
        self.path_traversal_patterns = [
            r"\.\./",
            r"\.\.\\",
            r"%2e%2e%2f",
            r"%2e%2e\\",
        ]
        
        # Rate limiting per IP
        self.request_counts: Dict[str, List[float]] = {}
        self.max_requests_per_minute = 60
        self.max_requests_per_hour = 1000

    async def dispatch(self, request: Request, call_next):
        """Process request through WAF."""
        client_ip = self.get_client_ip(request)
        
        # Skip WAF for internal networks
        if self.is_internal_ip(client_ip):
            response = await call_next(request)
            response.headers["X-WAF-Status"] = "internal-bypass"
            return response
        
        # Check IP blacklist
        if client_ip in self.blocked_ips:
            logger.warning(f"Blocked IP attempted access: {client_ip}")
            return self.create_block_response("IP blocked")
        
        # Rate limiting
        if not self.check_rate_limit(client_ip):
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            return self.create_rate_limit_response()
        
        # Check for malicious patterns
        if await self.detect_attack(request):
            logger.error(f"Attack detected from {client_ip}: {request.url}")
            self.block_ip(client_ip)
            return self.create_block_response("Malicious request detected")
        
        # Process request
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-WAF-Status"] = "passed"
        response.headers["X-Request-ID"] = str(time.time())
        
        return response

    def get_client_ip(self, request: Request) -> str:
        """Get real client IP address."""
        # Check X-Forwarded-For header (from proxy/CDN)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct connection
        return request.client.host if request.client else "unknown"

    def is_internal_ip(self, ip: str) -> bool:
        """Check if IP is from internal network."""
        if not ip or ip == "unknown":
            return False
            
        try:
            import ipaddress
            ip_obj = ipaddress.ip_address(ip)
            
            # Check against internal networks
            for network in self.internal_networks:
                if "/" in network:
                    if ip_obj in ipaddress.ip_network(network):
                        return True
                else:
                    if str(ip_obj) == network:
                        return True
                        
            return False
        except ValueError:
            # Invalid IP format
            return False

    def check_rate_limit(self, ip: str) -> bool:
        """Check if IP is within rate limits."""
        now = time.time()
        
        # Initialize if not exists
        if ip not in self.request_counts:
            self.request_counts[ip] = []
        
        # Clean old requests (older than 1 hour)
        self.request_counts[ip] = [
            req_time for req_time in self.request_counts[ip] 
            if now - req_time < 3600
        ]
        
        # Check hourly limit
        if len(self.request_counts[ip]) >= self.max_requests_per_hour:
            return False
        
        # Check per-minute limit
        recent_requests = [
            req_time for req_time in self.request_counts[ip]
            if now - req_time < 60
        ]
        
        if len(recent_requests) >= self.max_requests_per_minute:
            return False
        
        # Add current request
        self.request_counts[ip].append(now)
        return True

    async def detect_attack(self, request: Request) -> bool:
        """Detect various attack patterns."""
        # Get request data
        url = str(request.url)
        headers = dict(request.headers)
        
        # Get body if POST/PUT
        body = ""
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body_bytes = await request.body()
                body = body_bytes.decode('utf-8')
            except (UnicodeDecodeError, Exception) as e:
                logger.warning(f"Failed to decode request body: {e}")
                body = ""
        
        # Check SQL injection
        if self.check_sql_injection(url + " " + body):
            return True
        
        # Check XSS
        if self.check_xss(url + " " + body):
            return True
        
        # Check path traversal
        if self.check_path_traversal(url):
            return True
        
        # Check suspicious headers
        if self.check_suspicious_headers(headers):
            return True
        
        return False

    def check_sql_injection(self, content: str) -> bool:
        """Check for SQL injection patterns."""
        content_lower = content.lower()
        for pattern in self.sql_injection_patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                return True
        return False

    def check_xss(self, content: str) -> bool:
        """Check for XSS patterns."""
        content_lower = content.lower()
        for pattern in self.xss_patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                return True
        return False

    def check_path_traversal(self, url: str) -> bool:
        """Check for path traversal patterns."""
        for pattern in self.path_traversal_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

    def check_suspicious_headers(self, headers: Dict[str, str]) -> bool:
        """Check for suspicious headers."""
        suspicious_headers = [
            "x-forwarded-host",
            "x-originating-ip", 
            "x-remote-ip",
            "x-remote-addr"
        ]
        
        for header in suspicious_headers:
            if header in headers:
                # Additional validation could be added here
                pass
        
        return False

    def block_ip(self, ip: str):
        """Add IP to blocklist."""
        # Don't block internal IPs
        if not self.is_internal_ip(ip):
            self.blocked_ips.add(ip)
            logger.error(f"IP blocked: {ip}")
        else:
            logger.warning(f"Attempted to block internal IP: {ip} - skipped")

    def unblock_ip(self, ip: str):
        """Remove IP from blocklist."""
        self.blocked_ips.discard(ip)
        logger.info(f"IP unblocked: {ip}")
        
    def clear_blocked_ips(self):
        """Clear all blocked IPs (emergency function)."""
        self.blocked_ips.clear()
        logger.info("All blocked IPs cleared")

    def create_block_response(self, reason: str) -> Response:
        """Create response for blocked requests."""
        return Response(
            content=json.dumps({"error": "Access denied", "reason": reason}),
            status_code=403,
            headers={"Content-Type": "application/json"}
        )

    def create_rate_limit_response(self) -> Response:
        """Create response for rate limited requests."""
        return Response(
            content=json.dumps({"error": "Rate limit exceeded"}),
            status_code=429,
            headers={
                "Content-Type": "application/json",
                "Retry-After": "60"
            }
        )


class SIEMLogger:
    """Security Information and Event Management logger."""
    
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        
    def log_security_event(self, event_type: str, details: Dict[str, Any]):
        """Log security event for SIEM."""
        event = {
            "timestamp": time.time(),
            "event_type": event_type,
            "details": details,
            "severity": self.get_severity(event_type)
        }
        
        self.events.append(event)
        logger.error(f"SECURITY EVENT: {event_type} - {details}")
        
        # In production, send to external SIEM system
        # await self.send_to_siem(event)
    
    def get_severity(self, event_type: str) -> str:
        """Get event severity level."""
        high_severity = ["sql_injection", "xss_attempt", "path_traversal"]
        medium_severity = ["rate_limit_exceeded", "suspicious_ip"]
        
        if event_type in high_severity:
            return "HIGH"
        elif event_type in medium_severity:
            return "MEDIUM"
        else:
            return "LOW"
    
    async def send_to_siem(self, event: Dict[str, Any]):
        """Send event to external SIEM system."""
        # Implementation for external SIEM integration
        # e.g., Splunk, ELK Stack, Azure Sentinel
        pass


# Global SIEM logger instance
siem_logger = SIEMLogger()
