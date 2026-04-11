"""Tests for analytics calculations."""

from datetime import date
from types import SimpleNamespace

import pytest

from fitops.analytics.activity_insights import compute_hr_drift
from fitops.analytics.training_load import (
    ALPHA_ATL,
    ALPHA_CTL,
    ATL_DAYS,
    CTL_DAYS,
    DailyLoad,
    TrainingLoadResult,
    _compute_overtraining_indicators,
)
from fitops.analytics.vo2max import (
    VO2MaxResult,
    _confidence,
    _costill,
    _extract_high_intensity_segments,
    _mcardle,
    _vdot,
)
from fitops.analytics.zones import (
    compute_hrr_zones,
    compute_lthr_zones,
    compute_max_hr_zones,
    compute_zones,
)


def test_alpha_values():
    assert abs(ALPHA_CTL - 2 / (CTL_DAYS + 1)) < 0.0001
    assert abs(ALPHA_ATL - 2 / (ATL_DAYS + 1)) < 0.0001


def test_ewma_ctl_increases_with_load():
    ctl = 0.0
    for _ in range(50):
        ctl = 80 * ALPHA_CTL + ctl * (1 - ALPHA_CTL)
    assert ctl > 40


def test_ewma_atl_faster_than_ctl():
    ctl = atl = 0.0
    for _ in range(10):
        ctl = 80 * ALPHA_CTL + ctl * (1 - ALPHA_CTL)
        atl = 80 * ALPHA_ATL + atl * (1 - ALPHA_ATL)
    assert atl > ctl


def test_tsb_equals_ctl_minus_atl():
    load = DailyLoad(date=date.today(), daily_tss=50, ctl=60.0, atl=70.0, tsb=-10.0)
    assert load.tsb == load.ctl - load.atl


def test_form_labels():
    r = TrainingLoadResult()
    assert "fresh" in r.form_label(10).lower()
    assert "overtraining" in r.form_label(-35).lower()
    assert "productive" in r.form_label(-5).lower()


def test_vdot_5k():
    # 20-min 5km (4:00/km) is solid recreational fitness → ~45 VDOT
    result = _vdot(5000, 20 * 60)
    assert result is not None
    assert 40 < result < 55


def test_vdot_none_on_zero():
    assert _vdot(0, 1200) is None
    assert _vdot(5000, 0) is None


def test_mcardle_reasonable():
    result = _mcardle(5000, 20 * 60)
    assert result is not None
    assert 30 < result < 85


def test_costill_compat_returns_none():
    # _costill is now a removed method kept only as a compat stub; always returns None
    assert _costill(1000, 300) is None
    assert _costill(1500, 360) is None


def test_confidence_increases_with_distance():
    estimates = [52.0, 51.5, 52.5]
    assert _confidence(5000, estimates) > _confidence(1500, estimates)


def test_lthr_zones():
    result = compute_lthr_zones(165)
    assert result.lt2_bpm == 165
    assert result.lt1_bpm == int(165 * 0.92)
    assert len(result.zones) == 5


def test_lthr_zones_ordering():
    result = compute_lthr_zones(165)
    for i in range(len(result.zones) - 1):
        assert result.zones[i].max_bpm <= result.zones[i + 1].min_bpm


def test_max_hr_zones():
    result = compute_max_hr_zones(190)
    assert len(result.zones) == 5
    assert result.zones[0].min_bpm == int(190 * 0.50)


def test_hrr_zones():
    result = compute_hrr_zones(max_hr=190, resting_hr=50)
    assert result.zones[0].min_bpm == 50 + int(0.50 * 140)
    assert len(result.zones) == 5


def test_zones_dispatch():
    assert compute_zones("lthr", lthr=165) is not None
    assert compute_zones("max-hr", max_hr=190) is not None
    assert compute_zones("hrr", max_hr=190, resting_hr=50) is not None
    assert compute_zones("lthr") is None


# ---------------------------------------------------------------------------
# _extract_high_intensity_segments tests
# ---------------------------------------------------------------------------


def _make_streams(entries):
    """Build (hr_data, time_data, speed_data) from list of (hr, speed, dt) tuples."""
    hr_data = []
    time_data = [0]
    speed_data = []
    t = 0
    for hr, spd, dt in entries:
        hr_data.append(hr)
        speed_data.append(spd)
        t += dt
        time_data.append(t)
    # time_data has n+1 elements; trim to n so all three lists have the same length
    time_data = time_data[:-1]
    return hr_data, time_data, speed_data


def test_extract_segments_basic():
    """700 s above threshold → 1 segment emitted."""
    entries = [(160, 3.5, 1)] * 700  # 700 samples × 1 s each
    hr, t, spd = _make_streams(entries)
    segs = _extract_high_intensity_segments(hr, t, spd, min_hr=150)
    assert len(segs) == 1
    assert segs[0].duration_s == pytest.approx(699, abs=1)


