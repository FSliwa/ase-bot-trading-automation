from __future__ import annotations

import logging
from logging.config import dictConfig
from typing import Any, Dict

_DEFAULT_LOGGING: Dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
}


def configure_logging(config: Dict[str, Any] | None = None) -> None:
    """Configure global logging using a dictionary config."""

    dictConfig(config or _DEFAULT_LOGGING)


def get_logger(name: str) -> logging.Logger:
    """Return application logger ensuring default config is applied."""

    if not logging.getLogger().handlers:
        configure_logging()
    return logging.getLogger(name)
