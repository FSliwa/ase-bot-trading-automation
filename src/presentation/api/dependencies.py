"""FastAPI dependency injection providers."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.user_service import UserService
from src.domain.entities.user import User
from src.domain.repositories.user_repository import UserRepository
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.database.session import get_db_session  # Assuming you'll create this
from src.infrastructure.database.sqlalchemy_user_repository import SQLAlchemyUserRepository
from src.infrastructure.security.password_hasher import PasswordHasher


# --- Rate Limiter Stub ---
# In a real app, this would be a more robust implementation
def rate_limiter(max_calls: int, time_window: int):
    def dependency():
        # This is a placeholder. The actual logic is in the middleware.
        pass

    return dependency


# --- Bearer Security ---
security = HTTPBearer()

# --- Dependency Providers ---


def get_password_hasher() -> PasswordHasher:
    """Get a password hasher instance."""
    return PasswordHasher()


def get_redis_cache() -> RedisCache:
    """Get a Redis cache instance."""
    # In a real app, the URL would come from config
    return RedisCache()


def get_user_repository(session: AsyncSession = Depends(get_db_session)) -> UserRepository:
    """Get a SQLAlchemy user repository instance."""
    return SQLAlchemyUserRepository(session)


def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository),
    cache: RedisCache = Depends(get_redis_cache),
    password_hasher: PasswordHasher = Depends(get_password_hasher),
) -> UserService:
    """Get a user service instance with dependencies."""
    return UserService(user_repository=user_repo, cache=cache, password_hasher=password_hasher)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_service: UserService = Depends(get_user_service),
):
    """Get the current authenticated user from a session token."""
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
    """Get user repository with RLS context."""
    session_gen = get_db_session(current_user.id)
    session = await session_gen.__anext__()
    try:
        yield SQLAlchemyUserRepository(session)
    finally:
        await session_gen.aclose()
