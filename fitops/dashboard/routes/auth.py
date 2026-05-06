"""Dashboard auth routes: /login, /logout (deploy mode) and /auth/local (local mode)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from fitops.auth.session import SESSION_COOKIE, SESSION_MAX_AGE, create_token

router = APIRouter()


def register(templates: Jinja2Templates) -> APIRouter:
    _pw_hash: str = os.environ.get("FITOPS_PASSWORD_HASH", "")
    _totp_secret: str = os.environ.get("FITOPS_TOTP_SECRET", "")
    _session_secret: str = os.environ.get("FITOPS_SESSION_SECRET", "")

    @router.get("/login", response_class=HTMLResponse)
    async def login_get(request: Request, next: str = "/", error: str = ""):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"request": request, "next": next, "error": error},
        )

    @router.post("/login")
    async def login_post(
        request: Request,
        password: str = Form(...),
        totp_code: str = Form(...),
        next: str = Form("/"),
    ):
        import bcrypt

        from fitops.auth.totp import verify as verify_totp

        pw_ok = bool(_pw_hash and bcrypt.checkpw(password.encode(), _pw_hash.encode()))
        totp_ok = bool(_totp_secret and verify_totp(_totp_secret, totp_code))

        if not (pw_ok and totp_ok):
            return templates.TemplateResponse(
                request,
                "auth/login.html",
                {
                    "request": request,
                    "next": next,
                    "error": "Invalid password or authenticator code.",
                },
                status_code=401,
            )

        token = create_token(_session_secret)
        safe_next = next if next.startswith("/") else "/"
        # Respect X-Forwarded-Proto so the cookie works behind HF's HTTP proxy
        proto = request.headers.get("x-forwarded-proto", "https")
        # Return a 200 HTML page that sets the cookie and then redirects via JS.
        # A 303 RedirectResponse with Set-Cookie can be swallowed by reverse
        # proxies (HF Spaces terminates TLS upstream), causing the browser to
        # follow the redirect before the cookie is stored. A 200 response
        # ensures Set-Cookie is fully processed first.
        safe_next_escaped = safe_next.replace('"', "%22")
        html = (
            f"<!doctype html><html><head>"
            f'<meta http-equiv="refresh" content="0;url={safe_next_escaped}">'
            f"</head><body>"
            f'<script>window.location.replace("{safe_next_escaped}");</script>'
            f"</body></html>"
        )
        response = HTMLResponse(content=html, status_code=200)
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=(proto == "https"),
        )
        return response

    @router.get("/logout")
    async def logout():
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        return response

    return router


_local_router = APIRouter()


def register_local(templates: Jinja2Templates) -> APIRouter:
    """Register local-mode auth routes (/auth/local and /auth/local/expired)."""

    @_local_router.get("/auth/local")
    async def local_auth(token: str = ""):
        from fitops.auth.local_token import (
            LOCAL_SESSION_COOKIE,
            LOCAL_SESSION_MAX_AGE,
            get_session_value,
            verify_startup_token,
        )

        if not token or not verify_startup_token(token):
            return RedirectResponse(url="/auth/local/expired", status_code=302)

        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            LOCAL_SESSION_COOKIE,
            get_session_value(),
            max_age=LOCAL_SESSION_MAX_AGE,
            httponly=True,
            samesite="strict",
            secure=False,  # always localhost, never HTTPS
        )
        return response

    @_local_router.get("/auth/local/expired")
    async def local_auth_expired(request: Request):
        return templates.TemplateResponse(
            request,
            "auth/local_expired.html",
            {"request": request},
        )

    return _local_router
