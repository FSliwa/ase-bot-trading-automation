"""Password hashing and verification utility."""

from passlib.context import CryptContext

# Use Argon2id as the primary scheme, with bcrypt as a fallback for legacy passwords
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


class PasswordHasher:
    """A wrapper around passlib for hashing and verifying passwords."""

    @staticmethod
    def hash(password: str) -> str:
        """Hashes a plain-text password."""
        return pwd_context.hash(password)

    @staticmethod
    def verify(plain_password: str, hashed_password: str) -> bool:
        """Verifies a plain-text password against a hash."""
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception:
            return False
