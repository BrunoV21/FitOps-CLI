"""Unit tests for fitops.analytics.running_power."""
from __future__ import annotations

import pytest

from fitops.analytics.running_power import (
    DISPLAY_POWER_COST,
    JOULES_PER_KCAL,
    METABOLIC_COST,
    estimate_kcal,
    estimate_power_stream,
    pick_pace_stream,
    summarize_power,
)


# ---------------------------------------------------------------------------
# pick_pace_stream
# ---------------------------------------------------------------------------


def test_pick_pace_stream_prefers_true_pace():
    streams = {
        "true_pace": [240.0, 241.0],
        "gap_pace": [250.0, 251.0],
        "velocity_smooth": [4.0, 4.1],
    }
    source, data = pick_pace_stream(streams)
    assert source == "true_pace"
    assert data == [240.0, 241.0]


def test_pick_pace_stream_falls_back_to_gap_pace():
    streams = {"gap_pace": [250.0, 255.0], "velocity_smooth": [4.0]}
    source, data = pick_pace_stream(streams)
    assert source == "gap_pace"
    assert data == [250.0, 255.0]


def test_pick_pace_stream_converts_velocity_smooth():
    streams = {"velocity_smooth": [4.0, 5.0]}
    source, data = pick_pace_stream(streams)
    assert source == "velocity_smooth"
    # 1000 / 4.0 = 250.0 s/km
    assert data[0] == pytest.approx(250.0)
    # 1000 / 5.0 = 200.0 s/km
    assert data[1] == pytest.approx(200.0)


def test_pick_pace_stream_velocity_zero_becomes_none():
    streams = {"velocity_smooth": [0.0, 4.0]}
    _, data = pick_pace_stream(streams)
    assert data[0] is None
    assert data[1] == pytest.approx(250.0)


def test_pick_pace_stream_empty_returns_none():
    source, data = pick_pace_stream({})
    assert source == "none"
    assert data == []


def test_pick_pace_stream_empty_lists_skipped():
    streams = {"true_pace": [], "gap_pace": [240.0]}
    source, data = pick_pace_stream(streams)
    assert source == "gap_pace"


# ---------------------------------------------------------------------------
# estimate_power_stream
# ---------------------------------------------------------------------------


def test_estimate_power_flat_4min_km_70kg():
    # 4:00/km = 240 s/km → v = 1000/240 ≈ 4.167 m/s
    # displayed running power is calibrated to realistic consumer ranges
    pace = [240.0]
    result = estimate_power_stream(pace, weight_kg=70.0)
    expected = DISPLAY_POWER_COST * 70.0 * (1000.0 / 240.0)
    assert result[0] == pytest.approx(expected, rel=1e-3)
    assert 280 < result[0] < 310


def test_estimate_power_none_for_zero_pace():
    result = estimate_power_stream([None, 0.0, 240.0], weight_kg=70.0)
    assert result[0] is None
    assert result[1] is None
    assert result[2] is not None


def test_estimate_power_scales_with_weight():
    pace = [240.0]
    p60 = estimate_power_stream(pace, weight_kg=60.0)[0]
    p80 = estimate_power_stream(pace, weight_kg=80.0)[0]
    assert p80 / p60 == pytest.approx(80.0 / 60.0, rel=1e-3)


# ---------------------------------------------------------------------------
# summarize_power
# ---------------------------------------------------------------------------


def test_summarize_power_basic():
    stream = [100.0, 200.0, 300.0]
    result = summarize_power(stream)
    assert result["avg_w"] == pytest.approx(200.0)
    assert result["max_w"] == pytest.approx(300.0)
    # np_w requires 30+ samples; with 3 samples it should be None
    assert result["np_w"] is None


def test_summarize_power_excludes_none():
    stream = [None, 100.0, None, 300.0]
    result = summarize_power(stream)
    assert result["avg_w"] == pytest.approx(200.0)
    assert result["max_w"] == pytest.approx(300.0)


def test_summarize_power_all_none_returns_none_fields():
    result = summarize_power([None, None])
    assert result == {"avg_w": None, "max_w": None, "np_w": None}


def test_summarize_power_np_computed_for_long_stream():
    # 30 uniform samples → NP should equal avg
    stream = [200.0] * 30
    result = summarize_power(stream)
    assert result["np_w"] == pytest.approx(200.0, rel=1e-3)


# ---------------------------------------------------------------------------
# estimate_kcal
# ---------------------------------------------------------------------------


def test_estimate_kcal_steady_run():
    # 70 kg, 4:00/km flat, 1 hour → displayed power ~292 W, kcal remains metabolic
    pace_s_per_km = 240.0
    v_ms = 1000.0 / pace_s_per_km
    power_w = DISPLAY_POWER_COST * 70.0 * v_ms  # ≈ 292 W displayed
    duration_s = 3600
    stream = [power_w] * duration_s
    kcal = estimate_kcal(stream)
    expected = round(power_w * (METABOLIC_COST / DISPLAY_POWER_COST) * duration_s / JOULES_PER_KCAL)
    assert kcal == expected
    # sanity: should still be roughly 900 kcal for 1 hr at 4:00/km @ 70 kg
    assert 800 < kcal < 1100


def test_estimate_kcal_with_time_stream():
    power_stream = [200.0, 200.0, 200.0]
    time_stream = [0, 2, 4]  # 2 s intervals
    kcal = estimate_kcal(power_stream, time_stream)
    total_joules = 200.0 * 2 + 200.0 * 2  # first 2 samples contribute dt=2
    assert kcal == max(1, round(total_joules / JOULES_PER_KCAL))


def test_estimate_kcal_none_stream_returns_none():
    assert estimate_kcal([None, None]) is None


def test_estimate_kcal_minimum_one():
    # Tiny power × tiny time rounds to 0 → should return 1
    result = estimate_kcal([0.001], [0, 0.001])
    # Either None (dt ≤ 0) or 1
    assert result is None or result >= 1
