from __future__ import annotations

from collections.abc import Callable
from typing import Dict

from src.domain.exchange.base import AdapterConfig, ExchangeAdapter
from src.domain.exchange.binance import BinanceAdapter
from src.domain.exchange.bitget import BitgetAdapter
from src.domain.exchange.exceptions import InvalidExchangeError


_ADAPTERS: Dict[str, Callable[[AdapterConfig], ExchangeAdapter]] = {
    BinanceAdapter.name: BinanceAdapter,
    BitgetAdapter.name: BitgetAdapter,
}


def register_adapter(name: str, factory: Callable[[AdapterConfig], ExchangeAdapter]) -> None:
    """Register a new adapter factory dynamically."""

    _ADAPTERS[name.lower()] = factory


def build_adapter(exchange: str, config: AdapterConfig) -> ExchangeAdapter:
    """Instantiate an adapter for the requested exchange."""

    factory = _ADAPTERS.get(exchange.lower())
    if not factory:
        raise InvalidExchangeError(f"Unsupported exchange: {exchange}")
    return factory(config)


def list_supported_exchanges() -> list[str]:
    """Return identifiers for all registered exchanges."""

    return sorted(_ADAPTERS.keys())
