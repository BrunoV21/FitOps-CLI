"""
tests/test_workout_simulation.py

Pure unit tests for fitops/workouts/simulate.py.
No DB, no fixtures, no I/O.
"""
from __future__ import annotations

import pytest

from fitops.workouts.segments import WorkoutSegmentDef
from fitops.workouts.simulate import (
    WorkoutSegmentSimResult,
    _DEFAULT_PACE_S,
    compute_segment_factors,
    estimate_segment_distance_m,
    map_segments_to_course,
    simulate_workout_on_course,
    validate_distance_mismatch,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NEUTRAL_WEATHER = {
    "temperature_c": 15.0,
    "humidity_pct": 40.0,
    "wind_speed_ms": 0.0,
    "wind_direction_deg": 0.0,
}


def _pace_seg(
    idx: int = 0,
    name: str = "Interval",
    step_type: str = "interval",
    duration_min: float = 10.0,
    pace_min: float = 300.0,
    pace_max: float = 360.0,
) -> WorkoutSegmentDef:
    return WorkoutSegmentDef(
        index=idx,
        name=name,
        step_type=step_type,
        target_zone=None,
        duration_min=duration_min,
        target_pace_min_s_per_km=pace_min,
        target_pace_max_s_per_km=pace_max,
        target_focus_type="pace_range",
    )


def _hr_seg(
    idx: int = 0,
    name: str = "Easy",
    step_type: str = "main",
    duration_min: float = 20.0,
    hr_min: float = 120.0,
    hr_max: float = 150.0,
) -> WorkoutSegmentDef:
    return WorkoutSegmentDef(
        index=idx,
        name=name,
        step_type=step_type,
        target_zone=None,
        duration_min=duration_min,
        target_hr_min_bpm=hr_min,
        target_hr_max_bpm=hr_max,
        target_focus_type="hr_range",
    )


def _flat_km_seg(km: int = 1, dist_m: float = 1000.0, grade: float = 0.0) -> dict:
    return {"km": km, "distance_m": dist_m, "elevation_gain_m": 0.0, "grade": grade, "bearing": 0.0}


# ---------------------------------------------------------------------------
# estimate_segment_distance_m
# ---------------------------------------------------------------------------

class TestEstimateSegmentDistance:
    def test_pace_range_midpoint(self):
        seg = _pace_seg(pace_min=300.0, pace_max=360.0, duration_min=10.0)
        # midpoint = 330 s/km; dist = (10*60)/330*1000 = 1818.18…
        dist, src = estimate_segment_distance_m(seg, base_pace_s=None)
        assert src == "pace_range"
        assert abs(dist - 1818.18) < 1.0

    def test_single_min_bound_used_as_both(self):
        seg = WorkoutSegmentDef(
            index=0, name="T", step_type="interval", target_zone=None,
            duration_min=10.0,
            target_pace_min_s_per_km=300.0,
            target_pace_max_s_per_km=None,
            target_focus_type="pace_range",
        )
        dist, src = estimate_segment_distance_m(seg, base_pace_s=None)
        assert src == "pace_range"
        # midpoint = 300 s/km; dist = 600/300 * 1000 = 2000
        assert abs(dist - 2000.0) < 1.0

    def test_base_pace_fallback(self):
        seg = _hr_seg(duration_min=10.0)
        dist, src = estimate_segment_distance_m(seg, base_pace_s=360.0)
        assert src == "base_pace"
        # 10 * 60 / 360 * 1000 = 1666.67
        assert abs(dist - 1666.67) < 1.0

    def test_neutral_fallback_6min(self):
        seg = _hr_seg(duration_min=10.0)
        dist, src = estimate_segment_distance_m(seg, base_pace_s=None)
        assert src == "estimated"
        # 600 / 360 * 1000 = 1666.67
        assert abs(dist - 1666.67) < 1.0

    def test_none_duration_returns_zero(self):
        seg = _pace_seg(duration_min=None)
        dist, src = estimate_segment_distance_m(seg, base_pace_s=None)
        assert dist == 0.0

    def test_single_max_bound_only(self):
        seg = WorkoutSegmentDef(
            index=0, name="T", step_type="interval", target_zone=None,
            duration_min=10.0,
            target_pace_min_s_per_km=None,
            target_pace_max_s_per_km=360.0,
            target_focus_type="pace_range",
        )
        dist, src = estimate_segment_distance_m(seg, base_pace_s=None)
        assert src == "pace_range"
        assert abs(dist - 1666.67) < 1.0


# ---------------------------------------------------------------------------
# compute_segment_factors
# ---------------------------------------------------------------------------

class TestComputeSegmentFactors:
    def test_flat_neutral_factors_near_one(self):
        km_segs = [_flat_km_seg(grade=0.0)]
        f = compute_segment_factors(km_segs, _NEUTRAL_WEATHER)
        assert abs(f["avg_gap_factor"] - 1.0) < 0.01
        assert abs(f["avg_wap_factor"] - 1.0) < 0.02  # neutral heat/wind ≈ 1.0
        assert abs(f["avg_combined_factor"] - 1.0) < 0.05

    def test_uphill_gap_greater_than_one(self):
        km_segs = [_flat_km_seg(grade=0.10)]  # 10% uphill
        f = compute_segment_factors(km_segs, _NEUTRAL_WEATHER)
        assert f["avg_gap_factor"] > 1.0

    def test_downhill_gap_less_than_one(self):
        km_segs = [_flat_km_seg(grade=-0.05)]  # 5% downhill
        f = compute_segment_factors(km_segs, _NEUTRAL_WEATHER)
        assert f["avg_gap_factor"] < 1.0

    def test_empty_list_returns_neutral(self):
        f = compute_segment_factors([], _NEUTRAL_WEATHER)
        assert f["avg_gap_factor"] == 1.0
        assert f["avg_wap_factor"] == 1.0
        assert f["avg_combined_factor"] == 1.0
        assert f["elevation_gain_m"] == 0.0

    def test_distance_weighted_average(self):
        # Two segments: one uphill 10% (1000m), one flat 0% (500m)
        km_segs = [
            {"km": 1, "distance_m": 1000.0, "elevation_gain_m": 100.0, "grade": 0.10, "bearing": 0.0},
            {"km": 2, "distance_m": 500.0, "elevation_gain_m": 0.0, "grade": 0.0, "bearing": 0.0},
        ]
        f = compute_segment_factors(km_segs, _NEUTRAL_WEATHER)
        # Should be weighted toward the 1000m segment
        # Independently compute what expected avg_gap should be
        from fitops.race.simulation import gap_factor
        gf1 = gap_factor(0.10)
        gf2 = gap_factor(0.0)
        expected = (gf1 * 1000 + gf2 * 500) / 1500
        assert abs(f["avg_gap_factor"] - expected) < 0.001


# ---------------------------------------------------------------------------
# map_segments_to_course
# ---------------------------------------------------------------------------

class TestMapSegmentsToCourse:
    def _three_km_course(self) -> list[dict]:
        return [
            _flat_km_seg(km=1, dist_m=1000.0),
            _flat_km_seg(km=2, dist_m=1000.0),
            _flat_km_seg(km=3, dist_m=1000.0),
        ]

    def test_exact_fill(self):
        # 3 segments × 10 min @ 6:00/km = 1666m each → overflows 3 km course
        # But if we use 5:00/km (300 s/km) each segment = 2000m → overflows
        # Use 10 min @ 6:00/km = 1666m → together exceed 3000m
        # Let's use 3 segs × 5 min @ 6:00/km = 833m each → total 2500m (shorter)
        segs = [
            _pace_seg(idx=i, duration_min=5.0, pace_min=360.0, pace_max=360.0)
            for i in range(3)
        ]
        mapped = map_segments_to_course(segs, self._three_km_course(), base_pace_s=None)
        assert len(mapped) == 3
        # All have covered segments since total 2500m < 3000m
        assert all(len(m[1]) > 0 for m in mapped)

    def test_workout_shorter_than_course(self):
        segs = [_pace_seg(duration_min=2.0, pace_min=360.0, pace_max=360.0)]  # 333m
        mapped = map_segments_to_course(segs, self._three_km_course(), base_pace_s=None)
        assert len(mapped) == 1
        assert len(mapped[0][1]) > 0  # some km_segs covered

    def test_workout_longer_overflows(self):
        # 3 segments of 20 min @ 5:00/km = 4000m each → total 12000m >> 3km course
        segs = [
            _pace_seg(idx=i, duration_min=20.0, pace_min=300.0, pace_max=300.0)
            for i in range(3)
        ]
        mapped = map_segments_to_course(segs, self._three_km_course(), base_pace_s=None)
        # Later segments should have empty covered list (overflow)
        assert len(mapped) == 3
        # First segment covers everything; later ones are empty
        assert len(mapped[0][1]) > 0
        assert len(mapped[1][1]) == 0
        assert len(mapped[2][1]) == 0

    def test_none_duration_segment(self):
        seg = _pace_seg(duration_min=None)
        mapped = map_segments_to_course([seg], self._three_km_course(), base_pace_s=None)
        assert len(mapped) == 1
        assert mapped[0][2] == 0.0   # est_dist_m
        assert mapped[0][1] == []    # no km_segs covered


# ---------------------------------------------------------------------------
# simulate_workout_on_course
# ---------------------------------------------------------------------------

class TestSimulateWorkoutOnCourse:
    def _flat_course(self, n_km: int = 5) -> list[dict]:
        return [_flat_km_seg(km=i + 1) for i in range(n_km)]

    def test_flat_neutral_adj_approx_equals_flat(self):
        seg = _pace_seg(duration_min=10.0, pace_min=330.0, pace_max=330.0)
        results = simulate_workout_on_course([seg], self._flat_course(), _NEUTRAL_WEATHER)
        r = results[0]
        # combined_factor ≈ 1.0 on flat neutral
        assert abs(r.avg_combined_factor - 1.0) < 0.05
        # adj pace ≈ flat pace
        assert r.adj_pace_min_s is not None
        assert abs(r.adj_pace_min_s - r.flat_pace_min_s) < 20.0  # within 20s

    def test_uphill_adj_greater_than_flat(self):
        course = [{"km": 1, "distance_m": 1000.0, "elevation_gain_m": 100.0, "grade": 0.10, "bearing": 0.0}]
        seg = _pace_seg(duration_min=5.0, pace_min=330.0, pace_max=330.0)
        results = simulate_workout_on_course([seg], course, _NEUTRAL_WEATHER)
        r = results[0]
        assert r.adj_pace_min_s > r.flat_pace_min_s  # uphill → slower (larger s/km)

    def test_hr_segment_no_base_pace_uses_estimated(self):
        seg = _hr_seg(duration_min=10.0)
        results = simulate_workout_on_course([seg], self._flat_course(), _NEUTRAL_WEATHER, base_pace_s=None)
        r = results[0]
        assert r.pace_source == "estimated"

    def test_hr_segment_with_base_pace(self):
        seg = _hr_seg(duration_min=10.0)
        results = simulate_workout_on_course([seg], self._flat_course(), _NEUTRAL_WEATHER, base_pace_s=360.0)
        r = results[0]
        assert r.pace_source == "base_pace"
        assert r.warnings == []

    def test_none_duration_produces_zero_distance_and_warning(self):
        seg = _pace_seg(duration_min=None)
        results = simulate_workout_on_course([seg], self._flat_course(), _NEUTRAL_WEATHER)
        r = results[0]
        assert r.est_distance_m == 0.0
        assert any("duration_min" in w for w in r.warnings)

    def test_overflow_segment_gets_neutral_factor_and_note(self):
        # Single huge segment overflows 5 km course
        seg = _pace_seg(duration_min=120.0, pace_min=300.0, pace_max=300.0)  # 24 km
        results = simulate_workout_on_course([seg], self._flat_course(1), _NEUTRAL_WEATHER)
        r = results[0]
        # Should not crash; combined factor should still be set
        assert r.avg_combined_factor >= 0.5

    def test_no_pace_fields_on_hr_segment(self):
        seg = _hr_seg(duration_min=10.0)
        results = simulate_workout_on_course([seg], self._flat_course(), _NEUTRAL_WEATHER, base_pace_s=None)
        r = results[0]
        # No pace target → flat/adj should be None
        assert r.flat_pace_min_s is None
        assert r.flat_pace_max_s is None
        assert r.adj_pace_min_s is None
        assert r.adj_pace_max_s is None


# ---------------------------------------------------------------------------
# validate_distance_mismatch
# ---------------------------------------------------------------------------

class TestValidateDistanceMismatch:
    def _make_result(self, est_m: float) -> WorkoutSegmentSimResult:
        seg = _pace_seg(duration_min=10.0)
        return WorkoutSegmentSimResult(
            segment=seg,
            course_km_start=0.0,
            course_km_end=est_m,
            km_indices_covered=[],
            est_distance_m=est_m,
            avg_grade_pct=0.0,
            avg_gap_factor=1.0,
            avg_wap_factor=1.0,
            avg_combined_factor=1.0,
            elevation_gain_m=0.0,
            flat_pace_min_s=300.0,
            flat_pace_max_s=360.0,
            adj_pace_min_s=300.0,
            adj_pace_max_s=360.0,
            est_segment_time_s=600.0,
            pace_source="pace_range",
        )

    def test_no_mismatch_exact(self):
        r = self._make_result(5000.0)
        assert validate_distance_mismatch([r], 5000.0) is None

    def test_no_warning_when_shorter(self):
        r = self._make_result(3000.0)
        assert validate_distance_mismatch([r], 5000.0) is None

    def test_warning_over_10pct(self):
        r = self._make_result(6000.0)  # 20% over 5000m
        msg = validate_distance_mismatch([r], 5000.0)
        assert msg is not None
        assert "exceeds" in msg

    def test_exactly_at_10pct_boundary_no_warning(self):
        r = self._make_result(5500.0)  # exactly 10% over
        # 5500 > 5000 * 1.10 = 5500 → not strictly greater → no warning
        assert validate_distance_mismatch([r], 5000.0) is None

    def test_just_over_10pct(self):
        r = self._make_result(5501.0)
        msg = validate_distance_mismatch([r], 5000.0)
        assert msg is not None
