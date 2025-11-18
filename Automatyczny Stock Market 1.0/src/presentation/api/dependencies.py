from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.trading_service import TradingService
from src.application.services.user_service import UserService
from src.domain.entities.user import User
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.database.session import get_db_session
from src.infrastructure.database.sqlalchemy_api_key_repository import (
    SQLAlchemyAPIKeyRepository,
)
from src.infrastructure.database.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from src.infrastructure.security.password_hasher import PasswordHasher

security = HTTPBearer(auto_error=True)
_cache: RedisCache | None = None
_password_hasher: PasswordHasher | None = None
async def get_cache() -> RedisCache:
    global _cache
    if _cache is None:
        _cache = RedisCache()
    return _cache


def get_password_hasher() -> PasswordHasher:
    global _password_hasher
    if _password_hasher is None:
        _password_hasher = PasswordHasher()
    return _password_hasher


async def get_user_service(
    session: AsyncSession = Depends(get_db_session),
    cache: RedisCache = Depends(get_cache),
    password_hasher: PasswordHasher = Depends(get_password_hasher),
) -> UserService:
    user_repo = SQLAlchemyUserRepository(session)
    return UserService(
        user_repository=user_repo,
        cache=cache,
        password_hasher=password_hasher,
    )


async def get_trading_service(
    session: AsyncSession = Depends(get_db_session),
) -> TradingService:
    api_key_repo = SQLAlchemyAPIKeyRepository(session)
    return TradingService(api_key_repository=api_key_repo)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_service: UserService = Depends(get_user_service),
) -> User:
    """Resolve the current authenticated user from the bearer token."""

    token = credentials.credentials
    user = await user_service.get_user_by_session(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
