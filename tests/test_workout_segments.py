"""Tests for Phase 3.2 — workout segment parsing and compliance scoring."""

from __future__ import annotations

from fitops.analytics.zones import compute_lthr_zones
from fitops.workouts.compliance import (
    _classify_hr_to_zone,
    _score_segment,
    compute_compliance,
    overall_compliance_score,
)
from fitops.workouts.segments import (
    WorkoutSegmentDef,
    _extract_duration_min,
    _extract_target_zone,
    _infer_step_type,
    parse_segments_from_body,
)

# ---------------------------------------------------------------------------
# Segment parser — step type inference
# ---------------------------------------------------------------------------


def test_step_type_warmup():
    assert _infer_step_type("Warmup") == "warmup"
    assert _infer_step_type("warm up") == "warmup"


def test_step_type_cooldown():
    assert _infer_step_type("Cooldown") == "cooldown"
    assert _infer_step_type("Cool Down") == "cooldown"


def test_step_type_recovery():
    assert _infer_step_type("Recovery Jog") == "recovery"
    assert _infer_step_type("Rest") == "recovery"


def test_step_type_interval():
    assert _infer_step_type("Main Set") == "interval"
    assert _infer_step_type("Threshold Intervals") == "interval"
    assert _infer_step_type("Hard Effort") == "interval"


def test_step_type_main_fallback():
    assert _infer_step_type("Steady State") == "main"


# ---------------------------------------------------------------------------
# Segment parser — zone extraction
# ---------------------------------------------------------------------------


def test_extract_zone_single():
    assert _extract_target_zone("Hold Z4 pace") == 4
    assert _extract_target_zone("Zone 3 effort") == 3
    assert _extract_target_zone("z2 easy") == 2


def test_extract_zone_range_takes_upper():
    assert _extract_target_zone("Z1–Z2") == 2
    assert _extract_target_zone("Z3-Z4") == 4
    assert _extract_target_zone("Zone 2 - Zone 3") == 3


def test_extract_zone_none():
    assert _extract_target_zone("Run at comfortable pace") is None


# ---------------------------------------------------------------------------
# Segment parser — duration extraction
# ---------------------------------------------------------------------------


def test_extract_duration_simple():
    assert _extract_duration_min("10 min easy") == 10.0
    assert _extract_duration_min("30 minutes") == 30.0
    assert _extract_duration_min("8 min @ Z4") == 8.0


def test_extract_duration_multiplied():
    assert _extract_duration_min("4 × 8 min") == 32.0
    assert _extract_duration_min("4x8 min") == 32.0
    assert _extract_duration_min("3 × 10 min") == 30.0


def test_extract_duration_none():
    assert _extract_duration_min("Hold Z4 pace") is None


# ---------------------------------------------------------------------------
# Segment parser — parse_segments_from_body
# ---------------------------------------------------------------------------

SAMPLE_BODY = """
## Warmup
10 min easy (Z1–Z2)

## Main Set
4 × 8 min @ Z4

## Recovery
2 min Z1 jog

## Cooldown
8 min easy Z1
"""


def test_parse_segments_count():
    segs = parse_segments_from_body(SAMPLE_BODY)
    assert len(segs) == 4


def test_parse_segments_names():
    segs = parse_segments_from_body(SAMPLE_BODY)
    assert segs[0].name == "Warmup"
    assert segs[1].name == "Main Set"
    assert segs[2].name == "Recovery"
    assert segs[3].name == "Cooldown"


def test_parse_segments_step_types():
    segs = parse_segments_from_body(SAMPLE_BODY)
    assert segs[0].step_type == "warmup"
    assert segs[1].step_type == "interval"
    assert segs[2].step_type == "recovery"
    assert segs[3].step_type == "cooldown"


def test_parse_segments_zones():
    segs = parse_segments_from_body(SAMPLE_BODY)
    assert segs[0].target_zone == 2  # Z1-Z2 → upper = 2
    assert segs[1].target_zone == 4  # Z4
    assert segs[2].target_zone == 1  # Z1
    assert segs[3].target_zone == 1  # Z1


def test_parse_segments_durations():
    segs = parse_segments_from_body(SAMPLE_BODY)
    assert segs[0].duration_min == 10.0
    assert segs[1].duration_min == 32.0  # 4 × 8 min
    assert segs[2].duration_min == 2.0
    assert segs[3].duration_min == 8.0


def test_parse_segments_indices():
    segs = parse_segments_from_body(SAMPLE_BODY)
    for i, seg in enumerate(segs):
        assert seg.index == i


def test_parse_segments_empty_body():
    segs = parse_segments_from_body("No headings here.\nJust text.")
    assert segs == []


def test_parse_segments_no_zones_or_durations():
    body = "## Free Run\nJust run however you feel."
    segs = parse_segments_from_body(body)
    assert len(segs) == 1
    assert segs[0].name == "Free Run"
    assert segs[0].target_zone is None
    assert segs[0].duration_min is None


# ---------------------------------------------------------------------------
# Compliance scoring — zone classification
# ---------------------------------------------------------------------------


def test_classify_hr_to_zone():
    zones = compute_lthr_zones(165)  # lthr=165
    # Z1 max = 140 (85% of 165), Z2 max = 152 (92%), Z3 max = 165 (100%)
    assert _classify_hr_to_zone(120.0, zones) == 1
    assert _classify_hr_to_zone(145.0, zones) == 2
    assert _classify_hr_to_zone(158.0, zones) == 3
    assert _classify_hr_to_zone(167.0, zones) == 4
    assert _classify_hr_to_zone(180.0, zones) == 5


