"""Tests for enriched `fitops activities get` output fields.

Covers:
- activity_splits: compute_km_splits, compute_avg_gap
- training_scores: aerobic_label, anaerobic_label
- weather_pace: weather_row_to_dict
- formatter: elapsed_time_s, efficiency_pct, description, device_name
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# format_activity_row — new fields (elapsed_time, description, device_name)
# ---------------------------------------------------------------------------

_BASE_ROW = {
    "strava_id": 99,
    "name": "Test Run",
    "sport_type": "Run",
    "start_date_local": None,
    "start_date": None,
    "timezone": None,
    "moving_time_s": 3600,
    "elapsed_time_s": 3800,
    "distance_m": 10000.0,
    "average_speed_ms": 2.778,
    "max_speed_ms": 4.0,
    "total_elevation_gain_m": 50.0,
    "average_heartrate": None,
    "max_heartrate": None,
    "average_cadence": None,
    "average_watts": None,
    "max_watts": None,
    "weighted_average_watts": None,
    "training_stress_score": None,
    "suffer_score": None,
    "calories": None,
    "trainer": False,
    "commute": False,
    "manual": False,
    "private": False,
    "kudos_count": 0,
    "comment_count": 0,
    "gear_id": None,
    "start_latlng": None,
    "end_latlng": None,
    "streams_fetched": False,
    "laps_fetched": False,
    "detail_fetched": False,
    "workout_type": None,
    "description": "  Great run today.  ",
    "device_name": "Garmin Forerunner 965",
}


def test_formatter_elapsed_time_seconds():
    from fitops.output.formatter import format_activity_row

    out = format_activity_row(_BASE_ROW)
    assert out["duration"]["elapsed_time_seconds"] == 3800


def test_formatter_elapsed_time_formatted():
    from fitops.output.formatter import format_activity_row

    out = format_activity_row(_BASE_ROW)
    assert out["duration"]["elapsed_time_formatted"] == "1:03:20"


def test_formatter_efficiency_pct():
    from fitops.output.formatter import format_activity_row

    out = format_activity_row(_BASE_ROW)
    # 3600 / 3800 * 100 = 94.7... → rounds to 95
    assert out["duration"]["efficiency_pct"] == 95


def test_formatter_efficiency_pct_perfect():
    from fitops.output.formatter import format_activity_row

    row = dict(_BASE_ROW, moving_time_s=3600, elapsed_time_s=3600)
    out = format_activity_row(row)
    assert out["duration"]["efficiency_pct"] == 100


def test_formatter_efficiency_pct_none_when_no_elapsed():
    from fitops.output.formatter import format_activity_row

    row = dict(_BASE_ROW, elapsed_time_s=None)
    out = format_activity_row(row)
    assert out["duration"]["efficiency_pct"] is None


def test_formatter_description_stripped():
    from fitops.output.formatter import format_activity_row

    out = format_activity_row(_BASE_ROW)
    assert out["description"] == "Great run today."


def test_formatter_description_none_when_empty():
    from fitops.output.formatter import format_activity_row

    row = dict(_BASE_ROW, description="   ")
    out = format_activity_row(row)
    assert out["description"] is None


def test_formatter_description_none_when_missing():
    from fitops.output.formatter import format_activity_row

    row = dict(_BASE_ROW)
    del row["description"]
    out = format_activity_row(row)
    assert out["description"] is None


def test_formatter_device_name():
    from fitops.output.formatter import format_activity_row

    out = format_activity_row(_BASE_ROW)
    assert out["device_name"] == "Garmin Forerunner 965"


def test_formatter_device_name_none():
    from fitops.output.formatter import format_activity_row

    row = dict(_BASE_ROW, device_name=None)
    out = format_activity_row(row)
    assert out["device_name"] is None


# ---------------------------------------------------------------------------
# activity_splits — compute_km_splits
# ---------------------------------------------------------------------------


def _make_stream(n: int, spacing_m: float = 10.0, speed_ms: float = 3.0) -> dict:
    """Build minimal distance + velocity_smooth streams covering ~n km."""
    dist = [i * spacing_m for i in range(n)]
    vel = [speed_ms] * n
    return {"distance": dist, "velocity_smooth": vel}


def test_km_splits_non_run_returns_none():
    from fitops.analytics.activity_splits import compute_km_splits

    streams = _make_stream(500, spacing_m=10.0)
    assert compute_km_splits(streams, "Ride") is None


def test_km_splits_insufficient_data_returns_none():
    from fitops.analytics.activity_splits import compute_km_splits

    # Only 5 data points
    assert (
        compute_km_splits(
            {"distance": [0, 100, 200, 300, 400], "velocity_smooth": [3] * 5}, "Run"
        )
        is None
    )


def test_km_splits_too_short_distance_returns_none():
    from fitops.analytics.activity_splits import compute_km_splits

    # 50 data points but < 1000m total
    streams = _make_stream(50, spacing_m=5.0, speed_ms=3.0)
    assert compute_km_splits(streams, "Run") is None


def test_km_splits_returns_list_for_run():
    from fitops.analytics.activity_splits import compute_km_splits

    # 500 data points × 10m = 5000m → should produce 4 full km + 1 partial
    streams = _make_stream(500, spacing_m=10.0, speed_ms=3.0)
    splits = compute_km_splits(streams, "Run")
    assert splits is not None
    assert len(splits) >= 4


def test_km_splits_each_split_has_required_keys():
    from fitops.analytics.activity_splits import compute_km_splits

    streams = _make_stream(200, spacing_m=10.0, speed_ms=3.0)
    splits = compute_km_splits(streams, "Run")
    assert splits is not None
    for split in splits:
        assert "km" in split
        assert "label" in split
        assert "partial" in split
        assert "pace" in split
        assert "pace_s" in split
        assert "elev_loss" in split
        assert "avg_true_pace" in split


def test_km_splits_true_pace_populated_when_provided():
    from fitops.analytics.activity_splits import compute_km_splits

    n = 200
    spacing_m = 10.0
    speed_ms = 3.0
    streams = _make_stream(n, spacing_m=spacing_m, speed_ms=speed_ms)
    # true_pace values in seconds per km (~333 s/km at 3 m/s)
    true_pace = [333.0] * n
    splits = compute_km_splits(streams, "Run", true_pace=true_pace)
    assert splits is not None
    for split in splits:
        assert split["avg_true_pace"] is not None
        assert "/km" in split["avg_true_pace"]


def test_km_splits_true_pace_none_when_not_provided():
    from fitops.analytics.activity_splits import compute_km_splits

    streams = _make_stream(200, spacing_m=10.0, speed_ms=3.0)
    splits = compute_km_splits(streams, "Run", true_pace=None)
    assert splits is not None
    for split in splits:
        assert split["avg_true_pace"] is None


def test_km_splits_include_distance_and_split_time():
    from fitops.analytics.activity_splits import compute_km_splits

    streams = {
        "distance": [i * 10.0 for i in range(201)],
        "time": [i * 3.0 for i in range(201)],
        "velocity_smooth": [3.333] * 201,
    }
    splits = compute_km_splits(streams, "Run")
    assert splits is not None
    assert splits[0]["distance_m"] == pytest.approx(1000.0, abs=5.0)
    assert splits[0]["split_time_s"] == pytest.approx(300.0, abs=5.0)
    assert splits[0]["split_time_fmt"] == "5:00"


def test_km_splits_apply_distance_and_time_scaling():
    from fitops.analytics.activity_splits import compute_km_splits

    streams = {
        "distance": [i * 10.0 for i in range(201)],
        "time": [i * 3.0 for i in range(201)],
        "velocity_smooth": [3.333] * 201,
    }
    splits = compute_km_splits(
        streams,
        "Run",
        distance_scale=1.02,
        time_scale=0.98,
    )
    assert splits is not None
    assert splits[0]["distance_m"] > 1000.0
    assert splits[0]["split_time_s"] < 300.0
    assert splits[0]["pace_s"] < 300.0


def test_km_splits_elev_loss_populated_when_altitude_descends():
    from fitops.analytics.activity_splits import compute_km_splits

    n = 150
    spacing_m = 10.0
    dist = [i * spacing_m for i in range(n)]
    vel = [3.0] * n
    # Descending altitude: 100m → 50m over 1500m
    alt = [100.0 - i * (50.0 / (n - 1)) for i in range(n)]
    streams = {"distance": dist, "velocity_smooth": vel, "altitude": alt}
    splits = compute_km_splits(streams, "Run")
    assert splits is not None
    # At least one split should have elev_loss > 0
    assert any(sp["elev_loss"] and sp["elev_loss"] > 0 for sp in splits)


def test_km_splits_trail_run_supported():
    from fitops.analytics.activity_splits import compute_km_splits

    streams = _make_stream(200, spacing_m=10.0, speed_ms=3.0)
    assert compute_km_splits(streams, "TrailRun") is not None


def test_km_splits_partial_flag_on_last():
    from fitops.analytics.activity_splits import compute_km_splits

    # 1500m total → 1 full km + partial last
    streams = _make_stream(150, spacing_m=10.0, speed_ms=3.0)
    splits = compute_km_splits(streams, "Run")
    assert splits is not None
    # Last split should be partial
    assert splits[-1]["partial"] is True
    # First split should not be partial
    assert splits[0]["partial"] is False


def test_km_splits_walk_returns_splits():
    from fitops.analytics.activity_splits import compute_km_splits

    streams = _make_stream(200, spacing_m=10.0, speed_ms=1.5)
    assert compute_km_splits(streams, "Walk") is not None


# ---------------------------------------------------------------------------
# activity_splits — compute_avg_gap
# ---------------------------------------------------------------------------


def test_avg_gap_non_run_returns_none():
    from fitops.analytics.activity_splits import compute_avg_gap

    streams = {"grade_adjusted_speed": [3.0] * 100}
    assert compute_avg_gap(streams, "Ride") is None


def test_avg_gap_returns_formatted_string():
    from fitops.analytics.activity_splits import compute_avg_gap

    # 4.0 m/s → exactly 250 s/km → 4:10/km (clean float division)
    streams = {"grade_adjusted_speed": [4.0] * 50}
    result = compute_avg_gap(streams, "Run")
    assert result == "4:10/km"


def test_avg_gap_falls_back_to_vel_and_grade():
    from fitops.analytics.activity_splits import compute_avg_gap

    # No grade_adjusted_speed; fallback computes from velocity + grade
    # flat grade → GAP ≈ velocity
    streams = {
        "velocity_smooth": [1000 / 300] * 50,
        "grade_smooth": [0.0] * 50,
    }
    result = compute_avg_gap(streams, "Run")
    assert result is not None
    assert "/km" in result


def test_avg_gap_empty_streams_returns_none():
    from fitops.analytics.activity_splits import compute_avg_gap

    assert compute_avg_gap({}, "Run") is None


# ---------------------------------------------------------------------------
# training_scores — aerobic_label, anaerobic_label
# ---------------------------------------------------------------------------


def test_aerobic_label_exceptional():
    from fitops.analytics.training_scores import aerobic_label

    assert aerobic_label(5.0) == "Exceptional aerobic session"


def test_aerobic_label_strong():
    from fitops.analytics.training_scores import aerobic_label

    assert aerobic_label(4.0) == "Strong aerobic stimulus"


def test_aerobic_label_solid():
    from fitops.analytics.training_scores import aerobic_label

    assert aerobic_label(3.0) == "Solid aerobic base work"


def test_aerobic_label_moderate():
    from fitops.analytics.training_scores import aerobic_label

    assert aerobic_label(2.0) == "Moderate aerobic benefit"


def test_aerobic_label_light():
    from fitops.analytics.training_scores import aerobic_label

    assert aerobic_label(1.0) == "Light aerobic stimulus"


def test_aerobic_label_minimal():
    from fitops.analytics.training_scores import aerobic_label

    assert aerobic_label(0.0) == "Minimal aerobic benefit"


def test_anaerobic_label_race():
    from fitops.analytics.training_scores import anaerobic_label

    assert anaerobic_label(5.0) == "Race-intensity effort"


def test_anaerobic_label_hard():
    from fitops.analytics.training_scores import anaerobic_label

    assert anaerobic_label(4.0) == "Hard anaerobic session"


def test_anaerobic_label_significant():
    from fitops.analytics.training_scores import anaerobic_label

    assert anaerobic_label(3.0) == "Significant threshold stress"


def test_anaerobic_label_moderate():
    from fitops.analytics.training_scores import anaerobic_label

    assert anaerobic_label(2.0) == "Moderate anaerobic load"


def test_anaerobic_label_light():
    from fitops.analytics.training_scores import anaerobic_label

    assert anaerobic_label(1.0) == "Light anaerobic stimulus"


def test_anaerobic_label_minimal():
    from fitops.analytics.training_scores import anaerobic_label

    assert anaerobic_label(0.0) == "Minimal anaerobic stress"


# ---------------------------------------------------------------------------
# weather_pace — weather_row_to_dict
# ---------------------------------------------------------------------------


def _make_weather_obj(**kwargs):
    defaults = {
        "temperature_c": 20.0,
        "apparent_temp_c": 19.0,
        "humidity_pct": 60.0,
        "wind_speed_ms": 3.0,
        "wind_direction_deg": 180.0,
        "precipitation_mm": 0.0,
        "wbgt_c": 15.5,
        "weather_code": 1,
        "pace_heat_factor": 1.02,
        "source": "open-meteo",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_weather_row_to_dict_basic_fields():
    from fitops.analytics.weather_pace import weather_row_to_dict

    w = _make_weather_obj()
    d = weather_row_to_dict(w)
    assert d["temperature_c"] == 20.0
    assert d["humidity_pct"] == 60.0
    assert d["wind_speed_ms"] == 3.0
    assert d["source"] == "open-meteo"


def test_weather_row_to_dict_wind_speed_kmh():
    from fitops.analytics.weather_pace import weather_row_to_dict

    w = _make_weather_obj(wind_speed_ms=5.0)
    d = weather_row_to_dict(w)
    assert d["wind_speed_kmh"] == 18.0


def test_weather_row_to_dict_wind_direction_compass():
    from fitops.analytics.weather_pace import weather_row_to_dict

    w = _make_weather_obj(wind_direction_deg=180.0)
    d = weather_row_to_dict(w)
    assert d["wind_dir_compass"] == "S"


def test_weather_row_to_dict_wbgt_flag_green():
    from fitops.analytics.weather_pace import weather_row_to_dict

    w = _make_weather_obj(wbgt_c=8.0)
    d = weather_row_to_dict(w)
    assert d["wbgt_flag"] == "green"


def test_weather_row_to_dict_wbgt_flag_yellow():
    from fitops.analytics.weather_pace import weather_row_to_dict

    w = _make_weather_obj(wbgt_c=20.0)
    d = weather_row_to_dict(w)
    assert d["wbgt_flag"] == "yellow"


def test_weather_row_to_dict_wbgt_flag_red():
    from fitops.analytics.weather_pace import weather_row_to_dict

    w = _make_weather_obj(wbgt_c=25.0)
    d = weather_row_to_dict(w)
    assert d["wbgt_flag"] == "red"


def test_weather_row_to_dict_wbgt_flag_black():
    from fitops.analytics.weather_pace import weather_row_to_dict

    w = _make_weather_obj(wbgt_c=30.0)
    d = weather_row_to_dict(w)
    assert d["wbgt_flag"] == "black"


def test_weather_row_to_dict_condition_label():
    from fitops.analytics.weather_pace import weather_row_to_dict

    w = _make_weather_obj(weather_code=1)
    d = weather_row_to_dict(w)
    assert d["condition"] == "Mainly clear"


def test_weather_row_to_dict_temp_fmt():
    from fitops.analytics.weather_pace import weather_row_to_dict

    w = _make_weather_obj(temperature_c=22.7)
    d = weather_row_to_dict(w)
    assert d["temp_fmt"] == "23°C"


def test_weather_row_to_dict_null_wind_speed():
    from fitops.analytics.weather_pace import weather_row_to_dict

    w = _make_weather_obj(wind_speed_ms=None)
    d = weather_row_to_dict(w)
    assert d["wind_speed_kmh"] is None


def test_weather_row_to_dict_null_wbgt_defaults_green():
    from fitops.analytics.weather_pace import weather_row_to_dict

    w = _make_weather_obj(wbgt_c=None)
    d = weather_row_to_dict(w)
    assert d["wbgt_flag"] == "green"


def test_print_activity_detail_hides_adj_pace(capsys):
    from fitops.output.text_formatter import print_activity_detail

    activity = {
        "name": "Fast Run",
        "sport_type": "Run",
        "start_date_local": "2026-05-09T08:00:00",
        "distance": {"km": 5.23},
        "duration": {"moving_time_formatted": "19:20"},
        "pace": {"average_per_km": "3:41", "average_per_mile": "5:56"},
        "elevation": {"total_gain_m": 49.2},
        "heart_rate": {"average_bpm": 190, "max_bpm": 196},
        "training_metrics": {"calories": 297},
        "insights": {"aerobic_training_score": 3.1, "anaerobic_training_score": 3.7},
        "avg_gap": "3:39/km",
        "weather": {
            "true_pace_fmt": "3:37/km",
            "wap_fmt": "3:43/km",
            "wap_factor_pct": -0.7,
            "temp_fmt": "14°C",
            "condition": "Light drizzle",
            "wbgt_flag": "green",
            "wind_speed_kmh": 10.5,
            "wind_dir_compass": "S",
            "precipitation_mm": 0.1,
        },
    }

    print_activity_detail(activity)
    out = capsys.readouterr().out
    assert "True Pace 3:37/km" in out
    assert "Adj Pace" not in out
    assert "conditions easier" not in out


@pytest.mark.asyncio
async def test_replace_activity_streams_replaces_all_existing_rows():
    from fitops.cli.activities import _replace_activity_streams

    execute_calls = []
    added_rows = []

    class _Session:
        async def execute(self, stmt):
            execute_calls.append(stmt)
            return None

        def add(self, row):
            added_rows.append(row)

    session = _Session()
    stream_data = {
        "velocity_smooth": {"data": [3.0, 3.1, 3.2]},
        "latlng": [[1.0, 2.0], [1.1, 2.1]],
    }

    await _replace_activity_streams(session, 42, stream_data)

    assert len(execute_calls) == 1
    assert "DELETE FROM activity_streams" in str(execute_calls[0])
    assert len(added_rows) == 2
    assert {row.stream_type for row in added_rows} == {"velocity_smooth", "latlng"}
    assert all(row.activity_id == 42 for row in added_rows)


@pytest.mark.asyncio
async def test_refresh_activity_weather_cache_uses_strava_activity_id(monkeypatch):
    from fitops.cli.activities import _refresh_activity_weather_cache

    execute_calls = []
    weather_row = SimpleNamespace(activity_id=18435320363)

    class _Result:
        def scalar_one_or_none(self):
            return weather_row

    class _Session:
        async def execute(self, stmt):
            execute_calls.append(stmt)
            return _Result()

    class _SessionCtx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    persist_mock = AsyncMock()

    monkeypatch.setattr("fitops.cli.activities.get_async_session", lambda: _SessionCtx())
    monkeypatch.setattr(
        "fitops.analytics.weather_pace.persist_derived_weather",
        persist_mock,
    )

    activity = SimpleNamespace(id=7, strava_id=18435320363)
    streams = {"velocity_smooth": [3.0, 3.1]}

    refreshed = await _refresh_activity_weather_cache(
        activity,
        strava_activity_id=18435320363,
        streams=streams,
    )

    assert refreshed is weather_row
    assert len(execute_calls) == 1
    compiled = execute_calls[0].compile()
    assert 18435320363 in compiled.params.values()
    assert 7 not in compiled.params.values()
    persist_mock.assert_awaited_once()
    args = persist_mock.await_args.args
    assert args[1] is weather_row
    assert args[2] is activity
    assert args[3] == streams


# ---------------------------------------------------------------------------
# format_activity_row — running power fields
# ---------------------------------------------------------------------------

_POWER_RUN_ROW = {
    **_BASE_ROW,
    "est_power_avg_w": 245.7,
    "est_power_max_w": 410.2,
    "est_power_np_w": 251.3,
    "est_kcal_model": 820,
    "est_power_source": "true_pace",
}


def test_formatter_run_power_present():
    from fitops.output.formatter import format_activity_row

    out = format_activity_row(_POWER_RUN_ROW)
    p = out["power"]
    assert p is not None
    assert p["avg_w"] == 246
    assert p["max_w"] == 410
    assert p["np_w"] == 251
    assert p["est_kcal"] == 820
    assert p["source"] == "true_pace"


def test_formatter_run_power_absent_returns_none():
    from fitops.output.formatter import format_activity_row

    row = {**_BASE_ROW, "est_power_avg_w": None}
    out = format_activity_row(row)
    assert out["power"] is None


def test_formatter_ride_power_unchanged():
    from fitops.output.formatter import format_activity_row

    ride_row = {
        **_BASE_ROW,
        "sport_type": "Ride",
        "average_watts": 200.0,
        "max_watts": 450,
        "weighted_average_watts": 210.0,
        "est_power_avg_w": None,
    }
    out = format_activity_row(ride_row)
    p = out["power"]
    assert p is not None
    assert p["average_watts"] == 200.0
    assert "avg_w" not in p


def test_formatter_run_power_partial_nulls():
    from fitops.output.formatter import format_activity_row

    row = {
        **_BASE_ROW,
        "est_power_avg_w": 230.0,
        "est_power_max_w": None,
        "est_power_np_w": None,
        "est_kcal_model": None,
        "est_power_source": "velocity_smooth",
    }
    out = format_activity_row(row)
    p = out["power"]
    assert p["avg_w"] == 230
    assert p["max_w"] is None
    assert p["np_w"] is None
    assert p["est_kcal"] is None
    assert p["source"] == "velocity_smooth"


# ---------------------------------------------------------------------------
# dashboard _activity_row — running power fields in template context
# ---------------------------------------------------------------------------


def _make_activity_ns(**kwargs):
    defaults = {
        "strava_id": 123,
        "name": "Test Run",
        "sport_type": "Run",
        "start_date_local": None,
        "distance_m": 10000.0,
        "moving_time_s": 3600,
        "elapsed_time_s": 3800,
        "average_speed_ms": 2.778,
        "average_heartrate": None,
        "max_heartrate": None,
        "average_watts": None,
        "weighted_average_watts": None,
        "max_watts": None,
        "training_stress_score": None,
        "total_elevation_gain_m": 50.0,
        "is_race": False,
        "trainer": False,
        "commute": False,
        "average_cadence": None,
        "calories": None,
        "suffer_score": None,
        "description": None,
        "device_name": None,
        "gear_id": None,
        "aerobic_score": None,
        "anaerobic_score": None,
        "est_power_avg_w": None,
        "est_power_max_w": None,
        "est_power_np_w": None,
        "est_kcal_model": None,
        "est_power_source": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _patch_scores(monkeypatch):
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.compute_aerobic_score", lambda *a, **k: 3.0
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.compute_anaerobic_score",
        lambda *a, **k: 2.0,
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_athlete_settings",
        lambda: SimpleNamespace(),
    )


def test_activity_row_power_present(monkeypatch):
    from fitops.dashboard.routes.activities import _activity_row

    _patch_scores(monkeypatch)
    a = _make_activity_ns(
        est_power_avg_w=243.7,
        est_power_max_w=410.0,
        est_power_np_w=250.1,
        est_kcal_model=850,
        est_power_source="true_pace",
    )
    row = _activity_row(a)
    assert row["est_power_avg_w"] == 244
    assert row["est_power_max_w"] == 410
    assert row["est_power_np_w"] == 250
    assert row["est_kcal_model"] == 850
    assert row["est_power_source"] == "true_pace"


def test_activity_row_power_absent(monkeypatch):
    from fitops.dashboard.routes.activities import _activity_row

    _patch_scores(monkeypatch)
    a = _make_activity_ns()
    row = _activity_row(a)
    assert row["est_power_avg_w"] is None
    assert row["est_power_max_w"] is None
    assert row["est_power_np_w"] is None
    assert row["est_kcal_model"] is None
    assert row["est_power_source"] is None
