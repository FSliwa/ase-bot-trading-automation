"""
Advanced System Monitoring and Performance Tracking
Prometheus metrics, Grafana integration, alerting system
"""

import asyncio
import logging
import psutil
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import threading
from collections import defaultdict, deque

# Monitoring and metrics imports
try:
    from prometheus_client import Counter, Histogram, Gauge, Summary, CollectorRegistry, generate_latest
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

logger = logging.getLogger(__name__)

class MetricType(str, Enum):
    """Types of metrics to track"""
    COUNTER = "counter"
    GAUGE = "gauge" 
    HISTOGRAM = "histogram"
    SUMMARY = "summary"

class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class MetricConfig:
    """Metric configuration"""
    name: str
    metric_type: MetricType
    description: str
    labels: List[str] = field(default_factory=list)
    buckets: Optional[List[float]] = None
    objectives: Optional[Dict[float, float]] = None

@dataclass
class Alert:
    """System alert definition"""
    id: str
    severity: AlertSeverity
    message: str
    metric_name: str
    threshold: float
    current_value: float
    timestamp: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolved_at: Optional[datetime] = None

@dataclass
class SystemStats:
    """System performance statistics"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_available_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_free_gb: float
    network_sent_mb: float
    network_recv_mb: float
    active_threads: int
    open_files: int
    load_average: List[float]

class SystemMonitor:
    """Advanced system monitoring and alerting"""
    
    def __init__(self, enable_prometheus: bool = True):
        # Prometheus setup
        self.enable_prometheus = enable_prometheus and HAS_PROMETHEUS
        self.registry = CollectorRegistry() if self.enable_prometheus else None
        
        # Core metrics
        self.metrics: Dict[str, Any] = {}
        self.metric_configs: Dict[str, MetricConfig] = {}
        
        # Performance tracking
        self.system_stats_history: deque = deque(maxlen=3600)  # 1 hour of data
        self.performance_baselines: Dict[str, float] = {}
        
        # Alerting
        self.alerts: Dict[str, Alert] = {}
        self.alert_rules: Dict[str, Dict] = {}
        self.alert_callbacks: List[callable] = []
        
        # Monitoring state
        self.is_monitoring = False
        self.monitor_interval = 10.0  # 10 seconds
        self.cleanup_interval = 3600.0  # 1 hour
        
        # Trading-specific metrics
        self.trading_metrics: Dict[str, Any] = defaultdict(int)
        self.latency_history: deque = deque(maxlen=1000)
        self.error_counts: Dict[str, int] = defaultdict(int)
        
        # Thread safety
        self.lock = threading.Lock()
        
        # Initialize default metrics
        self._setup_default_metrics()
        self._setup_default_alert_rules()

    def _setup_default_metrics(self):
        """Setup default system metrics"""
        default_metrics = [
            # System metrics
            MetricConfig("system_cpu_percent", MetricType.GAUGE, "CPU usage percentage"),
            MetricConfig("system_memory_percent", MetricType.GAUGE, "Memory usage percentage"),
            MetricConfig("system_disk_percent", MetricType.GAUGE, "Disk usage percentage"),
            MetricConfig("system_network_bytes_sent", MetricType.COUNTER, "Network bytes sent"),
            MetricConfig("system_network_bytes_recv", MetricType.COUNTER, "Network bytes received"),
            MetricConfig("system_threads_active", MetricType.GAUGE, "Active threads count"),
            MetricConfig("system_files_open", MetricType.GAUGE, "Open files count"),
            
            # Trading metrics
            MetricConfig("trading_orders_total", MetricType.COUNTER, "Total orders processed", ["status", "exchange"]),
            MetricConfig("trading_positions_active", MetricType.GAUGE, "Active positions count", ["exchange"]),
            MetricConfig("trading_balance_total", MetricType.GAUGE, "Total balance", ["currency", "exchange"]),
            MetricConfig("trading_pnl_realized", MetricType.COUNTER, "Realized P&L", ["exchange"]),
            MetricConfig("trading_api_requests", MetricType.COUNTER, "API requests count", ["exchange", "endpoint"]),
            MetricConfig("trading_api_latency", MetricType.HISTOGRAM, "API request latency", ["exchange"], 
                        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]),
            
            # Application metrics  
            MetricConfig("app_requests_total", MetricType.COUNTER, "HTTP requests total", ["method", "endpoint", "status"]),
            MetricConfig("app_request_duration", MetricType.HISTOGRAM, "HTTP request duration", ["endpoint"],
                        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]),
            MetricConfig("app_errors_total", MetricType.COUNTER, "Application errors", ["error_type"]),
            MetricConfig("app_cache_hits", MetricType.COUNTER, "Cache hits", ["cache_type"]),
            MetricConfig("app_cache_misses", MetricType.COUNTER, "Cache misses", ["cache_type"]),
            
            # Database metrics
            MetricConfig("db_connections_active", MetricType.GAUGE, "Active database connections"),
            MetricConfig("db_queries_total", MetricType.COUNTER, "Database queries total", ["operation"]),
            MetricConfig("db_query_duration", MetricType.HISTOGRAM, "Database query duration", ["operation"],
                        buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]),
        ]
        
        for config in default_metrics:
            self.add_metric(config)

    def _setup_default_alert_rules(self):
        """Setup default alerting rules"""
        self.alert_rules = {
            # System alerts
            "high_cpu_usage": {
                "metric": "system_cpu_percent",
                "threshold": 80.0,
                "operator": "gt",
                "severity": AlertSeverity.WARNING,
                "message": "High CPU usage detected: {value:.1f}%"
            },
            "critical_cpu_usage": {
                "metric": "system_cpu_percent", 
                "threshold": 95.0,
                "operator": "gt",
                "severity": AlertSeverity.CRITICAL,
                "message": "Critical CPU usage: {value:.1f}%"
            },
            "high_memory_usage": {
                "metric": "system_memory_percent",
                "threshold": 85.0,
                "operator": "gt", 
                "severity": AlertSeverity.WARNING,
                "message": "High memory usage: {value:.1f}%"
            },
            "critical_memory_usage": {
                "metric": "system_memory_percent",
                "threshold": 95.0,
                "operator": "gt",
                "severity": AlertSeverity.CRITICAL,
                "message": "Critical memory usage: {value:.1f}%"
            },
            "high_disk_usage": {
                "metric": "system_disk_percent",
                "threshold": 90.0,
                "operator": "gt",
                "severity": AlertSeverity.WARNING,
                "message": "High disk usage: {value:.1f}%"
            },
            
            # Trading alerts
            "high_api_latency": {
                "metric": "trading_api_latency_avg",
                "threshold": 2.0,
                "operator": "gt",
                "severity": AlertSeverity.WARNING, 
                "message": "High API latency: {value:.2f}s"
            },
            "trading_errors_spike": {
                "metric": "app_errors_rate",
                "threshold": 10.0,
                "operator": "gt",
                "severity": AlertSeverity.ERROR,
                "message": "Trading errors spike: {value:.1f} errors/min"
            }
        }

    def add_metric(self, config: MetricConfig):
        """Add a new metric for tracking"""
        if not self.enable_prometheus:
            logger.warning("Prometheus not available, metrics will be stored locally only")
        
        self.metric_configs[config.name] = config
        
        if self.enable_prometheus:
            try:
                if config.metric_type == MetricType.COUNTER:
                    metric = Counter(
                        config.name,
                        config.description, 
                        labelnames=config.labels,
                        registry=self.registry
                    )
                elif config.metric_type == MetricType.GAUGE:
                    metric = Gauge(
                        config.name,
                        config.description,
                        labelnames=config.labels,
                        registry=self.registry
                    )
                elif config.metric_type == MetricType.HISTOGRAM:
                    buckets = config.buckets or [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
                    metric = Histogram(
                        config.name,
                        config.description,
                        labelnames=config.labels,
                        buckets=buckets,
                        registry=self.registry
                    )
                elif config.metric_type == MetricType.SUMMARY:
                    objectives = config.objectives or {0.5: 0.05, 0.9: 0.01, 0.99: 0.001}
                    metric = Summary(
                        config.name,
                        config.description,
                        labelnames=config.labels,
                        objectives=objectives,
                        registry=self.registry
                    )
                
                self.metrics[config.name] = metric
                logger.debug(f"📊 Added metric: {config.name}")
                
            except Exception as e:
                logger.error(f"Failed to create metric {config.name}: {e}")
        else:
            # Store local metric placeholder
            self.metrics[config.name] = {"type": config.metric_type, "value": 0, "labels": {}}

    def record_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a metric value"""
        labels = labels or {}
        
        with self.lock:
            if name not in self.metrics:
                logger.warning(f"Metric {name} not found")
                return
            
            try:
                if self.enable_prometheus:
                    metric = self.metrics[name]
                    config = self.metric_configs[name]
                    
                    if config.metric_type == MetricType.COUNTER:
                        if labels:
                            metric.labels(**labels).inc(value)
                        else:
                            metric.inc(value)
                    elif config.metric_type == MetricType.GAUGE:
                        if labels:
                            metric.labels(**labels).set(value)
                        else:
                            metric.set(value)
                    elif config.metric_type == MetricType.HISTOGRAM:
                        if labels:
                            metric.labels(**labels).observe(value)
                        else:
                            metric.observe(value)
                    elif config.metric_type == MetricType.SUMMARY:
                        if labels:
                            metric.labels(**labels).observe(value)
                        else:
                            metric.observe(value)
                else:
                    # Local storage
                    metric = self.metrics[name]
                    metric["value"] = value
                    metric["labels"] = labels
                    metric["timestamp"] = datetime.now()
                
                # Check alert rules
                self._check_alert_rules(name, value)
                
            except Exception as e:
                logger.error(f"Failed to record metric {name}: {e}")

    def increment_counter(self, name: str, amount: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric"""
        self.record_metric(name, amount, labels)

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric value"""
        self.record_metric(name, value, labels)

    def observe_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record histogram observation"""
        self.record_metric(name, value, labels)

    def time_function(self, metric_name: str, labels: Optional[Dict[str, str]] = None):
        """Decorator to time function execution"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    execution_time = time.time() - start_time
                    self.observe_histogram(metric_name, execution_time, labels)
                    return result
                except Exception as e:
                    execution_time = time.time() - start_time
                    self.observe_histogram(metric_name, execution_time, labels)
                    self.increment_counter("app_errors_total", 1.0, {"error_type": type(e).__name__})
                    raise
            return wrapper
        return decorator

    async def start_monitoring(self):
        """Start system monitoring"""
        if self.is_monitoring:
            logger.warning("Monitoring already running")
            return
        
        self.is_monitoring = True
        logger.info("🔍 Starting System Monitor...")
        
        # Start monitoring tasks
        asyncio.create_task(self._system_monitoring_loop())
        asyncio.create_task(self._alert_monitoring_loop())
        asyncio.create_task(self._cleanup_loop())
        asyncio.create_task(self._performance_analysis_loop())
        
        logger.info("✅ System monitoring started")

    async def stop_monitoring(self):
        """Stop system monitoring"""
        self.is_monitoring = False
        logger.info("🛑 System monitoring stopped")

    async def _system_monitoring_loop(self):
        """Main system monitoring loop"""
        while self.is_monitoring:
            try:
                # Collect system stats
                stats = await self._collect_system_stats()
                
                # Record metrics
                self.set_gauge("system_cpu_percent", stats.cpu_percent)
                self.set_gauge("system_memory_percent", stats.memory_percent)
                self.set_gauge("system_disk_percent", stats.disk_percent)
                self.set_gauge("system_threads_active", stats.active_threads)
                self.set_gauge("system_files_open", stats.open_files)
                
                # Store in history
                self.system_stats_history.append(stats)
                
                await asyncio.sleep(self.monitor_interval)
                
            except Exception as e:
                logger.error(f"System monitoring error: {e}")
                await asyncio.sleep(30.0)

    async def _collect_system_stats(self) -> SystemStats:
        """Collect current system statistics"""
        try:
            # CPU and memory
            cpu_percent = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            
            # Network stats
            network = psutil.net_io_counters()
            
            # Process info
            process = psutil.Process()
            threads = process.num_threads()
            open_files = len(process.open_files())
            
            # Load average (Linux/Unix)
            load_avg = list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else [0.0, 0.0, 0.0]
            
            return SystemStats(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_gb=memory.used / (1024**3),
                memory_available_gb=memory.available / (1024**3),
                disk_percent=(disk.used / disk.total) * 100,
                disk_used_gb=disk.used / (1024**3),
                disk_free_gb=disk.free / (1024**3),
                network_sent_mb=network.bytes_sent / (1024**2),
                network_recv_mb=network.bytes_recv / (1024**2),
                active_threads=threads,
                open_files=open_files,
                load_average=load_avg
            )
            
        except Exception as e:
            logger.error(f"Failed to collect system stats: {e}")
            return SystemStats(
                timestamp=datetime.now(),
                cpu_percent=0.0, memory_percent=0.0, memory_used_gb=0.0,
                memory_available_gb=0.0, disk_percent=0.0, disk_used_gb=0.0,
                disk_free_gb=0.0, network_sent_mb=0.0, network_recv_mb=0.0,
                active_threads=0, open_files=0, load_average=[0.0, 0.0, 0.0]
            )

    def _check_alert_rules(self, metric_name: str, value: float):
        """Check alert rules for metric value"""
        for rule_name, rule in self.alert_rules.items():
            if rule["metric"] != metric_name:
                continue
            
            threshold = rule["threshold"]
            operator = rule["operator"]
            
            # Check condition
            triggered = False
            if operator == "gt" and value > threshold:
                triggered = True
            elif operator == "lt" and value < threshold:
                triggered = True
            elif operator == "eq" and abs(value - threshold) < 0.001:
                triggered = True
            
            if triggered:
                self._trigger_alert(rule_name, rule, value)

    def _trigger_alert(self, rule_name: str, rule: Dict, current_value: float):
        """Trigger an alert"""
        alert_id = f"{rule_name}_{int(time.time())}"
        
        # Check if similar alert already exists
        existing_alert = None
        for alert in self.alerts.values():
            if (alert.metric_name == rule["metric"] and 
                alert.severity == rule["severity"] and 
                not alert.resolved):
                existing_alert = alert
                break
        
        if existing_alert:
            # Update existing alert
            existing_alert.current_value = current_value
            existing_alert.timestamp = datetime.now()
        else:
            # Create new alert
            alert = Alert(
                id=alert_id,
                severity=rule["severity"],
                message=rule["message"].format(value=current_value),
                metric_name=rule["metric"],
                threshold=rule["threshold"],
                current_value=current_value
            )
            
            self.alerts[alert_id] = alert
            
            # Call alert callbacks
            for callback in self.alert_callbacks:
                try:
                    callback(alert)
                except Exception as e:
                    logger.error(f"Alert callback failed: {e}")
            
            logger.warning(f"🚨 Alert triggered: {alert.message}")

    async def _alert_monitoring_loop(self):
        """Monitor and resolve alerts"""
        while self.is_monitoring:
            try:
                current_time = datetime.now()
                
                # Check for alerts to resolve
                for alert in list(self.alerts.values()):
                    if alert.resolved:
                        continue
                    
                    # Check if alert condition no longer applies
                    if self._should_resolve_alert(alert):
                        alert.resolved = True
                        alert.resolved_at = current_time
                        logger.info(f"✅ Alert resolved: {alert.id}")
                
                await asyncio.sleep(60.0)  # Check every minute
                
            except Exception as e:
                logger.error(f"Alert monitoring error: {e}")
                await asyncio.sleep(120.0)

    def _should_resolve_alert(self, alert: Alert) -> bool:
        """Check if alert should be resolved"""
        # Get recent metric values
        if not self.system_stats_history:
            return False
        
        recent_stats = list(self.system_stats_history)[-5:]  # Last 5 readings
        
        # Map metric names to stat attributes
        metric_mapping = {
            "system_cpu_percent": "cpu_percent",
            "system_memory_percent": "memory_percent",
            "system_disk_percent": "disk_percent"
        }
        
        attr_name = metric_mapping.get(alert.metric_name)
        if not attr_name:
            return False
        
        # Check if recent values are below threshold
        for stats in recent_stats:
            value = getattr(stats, attr_name, 0)
            if value > alert.threshold:
                return False
        
        return True

    async def _cleanup_loop(self):
        """Cleanup old alerts and data"""
        while self.is_monitoring:
            try:
                current_time = datetime.now()
                cutoff_time = current_time - timedelta(hours=24)
                
                # Remove old resolved alerts
                to_remove = []
                for alert_id, alert in self.alerts.items():
                    if (alert.resolved and 
                        alert.resolved_at and 
                        alert.resolved_at < cutoff_time):
                        to_remove.append(alert_id)
                
                for alert_id in to_remove:
                    del self.alerts[alert_id]
                
                logger.debug(f"🧹 Cleaned up {len(to_remove)} old alerts")
                
                await asyncio.sleep(self.cleanup_interval)
                
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                await asyncio.sleep(3600.0)

    async def _performance_analysis_loop(self):
        """Analyze performance trends"""
        while self.is_monitoring:
            try:
                if len(self.system_stats_history) >= 60:  # Need at least 10 minutes of data
                    await self._analyze_performance_trends()
                
                await asyncio.sleep(600.0)  # Analyze every 10 minutes
                
            except Exception as e:
                logger.error(f"Performance analysis error: {e}")
                await asyncio.sleep(1800.0)

    async def _analyze_performance_trends(self):
        """Analyze system performance trends"""
        recent_stats = list(self.system_stats_history)[-360:]  # Last 1 hour
        
        # Calculate averages
        avg_cpu = sum(s.cpu_percent for s in recent_stats) / len(recent_stats)
        avg_memory = sum(s.memory_percent for s in recent_stats) / len(recent_stats)
        
        # Update baselines
        self.performance_baselines["cpu_avg"] = avg_cpu
        self.performance_baselines["memory_avg"] = avg_memory
        
        # Record trend metrics
        self.set_gauge("system_cpu_avg_1h", avg_cpu)
        self.set_gauge("system_memory_avg_1h", avg_memory)
        
        logger.debug(f"📈 Performance baseline updated: CPU {avg_cpu:.1f}%, Memory {avg_memory:.1f}%")

    def add_alert_callback(self, callback: callable):
        """Add callback for alert notifications"""
        self.alert_callbacks.append(callback)

    def get_metrics_export(self) -> str:
        """Get Prometheus metrics export"""
        if self.enable_prometheus and self.registry:
            return generate_latest(self.registry).decode('utf-8')
        else:
            # Return local metrics in Prometheus format
            lines = []
            for name, metric in self.metrics.items():
                if isinstance(metric, dict):
                    lines.append(f"# TYPE {name} gauge")
                    lines.append(f"{name} {metric['value']}")
            return "\n".join(lines)

    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status"""
        if not self.system_stats_history:
            return {"status": "unknown", "reason": "No data available"}
        
        latest_stats = self.system_stats_history[-1]
        
        # Health checks
        issues = []
        if latest_stats.cpu_percent > 80:
            issues.append(f"High CPU usage: {latest_stats.cpu_percent:.1f}%")
        if latest_stats.memory_percent > 85:
            issues.append(f"High memory usage: {latest_stats.memory_percent:.1f}%")
        if latest_stats.disk_percent > 90:
            issues.append(f"High disk usage: {latest_stats.disk_percent:.1f}%")
        
        # Active alerts
        active_alerts = [a for a in self.alerts.values() if not a.resolved]
        
        status = "healthy"
        if active_alerts:
            critical_alerts = [a for a in active_alerts if a.severity == AlertSeverity.CRITICAL]
            error_alerts = [a for a in active_alerts if a.severity == AlertSeverity.ERROR]
            
            if critical_alerts:
                status = "critical"
            elif error_alerts:
                status = "degraded"
            else:
                status = "warning"
        
        return {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "system_stats": {
                "cpu_percent": latest_stats.cpu_percent,
                "memory_percent": latest_stats.memory_percent,
                "disk_percent": latest_stats.disk_percent,
                "active_threads": latest_stats.active_threads
            },
            "issues": issues,
            "active_alerts": len(active_alerts),
            "metrics_count": len(self.metrics),
            "uptime_hours": (datetime.now() - latest_stats.timestamp).total_seconds() / 3600 if self.system_stats_history else 0
        }

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        if not self.system_stats_history:
            return {}
        
        recent_stats = list(self.system_stats_history)[-60:]  # Last 10 minutes
        
        return {
            "cpu": {
                "current": recent_stats[-1].cpu_percent,
                "avg_10min": sum(s.cpu_percent for s in recent_stats) / len(recent_stats),
                "max_10min": max(s.cpu_percent for s in recent_stats),
                "min_10min": min(s.cpu_percent for s in recent_stats)
            },
            "memory": {
                "current": recent_stats[-1].memory_percent,
                "avg_10min": sum(s.memory_percent for s in recent_stats) / len(recent_stats),
                "max_10min": max(s.memory_percent for s in recent_stats),
                "min_10min": min(s.memory_percent for s in recent_stats)
            },
            "baselines": self.performance_baselines.copy(),
            "data_points": len(self.system_stats_history)
        }

# Global monitor instance
system_monitor = SystemMonitor()

# Convenience functions
async def start_monitoring():
    """Start system monitoring"""
    await system_monitor.start_monitoring()

async def get_system_monitor():
    """Get system monitor instance"""
    return system_monitor
