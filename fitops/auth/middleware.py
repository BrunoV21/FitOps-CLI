"""Starlette middleware that enforces session-cookie auth on all routes
except the explicit exempt list."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from fitops.auth.session import SESSION_COOKIE, verify_token

# Paths that never require a session
_EXEMPT_EXACT = {"/login", "/logout", "/health"}
_EXEMPT_PREFIX = ("/static/",)


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, session_secret: str) -> None:
        super().__init__(app)
        self._secret = session_secret

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Internal sync endpoint is token-protected, not session-protected
        if path == "/api/internal/sync":
            return await call_next(request)

        if path in _EXEMPT_EXACT or any(path.startswith(p) for p in _EXEMPT_PREFIX):
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE)
        if token and verify_token(self._secret, token):
            return await call_next(request)

        # Preserve the original URL so /login can redirect back after success
        from urllib.parse import quote

        next_url = quote(str(request.url), safe="")
        return RedirectResponse(url=f"/login?next={next_url}", status_code=302)
