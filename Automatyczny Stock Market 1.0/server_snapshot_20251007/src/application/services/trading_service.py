from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from typing import Optional

from src.domain.entities.api_key import APIKey
from src.domain.entities.trade import OrderSide, OrderType, TradeRequest, TradeResponse
from src.domain.exchange import (
    AdapterConfig,
    CredentialsError,
    ExchangeError,
    build_adapter,
    list_supported_exchanges,
)
from src.domain.repositories.api_key_repository import APIKeyRepository
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class TradingService:
    """Coordinates exchange operations and credential management."""

    def __init__(self, api_key_repository: APIKeyRepository):
        self.api_key_repository = api_key_repository

    async def supported_exchanges(self) -> list[str]:
        """Return identifiers of available exchanges."""

        return list_supported_exchanges()

    async def list_api_keys(self, user_id: int) -> Sequence[APIKey]:
        return await self.api_key_repository.get_for_user(user_id)

    async def upsert_api_key(
        self,
        *,
        user_id: int,
        exchange: str,
        access_key: str,
        secret_key: str,
        passphrase: Optional[str] = None,
        label: Optional[str] = None,
    ) -> APIKey:
        """Create or update exchange credentials for a user."""

        exchange = exchange.lower()
        existing = await self.api_key_repository.find_active_for_exchange(
            user_id=user_id, exchange=exchange
        )

        if existing:
            logger.info("Updating API key", extra={"exchange": exchange, "user_id": user_id})
            existing.access_key = access_key
            existing.secret_key = secret_key
            existing.passphrase = passphrase
            existing.label = label
            existing.is_active = True
            existing.touch()
            return await self.api_key_repository.update(existing)

        logger.info("Creating API key", extra={"exchange": exchange, "user_id": user_id})
        api_key = APIKey(
            id=None,
            user_id=user_id,
            exchange=exchange,
            access_key=access_key,
            secret_key=secret_key,
            passphrase=passphrase,
            label=label,
        )
        return await self.api_key_repository.create(api_key)

    async def deactivate_api_key(self, user_id: int, api_key_id: int) -> None:
        api_key = await self.api_key_repository.get_by_id(api_key_id)
        if not api_key or api_key.user_id != user_id:
            raise CredentialsError("API key not found")
        api_key.is_active = False
        api_key.touch()
        await self.api_key_repository.update(api_key)

    async def delete_api_key(self, user_id: int, api_key_id: int) -> None:
        api_key = await self.api_key_repository.get_by_id(api_key_id)
        if not api_key or api_key.user_id != user_id:
            raise CredentialsError("API key not found")
        await self.api_key_repository.delete(api_key_id)

    async def place_order(
        self,
        *,
        user_id: int,
        exchange: str,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
    ) -> TradeResponse:
        """Submit an order on behalf of a user."""

        credentials = await self.api_key_repository.find_active_for_exchange(
            user_id=user_id, exchange=exchange
        )
        if not credentials or not credentials.is_active:
            raise CredentialsError("Active API key not configured for this exchange")

        request = TradeRequest(
            exchange=exchange,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            user_id=user_id,
            api_key_id=credentials.id,
        )

        adapter_config = AdapterConfig(
            api_key=credentials.access_key,
            api_secret=credentials.secret_key,
            passphrase=credentials.passphrase,
        )

        adapter = build_adapter(exchange, adapter_config)

        async with adapter as client:
            try:
                response = await client.place_order(request)
                logger.info(
                    "Order placed",
                    extra={
                        "exchange": exchange,
                        "user_id": user_id,
                        "order": asdict(response),
                    },
                )
                return response
            except ExchangeError:
                logger.exception("Exchange error while placing order")
                raise

    async def cancel_order(
        self,
        *,
        user_id: int,
        exchange: str,
        symbol: str,
        order_id: str,
    ) -> None:
        credentials = await self.api_key_repository.find_active_for_exchange(
            user_id=user_id, exchange=exchange
        )
        if not credentials or not credentials.is_active:
            raise CredentialsError("Active API key not configured for this exchange")

        adapter = build_adapter(
            exchange,
            AdapterConfig(
                api_key=credentials.access_key,
                api_secret=credentials.secret_key,
                passphrase=credentials.passphrase,
            ),
        )

        async with adapter as client:
            await client.cancel_order(symbol=symbol, order_id=order_id)
            logger.info(
                "Order cancelled",
                extra={"exchange": exchange, "user_id": user_id, "order_id": order_id},
            )
