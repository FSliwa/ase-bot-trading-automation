"""Compatibility layer exposing the FastAPI application under the historical
``web.app`` import path.

This module simply re-exports the main FastAPI ``app`` instance defined in
``app.py`` so that legacy scripts, deployment tooling, and tests that still
reference ``web.app`` keep working.  It also provides a small ``__main__``
entrypoint so the application can be started directly with
``python -m web.app`` if desired.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure the project root (one level above ``web/``) is available on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from app import app as _app
except ImportError as exc:  # pragma: no cover - failure path is for diagnostics
    raise ImportError(
        "Nie można zaimportować głównej aplikacji FastAPI z pliku 'app.py'. "
        "Upewnij się, że plik istnieje i że wszystkie zależności są zainstalowane."
    ) from exc

# Public FastAPI application instance expected by uvicorn and the test suite.
app = _app


def _parse_reload_flag(value: str | None) -> bool:
    """Parse text flags such as "true", "1", "yes" into boolean reload toggle."""

    if value is None:
        return False
    return value.lower() in {"1", "true", "t", "yes", "y", "on"}


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)

    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8008"))
    reload_enabled = _parse_reload_flag(os.getenv("UVICORN_RELOAD"))

    logging.info(
        "Starting FastAPI server via legacy web.app shim (host=%s, port=%s, reload=%s)",
        host,
        port,
        reload_enabled,
    )

    uvicorn.run("web.app:app", host=host, port=port, reload=reload_enabled)
