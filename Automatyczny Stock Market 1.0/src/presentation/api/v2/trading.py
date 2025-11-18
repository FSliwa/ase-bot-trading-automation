from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.application.services.trading_service import TradingService
from src.domain.entities.trade import OrderSide, OrderType, TradeResponse
from src.domain.entities.user import User
from src.domain.exchange.exceptions import CredentialsError, ExchangeError, OrderPlacementError
from src.presentation.api.dependencies import (
    get_current_user,
    get_trading_service,
)
from src.infrastructure.http.rate_limiter import limiter

router = APIRouter(prefix="/api/v2/trading", tags=["trading"])


class APIKeyRequest(BaseModel):
    exchange: str = Field(..., description="Exchange identifier, e.g. binance")
    access_key: str = Field(..., min_length=4)
    secret_key: str = Field(..., min_length=4)
    passphrase: str | None = Field(
        default=None,
        description="Required for exchanges such as Coinbase Pro and Bitget",
    )
    label: str | None = Field(default=None, max_length=120)


class APIKeyResponse(BaseModel):
    id: int
    exchange: str
    label: str | None
    masked_access_key: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TradeOrderRequest(BaseModel):
    exchange: str = Field(..., description="Exchange identifier")
    symbol: str = Field(..., description="Trading pair, e.g. BTC/USDT")
    side: OrderSide
    quantity: float = Field(..., gt=0)
    order_type: OrderType = OrderType.MARKET
    price: float | None = Field(default=None, gt=0)


class TradeOrderResponse(BaseModel):
    exchange: str
    symbol: str
    order_id: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    executed_quantity: float
    price: float | None
    status: str
    created_at: datetime

    @classmethod
    def from_entity(cls, trade: TradeResponse) -> "TradeOrderResponse":
        return cls(
            exchange=trade.exchange,
            symbol=trade.symbol,
            order_id=trade.order_id,
            side=trade.side,
            order_type=trade.order_type,
            quantity=trade.quantity,
            executed_quantity=trade.executed_quantity,
            price=trade.price,
            status=trade.status,
            created_at=trade.created_at,
        )


@router.get("/exchanges")
@limiter.limit("30/minute")
async def list_exchanges(
    _request: Request,
    trading_service: TradingService = Depends(get_trading_service),
) -> dict[str, list[str]]:
    """Return exchanges supported by the backend."""

    exchanges = await trading_service.supported_exchanges()
    return {"exchanges": exchanges}


@router.get("/keys")
@limiter.limit("30/minute")
async def list_api_keys(
    _request: Request,
    user: User = Depends(get_current_user),
    trading_service: TradingService = Depends(get_trading_service),
) -> dict[str, list[APIKeyResponse]]:
    if user.id is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Authenticated user has no id")

    keys = await trading_service.list_api_keys(user.id)
    items = [
        APIKeyResponse(
            id=key.id or 0,
            exchange=key.exchange,
            label=key.label,
            masked_access_key=key.mask_access_key(),
            is_active=key.is_active,
            created_at=key.created_at,
            updated_at=key.updated_at,
        )
        for key in keys
    ]
    return {"items": items}


@router.post(
    "/keys",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
async def upsert_api_key(
    _request: Request,
    payload: APIKeyRequest,
    user: User = Depends(get_current_user),
    trading_service: TradingService = Depends(get_trading_service),
) -> APIKeyResponse:
    if user.id is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Authenticated user has no id")

    api_key = await trading_service.upsert_api_key(
        user_id=user.id,
        exchange=payload.exchange,
        access_key=payload.access_key,
        secret_key=payload.secret_key,
        passphrase=payload.passphrase,
        label=payload.label,
    )
    return APIKeyResponse(
        id=api_key.id or 0,
        exchange=api_key.exchange,
        label=api_key.label,
        masked_access_key=api_key.mask_access_key(),
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        updated_at=api_key.updated_at,
    )


@router.delete(
    "/keys/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("10/minute")
async def delete_api_key(
    _request: Request,
    api_key_id: int,
    user: User = Depends(get_current_user),
    trading_service: TradingService = Depends(get_trading_service),
) -> None:
    if user.id is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Authenticated user has no id")

    await trading_service.delete_api_key(user.id, api_key_id)


@router.post(
    "/orders",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
async def place_order(
    _request: Request,
    payload: TradeOrderRequest,
    user: User = Depends(get_current_user),
    trading_service: TradingService = Depends(get_trading_service),
) -> TradeOrderResponse:
    if user.id is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Authenticated user has no id")

    try:
        trade = await trading_service.place_order(
            user_id=user.id,
            exchange=payload.exchange,
            symbol=payload.symbol,
            side=payload.side,
            quantity=payload.quantity,
            order_type=payload.order_type,
            price=payload.price,
        )
    except CredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OrderPlacementError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ExchangeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return TradeOrderResponse.from_entity(trade)


@router.delete(
    "/orders/{exchange}/{symbol}/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("20/minute")
async def cancel_order(
    _request: Request,
    exchange: str,
    symbol: str,
    order_id: str,
    user: User = Depends(get_current_user),
    trading_service: TradingService = Depends(get_trading_service),
) -> None:
    if user.id is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Authenticated user has no id")

    try:
        await trading_service.cancel_order(
            user_id=user.id,
            exchange=exchange,
            symbol=symbol,
            order_id=order_id,
        )
    except CredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ExchangeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