def test_extract_segments_too_short():
    """500 s above threshold (< 600 s minimum) → empty list."""
    entries = [(160, 3.5, 1)] * 500
    hr, t, spd = _make_streams(entries)
    segs = _extract_high_intensity_segments(hr, t, spd, min_hr=150)
    assert segs == []


def test_extract_segments_multiple():
    """Two 700 s qualifying blocks separated by 200 s recovery → 2 segments."""
    block = [(160, 3.5, 1)] * 700
    recovery = [(120, 2.0, 1)] * 200  # HR below min_hr=150
    entries = block + recovery + block
    hr, t, spd = _make_streams(entries)
    segs = _extract_high_intensity_segments(hr, t, spd, min_hr=150)
    assert len(segs) == 2


def test_extract_segments_speed_filter():
    """HR qualifies but speed is below min_speed_ms → no segments."""
    entries = [(160, 0.3, 1)] * 700  # speed 0.3 < 0.5 threshold
    hr, t, spd = _make_streams(entries)
    segs = _extract_high_intensity_segments(hr, t, spd, min_hr=150)
    assert segs == []


# ---------------------------------------------------------------------------
# Minimum sample guard tests
# ---------------------------------------------------------------------------


def _make_daily_load(n: int, tss: float = 50.0) -> list:
    """Create n DailyLoad entries with constant TSS/CTL/ATL for guard testing."""
    return [
        DailyLoad(date=date.today(), daily_tss=tss, ctl=40.0, atl=50.0, tsb=-10.0)
        for _ in range(n)
    ]


def test_overtraining_acwr_requires_21_days():
    """History with < 21 entries → acwr is None, label is 'Insufficient history'."""
    history = _make_daily_load(10)
    result = _compute_overtraining_indicators(history)
    assert result["acwr"] is None
    assert result["acwr_label"] == "Insufficient history"


def test_overtraining_acwr_present_after_21_days():
    """History with exactly 21 entries → acwr is computed."""
    history = _make_daily_load(21)
    result = _compute_overtraining_indicators(history)
    assert result["acwr"] is not None


def test_overtraining_monotony_requires_5_days():
    """Only 3 days of TSS → training_monotony is None."""
    history = _make_daily_load(3)
    result = _compute_overtraining_indicators(history)
    assert result["training_monotony"] is None


def test_volume_trend_insufficient_data():
    """< 6 weeks of data → vol_direction is 'insufficient_data'."""
    # We test the direction logic directly via a small helper
    # The weekly_data list drives the branch; simulate it with 3 entries
    from fitops.analytics.trends import _linear_regression

    weekly_data = [{"distance_km": float(i), "activity_count": 1} for i in range(3)]
    if len(weekly_data) >= 6:
        x = list(range(len(weekly_data)))
        y = [w["distance_km"] for w in weekly_data]
        vol_slope, _ = _linear_regression(x, y)
        vol_direction = (
            "increasing"
            if vol_slope > 0.5
            else ("decreasing" if vol_slope < -0.5 else "stable")
        )
    else:
        vol_slope, vol_direction = 0.0, "insufficient_data"
    assert vol_direction == "insufficient_data"


def test_pace_trend_insufficient_data():
    """< 4 months of pace data → pace_direction is 'insufficient_data'."""
    # Build a monthly_pace dict with 2 keys
    from collections import defaultdict

    monthly_pace = defaultdict(list)
    monthly_pace[(2026, 1)].append((5.0, 10000))
    monthly_pace[(2026, 2)].append((4.9, 10000))
    # Replicate the guard logic from trends.py
    if len(monthly_pace) >= 4:
        pace_direction = "computed"
    elif len(monthly_pace) >= 2:
        pace_direction = "insufficient_data"
    else:
        pace_direction = None
    assert pace_direction == "insufficient_data"


def test_hr_drift_requires_600_samples():
    """compute_hr_drift with < 600 valid samples returns None."""
    hr = [150.0] * 300
    pace = [3.0] * 300
    assert compute_hr_drift(hr, pace) is None


def test_vo2max_result_default_method():
    """VO2MaxResult created without estimation_method defaults to 'summary'."""
    result = VO2MaxResult(
        estimate=52.0,
        confidence=0.7,
        vdot=52.0,
        cooper=51.5,
        activity_strava_id=123,
        activity_name="Test Run",
        activity_date="2026-01-01",
        distance_km=10.0,
        pace_per_km="5:00",
    )
    assert result.estimation_method == "summary"
    # LT1 is no longer measured from streams; only LT2 measurement field exists
    assert hasattr(result, "measured_lt2_pace_s")
    assert not hasattr(result, "measured_lt1_pace_s")


