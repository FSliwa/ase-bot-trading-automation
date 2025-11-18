from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Optional

from src.domain.entities.api_key import APIKey


class APIKeyRepository(ABC):
    """Abstraction for storing exchange API credentials securely."""

    @abstractmethod
    async def create(self, api_key: APIKey) -> APIKey:
        """Persist a new API key for a user."""

    @abstractmethod
    async def update(self, api_key: APIKey) -> APIKey:
        """Update an existing API key."""

    @abstractmethod
    async def delete(self, api_key_id: int) -> None:
        """Remove an API key."""

    @abstractmethod
    async def get_by_id(self, api_key_id: int) -> Optional[APIKey]:
        """Fetch a key by its identifier."""

    @abstractmethod
    async def get_for_user(self, user_id: int) -> Sequence[APIKey]:
        """Return all keys owned by user."""

    @abstractmethod
    async def find_active_for_exchange(self, user_id: int, exchange: str) -> Optional[APIKey]:
        """Return the active credentials for the specified exchange."""
