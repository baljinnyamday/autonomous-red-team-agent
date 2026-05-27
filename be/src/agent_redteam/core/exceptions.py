class RedTeamError(Exception):
    """Base error for the red team framework."""


class AuthorizationError(RedTeamError):
    """Raised when an operation lacks explicit authorization."""


class OutOfScopeError(RedTeamError):
    """Raised when a target or action is outside the engagement scope."""
