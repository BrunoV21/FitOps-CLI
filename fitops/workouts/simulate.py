"""
fitops/workouts/simulate.py

Per-segment terrain + weather simulation for workout files.

Maps workout segments (warmup, intervals, cooldown …) onto a course's km-segments
and computes distance-weighted average grade/weather factors per workout segment,
then outputs adjusted pace targets.

Pure computation — no DB access, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fitops.analytics.weather_pace import compute_wap_factor
from fitops.race.course_parser import _fmt_duration, _fmt_pace
from fitops.race.simulation import gap_factor
from fitops.workouts.segments import WorkoutSegmentDef

# Fallback pace when no pace/base-pace provided: 6:00/km
_DEFAULT_PACE_S = 360.0


@dataclass
class WorkoutSegmentSimResult:
    """Simulation result for a single workout segment."""

    segment: WorkoutSegmentDef
    course_km_start: float  # course distance at start of this segment (m)
    course_km_end: float  # course distance at end of this segment (m)
    km_indices_covered: list[
        int
    ]  # 1-based km indices from RaceCourse.get_km_segments()

    est_distance_m: float
    avg_grade_pct: float
    avg_gap_factor: float
    avg_wap_factor: float
    avg_combined_factor: float
    elevation_gain_m: float

    flat_pace_min_s: float | None
    flat_pace_max_s: float | None
    adj_pace_min_s: float | None
    adj_pace_max_s: float | None

    est_segment_time_s: float
    pace_source: str  # "pace_range" | "base_pace" | "estimated"
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Distance / pace helpers
# ---------------------------------------------------------------------------


def estimate_segment_distance_m(
    seg: WorkoutSegmentDef,
    base_pace_s: float | None,
) -> tuple[float, str]:
    """Estimate how far this segment covers on the course.

    Returns (distance_m, pace_source).
    distance_m = 0 if duration_min is None.
    """
    if seg.duration_min is None:
        return 0.0, "estimated"

    duration_s = seg.duration_min * 60.0

    if (
        seg.target_pace_min_s_per_km is not None
        or seg.target_pace_max_s_per_km is not None
    ):
        lo = seg.target_pace_min_s_per_km
        hi = seg.target_pace_max_s_per_km
        if lo is not None and hi is not None:
            midpoint = (lo + hi) / 2.0
        elif lo is not None:
            midpoint = lo
        else:
            midpoint = hi  # type: ignore[assignment]
        distance_m = (duration_s / midpoint) * 1000.0
        return distance_m, "pace_range"

    if base_pace_s is not None:
        distance_m = (duration_s / base_pace_s) * 1000.0
        return distance_m, "base_pace"

    # Fallback: 6:00/km
    distance_m = (duration_s / _DEFAULT_PACE_S) * 1000.0
    return distance_m, "estimated"


def compute_segment_factors(
    covered_km_segs: list[dict],
    weather: dict,
) -> dict:
    """Distance-weighted average of gap/wap/combined factors for a set of km-segs.

    Returns dict with keys: avg_grade, avg_gap_factor, avg_wap_factor,
    avg_combined_factor, elevation_gain_m.
    Falls back to 1.0 factors if list is empty.
    """
    if not covered_km_segs:
        return {
            "avg_grade": 0.0,
            "avg_gap_factor": 1.0,
            "avg_wap_factor": 1.0,
            "avg_combined_factor": 1.0,
            "elevation_gain_m": 0.0,
        }

    temp_c = weather["temperature_c"]
    rh_pct = weather["humidity_pct"]
    wind_ms = weather.get("wind_speed_ms", 0.0)
    wind_dir = weather.get("wind_direction_deg", 0.0)

    total_dist = 0.0
    wsum_grade = 0.0
    wsum_gf = 0.0
    wsum_wf = 0.0
    wsum_cf = 0.0
    elev_gain = 0.0

    for km_seg in covered_km_segs:
        dist = km_seg["distance_m"]
        gf = gap_factor(km_seg["grade"])
        wf = compute_wap_factor(
            temp_c, rh_pct, wind_ms, wind_dir, km_seg.get("bearing")
        )
        cf = gf * wf

        wsum_grade += km_seg["grade"] * dist
        wsum_gf += gf * dist
        wsum_wf += wf * dist
        wsum_cf += cf * dist
        elev_gain += km_seg.get("elevation_gain_m", 0.0)
        total_dist += dist

    return {
        "avg_grade": wsum_grade / total_dist if total_dist > 0 else 0.0,
        "avg_gap_factor": wsum_gf / total_dist if total_dist > 0 else 1.0,
        "avg_wap_factor": wsum_wf / total_dist if total_dist > 0 else 1.0,
        "avg_combined_factor": wsum_cf / total_dist if total_dist > 0 else 1.0,
        "elevation_gain_m": elev_gain,
    }


# ---------------------------------------------------------------------------
# Course mapping
# ---------------------------------------------------------------------------


def map_segments_to_course(
    workout_segments: list[WorkoutSegmentDef],
    km_segments: list[dict],
    base_pace_s: float | None,
) -> list[tuple[WorkoutSegmentDef, list[dict], float, str]]:
    """Walk a distance cursor through km_segments, assigning each workout segment
    the km-segs it covers.

    Returns list of (seg, covered_km_segs, est_dist_m, pace_source).
    Segments that overflow the course end get covered_km_segs=[].
    """
    # Build cumulative end-distance lookup for fast range queries
    # Each km_seg spans [cumulative_start, cumulative_end)
    km_ends: list[float] = []
    running = 0.0
    for ks in km_segments:
        running += ks["distance_m"]
        km_ends.append(running)

    course_total_m = km_ends[-1] if km_ends else 0.0

    cursor_m = 0.0
    result = []

    for seg in workout_segments:
        est_dist_m, pace_src = estimate_segment_distance_m(seg, base_pace_s)

        if est_dist_m <= 0 or cursor_m >= course_total_m:
            result.append((seg, [], est_dist_m, pace_src))
            continue

        seg_start = cursor_m
        seg_end = min(cursor_m + est_dist_m, course_total_m)

        # Collect km_segs whose range overlaps [seg_start, seg_end)
        covered: list[dict] = []
        km_start = 0.0
        for i, ks in enumerate(km_segments):
            km_end = km_ends[i]
            if km_end <= seg_start:
                km_start = km_end
                continue
            if km_start >= seg_end:
                break
            covered.append(ks)
            km_start = km_end

        cursor_m += est_dist_m
        result.append((seg, covered, est_dist_m, pace_src))

    return result


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------


def simulate_workout_on_course(
    segments: list[WorkoutSegmentDef],
    km_segments: list[dict],
    weather: dict,
    base_pace_s: float | None = None,
) -> list[WorkoutSegmentSimResult]:
    """Orchestrate workout-on-course simulation.

    Pure computation — all errors become per-segment warnings; no exceptions raised.
    """
    mapped = map_segments_to_course(segments, km_segments, base_pace_s)

    # Build cumulative start offset for course_km_start/end reporting
    cursor_m = 0.0
    results: list[WorkoutSegmentSimResult] = []

    for seg, covered_km_segs, est_dist_m, pace_src in mapped:
        warnings: list[str] = []
        km_start = cursor_m

        # Warn: None duration
        if seg.duration_min is None:
            warnings.append("duration_min is None — distance estimated as 0 m")

        # Warn: overflowed course
        if est_dist_m > 0 and not covered_km_segs:
            warnings.append("Segment falls beyond course end — neutral factors applied")

        factors = compute_segment_factors(covered_km_segs, weather)

        combined = factors["avg_combined_factor"]

        # Flat pace bounds
        flat_min = seg.target_pace_min_s_per_km
        flat_max = seg.target_pace_max_s_per_km

        # Single-bound: mirror to both
        if flat_min is not None and flat_max is None:
            flat_max = flat_min
        if flat_max is not None and flat_min is None:
            flat_min = flat_max

        # Adjusted pace
        adj_min = flat_min * combined if flat_min is not None else None
        adj_max = flat_max * combined if flat_max is not None else None

        # Estimated segment time: use midpoint of adj pace × distance
        if est_dist_m > 0:
            if adj_min is not None and adj_max is not None:
                adj_mid = (adj_min + adj_max) / 2.0
            elif adj_min is not None:
                adj_mid = adj_min
            elif adj_max is not None:
                adj_mid = adj_max
            else:
                adj_mid = _DEFAULT_PACE_S * combined
            est_time_s = adj_mid * (est_dist_m / 1000.0)
        else:
            est_time_s = 0.0

        km_end = km_start + est_dist_m
        cursor_m += est_dist_m

        results.append(
            WorkoutSegmentSimResult(
                segment=seg,
                course_km_start=round(km_start, 1),
                course_km_end=round(km_end, 1),
                km_indices_covered=[ks["km"] for ks in covered_km_segs],
                est_distance_m=round(est_dist_m, 1),
                avg_grade_pct=round(factors["avg_grade"] * 100, 2),
                avg_gap_factor=round(factors["avg_gap_factor"], 4),
                avg_wap_factor=round(factors["avg_wap_factor"], 4),
                avg_combined_factor=round(combined, 4),
                elevation_gain_m=round(factors["elevation_gain_m"], 1),
                flat_pace_min_s=flat_min,
                flat_pace_max_s=flat_max,
                adj_pace_min_s=adj_min,
                adj_pace_max_s=adj_max,
                est_segment_time_s=round(est_time_s, 1),
                pace_source=pace_src,
                warnings=warnings,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_distance_mismatch(
    results: list[WorkoutSegmentSimResult],
    course_total_m: float,
) -> str | None:
    """Return a warning string if total estimated workout distance exceeds course
    total by more than 10%.  No warning if workout is shorter (intentional partial use).
    """
    total_est = sum(r.est_distance_m for r in results)
    if course_total_m > 0 and total_est > course_total_m * 1.10:
        over_pct = round((total_est / course_total_m - 1) * 100, 1)
        return (
            f"Estimated workout distance ({total_est / 1000:.2f} km) exceeds course "
            f"length ({course_total_m / 1000:.2f} km) by {over_pct}%. "
            "Segments beyond the course end use neutral factors."
        )
    return None


# ---------------------------------------------------------------------------
# JSON serialisation helper
# ---------------------------------------------------------------------------


def result_to_dict(r: WorkoutSegmentSimResult) -> dict:
    """Convert a WorkoutSegmentSimResult to the plan's JSON output structure."""
    seg = r.segment
    return {
        "segment_index": seg.index,
        "segment_name": seg.name,
        "step_type": seg.step_type,
        "duration_min": seg.duration_min,
        "course_portion": {
            "m_start": r.course_km_start,
            "m_end": r.course_km_end,
            "km_segments_covered": r.km_indices_covered,
        },
        "terrain": {
            "avg_grade_pct": r.avg_grade_pct,
            "gap_factor": r.avg_gap_factor,
            "elevation_gain_m": r.elevation_gain_m,
        },
        "weather_adjustment": {
            "wap_factor": r.avg_wap_factor,
        },
        "combined_factor": r.avg_combined_factor,
        "pace": {
            "flat_target_min": _fmt_pace(r.flat_pace_min_s)
            if r.flat_pace_min_s is not None
            else None,
            "flat_target_max": _fmt_pace(r.flat_pace_max_s)
            if r.flat_pace_max_s is not None
            else None,
            "adjusted_min": _fmt_pace(r.adj_pace_min_s)
            if r.adj_pace_min_s is not None
            else None,
            "adjusted_max": _fmt_pace(r.adj_pace_max_s)
            if r.adj_pace_max_s is not None
            else None,
            "pace_source": r.pace_source,
        },
        "est_distance_m": r.est_distance_m,
        "est_segment_time_s": r.est_segment_time_s,
        "est_segment_time_fmt": _fmt_duration(r.est_segment_time_s),
        "warnings": r.warnings,
    }
