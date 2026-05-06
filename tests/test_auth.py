"""Tests for auth middleware, TOTP helpers, and protected API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# TOTP helpers
# ---------------------------------------------------------------------------


def test_totp_generate_secret():
    pytest.importorskip("pyotp")
    from fitops.auth.totp import generate_secret

    secret = generate_secret()
    assert len(secret) >= 16
    assert secret.isalpha() or secret.isalnum()


def test_totp_verify_valid_code():
    pyotp = pytest.importorskip("pyotp")
    from fitops.auth.totp import generate_secret, verify

    secret = generate_secret()
    code = pyotp.TOTP(secret).now()
    assert verify(secret, code) is True


def test_totp_verify_invalid_code():
    pytest.importorskip("pyotp")
    from fitops.auth.totp import generate_secret, verify

    secret = generate_secret()
    assert verify(secret, "000000") is False


def test_totp_provisioning_uri():
    pytest.importorskip("pyotp")
    from fitops.auth.totp import generate_secret, provisioning_uri

    secret = generate_secret()
    uri = provisioning_uri(secret, account="test@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "FitOps" in uri


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def test_session_roundtrip():
    pytest.importorskip("itsdangerous")
    from fitops.auth.session import create_token, verify_token

    secret = "test-secret-key"
    token = create_token(secret)
    assert verify_token(secret, token) is True


def test_session_wrong_secret():
    pytest.importorskip("itsdangerous")
    from fitops.auth.session import create_token, verify_token

    token = create_token("secret-a")
    assert verify_token("secret-b", token) is False


def test_session_invalid_token():
    pytest.importorskip("itsdangerous")
    from fitops.auth.session import verify_token

    assert verify_token("any-secret", "not-a-valid-token") is False


# ---------------------------------------------------------------------------
# Auth middleware — integration via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_app(monkeypatch):
    """Create a test app with auth enabled using a known session secret."""
    pytest.importorskip("itsdangerous")
    pytest.importorskip("bcrypt")
    monkeypatch.setenv("FITOPS_AUTH_ENABLED", "true")
    monkeypatch.setenv("FITOPS_SESSION_SECRET", "test-session-secret-32-chars-long!!")

    with patch("fitops.db.migrations.create_all_tables", new_callable=AsyncMock):
        with patch(
            "fitops.dashboard.routes.backup.run_scheduler", new_callable=AsyncMock
        ):
            with patch(
                "fitops.dashboard.routes.auto_sync.run_auto_sync_scheduler",
                new_callable=AsyncMock,
            ):
                from fitops.dashboard.server import create_app

                return create_app()


def test_middleware_redirects_unauthenticated(auth_app):
    from starlette.testclient import TestClient

    with TestClient(auth_app, follow_redirects=False) as c:
        resp = c.get("/")
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]


def test_middleware_allows_login_page(auth_app):
    from starlette.testclient import TestClient

    with TestClient(auth_app, follow_redirects=False) as c:
        resp = c.get("/login")
        assert resp.status_code == 200


def test_middleware_allows_health_endpoint(auth_app):
    from starlette.testclient import TestClient

    with TestClient(auth_app, follow_redirects=False) as c:
        resp = c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


def test_middleware_allows_static_assets(auth_app):
    from starlette.testclient import TestClient

    with TestClient(auth_app, follow_redirects=False) as c:
        # /static/ prefix is exempt — 404 is fine (file may not exist), but not a redirect
        resp = c.get("/static/does-not-exist.css")
        assert resp.status_code != 302


def test_middleware_allows_authenticated_request(auth_app):
    from unittest.mock import MagicMock

    from starlette.testclient import TestClient

    from fitops.auth.session import SESSION_COOKIE, create_token

    token = create_token("test-session-secret-32-chars-long!!")

    mock_settings = MagicMock()
    mock_settings.is_authenticated = True
    mock_settings.athlete_id = None

    with patch(
        "fitops.dashboard.routes.overview.get_settings", return_value=mock_settings
    ):
        with TestClient(auth_app, follow_redirects=False) as c:
            resp = c.get("/", cookies={SESSION_COOKIE: token})
            assert resp.status_code != 302


# ---------------------------------------------------------------------------
# /health endpoint (no auth required)
# ---------------------------------------------------------------------------


def test_health_no_auth():
    from unittest.mock import AsyncMock, patch

    with patch("fitops.db.migrations.create_all_tables", new_callable=AsyncMock):
        with patch(
            "fitops.dashboard.routes.backup.run_scheduler", new_callable=AsyncMock
        ):
            with patch(
                "fitops.dashboard.routes.auto_sync.run_auto_sync_scheduler",
                new_callable=AsyncMock,
            ):
                from starlette.testclient import TestClient

                from fitops.dashboard.server import create_app

                with TestClient(create_app()) as c:
                    resp = c.get("/health")
                    assert resp.status_code == 200
                    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# /api/internal/sync endpoint
# ---------------------------------------------------------------------------


def test_sync_endpoint_not_configured():
    from unittest.mock import AsyncMock, patch

    with patch("fitops.db.migrations.create_all_tables", new_callable=AsyncMock):
        with patch(
            "fitops.dashboard.routes.backup.run_scheduler", new_callable=AsyncMock
        ):
            with patch(
                "fitops.dashboard.routes.auto_sync.run_auto_sync_scheduler",
                new_callable=AsyncMock,
            ):
                from starlette.testclient import TestClient

                from fitops.dashboard.server import create_app

                with TestClient(create_app()) as c:
                    resp = c.post("/api/internal/sync")
                    assert resp.status_code == 501


def test_sync_endpoint_bad_token(monkeypatch):
    monkeypatch.setenv("FITOPS_SYNC_TOKEN", "correct-token")
    from unittest.mock import AsyncMock, patch

    with patch("fitops.db.migrations.create_all_tables", new_callable=AsyncMock):
        with patch(
            "fitops.dashboard.routes.backup.run_scheduler", new_callable=AsyncMock
        ):
            with patch(
                "fitops.dashboard.routes.auto_sync.run_auto_sync_scheduler",
                new_callable=AsyncMock,
            ):
                from starlette.testclient import TestClient

                from fitops.dashboard.server import create_app

                with TestClient(create_app()) as c:
                    resp = c.post(
                        "/api/internal/sync",
                        headers={"X-Sync-Token": "wrong-token"},
                    )
                    assert resp.status_code == 403


def test_sync_endpoint_valid_token(monkeypatch):
    monkeypatch.setenv("FITOPS_SYNC_TOKEN", "my-secret-sync-token")
    from unittest.mock import AsyncMock, patch

    with patch("fitops.db.migrations.create_all_tables", new_callable=AsyncMock):
        with patch(
            "fitops.dashboard.routes.backup.run_scheduler", new_callable=AsyncMock
        ):
            with patch(
                "fitops.dashboard.routes.auto_sync.run_auto_sync_scheduler",
                new_callable=AsyncMock,
            ):
                with patch("subprocess.run"):
                    from starlette.testclient import TestClient

                    from fitops.dashboard.server import create_app

                    with TestClient(create_app()) as c:
                        resp = c.post(
                            "/api/internal/sync",
                            headers={"X-Sync-Token": "my-secret-sync-token"},
                        )
                        assert resp.status_code == 202
