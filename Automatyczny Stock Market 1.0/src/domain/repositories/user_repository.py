from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.domain.entities.user import User


class UserRepository(ABC):
    """Abstraction for user persistence operations."""

    @abstractmethod
    async def create(self, user: User) -> User:
        """Persist a new user instance."""

    @abstractmethod
    async def update(self, user: User) -> User:
        """Persist an existing user instance."""

    @abstractmethod
    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Retrieve user by identifier."""

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        """Retrieve user by email."""

    @abstractmethod
    async def get_by_username(self, username: str) -> Optional[User]:
        """Retrieve user by username."""

    @abstractmethod
    async def delete(self, user_id: int) -> None:
        """Remove a user by identifier."""

    @abstractmethod
    async def list_active_users(self, limit: int = 100, offset: int = 0) -> list[User]:
        """Return active users for administrative listings."""
