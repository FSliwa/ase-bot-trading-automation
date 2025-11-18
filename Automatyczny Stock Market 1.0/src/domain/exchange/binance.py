from __future__ import annotations

from typing import Any, Mapping, Sequence

import ccxt.async_support as ccxt
from ccxt.base.errors import AuthenticationError, ExchangeError as CCXTExchangeError

from src.domain.entities.trade import OrderSide, OrderType, TradeRequest, TradeResponse
from src.domain.exchange.base import AdapterConfig, ExchangeAdapter, ExchangeMarket
from src.domain.exchange.exceptions import CredentialsError, OrderPlacementError


class BinanceAdapter(ExchangeAdapter):
    """Adapter that proxies trading operations to Binance via CCXT."""

    name = "binance"
    requires_passphrase = False

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self._client = ccxt.binance({
            "apiKey": config.api_key,
            "secret": config.api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        if config.testnet:
            self._client.set_sandbox_mode(True)

    async def list_markets(self) -> Sequence[ExchangeMarket]:
        markets = await self._client.load_markets()
        result: list[ExchangeMarket] = []
        for symbol, details in markets.items():
            result.append(
                ExchangeMarket(
                    symbol=symbol,
                    base=details.get("base", ""),
                    quote=details.get("quote", ""),
                    active=details.get("active", True),
                )
            )
        return result

    async def fetch_ticker(self, symbol: str) -> Mapping[str, Any]:
        return await self._client.fetch_ticker(symbol)

    async def fetch_balance(self) -> Mapping[str, Any]:
        try:
            return await self._client.fetch_balance()
        except AuthenticationError as exc:
            raise CredentialsError("Invalid Binance credentials") from exc

    async def place_order(self, request: TradeRequest) -> TradeResponse:
        request.validate()
        price = request.price if request.order_type is OrderType.LIMIT else None
        try:
            order = await self._client.create_order(
                symbol=request.symbol,
                type=request.order_type.value,
                side=request.side.value,
                amount=request.quantity,
                price=price,
            )
        except AuthenticationError as exc:
            raise CredentialsError("Invalid Binance credentials") from exc
        except CCXTExchangeError as exc:
            raise OrderPlacementError(str(exc)) from exc

        return TradeResponse(
            exchange=self.name,
            symbol=request.symbol,
            order_id=str(order.get("id")),
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            executed_quantity=float(order.get("filled", 0.0) or 0.0),
            price=float(order.get("price", price or 0.0) or 0.0) if price else None,
            status=str(order.get("status", "")),
            raw=order,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> None:
        await self._client.cancel_order(id=order_id, symbol=symbol)

    async def close(self) -> None:
        await self._client.close()
