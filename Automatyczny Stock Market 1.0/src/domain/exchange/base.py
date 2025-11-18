from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.domain.entities.trade import OrderSide, OrderType, TradeRequest, TradeResponse


@dataclass(slots=True)
class ExchangeMarket:
    """Metadata for a tradable symbol."""

    symbol: str
    base: str
    quote: str
    active: bool


@dataclass(slots=True)
class AdapterConfig:
    """Configuration required to instantiate an exchange adapter."""

    api_key: str
    api_secret: str
    passphrase: str | None = None
    testnet: bool = False


class ExchangeAdapter(ABC):
    """Contract that all exchange adapters must fulfill."""

    name: str
    requires_passphrase: bool = False

    def __init__(self, config: AdapterConfig):
        self.config = config

    @abstractmethod
    async def list_markets(self) -> Sequence[ExchangeMarket]:
        """Return metadata for supported markets."""

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Mapping[str, Any]:
        """Return the most recent ticker information for a symbol."""

    @abstractmethod
    async def fetch_balance(self) -> Mapping[str, Any]:
        """Return account balance across currencies."""

    @abstractmethod
    async def place_order(self, request: TradeRequest) -> TradeResponse:
        """Submit an order to the exchange and return normalized response."""

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> None:
        """Cancel an order on the exchange."""

    @abstractmethod
    async def close(self) -> None:
        """Tear down any open connections."""

    async def __aenter__(self) -> "ExchangeAdapter":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
