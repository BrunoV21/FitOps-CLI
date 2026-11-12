"""Cross-runtime formula references shared with FitOps Mobile's Jest tests.

The fixtures intentionally exercise calibrated formula paths. Mobile does not
inherit desktop's missing-input defaults or its clipping of VO2max estimates.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fitops.analytics.training_load import _estimate_tss
from fitops.analytics.vo2max import _daniels_vdot
from fitops.analytics.zones import compute_zones
from fitops.db.models.activity import Activity

REFERENCE = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "mobile/contracts/fixtures/metric-reference.json"
    ).read_text()
)


@pytest.mark.parametrize("reference", REFERENCE["zone_cases"], ids=lambda r: r["name"])
def test_mobile_zone_reference_matches_desktop(reference):
    calibration = reference["calibration"]
    result = compute_zones(
        method=calibration["method"],
        lthr=calibration["lthr_bpm"],
        max_hr=calibration["max_hr_bpm"],
        resting_hr=calibration["resting_hr_bpm"],
    )
    assert result is not None
    assert [zone.min_bpm for zone in result.zones] == reference["lower_bpm"]


@pytest.mark.parametrize("reference", REFERENCE["daniels_cases"])
def test_mobile_daniels_reference_matches_desktop(reference):
    result = _daniels_vdot(reference["distance_m"], reference["duration_seconds"])
    assert result is not None
    assert round(result, 1) == reference["expected_ml_per_kg_min"]


@pytest.mark.parametrize(
    "reference", REFERENCE["stress_cases"], ids=lambda r: r["name"]
)
def test_mobile_calibrated_stress_reference_matches_desktop(reference, monkeypatch):
    pace = reference["threshold_pace_seconds_per_km"]
    monkeypatch.setattr(
        "fitops.analytics.athlete_settings.get_athlete_settings",
        lambda: SimpleNamespace(
            ftp=None,
            threshold_pace_per_km_s=pace,
            lthr=170,
            max_hr=None,
            age=None,
        ),
    )
    activity = Activity(
        sport_type="Run",
        moving_time_s=reference["duration_seconds"],
        average_heartrate=reference["heartrate_bpm"],
        # Running HR cases deliberately select desktop's calibrated HR branch.
        average_speed_ms=(
            reference["distance_m"] / reference["duration_seconds"]
            if pace is not None
            else None
        ),
    )
    assert _estimate_tss(activity) == reference["expected_tss"]
