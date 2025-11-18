from __future__ import annotations

import logging
import os
import re
from typing import Optional

from rich.logging import RichHandler


_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key)\s*[:=]\s*([A-Za-z0-9_\-]{6,})"),
    re.compile(r"(?i)(api[_-]?secret|secret)\s*[:=]\s*([A-Za-z0-9_\-]{6,})"),
]


class RedactSecretsFilter(logging.Filter):
    """Logging filter that redacts API secrets if they appear in log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        try:
            msg = str(record.getMessage())
        except Exception:
            return True

        redacted = msg
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(lambda m: f"{m.group(1)}=***REDACTED***", redacted)

        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger(name if name else __name__)
    if not logger.handlers:
        handler = RichHandler(rich_tracebacks=True, markup=True)
        handler.addFilter(RedactSecretsFilter())
        logger.addHandler(handler)
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))
        logger.propagate = False
    return logger


