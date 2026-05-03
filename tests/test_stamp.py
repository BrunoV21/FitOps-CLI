"""Tests for Strava activity stamping — fitops/analytics/stamp.py and stamp API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from fitops.analytics.stamp import STAMP_SENTINEL, apply_stamp, compose_stamp

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _activity(**kwargs) -> MagicMock:
    act = MagicMock()
    act.sport_type = "Run"
    act.distance_m = 10_000.0
    act.moving_time_s = 2_700
    act.average_speed_ms = 3.7
    act.average_heartrate = 152.0
    act.max_heartrate = 171.0
    act.average_watts = None
    act.max_watts = None
    act.weighted_average_watts = None
    act.est_power_avg_w = None
    act.est_power_max_w = None
    act.est_power_np_w = None
    act.est_power_source = None
    act.vo2max_estimate = 52.3
    act.aerobic_score = 74.0
    act.anaerobic_score = 18.0
    act.suffer_score = 42
    act.calories = 620
    act.description = None
    for k, v in kwargs.items():
        setattr(act, k, v)
    return act


def _fake_settings(
    *, authenticated: bool = True, write_scope: bool = True
) -> MagicMock:
    s = MagicMock()
    s.is_authenticated = authenticated
    s.has_write_scope = write_scope
    s.athlete_id = 1
    return s


# ---------------------------------------------------------------------------
# Unit tests — compose_stamp
# ---------------------------------------------------------------------------


def test_compose_stamp_excludes_strava_basics():
    # distance, time, pace, and HR are already shown by Strava — not in stamp
    stamp = compose_stamp(_activity())
    assert "10.0 km" not in stamp
    assert "HR" not in stamp
    assert "152" not in stamp
    assert "171" not in stamp


def test_compose_stamp_includes_scores_with_labels():
    stamp = compose_stamp(_activity())
    assert "Aer" in stamp
    assert "Ana" in stamp
    # aerobic_score=74.0 → "exceptional" short label
    assert "exceptional" in stamp


def test_compose_stamp_includes_vo2max():
    stamp = compose_stamp(_activity())
    assert "52.3" in stamp


def test_compose_stamp_includes_scores():
    stamp = compose_stamp(_activity())
    assert "Aer" in stamp
    assert "Ana" in stamp


def test_compose_stamp_real_power_takes_priority():
    act = _activity(average_watts=210.0, est_power_avg_w=200.0)
    stamp = compose_stamp(act)
    assert "210" in stamp
    assert "Power (est" not in stamp


def test_compose_stamp_estimated_power_fallback():
    act = _activity(est_power_avg_w=195.0, est_power_source="running_power_model")
    stamp = compose_stamp(act)
    assert "195" in stamp
    assert "running_power_model" in stamp


def test_compose_stamp_no_power_fields():
    act = _activity(average_watts=None, est_power_avg_w=None)
    stamp = compose_stamp(act)
    assert "Power" not in stamp


def test_compose_stamp_includes_repo_link():
    from fitops.analytics.stamp import REPO_LINK

    stamp = compose_stamp(_activity())
    assert REPO_LINK in stamp


# ---------------------------------------------------------------------------
# Unit tests — apply_stamp
# ---------------------------------------------------------------------------


def test_apply_stamp_fresh_activity():
    result = apply_stamp(None, "STAMP")
    assert "STAMP" in result
    assert STAMP_SENTINEL not in result


def test_apply_stamp_replaces_existing_stamp():
    existing = f"My cool run{STAMP_SENTINEL}OLD STAMP"
    result = apply_stamp(existing, "NEW STAMP")
    assert "NEW STAMP" in result
    assert "OLD STAMP" not in result
    assert "My cool run" in result


def test_apply_stamp_preserves_user_description():
    result = apply_stamp("User wrote this", "STAMP")
    assert "User wrote this" in result
    assert "STAMP" in result


def test_apply_stamp_handles_empty_description():
    result = apply_stamp("", "STAMP")
    assert "STAMP" in result


def test_apply_stamp_idempotent_sentinel_count():
    first = apply_stamp("Base", "S1")
    second = apply_stamp(first, "S2")
    assert second.count(STAMP_SENTINEL) == 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    from starlette.testclient import TestClient

    from fitops.dashboard.server import create_app

    with TestClient(create_app()) as c:
        yield c


# ---------------------------------------------------------------------------
# Dashboard tests — POST /api/activities/{strava_id}/stamp
# ---------------------------------------------------------------------------


def test_stamp_activity_returns_401_when_not_authenticated(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.config.settings.get_settings",
        lambda: _fake_settings(authenticated=False),
    )
    resp = client.post("/api/activities/12345/stamp")
    assert resp.status_code == 401


def test_stamp_activity_returns_403_without_write_scope(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.config.settings.get_settings",
        lambda: _fake_settings(write_scope=False),
    )
    resp = client.post("/api/activities/12345/stamp")
    assert resp.status_code == 403


def test_stamp_activity_returns_404_when_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.config.settings.get_settings",
        lambda: _fake_settings(),
    )

    from fitops.strava.client import StravaClient

    monkeypatch.setattr(StravaClient, "__init__", lambda self: None)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    monkeypatch.setattr("fitops.db.session.get_async_session", lambda: mock_session)

    resp = client.post("/api/activities/99999/stamp")
    assert resp.status_code == 404


def test_stamp_activity_returns_200_on_success(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.config.settings.get_settings",
        lambda: _fake_settings(),
    )

    from fitops.strava.client import StravaClient

    monkeypatch.setattr(StravaClient, "__init__", lambda self: None)

    activity = _activity()
    activity.id = 1
    activity.strava_id = 42001

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = activity
    mock_session.execute = AsyncMock(return_value=mock_result)

    monkeypatch.setattr("fitops.db.session.get_async_session", lambda: mock_session)

    monkeypatch.setattr("fitops.analytics.stamp.stamp_activity", AsyncMock())

    resp = client.post("/api/activities/42001/stamp")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# Dashboard tests — POST /api/activities/stamp-all
# ---------------------------------------------------------------------------


def test_stamp_all_returns_403_without_write_scope(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.config.settings.get_settings",
        lambda: _fake_settings(write_scope=False),
    )
    resp = client.post("/api/activities/stamp-all")
    assert resp.status_code == 403


def test_stamp_all_returns_200_with_counts(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.config.settings.get_settings",
        lambda: _fake_settings(),
    )

    from fitops.strava.client import StravaClient

    monkeypatch.setattr(StravaClient, "__init__", lambda self: None)

    act1 = _activity()
    act1.strava_id = 1001
    act2 = _activity()
    act2.strava_id = 1002

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [act1, act2]
    mock_session.execute = AsyncMock(return_value=mock_result)

    monkeypatch.setattr("fitops.db.session.get_async_session", lambda: mock_session)
    monkeypatch.setattr("fitops.analytics.stamp.stamp_activity", AsyncMock())

    resp = client.post("/api/activities/stamp-all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data["stamped"]) == 2
    assert data["failed"] == []


def test_stamp_all_reports_failures(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.config.settings.get_settings",
        lambda: _fake_settings(),
    )

    from fitops.strava.client import StravaClient

    monkeypatch.setattr(StravaClient, "__init__", lambda self: None)

    act = _activity()
    act.strava_id = 2001

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [act]
    mock_session.execute = AsyncMock(return_value=mock_result)

    monkeypatch.setattr("fitops.db.session.get_async_session", lambda: mock_session)
    monkeypatch.setattr(
        "fitops.analytics.stamp.stamp_activity",
        AsyncMock(side_effect=RuntimeError("Strava down")),
    )

    resp = client.post("/api/activities/stamp-all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["failed"] == [2001]
    assert data["stamped"] == []


# ---------------------------------------------------------------------------
# Dashboard tests — GET /api/auth/reauth
# ---------------------------------------------------------------------------


def test_reauth_redirects_to_strava(client, monkeypatch):
    from fitops.config.settings import FitOpsSettings

    fake = MagicMock(spec=FitOpsSettings)
    fake.client_id = "test_id"
    fake.client_secret = "test_secret"
    fake.save_pending_state = MagicMock()

    monkeypatch.setattr("fitops.dashboard.routes.setup.get_settings", lambda: fake)

    resp = client.get("/api/auth/reauth", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "strava.com" in location
    assert "approval_prompt=force" in location


def test_reauth_redirects_to_setup_when_no_credentials(client, monkeypatch):
    from fitops.config.settings import FitOpsSettings

    fake = MagicMock(spec=FitOpsSettings)
    fake.client_id = None
    fake.client_secret = None

    monkeypatch.setattr("fitops.dashboard.routes.setup.get_settings", lambda: fake)

    resp = client.get("/api/auth/reauth", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/setup" in resp.headers["location"]


# ---------------------------------------------------------------------------
# CLI tests — fitops activities stamp
# ---------------------------------------------------------------------------


def _fake_cli_settings(*, authenticated: bool = True, write_scope: bool = True):
    s = MagicMock()
    s.require_auth = MagicMock()
    s.has_write_scope = write_scope
    if not authenticated:
        from fitops.utils.exceptions import NotAuthenticatedError

        s.require_auth.side_effect = NotAuthenticatedError("Not authenticated")
    return s


def _make_mock_session(activities: list):
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = (
        activities[0] if len(activities) == 1 else None
    )
    mock_result.scalars.return_value.all.return_value = activities
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


def test_cli_stamp_exits_1_when_not_authenticated(monkeypatch):
    from typer.testing import CliRunner

    from fitops.cli.activities import app

    monkeypatch.setattr(
        "fitops.cli.activities.get_settings",
        lambda: _fake_cli_settings(authenticated=False),
    )

    result = CliRunner().invoke(app, ["stamp", "--all"])
    assert result.exit_code == 1


def test_cli_stamp_exits_1_without_write_scope(monkeypatch):
    from typer.testing import CliRunner

    from fitops.cli.activities import app

    monkeypatch.setattr(
        "fitops.cli.activities.get_settings",
        lambda: _fake_cli_settings(write_scope=False),
    )

    result = CliRunner().invoke(app, ["stamp", "--all"])
    assert result.exit_code == 1


def test_cli_stamp_all_json_output_shape(monkeypatch):
    import json

    from typer.testing import CliRunner

    from fitops.cli.activities import app
    from fitops.strava.client import StravaClient

    monkeypatch.setattr(
        "fitops.cli.activities.get_settings", lambda: _fake_cli_settings()
    )
    monkeypatch.setattr("fitops.cli.activities.init_db", lambda: None)
    monkeypatch.setattr(StravaClient, "__init__", lambda self: None)

    act1 = _activity()
    act1.strava_id = 5001
    act1.stamped_at = None
    act2 = _activity()
    act2.strava_id = 5002
    act2.stamped_at = None

    monkeypatch.setattr(
        "fitops.cli.activities.get_async_session",
        lambda: _make_mock_session([act1, act2]),
    )
    monkeypatch.setattr("fitops.analytics.stamp.stamp_activity", AsyncMock())

    result = CliRunner().invoke(app, ["stamp", "--all", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "stamped" in data
    assert "skipped" in data
    assert "failed" in data
    assert isinstance(data["stamped"], list)
    assert data["failed"] == []


def test_cli_stamp_single_json_output_shape(monkeypatch):
    import json

    from typer.testing import CliRunner

    from fitops.cli.activities import app
    from fitops.strava.client import StravaClient

    monkeypatch.setattr(
        "fitops.cli.activities.get_settings", lambda: _fake_cli_settings()
    )
    monkeypatch.setattr("fitops.cli.activities.init_db", lambda: None)
    monkeypatch.setattr(StravaClient, "__init__", lambda self: None)

    act = _activity()
    act.strava_id = 6001
    act.stamped_at = None

    monkeypatch.setattr(
        "fitops.cli.activities.get_async_session", lambda: _make_mock_session([act])
    )
    monkeypatch.setattr("fitops.analytics.stamp.stamp_activity", AsyncMock())

    result = CliRunner().invoke(app, ["stamp", "--id", "6001", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "stamped" in data
    assert "skipped" in data
    assert "failed" in data


def test_cli_stamp_reports_failures_in_json(monkeypatch):
    import json

    from typer.testing import CliRunner

    from fitops.cli.activities import app
    from fitops.strava.client import StravaClient

    monkeypatch.setattr(
        "fitops.cli.activities.get_settings", lambda: _fake_cli_settings()
    )
    monkeypatch.setattr("fitops.cli.activities.init_db", lambda: None)
    monkeypatch.setattr(StravaClient, "__init__", lambda self: None)

    act = _activity()
    act.strava_id = 7001
    act.stamped_at = None

    monkeypatch.setattr(
        "fitops.cli.activities.get_async_session", lambda: _make_mock_session([act])
    )
    monkeypatch.setattr(
        "fitops.analytics.stamp.stamp_activity",
        AsyncMock(side_effect=RuntimeError("network error")),
    )

    result = CliRunner().invoke(app, ["stamp", "--all", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["failed"] == [7001]
    assert data["stamped"] == []
