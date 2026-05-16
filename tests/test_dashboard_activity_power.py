"""Dashboard HTTP 200 tests for the activity detail page with running power data.

Covers:
- GET /activities/{strava_id} returns 200 when activity has est_power_avg_w set
- GET /activities/{strava_id} returns 200 when activity has no power (streams empty)
- GET /activities/{strava_id} returns 404 when activity not found
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from fitops.dashboard.routes.activities import (
    _deep_analysis_summary_stats,
    _downsample_streams,
)

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
def client(monkeypatch):
    from starlette.testclient import TestClient

    from fitops.dashboard.server import create_app
    from fitops.db import migrations

    monkeypatch.setattr(migrations, "create_all_tables", AsyncMock(return_value=None))
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


def test_activity_detail_weather_panel_hides_true_pace_header_badge(
    client, monkeypatch
):
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
        AsyncMock(
            return_value={
                99001: MagicMock(
                    source="open-meteo",
                    temperature_c=14.0,
                    apparent_temp_c=14.0,
                    humidity_pct=70.0,
                    wind_speed_ms=2.9,
                    wind_direction_deg=180.0,
                    precipitation_mm=0.1,
                    wbgt_c=10.0,
                    weather_code=61,
                    pace_heat_factor=1.0,
                    wap_factor=0.993,
                    course_bearing=180.0,
                    hr_heat_pct=None,
                    hr_heat_bpm=None,
                    true_pace_s_per_km=217.0,
                )
            }
        ),
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
    assert "Conditions" in resp.text
    assert "WAP" not in resp.text
    assert "-0.7%" not in resp.text


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


def test_deep_analysis_summary_stats_include_average_pace_metrics_and_stay_even():
    act = SimpleNamespace(
        distance_m=10_000.0,
        moving_time_s=2_550,
        average_speed_ms=4.0,
        average_heartrate=158.0,
        average_cadence=88.0,
        average_watts=None,
        est_power_avg_w=252.0,
        weighted_average_watts=None,
        est_power_np_w=265.0,
        total_elevation_gain_m=84.0,
        training_stress_score=72.34,
        calories=None,
        max_heartrate=181.0,
    )
    streams = {
        "true_pace": [250.0, 260.0, None],
        "wap_pace": [252.0, 254.0],
    }

    stats = _deep_analysis_summary_stats(
        act,
        streams,
        "Run",
        "4:12/km",
        {"true_pace_fmt": "3:37/km", "wap_fmt": "3:40/km"},
    )
    by_label = {stat["label"]: stat for stat in stats}

    assert len(stats) % 2 == 0
    assert by_label["True Pace"]["value"] == "3:37/km"
    assert by_label["GAP"]["value"] == "4:12/km"
    assert by_label["WAP"]["value"] == "3:40/km"
    assert by_label["Avg Cadence"]["key"] == "cadence"
    assert by_label["Avg Cadence"]["value"] == 88
    assert by_label["Avg Cadence"]["unit"] == "spm"
    assert "step rate" in by_label["Avg Cadence"]["description"]
    assert by_label["Avg Power"]["value"] == 252
    assert by_label["Norm Power"]["value"] == 265
    assert "temperature and humidity only" in by_label["WAP"]["description"]
    assert "local wind" in by_label["True Pace"]["description"]


def test_downsample_streams_aligns_all_series_and_keeps_last_point():
    streams = {
        "time": list(range(1200)),
        "distance": [float(i * 10) for i in range(1198)],
        "latlng": [[40.0 + i * 0.0001, -8.0 - i * 0.0001] for i in range(1199)],
        "heartrate": [140 + (i % 7) for i in range(1201)],
    }

    result = _downsample_streams(streams, target=500)

    assert {len(v) for v in result.values()} == {500}
    assert result["time"][0] == 0
    assert result["time"][-1] == 1199
    assert result["distance"][-1] == streams["distance"][-1]
    assert result["latlng"][-1] == streams["latlng"][-1]
    assert result["heartrate"][-1] == streams["heartrate"][-1]


def test_downsample_streams_preserves_short_streams_without_truncation():
    streams = {
        "time": [0, 1, 2, 3],
        "distance": [0.0, 15.0, 31.0, 47.0],
        "latlng": [[40.0, -8.0], [40.1, -8.1], [40.2, -8.2], [40.3, -8.3]],
    }

    result = _downsample_streams(streams, target=500)

    assert result == streams
