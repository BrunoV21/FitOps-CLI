class FitOpsError(Exception):
    """Base exception for FitOps-CLI."""


class StravaAuthError(FitOpsError):
    """Raised when Strava authentication fails or token is invalid."""


class SyncError(FitOpsError):
    """Raised when activity sync fails."""


class StravaAPIError(SyncError):
    """A response from Strava that should be preserved at interface boundaries."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        endpoint: str | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.endpoint = endpoint
        self.response_body = response_body


class BrowserPublicationError(FitOpsError):
    """Raised when browser-based Strava publication cannot safely proceed."""

    def __init__(self, message: str, *, code: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ConfigError(FitOpsError):
    """Raised when configuration is missing or invalid."""


class NotAuthenticatedError(FitOpsError):
    """Raised when a command requires auth but no valid token exists."""
