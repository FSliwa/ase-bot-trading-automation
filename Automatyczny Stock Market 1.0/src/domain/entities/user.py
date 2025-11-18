from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    """Enumerates known user roles within the platform."""

    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


@dataclass(slots=True)
class User:
    """Domain entity representing an authenticated user."""

    id: Optional[int]
    email: str
    username: str
    password_hash: str
    role: UserRole
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_login_at: Optional[datetime] = None

    def update_last_login(self) -> None:
        """Update last login timestamp and touch the `updated_at` field."""

        now = datetime.utcnow()
        self.last_login_at = now
        self.updated_at = now