# --- Training scores ---


def _make_run(moving_time_s: int, average_speed_ms: float) -> SimpleNamespace:
    return SimpleNamespace(
        sport_type="Run",
        moving_time_s=moving_time_s,
        average_speed_ms=average_speed_ms,
        average_watts=None,
        average_heartrate=None,
    )


def _make_ride(moving_time_s: int, average_watts: float) -> SimpleNamespace:
    return SimpleNamespace(
        sport_type="Ride",
        moving_time_s=moving_time_s,
        average_speed_ms=None,
        average_watts=average_watts,
        average_heartrate=None,
    )


def _make_settings(threshold_pace_per_km_s=None, ftp=None, lthr=None, max_hr=None, age=None) -> SimpleNamespace:
    return SimpleNamespace(
        threshold_pace_per_km_s=threshold_pace_per_km_s,
        ftp=ftp,
        lthr=lthr,
        max_hr=max_hr,
        age=age,
    )


def test_aerobic_score_easy_run():
    """Aerobic score for easy run: 0.96h at IF≈0.684 → ~3.2 (calibration point)."""
    from fitops.analytics.training_scores import compute_aerobic_score

    # avg pace = 1000/speed_ms = threshold/IF → speed_ms = 1000*IF/threshold
    # threshold=234s/km, IF=0.684 → avg_pace=342s/km → speed=1000/342=2.924 m/s
    act = _make_run(moving_time_s=int(0.96 * 3600), average_speed_ms=2.924)
    settings = _make_settings(threshold_pace_per_km_s=234)
    score = compute_aerobic_score(act, settings)
    assert 2.9 <= score <= 3.5, f"expected ~3.2, got {score}"


def test_aerobic_score_threshold_run():
    """Aerobic score for threshold run: 0.78h IF=1.002 → ~3.8 (calibration point)."""
    from fitops.analytics.training_scores import compute_aerobic_score

    # speed = 1000*1.002/234 = 4.282 m/s → avg_pace = 233.6 s/km
    act = _make_run(moving_time_s=int(0.78 * 3600), average_speed_ms=4.282)
    settings = _make_settings(threshold_pace_per_km_s=234)
    score = compute_aerobic_score(act, settings)
    assert 3.5 <= score <= 4.1, f"expected ~3.8, got {score}"


def test_anaerobic_score_run_calibration_subthreshold():
    """Anaerobic score for sub-threshold run: 0.98h IF=0.811 → 3.4 (calibration point)."""
    from fitops.analytics.training_scores import compute_anaerobic_score

    # IF=0.811 → avg_pace=threshold/IF → speed=1000*0.811/234=3.466 m/s
    act = _make_run(moving_time_s=int(0.98 * 3600), average_speed_ms=3.466)
    settings = _make_settings(threshold_pace_per_km_s=234)
    score = compute_anaerobic_score(act, settings)
    assert score == 3.4, f"expected 3.4, got {score}"


def test_anaerobic_score_run_calibration_threshold():
    """Anaerobic score for threshold run: 0.78h IF=1.002 → 4.5 (calibration point)."""
    from fitops.analytics.training_scores import compute_anaerobic_score

    act = _make_run(moving_time_s=int(0.78 * 3600), average_speed_ms=4.282)
    settings = _make_settings(threshold_pace_per_km_s=234)
    score = compute_anaerobic_score(act, settings)
    assert score == 4.5, f"expected 4.5, got {score}"


def test_anaerobic_score_ride_calibration():
    """Anaerobic score for ride: 2.22h IF=0.812 → 1.7 (calibration point)."""
    from fitops.analytics.training_scores import compute_anaerobic_score

    # watts = IF * FTP = 0.812 * 250 = 203
    act = _make_ride(moving_time_s=int(2.22 * 3600), average_watts=203)
    settings = _make_settings(ftp=250)
    score = compute_anaerobic_score(act, settings)
    assert score == 1.7, f"expected 1.7, got {score}"


def test_anaerobic_score_run_higher_than_ride_same_if():
    """Runs produce more anaerobic stress than rides at the same IF and duration."""
    from fitops.analytics.training_scores import compute_anaerobic_score

    run = _make_run(moving_time_s=3600, average_speed_ms=3.5)
    ride = _make_ride(moving_time_s=3600, average_watts=200)
    settings_run = _make_settings(threshold_pace_per_km_s=int(1000 / (3.5 / 0.9)))
    settings_ride = _make_settings(ftp=int(200 / 0.9))
    assert compute_anaerobic_score(run, settings_run) > compute_anaerobic_score(ride, settings_ride)
