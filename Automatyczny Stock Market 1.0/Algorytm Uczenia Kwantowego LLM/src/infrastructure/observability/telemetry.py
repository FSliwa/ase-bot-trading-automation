"""OpenTelemetry configuration and instrumentation."""

from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.trace import Status, StatusCode
from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

import logging
from functools import wraps
from typing import Optional, Dict, Any
import time

from src.infrastructure.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def setup_telemetry(app=None):
    """Initialize OpenTelemetry with all instrumentations."""
    
    # Skip if no exporter endpoint configured
    if not settings.otel_exporter_endpoint:
        logger.info("OpenTelemetry disabled - no exporter endpoint configured")
        return
    
    # Configure resource
    resource = Resource.create({
        "service.name": settings.otel_service_name,
        "service.version": "2.0.0",
        "service.environment": settings.otel_environment,
    })
    
    # Configure trace provider
    trace_provider = TracerProvider(resource=resource)
    trace_exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_endpoint,
        insecure=True,  # Use secure=False for local development
    )
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)
    
    # Configure metrics provider
    metric_reader = PeriodicExportingMetricReader(
        exporter=OTLPMetricExporter(
            endpoint=settings.otel_exporter_endpoint,
            insecure=True,
        ),
        export_interval_millis=30000,  # Export every 30 seconds
    )
    metrics_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(metrics_provider)
    
    # Set propagator
    set_global_textmap(TraceContextTextMapPropagator())
    
    # Auto-instrumentation
    if app:
        FastAPIInstrumentor.instrument_app(app)
    
    SQLAlchemyInstrumentor().instrument(
        engine=None,  # Will instrument all engines
        enable_commenter=True,
        commenter_options={
            "opentelemetry_values": True,
        }
    )
    
    RedisInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)
    SystemMetricsInstrumentor().instrument()
    
    logger.info(f"OpenTelemetry initialized - exporting to {settings.otel_exporter_endpoint}")


# Get global tracer
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Create metrics
request_counter = meter.create_counter(
    name="http_requests_total",
    description="Total number of HTTP requests",
    unit="1",
)

request_duration = meter.create_histogram(
    name="http_request_duration_seconds",
    description="HTTP request duration",
    unit="s",
)

db_query_duration = meter.create_histogram(
    name="db_query_duration_seconds",
    description="Database query duration",
    unit="s",
)

cache_hits = meter.create_counter(
    name="cache_hits_total",
    description="Total number of cache hits",
    unit="1",
)

cache_misses = meter.create_counter(
    name="cache_misses_total",
    description="Total number of cache misses",
    unit="1",
)


def trace_async(name: str, attributes: Optional[Dict[str, Any]] = None):
    """Decorator for tracing async functions."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(name) as span:
                if attributes:
                    span.set_attributes(attributes)
                
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
                finally:
                    duration = time.time() - start_time
                    span.set_attribute("duration_seconds", duration)
        
        return wrapper
    return decorator


def trace_sync(name: str, attributes: Optional[Dict[str, Any]] = None):
    """Decorator for tracing sync functions."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(name) as span:
                if attributes:
                    span.set_attributes(attributes)
                
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
                finally:
                    duration = time.time() - start_time
                    span.set_attribute("duration_seconds", duration)
        
        return wrapper
    return decorator


class TracedCache:
    """Wrapper for Redis cache with tracing."""
    
    def __init__(self, cache):
        self.cache = cache
    
    @trace_async("cache.get")
    async def get(self, key: str) -> Any:
        result = await self.cache.get(key)
        if result is not None:
            cache_hits.add(1, {"operation": "get"})
        else:
            cache_misses.add(1, {"operation": "get"})
        return result
    
    @trace_async("cache.set")
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        return await self.cache.set(key, value, ttl)
    
    @trace_async("cache.delete")
    async def delete(self, key: str) -> bool:
        return await self.cache.delete(key)


# Custom span processor for adding trace_id to logs
class TraceIdProcessor(logging.LogRecord):
    def process(self, msg, kwargs):
        # Get current span
        span = trace.get_current_span()
        if span and span.is_recording():
            trace_id = format(span.get_span_context().trace_id, '032x')
            kwargs['extra'] = kwargs.get('extra', {})
            kwargs['extra']['trace_id'] = trace_id
        return msg, kwargs
