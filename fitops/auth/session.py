"""Signed-cookie session management (stateless, no DB)."""

from __future__ import annotations

from datetime import timedelta

SESSION_COOKIE = "fitops_session"
SESSION_MAX_AGE = int(timedelta(hours=24).total_seconds())


def _signer(secret: str):
    from itsdangerous import URLSafeTimedSerializer

    return URLSafeTimedSerializer(secret)


def create_token(secret: str) -> str:
    return _signer(secret).dumps({"u": "admin"})


def verify_token(secret: str, token: str) -> bool:
    try:
        _signer(secret).loads(token, max_age=SESSION_MAX_AGE)
        return True
    except Exception:
        return False
