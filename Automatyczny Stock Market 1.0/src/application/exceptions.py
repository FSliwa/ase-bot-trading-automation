class UserAlreadyExistsError(Exception):
    """Raised when attempting to register a user that already exists."""


class UserNotFoundError(Exception):
    """Raised when a user is not found in the repository."""


class InvalidCredentialsError(Exception):
    """Raised upon authentication failure."""
