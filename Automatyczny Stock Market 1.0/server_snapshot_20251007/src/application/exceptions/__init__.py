"""Application-specific exceptions."""


class UserAlreadyExistsError(Exception):
    """Raised when trying to create a user that already exists."""
    pass


class UserNotFoundError(Exception):
    """Raised when a user is not found."""
    pass


class InvalidCredentialsError(Exception):
    """Raised when login credentials are invalid."""
    pass


class PermissionError(Exception):
    """Raised when a user doesn't have permission for an action."""
    pass


__all__ = [
    "UserAlreadyExistsError",
    "UserNotFoundError", 
    "InvalidCredentialsError",
    "PermissionError"
]
