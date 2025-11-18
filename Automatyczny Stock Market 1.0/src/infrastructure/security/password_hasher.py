from __future__ import annotations

from passlib.context import CryptContext


class PasswordHasher:
    """Wrapper around Passlib's CryptContext simplifying hashing operations."""

    def __init__(self) -> None:
        self._context = CryptContext(schemes=["argon2"], deprecated="auto")

    def hash(self, password: str) -> str:
        return self._context.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        return self._context.verify(password, password_hash)
