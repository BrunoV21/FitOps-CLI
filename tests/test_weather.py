"""
Tests for fitops/analytics/weather_pace.py — pure function coverage.
"""

from __future__ import annotations

from fitops.analytics.weather_pace import (
    compute_bearing,
    compute_wap_factor,
    headwind_ms,
    pace_heat_factor,
    pace_wind_factor,
    vo2max_heat_factor,
    wbgt_approx,
    wet_bulb_temp,
)

# ---------------------------------------------------------------------------
# wet_bulb_temp
# ---------------------------------------------------------------------------


def test_wet_bulb_cool_dry():
    """0°C, 50% RH → Tw < 0°C (below dry bulb)."""
    tw = wet_bulb_temp(0.0, 50.0)
    assert tw < 0.0


def test_wet_bulb_hot_humid():
    """35°C, 80% RH → Tw in range [30, 35]."""
    tw = wet_bulb_temp(35.0, 80.0)
    assert 30.0 <= tw <= 35.0


# ---------------------------------------------------------------------------
# pace_heat_factor
# ---------------------------------------------------------------------------


def test_pace_heat_factor_neutral():
    """10°C, 40% RH → WBGT < 10 → factor = 1.0"""
    wbgt = wbgt_approx(10.0, 40.0)
    assert wbgt < 10.0
    assert pace_heat_factor(10.0, 40.0) == 1.0


def test_pace_heat_factor_hot():
    """30°C, 70% RH → factor > 1.08 (>8% slower)."""
    factor = pace_heat_factor(30.0, 70.0)
    assert factor > 1.08


def test_pace_heat_factor_mild():
    """20°C, 50% RH → factor between 1.0 and 1.08."""
    factor = pace_heat_factor(20.0, 50.0)
    assert 1.0 <= factor <= 1.08


# ---------------------------------------------------------------------------
# headwind_ms
# ---------------------------------------------------------------------------


def test_headwind_pure_headwind():
    """Wind from North (0°) at 5 m/s, running North (0°) → headwind = 5 m/s."""
    hw = headwind_ms(wind_speed_ms=5.0, wind_dir_deg=0.0, course_bearing_deg=0.0)
    assert abs(hw - 5.0) < 0.01


def test_headwind_pure_tailwind():
    """Wind from South (180°) at 5 m/s, running North (0°) → headwind = -5 m/s."""
    hw = headwind_ms(wind_speed_ms=5.0, wind_dir_deg=180.0, course_bearing_deg=0.0)
    assert abs(hw - (-5.0)) < 0.01


def test_headwind_crosswind():
    """Wind from East (90°) at 5 m/s, running North (0°) → headwind ≈ 0."""
    hw = headwind_ms(wind_speed_ms=5.0, wind_dir_deg=90.0, course_bearing_deg=0.0)
    assert abs(hw) < 0.1


# ---------------------------------------------------------------------------
# pace_wind_factor
# ---------------------------------------------------------------------------


def test_pace_wind_factor_headwind():
    """2.8 m/s (~10 km/h) headwind → ~4-5% penalty (Pugh 1971 calibration)."""
    factor = pace_wind_factor(2.8)
    assert 1.03 < factor < 1.07


def test_pace_wind_factor_pugh_calibration():
    """Verify against Pugh (1971) empirical measurements."""
    # 6.4 km/h (1.78 m/s): ~4% measured; we expect 1-5%
    assert 0.01 < pace_wind_factor(1.78) - 1.0 < 0.05
    # 12.9 km/h (3.58 m/s): ~8% measured; we expect 6-10%
    assert 0.06 < pace_wind_factor(3.58) - 1.0 < 0.10
    # 19.3 km/h (5.36 m/s): ~16% measured; we expect 14-20%
    assert 0.14 < pace_wind_factor(5.36) - 1.0 < 0.20


def test_pace_wind_factor_tailwind():
    """Tailwind benefit (factor < 1.0) is smaller magnitude than equivalent headwind cost."""
    headwind_cost = pace_wind_factor(3.0)  # > 1.0
    tailwind_benefit = pace_wind_factor(-3.0)  # < 1.0
    headwind_delta = headwind_cost - 1.0
    tailwind_delta = 1.0 - tailwind_benefit
    assert tailwind_delta < headwind_delta


def test_pace_wind_factor_calm():
    """0 m/s wind → factor = 1.0."""
    assert pace_wind_factor(0.0) == 1.0


# ---------------------------------------------------------------------------
# vo2max_heat_factor
# ---------------------------------------------------------------------------


def test_vo2max_heat_factor_cool():
    """10°C, 50% RH → factor = 1.0"""
    assert vo2max_heat_factor(10.0, 50.0) == 1.0


def test_vo2max_heat_factor_hot():
    """30°C, 70% RH → factor < 0.92 (at least 8% VO2max reduction)."""
    factor = vo2max_heat_factor(30.0, 70.0)
    assert factor < 0.92


# ---------------------------------------------------------------------------
# compute_bearing
# ---------------------------------------------------------------------------


def test_compute_bearing_north():
    """Two points same longitude, lat2 > lat1 → bearing ≈ 0°."""
    bearing = compute_bearing(0.0, 0.0, 1.0, 0.0)
    assert abs(bearing) < 1.0 or abs(bearing - 360) < 1.0


def test_compute_bearing_east():
    """Two points same latitude, lon2 > lon1 → bearing ≈ 90°."""
    bearing = compute_bearing(0.0, 0.0, 0.0, 1.0)
    assert abs(bearing - 90.0) < 1.0


def test_compute_bearing_south():
    """lat2 < lat1, same lon → bearing ≈ 180°."""
    bearing = compute_bearing(1.0, 0.0, 0.0, 0.0)
    assert abs(bearing - 180.0) < 1.0


# ---------------------------------------------------------------------------
# compute_wap_factor
# ---------------------------------------------------------------------------


def test_compute_wap_factor_cold_no_wind():
    """Cold, dry, no wind → factor ≈ 1.0."""
    factor = compute_wap_factor(5.0, 40.0, 0.0, 0.0, None)
    assert abs(factor - 1.0) < 0.01


def test_compute_wap_factor_hot_headwind():
    """Hot humid conditions + headwind → factor > 1.05."""
    factor = compute_wap_factor(28.0, 75.0, 5.0, 0.0, 0.0)  # wind from N, running N
    assert factor > 1.05
