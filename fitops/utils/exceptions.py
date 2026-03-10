class FitOpsError(Exception):
    """Base exception for FitOps-CLI."""


class StravaAuthError(FitOpsError):
    """Raised when Strava authentication fails or token is invalid."""


class SyncError(FitOpsError):
    """Raised when activity sync fails."""


class ConfigError(FitOpsError):
    """Raised when configuration is missing or invalid."""


class NotAuthenticatedError(FitOpsError):
    """Raised when a command requires auth but no valid token exists."""
