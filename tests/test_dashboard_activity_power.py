"""Dashboard HTTP 200 tests for the activity detail page with running power data.

Covers:
- GET /activities/{strava_id} returns 200 when activity has est_power_avg_w set
- GET /activities/{strava_id} returns 200 when activity has no power (streams empty)
- GET /activities/{strava_id} returns 404 when activity not found
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_activity(*, power: bool = True) -> MagicMock:
    act = MagicMock()
    act.id = 1
    act.strava_id = 99001
    act.sport_type = "Run"
    act.name = "Morning Run"
    act.start_date = "2026-04-20T07:00:00+00:00"
    act.distance_m = 10_000.0
    act.moving_time_s = 3_000
    act.elapsed_time_s = 3_060
    act.total_elevation_gain_m = 50.0
    act.average_speed_ms = 3.33
    act.max_speed_ms = 4.0
    act.average_heartrate = 155.0
    act.max_heartrate = 172.0
    act.average_cadence = 85.0
    act.average_watts = None
    act.kilojoules = None
    act.streams_fetched = False
    act.laps_fetched = False
    act.gear_id = None
    act.start_latlng = None
    act.end_latlng = None
    act.description = None
    act.device_name = None
    act.calories = None
    act.suffer_score = None
    act.kudos_count = 0
    act.achievement_count = 0
    act.pr_count = 0
    act.vo2max_estimate = None
    act.aerobic_score = None
    act.anaerobic_score = None
    # Power fields
    act.est_power_avg_w = 245.0 if power else None
    act.est_power_max_w = 310.0 if power else None
    act.est_power_np_w = 255.0 if power else None
    act.est_kcal_model = 520.0 if power else None
    act.est_power_source = "running_power_model" if power else None
    return act


def _fake_settings() -> MagicMock:
    s = MagicMock()
    s.athlete_id = 42
    return s


def _fake_athlete_settings() -> MagicMock:
    s = MagicMock()
    s.lthr = 160
    s.max_hr = 185
    s.weight_kg = 70.0
    s.ftp_w = None
    s.ftp = None
    s.vo2max = None
    s.zones = None
    s.threshold_pace_per_km_s = None
    return s


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    from starlette.testclient import TestClient

    from fitops.dashboard.server import create_app
    from fitops.db import migrations

    migrations.create_all_tables = AsyncMock(return_value=None)
    with TestClient(create_app()) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_activity_detail_with_power(client, monkeypatch):
    """GET /activities/{id} returns 200 when the activity has stored power data."""
    act = _fake_activity(power=True)

    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_settings",
        lambda: _fake_settings(),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_activity_detail",
        AsyncMock(return_value=act),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_activity_laps",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_activity_streams",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_activity_calibration",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_weather_for_activities",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_athlete_settings",
        _fake_athlete_settings,
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.compute_activity_analytics",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.compute_activity_performance_insights",
        lambda *_: [],
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_all_workouts",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_workout_for_activity",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_race_plan_for_activity",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_athlete",
        AsyncMock(return_value=None),
    )

    resp = client.get("/activities/99001")
    assert resp.status_code == 200


def test_activity_detail_no_power(client, monkeypatch):
    """GET /activities/{id} returns 200 when the activity has no power data."""
    act = _fake_activity(power=False)

    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_settings",
        lambda: _fake_settings(),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_activity_detail",
        AsyncMock(return_value=act),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_activity_laps",
        AsyncMock(return_value=[]),
    )
    # No streams → lazy compute block is skipped
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_activity_streams",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_activity_calibration",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_weather_for_activities",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_activity_calibration",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_athlete_settings",
        _fake_athlete_settings,
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.compute_activity_analytics",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.compute_activity_performance_insights",
        lambda *_: [],
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_all_workouts",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_workout_for_activity",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_race_plan_for_activity",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_athlete",
        AsyncMock(return_value=None),
    )

    resp = client.get("/activities/99001")
    assert resp.status_code == 200


def test_activity_detail_not_found(client, monkeypatch):
    """GET /activities/{id} returns 404 when the activity doesn't exist."""
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_settings",
        lambda: _fake_settings(),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_activity_detail",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_weather_for_activities",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_athlete_settings",
        _fake_athlete_settings,
    )

    resp = client.get("/activities/00000")
    assert resp.status_code == 404
