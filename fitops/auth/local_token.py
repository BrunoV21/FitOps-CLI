"""In-process startup token for local dashboard sessions.

No external dependencies — pure stdlib (hmac + secrets).

Flow:
  1. CLI calls init() before uvicorn starts → returns the startup token
  2. CLI opens browser at http://localhost:PORT/auth/local?token=<startup_token>
  3. /auth/local validates token (constant-time), sets session cookie, redirects to /
  4. LocalAuthMiddleware validates that cookie on every subsequent request
  5. All values live only in memory — invalidated when the server process exits
"""

from __future__ import annotations

import hmac
import secrets
import threading

_lock = threading.Lock()
_startup_token: str = ""
_session_value: str = ""

LOCAL_SESSION_COOKIE = "fitops_local_session"
LOCAL_SESSION_MAX_AGE = 8 * 3600  # 8 hours — survives browser restarts within a day


def init() -> str:
    """Generate a fresh startup token and session value.

    Call once before uvicorn starts. Returns the startup token to embed in
    the browser URL (e.g. http://localhost:8888/auth/local?token=<value>).
    """
    global _startup_token, _session_value
    with _lock:
        _startup_token = secrets.token_urlsafe(32)
        _session_value = secrets.token_urlsafe(32)
    return _startup_token


def get_session_value() -> str:
    """Return the valid session cookie value for this process."""
    return _session_value


def verify_startup_token(token: str) -> bool:
    """Constant-time comparison against the in-memory startup token."""
    if not _startup_token:
        return False
    return hmac.compare_digest(token.encode("utf-8"), _startup_token.encode("utf-8"))


def verify_session(value: str) -> bool:
    """Constant-time comparison against the in-memory session cookie value."""
    if not _session_value:
        return False
    return hmac.compare_digest(value.encode("utf-8"), _session_value.encode("utf-8"))
