class ExchangeError(Exception):
    """Base type for all exchange-related failures."""


class InvalidExchangeError(ExchangeError):
    """Raised when an adapter for a requested exchange is not available."""


class OrderPlacementError(ExchangeError):
    """Raised when submitting an order fails."""


class CredentialsError(ExchangeError):
    """Raised when API credentials are invalid or missing."""
