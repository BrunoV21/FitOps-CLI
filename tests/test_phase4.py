"""Tests for Phase 4 and Phase 5 analytics functions."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from fitops.analytics.trends import _linear_regression, _trend_strength, _pace_direction, _hr_direction
from fitops.analytics.performance_metrics import _percentile, _cv
from fitops.analytics.pace_zones import compute_pace_zones, _parse_mm_ss
from fitops.analytics.vo2max import apply_age_adjustment
from fitops.analytics.zone_inference import _confidence_score
from fitops.analytics.power_curves import _max_mean


# --- _linear_regression ---

def test_linear_regression_perfect_slope():
    x = [0.0, 1.0, 2.0, 3.0]
    y = [0.0, 2.0, 4.0, 6.0]
    slope, intercept = _linear_regression(x, y)
    assert abs(slope - 2.0) < 0.001
    assert abs(intercept) < 0.001


def test_linear_regression_flat():
    x = [0.0, 1.0, 2.0]
    y = [5.0, 5.0, 5.0]
    slope, intercept = _linear_regression(x, y)
    assert abs(slope) < 0.001
    assert abs(intercept - 5.0) < 0.001


def test_linear_regression_single_point():
    slope, intercept = _linear_regression([1.0], [3.0])
    assert slope == 0.0
    assert intercept == 3.0


def test_linear_regression_negative_slope():
    x = [0.0, 1.0, 2.0, 3.0]
    y = [10.0, 7.0, 4.0, 1.0]
    slope, intercept = _linear_regression(x, y)
    assert abs(slope - (-3.0)) < 0.001


# --- _trend_strength ---

def test_trend_strength_weak():
    assert _trend_strength(0.05) == "weak"
    assert _trend_strength(-0.05) == "weak"
    assert _trend_strength(0.0) == "weak"


def test_trend_strength_moderate():
    assert _trend_strength(0.15) == "moderate"
    assert _trend_strength(-0.2) == "moderate"


def test_trend_strength_strong():
    assert _trend_strength(0.5) == "strong"
    assert _trend_strength(-1.0) == "strong"


def test_trend_strength_boundary_weak_moderate():
    # 0.1 is the weak/moderate boundary (< 0.1 is weak, >= 0.1 is moderate)
    assert _trend_strength(0.09) == "weak"
    assert _trend_strength(0.1) == "moderate"


# --- _pace_direction ---

def test_pace_direction_improving():
    # Negative slope = faster pace (lower min/km) = improving
    assert _pace_direction(-0.05) == "improving"
    assert _pace_direction(-1.0) == "improving"


def test_pace_direction_declining():
    assert _pace_direction(0.05) == "declining"
    assert _pace_direction(1.0) == "declining"


def test_pace_direction_stable():
    assert _pace_direction(0.0) == "stable"
    assert _pace_direction(0.005) == "stable"


# --- _hr_direction ---

def test_hr_direction_improving():
    # Negative slope = lower HR = improving cardiac efficiency
    assert _hr_direction(-1.0) == "improving"
    assert _hr_direction(-5.0) == "improving"


def test_hr_direction_declining():
    assert _hr_direction(1.0) == "declining"


def test_hr_direction_stable():
    assert _hr_direction(0.0) == "stable"
    assert _hr_direction(-0.3) == "stable"


# --- _percentile ---

def test_percentile_median():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _percentile(values, 50) == 3.0


def test_percentile_min():
    values = [10.0, 20.0, 30.0]
    result = _percentile(values, 0)
    assert result == 10.0


def test_percentile_max():
    values = [10.0, 20.0, 30.0]
    result = _percentile(values, 100)
    assert result == 30.0


def test_percentile_empty():
    assert _percentile([], 50) is None


def test_percentile_single():
    assert _percentile([42.0], 50) == 42.0
    assert _percentile([42.0], 99) == 42.0


def test_percentile_interpolation():
    values = [0.0, 10.0]
    result = _percentile(values, 50)
    assert result == 5.0


# --- _cv (coefficient of variation) ---

def test_cv_zero_for_identical():
    assert _cv([5.0, 5.0, 5.0]) == 0.0


def test_cv_single_value():
    assert _cv([100.0]) == 0.0


def test_cv_empty():
    assert _cv([]) == 0.0


def test_cv_positive():
    values = [100.0, 200.0, 300.0]
    result = _cv(values)
    assert result > 0.0
    assert result < 1.0


def test_cv_zero_mean():
    # mean=0 should return 0.0 without division error
    assert _cv([0.0, 0.0, 0.0]) == 0.0


# --- compute_pace_zones ---

def test_pace_zones_threshold_300s():
    """300 s/km = 5:00/km threshold."""
    result = compute_pace_zones(300)
    assert result.threshold_pace_s == 300
    assert result.threshold_pace_fmt == "5:00"
    assert len(result.zones) == 5


def test_pace_zones_zone_names():
    result = compute_pace_zones(300)
    names = [z["name"] for z in result.zones]
    assert names == ["Easy", "Aerobic", "Tempo", "Threshold", "VO2max"]


def test_pace_zones_boundaries_ordered():
    """For zones 1-4, max of zone N = min of zone N+1."""
    result = compute_pace_zones(300)
    zones = result.zones
    # Zone 1 (Easy): min_s = threshold * 1.16, max_s = None
    # Zone 5 (VO2max): min_s = None, max_s = threshold * 0.96
    # Zones 2-4 should have overlapping boundaries
    assert zones[0]["min_s_per_km"] == round(300 * 1.16)
    assert zones[0]["max_s_per_km"] is None
    assert zones[4]["min_s_per_km"] is None
    assert zones[4]["max_s_per_km"] == round(300 * 0.96)


def test_pace_zones_fmt_pace():
    result = compute_pace_zones(345)  # 5:45/km
    assert result.threshold_pace_fmt == "5:45"


def test_pace_zones_source_default():
    result = compute_pace_zones(300)
    assert result.source == "manual"


def test_pace_zones_source_custom():
    result = compute_pace_zones(300, source="inferred")
    assert result.source == "inferred"


# --- _parse_mm_ss ---

def test_parse_mm_ss_five_minutes():
    assert _parse_mm_ss("5:00") == 300


def test_parse_mm_ss_five_forty_five():
    assert _parse_mm_ss("5:45") == 345


def test_parse_mm_ss_invalid():
    with pytest.raises(ValueError):
        _parse_mm_ss("5-00")


def test_parse_mm_ss_with_whitespace():
    assert _parse_mm_ss("  4:30  ") == 270


# --- apply_age_adjustment (vo2max) ---

def test_age_adjustment_at_25_is_no_change():
    estimate, factor = apply_age_adjustment(50.0, 25)
    assert factor == 1.0
    assert estimate == 50.0


def test_age_adjustment_older_reduces_estimate():
    estimate_25, _ = apply_age_adjustment(50.0, 25)
    estimate_45, _ = apply_age_adjustment(50.0, 45)
    assert estimate_45 < estimate_25


def test_age_adjustment_factor_bounded():
    # At very old age factor should not go below VO2_AGE_FACTOR_FLOOR (0.5)
    _, factor = apply_age_adjustment(50.0, 200)
    assert factor == 0.5


def test_age_adjustment_returns_correct_factor():
    # age=35, decline = (35-25) * 0.008 = 0.08, factor = 0.92
    _, factor = apply_age_adjustment(50.0, 35)
    assert abs(factor - 0.920) < 0.001


def test_age_adjustment_younger_than_25():
    # age=20, decline = (20-25) * 0.008 = -0.04, factor = 1.04 -> capped? No floor is 0.5
    # 1 - (-0.04) = 1.04, but max() only floors at 0.5, so 1.04 is valid
    _, factor = apply_age_adjustment(50.0, 20)
    assert factor > 1.0


# --- _confidence_score (zone_inference) ---

def test_confidence_score_high_count():
    score = _confidence_score(10, 1.0, 1.0)
    assert score == 100


def test_confidence_score_low_count():
    score = _confidence_score(1, 0.0, 0.0)
    assert score == 5


def test_confidence_score_mid_count():
    score = _confidence_score(5, 0.5, 0.5)
    # 25 + round(0.5*30) + round(0.5*30) = 25 + 15 + 15 = 55
    assert score == 55


def test_confidence_score_capped_at_100():
    score = _confidence_score(15, 1.0, 1.0)
    assert score == 100


def test_confidence_score_two_activities():
    score = _confidence_score(2, 0.0, 0.0)
    assert score == 15


# --- _max_mean (power_curves) ---

def test_max_mean_simple():
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = _max_mean(data, 3)
    assert result == pytest.approx(4.0)  # best 3-window is [3,4,5] = 4.0 avg


def test_max_mean_full_window():
    data = [10.0, 10.0, 10.0]
    result = _max_mean(data, 3)
    assert result == 10.0


def test_max_mean_window_too_large():
    data = [1.0, 2.0]
    assert _max_mean(data, 5) is None


def test_max_mean_single_element_window():
    data = [3.0, 7.0, 2.0, 9.0, 1.0]
    result = _max_mean(data, 1)
    assert result == 9.0


def test_max_mean_all_zeros_returns_none():
    data = [0.0, 0.0, 0.0, 0.0]
    result = _max_mean(data, 2)
    assert result is None


# --- Athlete.age property ---

def test_athlete_age_no_birthday():
    from fitops.db.models.athlete import Athlete
    ath = Athlete()
    ath.birthday = None
    assert ath.age is None


def test_athlete_age_valid_birthday():
    from fitops.db.models.athlete import Athlete
    ath = Athlete()
    # Set birthday to 30 years ago from today
    today = date.today()
    bday = date(today.year - 30, today.month, today.day)
    ath.birthday = bday.isoformat()
    assert ath.age == 30


def test_athlete_age_before_birthday_this_year():
    from fitops.db.models.athlete import Athlete
    ath = Athlete()
    today = date.today()
    # Birthday is tomorrow (hasn't happened yet this year)
    future_day = today + timedelta(days=1)
    bday = date(today.year - 25, future_day.month, future_day.day)
    ath.birthday = bday.isoformat()
    # Should be 24, not 25
    assert ath.age == 24


def test_athlete_age_invalid_format():
    from fitops.db.models.athlete import Athlete
    ath = Athlete()
    ath.birthday = "not-a-date"
    assert ath.age is None
