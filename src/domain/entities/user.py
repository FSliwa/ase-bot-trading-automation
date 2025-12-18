"""User domain entity."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class UserRole(Enum):
    """User roles enumeration."""

    USER = "user"
    PREMIUM = "premium"
    ADMIN = "admin"


@dataclass
class User:
    """User entity representing core business model."""

    id: int | None
    email: str
    username: str
    password_hash: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login: datetime | None = None

    def can_access_premium_features(self) -> bool:
        """Check if user has access to premium features."""
        return self.role in [UserRole.PREMIUM, UserRole.ADMIN]

    def update_last_login(self) -> None:
        """Update last login timestamp."""
        self.last_login = datetime.utcnow()
        self.updated_at = datetime.utcnow()
