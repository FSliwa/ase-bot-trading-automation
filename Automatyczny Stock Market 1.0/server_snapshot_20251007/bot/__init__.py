"""Bot package for PrimeXBT Trading Bot (MVP).

This package provides:
- CLI entrypoint (see `bot/cli.py`)
- Configuration loading and safety gates (see `bot/config.py`)
- Rule-based command parser (see `bot/parser.py`)
- Paper trading broker (see `bot/broker/paper.py`)
- Risk manager (see `bot/risk.py`)
- HTTP client stubs for PrimeXBT (see `bot/http/primexbt_client.py`)
"""

__all__ = [
    "__version__",
]

__version__ = "0.1.0"


