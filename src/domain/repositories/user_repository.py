"""User repository interface."""

from abc import ABC, abstractmethod

from src.domain.entities.user import User


class UserRepository(ABC):
    """Abstract repository for User entity."""

    @abstractmethod
    async def create(self, user: User) -> User:
        """Create a new user."""
        pass

    @abstractmethod
    async def get_by_id(self, user_id: int) -> User | None:
        """Get user by ID."""
        pass

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None:
        """Get user by email."""
        pass

    @abstractmethod
    async def get_by_username(self, username: str) -> User | None:
        """Get user by username."""
        pass

    @abstractmethod
    async def update(self, user: User) -> User:
        """Update existing user."""
        pass

    @abstractmethod
    async def delete(self, user_id: int) -> bool:
        """Delete user by ID."""
        pass

    @abstractmethod
    async def list_active_users(self, limit: int = 100, offset: int = 0) -> list[User]:
        """List active users with pagination."""
        pass