def test_classify_hr_below_all_zones():
    zones = compute_lthr_zones(165)
    assert _classify_hr_to_zone(50.0, zones) == 1


# ---------------------------------------------------------------------------
# Compliance scoring — _score_segment
# ---------------------------------------------------------------------------


def _make_seg(
    index=0, name="Main Set", step_type="interval", target_zone=4, duration_min=8.0
):
    return WorkoutSegmentDef(
        index=index,
        name=name,
        step_type=step_type,
        target_zone=target_zone,
        duration_min=duration_min,
    )


def test_score_segment_no_hr_data():
    zones = compute_lthr_zones(165)
    seg = _make_seg(target_zone=4)
    result = _score_segment(seg, {}, 0, 100, zones)
    assert result.has_heartrate is False
    assert result.compliance_score == 0.0
    assert result.avg_heartrate is None


def test_score_segment_no_zones():
    seg = _make_seg(target_zone=4)
    hr = [165.0] * 100
    result = _score_segment(seg, {"heartrate": hr}, 0, 100, None)
    # HR data exists but zones are required to compute compliance
    assert result.has_heartrate is True
    assert result.avg_heartrate is None  # cannot classify without zones
    assert result.compliance_score == 0.0


def test_score_segment_perfect_compliance():
    zones = compute_lthr_zones(165)
    # Z4 for lthr=165: 165–175 BPM
    seg = _make_seg(target_zone=4)
    hr = [168.0] * 480  # all solidly in Z4
    result = _score_segment(seg, {"heartrate": hr}, 0, 480, zones)
    assert result.has_heartrate is True
    assert result.target_achieved is True
    assert result.time_in_target_pct > 0.9
    assert result.compliance_score > 0.8


def test_score_segment_all_below_target():
    zones = compute_lthr_zones(165)
    seg = _make_seg(target_zone=4)
    hr = [130.0] * 480  # all in Z2 when target is Z4
    result = _score_segment(seg, {"heartrate": hr}, 0, 480, zones)
    assert result.target_achieved is False
    assert result.time_below_pct > 0.9
    assert result.deviation_pct < 0


def test_score_segment_no_target_zone():
    zones = compute_lthr_zones(165)
    seg = WorkoutSegmentDef(
        index=0, name="Free Run", step_type="main", target_zone=None, duration_min=10.0
    )
    hr = [145.0] * 300
    result = _score_segment(seg, {"heartrate": hr}, 0, 300, zones)
    # No target → cannot fail
    assert result.compliance_score == 1.0
    assert result.avg_heartrate is not None


def test_score_segment_zone_distribution_sums_to_one():
    zones = compute_lthr_zones(165)
    seg = _make_seg(target_zone=3)
    # Mix of zones
    hr = [130.0] * 100 + [155.0] * 100 + [170.0] * 100
    result = _score_segment(seg, {"heartrate": hr}, 0, 300, zones)
    total = sum(result.hr_zone_distribution.values())
    assert abs(total - 1.0) < 0.01


# ---------------------------------------------------------------------------
# Compliance scoring — compute_compliance
# ---------------------------------------------------------------------------


def test_compute_compliance_proportional_slicing():
    zones = compute_lthr_zones(165)
    segs = parse_segments_from_body(SAMPLE_BODY)  # 10+32+2+8 = 52 min planned
    # 52 min = 3120s of HR data
    hr = [130.0] * 600 + [168.0] * 1920 + [120.0] * 120 + [125.0] * 480
    results = compute_compliance(segs, {"heartrate": hr}, 3120, zones)
    assert len(results) == 4


def test_compute_compliance_even_split_when_no_durations():
    zones = compute_lthr_zones(165)
    segs = [
        WorkoutSegmentDef(0, "Part A", "main", 3, None),
        WorkoutSegmentDef(1, "Part B", "main", 4, None),
    ]
    hr = [150.0] * 200 + [168.0] * 200
    results = compute_compliance(segs, {"heartrate": hr}, 400, zones)
    assert len(results) == 2
    # Even split: each gets 200 samples
    assert results[0].end_index == 200
    assert results[1].end_index == 400


def test_compute_compliance_empty_hr_stream():
    zones = compute_lthr_zones(165)
    segs = parse_segments_from_body(SAMPLE_BODY)
    results = compute_compliance(segs, {}, 3000, zones)
    for r in results:
        assert r.has_heartrate is False


# ---------------------------------------------------------------------------
# Overall compliance score
# ---------------------------------------------------------------------------


def test_overall_compliance_no_scored_segments():
    segs = [
        WorkoutSegmentDef(0, "Free", "main", None, 10.0),
    ]
    results = compute_compliance(segs, {}, 600, None)
    assert overall_compliance_score(results) is None


def test_overall_compliance_weighted_average():
    zones = compute_lthr_zones(165)
    # Segment 1: 600s, perfect Z4 compliance
    # Segment 2: 600s, all Z2 when targeting Z4 → low compliance
    segs = [
        WorkoutSegmentDef(0, "Good", "interval", 4, 10.0),
        WorkoutSegmentDef(1, "Bad", "interval", 4, 10.0),
    ]
    hr_good = [168.0] * 600
    hr_bad = [130.0] * 600
    hr = hr_good + hr_bad

    results = compute_compliance(segs, {"heartrate": hr}, 1200, zones)
    overall = overall_compliance_score(results)
    assert overall is not None
    # Good segment pulls score up, bad pulls down → somewhere in middle
    assert 0.0 < overall < 1.0
