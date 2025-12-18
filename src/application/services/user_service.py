"""User service containing business logic."""

import secrets
from datetime import datetime

from src.application.exceptions import (
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from src.domain.entities.user import User, UserRole
from src.domain.repositories.user_repository import UserRepository
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.security.password_hasher import PasswordHasher
from src.infrastructure.resilience import database_breaker, redis_breaker, CircuitBreakerOpenError

logger = get_logger(__name__)


class UserService:
    """Service layer for user-related business logic."""

    def __init__(
        self, user_repository: UserRepository, cache: RedisCache, password_hasher: PasswordHasher
    ):
        """Initialize user service with dependencies."""
        self.user_repository = user_repository
        self.cache = cache
        self.password_hasher = password_hasher

    async def register_user(self, email: str, username: str, password: str) -> User:
        """Register a new user with validation."""
        # Check if user already exists
        existing_user = await self.user_repository.get_by_email(email)
        if existing_user:
            logger.warning(f"Registration attempt with existing email: {email}")
            raise UserAlreadyExistsError(f"Email {email} is already registered")

        existing_user = await self.user_repository.get_by_username(username)
        if existing_user:
            logger.warning(f"Registration attempt with existing username: {username}")
            raise UserAlreadyExistsError(f"Username {username} is already taken")

        # Create new user
        now = datetime.utcnow()
        user = User(
            id=None,
            email=email,
            username=username,
            password_hash=self.password_hasher.hash(password),
            role=UserRole.USER,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        # Save to repository
        created_user = await self.user_repository.create(user)

        # Cache user data
        await self.cache.set(f"user:{created_user.id}", created_user, ttl=3600)

        logger.info(f"New user registered: {username} ({email})")
        return created_user

    async def authenticate_user(self, email: str, password: str) -> tuple[User, str]:
        """Authenticate user and return user with session token."""
        # Try to get user ID from cache first
        cached_user_id = await self.cache.get(f"user:email:{email}")
        
        if cached_user_id:
            user = await self.user_repository.get_by_id(int(cached_user_id))
        else:
            user = await self.user_repository.get_by_email(email)
            if user:
                # Cache email to user ID mapping for 1 hour
                await self.cache.set(f"user:email:{email}", user.id, ttl=3600)
                # Also cache full user data for faster subsequent access
                user_dict = {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "password_hash": user.password_hash,
                    "role": user.role.value,
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat(),
                    "updated_at": user.updated_at.isoformat(),
                    "last_login": user.last_login.isoformat() if user.last_login else None
                }
                await self.cache.set(f"user:{user.id}", user_dict, ttl=1800)  # 30 minutes
            
        if not user:
            logger.warning(f"Authentication failed - user not found: {email}")
            raise InvalidCredentialsError("Invalid email or password")

        # Verify password
        if not self.password_hasher.verify(password, user.password_hash):
            logger.warning(f"Authentication failed - invalid password for: {email}")
            raise InvalidCredentialsError("Invalid email or password")

        # Update last login
        user.update_last_login()
        await self.user_repository.update(user)

        # Generate session token
        session_token = self._generate_session_token()

        # Store session in cache
        await self.cache.set(
            f"session:{session_token}",
            {"user_id": user.id, "email": user.email},
            ttl=86400,  # 24 hours
        )

        logger.info(f"User authenticated successfully: {email}")
        return user, session_token

    async def get_user_by_session(self, session_token: str) -> User | None:
        """Get user by session token."""
        try:
            # Try to get user from cache first (with circuit breaker)
            cached_user = await redis_breaker.call(
                self.cache.get, f"user:session:{session_token}"
            )
            if cached_user:
                return User(**cached_user)
            
            # Get session from cache
            session_data = await redis_breaker.call(
                self.cache.get, f"session:{session_token}"
            )
            if not session_data:
                return None

            # Get user from database (with circuit breaker)
            user = await database_breaker.call(
                self.user_repository.get_by_id, session_data["user_id"]
            )
            
            if user:
                # Cache user data for 15 minutes
                user_dict = {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "password_hash": user.password_hash,
                    "role": user.role.value,
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat(),
                    "updated_at": user.updated_at.isoformat(),
                    "last_login": user.last_login.isoformat() if user.last_login else None
                }
                await redis_breaker.call(
                    self.cache.set,
                    f"user:session:{session_token}", 
                    user_dict, 
                    ttl=900  # 15 minutes
                )
            return user
            
        except CircuitBreakerOpenError as e:
            logger.warning(f"Circuit breaker open for user session lookup: {e}")
            return None

    async def logout_user(self, session_token: str) -> bool:
        """Logout user by invalidating session."""
        # Delete session and cached user data
        await self.cache.delete(f"user:session:{session_token}")
        return await self.cache.delete(f"session:{session_token}")

    async def update_user_role(self, user_id: int, new_role: UserRole, admin_user: User) -> User:
        """Update user role (admin only)."""
        if admin_user.role != UserRole.ADMIN:
            raise PermissionError("Only admins can change user roles")

        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        user.role = new_role
        user.updated_at = datetime.utcnow()

        updated_user = await self.user_repository.update(user)

        # Invalidate cache
        await self.cache.delete(f"user:{user_id}")

        logger.info(f"User role updated: {user_id} -> {new_role.value}")
        return updated_user

    def _generate_session_token(self) -> str:
        """Generate secure random session token."""
        return secrets.token_urlsafe(32)
