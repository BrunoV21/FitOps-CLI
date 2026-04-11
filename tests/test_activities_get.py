"""Tests for enriched `fitops activities get` output fields.

Covers:
- activity_splits: compute_km_splits, compute_avg_gap
- training_scores: aerobic_label, anaerobic_label
- weather_pace: weather_row_to_dict
- formatter: elapsed_time_s, efficiency_pct, description, device_name
"""

from __future__ import annotations

from types import SimpleNamespace

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
