from src.application.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
    InvalidCredentialsError,
)
from src.domain.entities.user import User, UserRole
from src.domain.repositories.user_repository import UserRepository
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.security.password_hasher import PasswordHasher
from src.infrastructure.logging.logger import get_logger
import secrets
from datetime import datetime
from typing import Optional

logger = get_logger(__name__)


class UserService:
    """Service layer for user-related business logic."""

    def __init__(
        self,
        user_repository: UserRepository,
        cache: RedisCache,
        password_hasher: PasswordHasher,
    ):
        """Initialize user service with dependencies."""
        self.user_repository = user_repository
        self.cache = cache
        self.password_hasher = password_hasher

    async def register_user(
        self, email: str, username: str, password: str
    ) -> User:
        """Register a new user with validation."""
        existing_user = await self.user_repository.get_by_email(email)
        if existing_user:
            logger.warning(f"Registration attempt with existing email: {email}")
            raise UserAlreadyExistsError(f"Email {email} is already registered")

        existing_user = await self.user_repository.get_by_username(username)
        if existing_user:
            logger.warning(
                f"Registration attempt with existing username: {username}"
            )
            raise UserAlreadyExistsError(f"Username {username} is already taken")

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

        created_user = await self.user_repository.create(user)

        await self.cache.set(
            f"user:{created_user.id}", created_user.__dict__, ttl=3600
        )

        logger.info(f"New user registered: {username} ({email})")
        return created_user

    async def authenticate_user(
        self, email: str, password: str
    ) -> tuple[User, str]:
        """Authenticate user and return user with session token."""
        user: Optional[User] = None
        user_data = await self.cache.get(f"user:email:{email}")
        if user_data and isinstance(user_data, dict):
            user_data["role"] = UserRole(user_data["role"])
            user = User(**user_data)

        if not user:
            user = await self.user_repository.get_by_email(email)
            if not user:
                logger.warning(f"Authentication failed - user not found: {email}")
                raise InvalidCredentialsError("Invalid email or password")
            await self.cache.set(f"user:email:{email}", user.__dict__, ttl=300)

        if not self.password_hasher.verify(password, user.password_hash):
            logger.warning(f"Authentication failed - invalid password for: {email}")
            raise InvalidCredentialsError("Invalid email or password")

        user.update_last_login()
        await self.user_repository.update(user)

        session_token = self._generate_session_token()

        await self.cache.set(
            f"session:{session_token}",
            {"user_id": user.id, "email": user.email},
            ttl=86400,
        )

        logger.info(f"User authenticated successfully: {email}")
        return user, session_token

    async def get_user_by_session(self, session_token: str) -> Optional[User]:
        """Get user by session token."""
        session_data = await self.cache.get(f"session:{session_token}")
        if not session_data or "user_id" not in session_data:
            return None
        return await self.user_repository.get_by_id(session_data["user_id"])

    async def logout_user(self, session_token: str) -> bool:
        """Logout user by invalidating session."""
        return await self.cache.delete(f"session:{session_token}")

    async def update_user_role(
        self, user_id: int, new_role: UserRole, admin_user: User
    ) -> User:
        """Update user role (admin only)."""
        if admin_user.role != UserRole.ADMIN:
            raise PermissionError("Only admins can change user roles")

        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        user.role = new_role
        user.updated_at = datetime.utcnow()

        updated_user = await self.user_repository.update(user)

        await self.cache.delete(f"user:{user_id}")
        await self.cache.delete(f"user:email:{user.email}")

        logger.info(f"User role updated: {user_id} -> {new_role.value}")
        return updated_user

    def _generate_session_token(self) -> str:
        """Generate secure random session token."""
        return secrets.token_urlsafe(32)
