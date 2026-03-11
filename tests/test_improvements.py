"""Tests for targeted improvements: ACWR, HR drift, Daniels VDOT, workout_type."""
from __future__ import annotations

from datetime import date


# ---------------------------------------------------------------------------
# Section 1: workout_type / is_race
# ---------------------------------------------------------------------------

def test_workout_type_is_race():
    from fitops.db.models.activity import Activity

    a = Activity()
    a.workout_type = 1
    assert a.is_race is True

    a.workout_type = 0
    assert a.is_race is False


def test_workout_type_none_not_race():
    from fitops.db.models.activity import Activity

    a = Activity()
    a.workout_type = None
    assert a.is_race is False


def test_format_activity_row_is_race_flag():
    from fitops.output.formatter import format_activity_row

    row = {
        "strava_id": 1,
        "name": "Test Run",
        "sport_type": "Run",
        "start_date_local": None,
        "start_date": None,
        "timezone": None,
        "moving_time_s": 3600,
        "elapsed_time_s": 3700,
        "distance_m": 10000.0,
        "average_speed_ms": 2.78,
        "max_speed_ms": 3.5,
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
        "map_summary_polyline": None,
        "streams_fetched": False,
        "laps_fetched": False,
        "detail_fetched": False,
        "workout_type": 1,
    }
    result = format_activity_row(row)
    assert result["flags"]["is_race"] is True

    row["workout_type"] = 0
    result2 = format_activity_row(row)
    assert result2["flags"]["is_race"] is False


# ---------------------------------------------------------------------------
# Section 3: ACWR and overtraining indicators
# ---------------------------------------------------------------------------

def _make_daily_load(ctl: float, atl: float, daily_tss: float = 50.0) -> object:
    from fitops.analytics.training_load import DailyLoad
    return DailyLoad(date=date.today(), daily_tss=daily_tss, ctl=ctl, atl=atl, tsb=round(ctl - atl, 2))


def test_acwr_optimal():
    from fitops.analytics.training_load import _compute_overtraining_indicators, DailyLoad

    history = [
        DailyLoad(date=date.today(), daily_tss=50.0, ctl=50.0, atl=55.0, tsb=-5.0)
    ]
    result = _compute_overtraining_indicators(history)
    assert result["acwr"] == round(55.0 / 50.0, 2)
    assert result["acwr_label"] == "Optimal"


def test_acwr_detraining():
    from fitops.analytics.training_load import _compute_overtraining_indicators, DailyLoad

    history = [
        DailyLoad(date=date.today(), daily_tss=10.0, ctl=50.0, atl=30.0, tsb=20.0)
    ]
    result = _compute_overtraining_indicators(history)
    assert result["acwr"] == round(30.0 / 50.0, 2)
    assert result["acwr_label"] == "Detraining"


def test_acwr_danger():
    from fitops.analytics.training_load import _compute_overtraining_indicators, DailyLoad

    history = [
        DailyLoad(date=date.today(), daily_tss=200.0, ctl=40.0, atl=75.0, tsb=-35.0)
    ]
    result = _compute_overtraining_indicators(history)
    assert result["acwr_label"] == "Danger — high injury risk"


def test_acwr_zero_ctl():
    from fitops.analytics.training_load import _compute_overtraining_indicators, DailyLoad

    history = [
        DailyLoad(date=date.today(), daily_tss=0.0, ctl=0.0, atl=0.0, tsb=0.0)
    ]
    result = _compute_overtraining_indicators(history)
    assert result["acwr"] is None
    assert result["acwr_label"] == "Unknown"


def test_acwr_empty_history():
    from fitops.analytics.training_load import _compute_overtraining_indicators

    result = _compute_overtraining_indicators([])
    assert result == {}


def test_monotony_varied():
    from fitops.analytics.training_load import _compute_overtraining_indicators, DailyLoad

    # Highly varied TSS → low monotony
    history = [
        DailyLoad(date=date.today(), daily_tss=float(tss), ctl=50.0, atl=50.0, tsb=0.0)
        for tss in [0, 100, 0, 100, 0, 100, 0]
    ]
    result = _compute_overtraining_indicators(history)
    if result["training_monotony"] is not None:
        assert result["monotony_label"] == "Varied — good training diversity"


# ---------------------------------------------------------------------------
# Section 4: HR drift
# ---------------------------------------------------------------------------

def test_hr_drift_well_coupled():
    from fitops.analytics.activity_insights import compute_hr_drift

    hr = [150.0] * 100
    pace = [3.5] * 100
    result = compute_hr_drift(hr, pace)
    assert result is not None
    assert abs(result["decoupling_pct"]) < 1.0
    assert "Well coupled" in result["label"]


