from __future__ import annotations

import pytest

# These imports will fail until plans 03 and 04 are complete — that is expected.
from fitops.race.course_parser import (
    build_km_segments,
    parse_gpx,
    parse_mapmyrun_html,
    parse_tcx,
)
from fitops.race.simulation import gap_factor, simulate_pacer_mode, simulate_splits

SAMPLE_GPX = "tests/fixtures/sample.gpx"
SAMPLE_TCX = "tests/fixtures/sample.tcx"

# Mock HTML for MapMyRun test — embeds minimal window.__STATE__ JSON
MOCK_MMR_HTML = """<script>window.__STATE__ = {"routes":{"route":{"points":[
    {"lat":51.5,"lng":-0.1,"ele":10.0,"dis":0.0},
    {"lat":51.501,"lng":-0.1,"ele":15.0,"dis":100.0}
]}}};</script>"""


def _make_flat_points(n_km: int) -> list[dict]:
    """Generate n_km * 10 flat course points (100m spacing, no elevation change)."""
    return [
        {
            "lat": 51.5 + i * 0.0009,
            "lon": -0.1,
            "elevation_m": 50.0,
            "distance_from_start_m": i * 100.0,
        }
        for i in range(n_km * 10 + 1)
    ]


def _make_hilly_points(n_km: int) -> list[dict]:
    """Generate n_km * 10 course points with alternating uphill/downhill segments.

    Elevation oscillates between 50m and 150m every km so that grade != 0 in every
    segment. This ensures gap_factor != 1.0 and combined_factor != 1.0, which means
    the scale normalisation step in simulate_splits has real work to do.
    """
    points = []
    for i in range(n_km * 10 + 1):
        km_bucket = (i * 100) // 1000
        # Alternate: even km buckets climb, odd km buckets descend
        if km_bucket % 2 == 0:
            ele = 50.0 + (i % 10) * 10.0  # rises 10m per 100m → ~10% grade
        else:
            ele = 150.0 - (i % 10) * 10.0  # falls 10m per 100m → ~-10% grade
        points.append(
            {
                "lat": 51.5 + i * 0.0009,
                "lon": -0.1,
                "elevation_m": ele,
                "distance_from_start_m": i * 100.0,
            }
        )
    return points


def test_parse_gpx():
    points = parse_gpx(SAMPLE_GPX)
    assert len(points) == 5
    assert all(
        k in points[0] for k in ("lat", "lon", "elevation_m", "distance_from_start_m")
    )
    assert points[0]["lat"] == pytest.approx(51.5, abs=0.001)


def test_parse_tcx():
    points = parse_tcx(SAMPLE_TCX)
    assert len(points) >= 3
    assert points[0]["lat"] != 0.0
    assert all(
        k in points[0] for k in ("lat", "lon", "elevation_m", "distance_from_start_m")
    )


def test_parse_mapmyrun_html():
    points = parse_mapmyrun_html(MOCK_MMR_HTML)
    assert len(points) == 2
    assert points[0]["lat"] == pytest.approx(51.5)
    assert points[0]["distance_from_start_m"] == pytest.approx(0.0)


def test_km_segments():
    points = _make_flat_points(2)
    segs = build_km_segments(points)
    assert len(segs) == 2
    assert segs[0]["km"] == 1
    assert segs[1]["km"] == 2
    for s in segs:
        assert "distance_m" in s and "grade" in s and "bearing" in s


def test_gap_factor():
    assert gap_factor(0.0) == pytest.approx(1.0, abs=0.001)
    assert gap_factor(0.10) == pytest.approx(1.22, abs=0.05)
    assert gap_factor(-0.05) < 1.0


def test_grade_clamp():
    assert gap_factor(0.50) == pytest.approx(gap_factor(0.45), abs=0.001)
    assert gap_factor(-0.50) == pytest.approx(gap_factor(-0.45), abs=0.001)


def test_even_split_total_time():
    points = _make_flat_points(5)
    segs = build_km_segments(points)
    weather = {
        "temperature_c": 15.0,
        "humidity_pct": 40.0,
        "wind_speed_ms": 0.0,
        "wind_direction_deg": 0.0,
    }
    target_s = 1500.0  # 5:00/km for 5km
    splits = simulate_splits(segs, target_s, weather, strategy="even")
    total = sum(s["segment_time_s"] for s in splits)
    assert abs(total - target_s) < 1.0


def test_even_split_total_time_hilly():
    """Exercises scale normalisation: hilly course means combined_factor != 1.0,
    so the raw_time sum != target before scaling. This test fails if the normalisation
    step is removed or broken."""
    points = _make_hilly_points(5)
    segs = build_km_segments(points)
    weather = {
        "temperature_c": 15.0,
        "humidity_pct": 40.0,
        "wind_speed_ms": 0.0,
        "wind_direction_deg": 0.0,
    }
    target_s = 1500.0
    splits = simulate_splits(segs, target_s, weather, strategy="even")
    total = sum(s["segment_time_s"] for s in splits)
    assert abs(total - target_s) < 1.0


def test_negative_split_halves():
    points = _make_flat_points(4)
    segs = build_km_segments(points)
    weather = {
        "temperature_c": 15.0,
        "humidity_pct": 40.0,
        "wind_speed_ms": 0.0,
        "wind_direction_deg": 0.0,
    }
    splits = simulate_splits(segs, 1200.0, weather, strategy="negative")
    first_half = [s["target_pace_s"] for s in splits[:2]]
    second_half = [s["target_pace_s"] for s in splits[2:]]
    assert sum(second_half) / len(second_half) < sum(first_half) / len(first_half)


def test_pacer_mode_total_time():
    points = _make_flat_points(5)
    segs = build_km_segments(points)
    weather = {
        "temperature_c": 15.0,
        "humidity_pct": 40.0,
        "wind_speed_ms": 0.0,
        "wind_direction_deg": 0.0,
    }
    target_s = 1500.0
    result = simulate_pacer_mode(
        segs, target_s, pacer_pace_s=310.0, drop_at_km=3.0, weather=weather
    )
    sit_t = result["sit_phase"]["sit_time_s"]
    push_t = sum(s["segment_time_s"] for s in result["push_phase"]["splits"])
    assert abs(sit_t + push_t - target_s) < 1.0


def test_pacer_too_slow_error():
    points = _make_flat_points(5)
    segs = build_km_segments(points)
    weather = {
        "temperature_c": 15.0,
        "humidity_pct": 40.0,
        "wind_speed_ms": 0.0,
        "wind_direction_deg": 0.0,
    }
    # Pacer at 400 s/km for 5km = 2000s total; target is only 1500s → impossible
    with pytest.raises(ValueError, match="too slow"):
        simulate_pacer_mode(
            segs, 1500.0, pacer_pace_s=400.0, drop_at_km=3.0, weather=weather
        )
