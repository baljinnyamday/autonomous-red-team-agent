class RedTeamError(Exception):
    """Base error for the red team framework."""


class ConfigurationError(RedTeamError):
    """Raised when runtime configuration is missing or invalid."""


class AuthorizationError(RedTeamError):
    """Raised when an operation lacks explicit authorization."""
