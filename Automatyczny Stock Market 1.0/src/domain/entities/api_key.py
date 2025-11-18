from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class APIKey:
    """Domain entity representing exchange API credentials bound to a user."""

    id: Optional[int]
    user_id: int
    exchange: str
    access_key: str
    secret_key: str
    passphrase: Optional[str] = None
    label: Optional[str] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def mask_access_key(self) -> str:
        """Return a masked representation of the access key for safe display."""

        if len(self.access_key) <= 4:
            return "****"
        return f"{self.access_key[:2]}***{self.access_key[-2:]}"

    def touch(self) -> None:
        """Update `updated_at` timestamp when mutating the secret."""

        self.updated_at = datetime.utcnow()
