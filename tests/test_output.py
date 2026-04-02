"""Tests for output formatting."""

from fitops.output.formatter import (
    _fmt_pace_per_km,
    _fmt_seconds,
    format_activity_row,
    make_meta,
)


def test_fmt_seconds_with_hours():
    assert _fmt_seconds(3723) == "1:02:03"


def test_fmt_seconds_no_hours():
    assert _fmt_seconds(123) == "2:03"


def test_fmt_seconds_none():
    assert _fmt_seconds(None) is None


def test_fmt_pace_per_km():
    # 1000 / (1000/360) = 360s = exactly 6:00/km
    result = _fmt_pace_per_km(1000 / 360)
    assert result == "6:00"


def test_format_activity_row_run():
    row = {
        "strava_id": 12345,
        "name": "Morning Run",
        "sport_type": "Run",
        "start_date_local": "2026-03-10T08:00:00",
        "start_date": "2026-03-10T07:00:00+00:00",
        "timezone": "Europe/London",
        "moving_time_s": 3600,
        "elapsed_time_s": 3650,
        "distance_m": 10000.0,
        "average_speed_ms": 2.778,
        "max_speed_ms": 4.0,
        "total_elevation_gain_m": 100.0,
        "average_heartrate": 148.0,
        "max_heartrate": 170,
        "average_cadence": 174.0,
        "average_watts": None,
        "max_watts": None,
        "weighted_average_watts": None,
        "suffer_score": 42,
        "calories": 600,
        "training_stress_score": None,
        "gear_id": "s1",
        "trainer": False,
        "commute": False,
        "manual": False,
        "private": False,
        "kudos_count": 5,
        "comment_count": 1,
        "start_latlng": "[51.5, -0.1]",
        "end_latlng": None,
        "streams_fetched": False,
        "laps_fetched": False,
        "detail_fetched": False,
    }
    gear_lookup = {"s1": {"name": "Nike Pegasus", "type": "shoes"}}
    out = format_activity_row(row, gear_lookup)
    assert out["strava_activity_id"] == 12345
    assert out["sport_type"] == "Run"
    assert out["distance"]["km"] == 10.0
    assert out["pace"] is not None
    assert out["power"] is None
    assert out["equipment"]["gear_name"] == "Nike Pegasus"
    assert out["data_availability"]["has_gps"] is True
    assert out["data_availability"]["has_heart_rate"] is True


def test_make_meta():
    meta = make_meta(total_count=5, filters_applied={"sport": "Run"})
    assert meta["tool"] == "fitops-cli"
    assert meta["total_count"] == 5
    assert meta["filters_applied"]["sport"] == "Run"