def test_hr_drift_fading():
    from fitops.analytics.activity_insights import compute_hr_drift

    # Rising HR with constant pace → HR:pace ratio worsens (efficiency drops)
    hr = [140.0 + i * 0.5 for i in range(100)]
    pace = [3.5] * 100
    result = compute_hr_drift(hr, pace)
    assert result is not None
    # efficiency in second half is lower (smaller pace/hr ratio)
    assert result["decoupling_pct"] < -1.0


def test_hr_drift_insufficient_data():
    from fitops.analytics.activity_insights import compute_hr_drift

    hr = [150.0] * 10
    pace = [3.5] * 10
    result = compute_hr_drift(hr, pace)
    assert result is None


def test_hr_drift_zero_hr_filtered():
    from fitops.analytics.activity_insights import compute_hr_drift

    # Some zeroes should be filtered out; if < 20 valid remain → None
    hr = [0.0] * 50 + [150.0] * 5
    pace = [3.5] * 55
    result = compute_hr_drift(hr, pace)
    assert result is None


# ---------------------------------------------------------------------------
# Section 5: Daniels VDOT + Cooper VO2max
# ---------------------------------------------------------------------------

def test_daniels_vdot_10k():
    from fitops.analytics.vo2max import _daniels_vdot

    # 10km in 40 min → reasonable VO2max range
    result = _daniels_vdot(10000, 2400)
    assert result is not None
    assert 45 <= result <= 65


def test_daniels_vdot_5k_20min():
    from fitops.analytics.vo2max import _daniels_vdot

    result = _daniels_vdot(5000, 20 * 60)
    assert result is not None
    assert 40 < result < 60


def test_daniels_vdot_too_short():
    from fitops.analytics.vo2max import _daniels_vdot

    assert _daniels_vdot(1000, 300) is None


def test_daniels_vdot_zero_time():
    from fitops.analytics.vo2max import _daniels_vdot

    assert _daniels_vdot(5000, 0) is None


def test_cooper_vo2max_reasonable():
    from fitops.analytics.vo2max import _cooper_vo2max

    result = _cooper_vo2max(5000, 20 * 60)
    assert result is not None
    assert 28 <= result <= 90


def test_vdot_backward_compat():
    """_vdot alias must still work (used by existing tests)."""
    from fitops.analytics.vo2max import _vdot

    result = _vdot(5000, 20 * 60)
    assert result is not None
    assert 30 < result < 90


def test_mcardle_backward_compat():
    """_mcardle alias (now Cooper) must still return a valid value for valid input."""
    from fitops.analytics.vo2max import _mcardle

    result = _mcardle(5000, 20 * 60)
    assert result is not None
    assert 30 < result < 85


# ---------------------------------------------------------------------------
# Section 2: TSS smoke test (no DB)
# ---------------------------------------------------------------------------

def test_tss_uses_threshold_pace():
    """Smoke test: TSS does not crash without athlete settings configured."""
    from fitops.analytics.training_load import _estimate_tss
    from fitops.db.models.activity import Activity

    a = Activity()
    a.sport_type = "Run"
    a.moving_time_s = 3600
    a.average_speed_ms = 3.5
    a.average_heartrate = None

    # Should not raise; returns a float
    result = _estimate_tss(a)
    assert isinstance(result, float)
    assert result > 0


def test_tss_cycling_fallback():
    from fitops.analytics.training_load import _estimate_tss
    from fitops.db.models.activity import Activity

    a = Activity()
    a.sport_type = "Ride"
    a.moving_time_s = 7200
    a.average_watts = 200.0
    a.average_speed_ms = None
    a.average_heartrate = None

    result = _estimate_tss(a)
    assert isinstance(result, float)
    assert result > 0


def test_tss_hr_fallback():
    from fitops.analytics.training_load import _estimate_tss
    from fitops.db.models.activity import Activity

    a = Activity()
    a.sport_type = "Swim"
    a.moving_time_s = 3600
    a.average_speed_ms = None
    a.average_watts = None
    a.average_heartrate = 150.0

    result = _estimate_tss(a)
    assert isinstance(result, float)
    assert result > 0


def test_tss_no_data_fallback():
    from fitops.analytics.training_load import _estimate_tss
    from fitops.db.models.activity import Activity

    a = Activity()
    a.sport_type = "Hike"
    a.moving_time_s = 3600
    a.average_speed_ms = None
    a.average_watts = None
    a.average_heartrate = None

    result = _estimate_tss(a)
    assert result == 50.0  # duration_h * 50
