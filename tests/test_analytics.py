"""Tests for analytics calculations."""
from datetime import date

from fitops.analytics.training_load import ALPHA_ATL, ALPHA_CTL, CTL_DAYS, ATL_DAYS, TrainingLoadResult, DailyLoad
from fitops.analytics.vo2max import _vdot, _mcardle, _costill, _confidence
from fitops.analytics.zones import compute_lthr_zones, compute_max_hr_zones, compute_hrr_zones, compute_zones


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
