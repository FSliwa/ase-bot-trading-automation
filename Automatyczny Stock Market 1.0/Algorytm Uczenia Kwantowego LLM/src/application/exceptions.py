"""Application specific exceptions."""


class UserAlreadyExistsError(Exception):
    """Raised when trying to register a user that already exists."""

    pass


class UserNotFoundError(Exception):
    """Raised when a user is not found in the database."""

    pass


class InvalidCredentialsError(Exception):
    """Raised during authentication if credentials are invalid."""

    pass
