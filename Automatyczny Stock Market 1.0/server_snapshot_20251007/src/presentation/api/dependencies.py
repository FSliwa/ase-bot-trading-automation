"""FastAPI dependency injection providers."""

from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.trading_service import TradingService
from src.application.services.user_service import UserService
from src.domain.entities.user import User
from src.domain.repositories.user_repository import UserRepository
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.database.session import get_db_session
from src.infrastructure.database.sqlalchemy_api_key_repository import SQLAlchemyAPIKeyRepository
from src.infrastructure.database.sqlalchemy_user_repository import SQLAlchemyUserRepository
from src.infrastructure.security.password_hasher import PasswordHasher

security = HTTPBearer(auto_error=True)

_cache: RedisCache | None = None
_password_hasher: PasswordHasher | None = None


def rate_limiter(max_calls: int, time_window: int) -> Callable[[], None]:
    """Lightweight rate-limiter placeholder used by route decorators."""

    def dependency() -> None:
        return None

    return dependency


async def get_cache() -> RedisCache:
    """Lazily provide a Redis cache instance."""
    global _cache
    if _cache is None:
        _cache = RedisCache()
    return _cache


def get_password_hasher() -> PasswordHasher:
    """Provide a singleton password hasher instance."""
    global _password_hasher
    if _password_hasher is None:
        _password_hasher = PasswordHasher()
    return _password_hasher


def get_user_repository(session: AsyncSession = Depends(get_db_session)) -> UserRepository:
    """Create a user repository bound to the current SQLAlchemy session."""
    return SQLAlchemyUserRepository(session)


def get_trading_service(
    session: AsyncSession = Depends(get_db_session),
) -> TradingService:
    """Provide the trading service with a database-backed API key repository."""

    api_key_repo = SQLAlchemyAPIKeyRepository(session)
    return TradingService(api_key_repository=api_key_repo)


def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository),
    cache: RedisCache = Depends(get_cache),
    password_hasher: PasswordHasher = Depends(get_password_hasher),
) -> UserService:
    """Assemble the user service with shared dependencies."""

    return UserService(user_repository=user_repo, cache=cache, password_hasher=password_hasher)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_service: UserService = Depends(get_user_service),
) -> User:
    """Resolve the current authenticated user from the provided bearer token."""

    token = credentials.credentials
    user = await user_service.get_user_by_session(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_user_repository_with_rls(
    current_user: User = Depends(get_current_user),
) -> UserRepository:
    """Yield a user repository scoped to row-level security for the current user."""

    session_gen = get_db_session(current_user.id)
    session = await session_gen.__anext__()
    try:
        yield SQLAlchemyUserRepository(session)
    finally:
        await session_gen.aclose()
