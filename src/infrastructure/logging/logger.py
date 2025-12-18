"""Standardized logger configuration."""

import logging
import sys

_initialized = False


class TraceIdFilter(logging.Filter):
    """Add trace ID to log records."""
    
    def filter(self, record):
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            if span and span.is_recording():
                trace_id = format(span.get_span_context().trace_id, '032x')
                record.trace_id = trace_id
            else:
                record.trace_id = "00000000000000000000000000000000"
        except ImportError:
            record.trace_id = "00000000000000000000000000000000"
        return True


def get_logger(name: str) -> logging.Logger:
    """Get a standardized logger instance."""
    global _initialized
    if not _initialized:
        handler = logging.StreamHandler(sys.stdout)
        handler.addFilter(TraceIdFilter())
        
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - [%(trace_id)s] - %(message)s",
            handlers=[handler],
        )
        _initialized = True

    return logging.getLogger(name)
