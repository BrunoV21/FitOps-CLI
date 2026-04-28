from __future__ import annotations

from dataclasses import dataclass, field

from fitops.analytics.zones import ZoneResult
from fitops.workouts.segments import WorkoutSegmentDef


@dataclass
class SegmentCompliance:
    """Compliance result for one workout segment."""

    segment: WorkoutSegmentDef
    start_index: int
    end_index: int
    duration_actual_s: int

    # HR actuals
    avg_heartrate: float | None
    actual_zone: int | None
    hr_zone_distribution: dict[str, float] = field(default_factory=dict)

    # Pace / speed actuals
    avg_pace_per_km: float | None = None  # seconds per km
    avg_speed_ms: float | None = None
    avg_cadence: float | None = None  # spm (already doubled for runs)
    avg_gap_per_km: float | None = None  # grade-adjusted pace, s/km
    distance_actual_m: float | None = None  # meters covered in this segment

    # Compliance metrics
    target_achieved: bool = False
    deviation_pct: float = 0.0  # positive = above target, negative = below
    time_in_target_pct: float = 0.0
    time_above_pct: float = 0.0
    time_below_pct: float = 0.0
    compliance_score: float = 0.0  # 0.0–1.0

    # Data quality
    has_heartrate: bool = False
    has_pace: bool = False
    data_completeness: float = 0.0  # fraction of slice with valid readings


# ---------------------------------------------------------------------------
# Actuals helpers (shared across all scorers)
# ---------------------------------------------------------------------------


def _compute_actuals(
    streams: dict[str, list],
    start_idx: int,
    end_idx: int,
    is_run: bool = True,
) -> dict:
    """Compute pace/speed/cadence/GAP/distance actuals for a stream slice."""
    vel = streams.get("velocity_smooth", [])
    cad = streams.get("cadence", [])
    gas = streams.get("grade_adjusted_speed", [])
    grade = streams.get("grade_smooth", [])
    dist = streams.get("distance", [])

    vel_slice = [v for v in vel[start_idx:end_idx] if v and v > 0.1] if vel else []
    cad_slice = [c for c in cad[start_idx:end_idx] if c and c > 0] if cad else []

    avg_speed = round(sum(vel_slice) / len(vel_slice), 3) if vel_slice else None
    avg_pace = round(1000.0 / avg_speed, 1) if avg_speed else None

    if is_run:
        avg_cad = round(sum(cad_slice) / len(cad_slice) * 2, 1) if cad_slice else None
    else:
        avg_cad = round(sum(cad_slice) / len(cad_slice), 1) if cad_slice else None

    # Grade-adjusted pace
    gas_slice = gas[start_idx:end_idx] if gas else []
    if not any(v and v > 0 for v in gas_slice):
        # Compute from velocity + grade
        if vel and grade:
            gas_slice = [
                v * (1 + 0.033 * g) if v and v > 0.1 else 0.0
                for v, g in zip(
                    (vel[start_idx:end_idx] if vel else []),
                    (grade[start_idx:end_idx] if grade else []),
                    strict=False,
                )
            ]
    valid_gas = [v for v in gas_slice if v and v > 0.1]
    avg_gap = (
        round(1000.0 / (sum(valid_gas) / len(valid_gas)), 1) if valid_gas else None
    )

    # Distance from cumulative distance stream
    distance_actual_m: float | None = None
    if dist and len(dist) > end_idx > start_idx:
        d_start = dist[start_idx]
        d_end = dist[end_idx - 1]
        if d_start is not None and d_end is not None:
            distance_actual_m = round(float(d_end) - float(d_start), 1)
    elif dist and end_idx > start_idx:
        # Partial slice near end of stream
        safe_end = min(end_idx, len(dist)) - 1
        safe_start = min(start_idx, len(dist) - 1)
        if (
            safe_end > safe_start
            and dist[safe_start] is not None
            and dist[safe_end] is not None
        ):
            distance_actual_m = round(
                float(dist[safe_end]) - float(dist[safe_start]), 1
            )

    return {
        "avg_speed_ms": avg_speed,
        "avg_pace_per_km": avg_pace,
        "avg_cadence": avg_cad,
        "avg_gap_per_km": avg_gap,
        "has_pace": avg_speed is not None,
        "distance_actual_m": distance_actual_m,
    }


# ---------------------------------------------------------------------------
# Zone-based HR scorer (existing logic, now multi-stream aware)
# ---------------------------------------------------------------------------


def _classify_hr_to_zone(hr: float, zones: ZoneResult) -> int:
    """Return the zone number (1–5) for a given HR value."""
    for z in reversed(zones.zones):
        if hr >= z.min_bpm:
            return z.zone
    return 1


def _score_segment_hr_zone(
    seg: WorkoutSegmentDef,
    streams: dict[str, list],
    start_idx: int,
    end_idx: int,
    zones: ZoneResult | None,
    is_run: bool = True,
) -> SegmentCompliance:
    """Score a segment against an HR zone target."""
    hr_stream = streams.get("heartrate", [])
    slice_data = [h for h in hr_stream[start_idx:end_idx] if h and h > 0]
    duration_actual_s = end_idx - start_idx
    has_hr = len(slice_data) > 0

    actuals = _compute_actuals(streams, start_idx, end_idx, is_run)

    base = SegmentCompliance(
        segment=seg,
        start_index=start_idx,
        end_index=end_idx,
        duration_actual_s=duration_actual_s,
        avg_heartrate=None,
        actual_zone=None,
        has_heartrate=has_hr,
        data_completeness=round(len(slice_data) / max(duration_actual_s, 1), 3),
        **actuals,
    )

    if not has_hr or zones is None:
        return base

    avg_hr = sum(slice_data) / len(slice_data)
    actual_zone = _classify_hr_to_zone(avg_hr, zones)
    total = len(slice_data)

    zone_counts: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for hr in slice_data:
        z = _classify_hr_to_zone(hr, zones)
        zone_counts[z] = zone_counts.get(z, 0) + 1
    zone_dist = {f"z{k}": round(v / total, 3) for k, v in zone_counts.items()}

    base.avg_heartrate = round(avg_hr, 1)
    base.actual_zone = actual_zone
    base.hr_zone_distribution = zone_dist

    target = seg.target_zone
    if target is None:
        base.compliance_score = 1.0
        return base

    time_in = zone_counts.get(target, 0)
    time_above = sum(v for k, v in zone_counts.items() if k > target)
    time_below = sum(v for k, v in zone_counts.items() if k < target)

    time_in_pct = round(time_in / total, 3)
    time_above_pct = round(time_above / total, 3)
    time_below_pct = round(time_below / total, 3)
    deviation_pct = round((actual_zone - target) / target * 100, 1)

    deviation_penalty = min(abs(deviation_pct) / 100 / 2, 1.0)
    score = round(min(1.0, time_in_pct * 0.6 + (1.0 - deviation_penalty) * 0.4), 3)

    base.target_achieved = time_in_pct >= 0.5
    base.deviation_pct = deviation_pct
    base.time_in_target_pct = time_in_pct
    base.time_above_pct = time_above_pct
    base.time_below_pct = time_below_pct
    base.compliance_score = score

    return base


# ---------------------------------------------------------------------------
# Absolute HR range scorer (warmup / cooldown with bpm targets)
# ---------------------------------------------------------------------------


def _score_segment_hr_range(
    seg: WorkoutSegmentDef,
    streams: dict[str, list],
    start_idx: int,
    end_idx: int,
    is_run: bool = True,
) -> SegmentCompliance:
    """Score a segment against an absolute HR range (min_bpm – max_bpm)."""
    hr_stream = streams.get("heartrate", [])
    slice_data = [h for h in hr_stream[start_idx:end_idx] if h and h > 0]
    duration_actual_s = end_idx - start_idx
    has_hr = len(slice_data) > 0

    actuals = _compute_actuals(streams, start_idx, end_idx, is_run)

    base = SegmentCompliance(
        segment=seg,
        start_index=start_idx,
        end_index=end_idx,
        duration_actual_s=duration_actual_s,
        avg_heartrate=None,
        actual_zone=None,
        has_heartrate=has_hr,
        data_completeness=round(len(slice_data) / max(duration_actual_s, 1), 3),
        **actuals,
    )

    if not has_hr:
        return base

    hr_min = seg.target_hr_min_bpm
    hr_max = seg.target_hr_max_bpm
    avg_hr = sum(slice_data) / len(slice_data)
    base.avg_heartrate = round(avg_hr, 1)
    total = len(slice_data)

    if hr_min is None and hr_max is None:
        base.compliance_score = 1.0
        return base

    lo = hr_min or 0.0
    hi = hr_max or float("inf")
    midpoint = (lo + hi) / 2 if hr_max else avg_hr
    half_range = (hi - lo) / 2 if hr_max and hr_min else 1.0

    time_in = sum(1 for h in slice_data if lo <= h <= hi)
    time_above = sum(1 for h in slice_data if h > hi)
    time_below = sum(1 for h in slice_data if h < lo)

    time_in_pct = round(time_in / total, 3)
    time_above_pct = round(time_above / total, 3)
    time_below_pct = round(time_below / total, 3)

    deviation = (avg_hr - midpoint) / max(half_range, 1.0)
    deviation_pct = round(deviation * 100, 1)

    deviation_penalty = min(abs(deviation), 1.0)
    score = round(min(1.0, time_in_pct * 0.6 + (1.0 - deviation_penalty) * 0.4), 3)

    base.target_achieved = time_in_pct >= 0.5
    base.deviation_pct = deviation_pct
    base.time_in_target_pct = time_in_pct
    base.time_above_pct = time_above_pct
    base.time_below_pct = time_below_pct
    base.compliance_score = score

    return base


# ---------------------------------------------------------------------------
# Pace range scorer (intervals with pace targets)
# ---------------------------------------------------------------------------


def _score_segment_pace_range(
    seg: WorkoutSegmentDef,
    streams: dict[str, list],
    start_idx: int,
    end_idx: int,
    is_run: bool = True,
) -> SegmentCompliance:
    """Score a segment against a pace range target (min/max s/km)."""
    vel_stream = streams.get("velocity_smooth", [])
    hr_stream = streams.get("heartrate", [])

    vel_slice = (
        [v for v in vel_stream[start_idx:end_idx] if v and v > 0.1]
        if vel_stream
        else []
    )
    hr_slice = (
        [h for h in hr_stream[start_idx:end_idx] if h and h > 0] if hr_stream else []
    )
    duration_actual_s = end_idx - start_idx

    has_pace = len(vel_slice) > 0
    has_hr = len(hr_slice) > 0

    actuals = _compute_actuals(streams, start_idx, end_idx, is_run)

    base = SegmentCompliance(
        segment=seg,
        start_index=start_idx,
        end_index=end_idx,
        duration_actual_s=duration_actual_s,
        avg_heartrate=round(sum(hr_slice) / len(hr_slice), 1) if has_hr else None,
        actual_zone=None,
        has_heartrate=has_hr,
        data_completeness=round(len(vel_slice) / max(duration_actual_s, 1), 3),
        **actuals,
    )

    pace_min = seg.target_pace_min_s_per_km  # faster = lower number
    pace_max = seg.target_pace_max_s_per_km  # slower = higher number

    if not has_pace or (pace_min is None and pace_max is None):
        if has_pace:
            base.compliance_score = 1.0
        return base

    # Convert vel (m/s) → pace (s/km)
    pace_values = [1000.0 / v for v in vel_slice]
    avg_pace = sum(pace_values) / len(pace_values)
    total = len(pace_values)

    lo = pace_min or 0.0  # fastest allowed (low s/km)
    hi = pace_max or float("inf")  # slowest allowed (high s/km)
    midpoint = (lo + hi) / 2 if pace_max and pace_min else avg_pace
    half_range = (hi - lo) / 2 if pace_max and pace_min else 1.0

    time_in = sum(1 for p in pace_values if lo <= p <= hi)
    time_above = sum(1 for p in pace_values if p > hi)  # too slow
    time_below = sum(1 for p in pace_values if p < lo)  # too fast

    time_in_pct = round(time_in / total, 3)
    time_above_pct = round(time_above / total, 3)
    time_below_pct = round(time_below / total, 3)

    deviation = (avg_pace - midpoint) / max(half_range, 1.0)
    deviation_pct = round(deviation * 100, 1)

    deviation_penalty = min(abs(deviation), 1.0)
    score = round(min(1.0, time_in_pct * 0.6 + (1.0 - deviation_penalty) * 0.4), 3)

    base.target_achieved = time_in_pct >= 0.5
    base.deviation_pct = deviation_pct
    base.time_in_target_pct = time_in_pct
    base.time_above_pct = time_above_pct
    base.time_below_pct = time_below_pct
    base.compliance_score = score

    return base


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def _score_segment(
    seg: WorkoutSegmentDef,
    streams: dict[str, list],
    start_idx: int,
    end_idx: int,
    zones: ZoneResult | None,
    is_run: bool = True,
) -> SegmentCompliance:
    """Dispatch to the appropriate scorer based on segment target type."""
    focus = seg.target_focus_type
    if focus == "hr_range":
        return _score_segment_hr_range(seg, streams, start_idx, end_idx, is_run)
    if focus == "pace_range":
        return _score_segment_pace_range(seg, streams, start_idx, end_idx, is_run)
    # Default: hr_zone (original behavior)
    return _score_segment_hr_zone(seg, streams, start_idx, end_idx, zones, is_run)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _time_to_index(time_stream: list, t0: float, target_elapsed_s: float) -> int:
    """Return the stream index where elapsed time first reaches target_elapsed_s.

    Uses bisect for O(log n) lookup. Falls back to stream end if target exceeds
    the recording length.
    """
    import bisect

    target_t = t0 + target_elapsed_s
    idx = bisect.bisect_left(time_stream, target_t)
    return min(idx, len(time_stream))


def compute_compliance(
    segments: list[WorkoutSegmentDef],
    streams: dict[str, list],
    activity_moving_time_s: int,
    zones: ZoneResult | None,
    is_run: bool = True,
) -> list[SegmentCompliance]:
    """Slice streams by segment durations and score each segment.

    Strategy (preferred — when time stream is present):
    - Use the recorded time stream to map each planned segment duration to an
      exact stream index range. This avoids cumulative drift caused by a global
      scale factor that does not account for per-segment timing differences
      (e.g., a warmup that ran to plan while intervals were cut short).

    Fallback (no time stream):
    - Scale planned durations proportionally via activity_moving_time_s /
      total_planned_s and slice by sample count.

    Segments without duration_min emit a zero-length placeholder.
    """
    # Use the primary stream to determine array length
    primary = (
        streams.get("heartrate")
        or streams.get("velocity_smooth")
        or streams.get("distance")
        or []
    )
    stream_len = len(primary)

    timed = [s for s in segments if s.duration_min is not None]

    if not timed:
        # Even split across all segments
        n = len(segments)
        return [
            _score_segment(
                seg,
                streams,
                int(stream_len * i / n),
                int(stream_len * (i + 1) / n),
                zones,
                is_run,
            )
            for i, seg in enumerate(segments)
        ]

    time_stream = streams.get("time", [])
    use_time_stream = bool(time_stream and len(time_stream) == stream_len)

    results: list[SegmentCompliance] = []

    if use_time_stream:
        # Time-based slicing: map planned elapsed seconds → stream index
        t0 = float(time_stream[0])
        planned_elapsed_s = 0.0
        cursor = 0

        for seg in segments:
            if seg.duration_min is None:
                results.append(
                    SegmentCompliance(
                        segment=seg,
                        start_index=cursor,
                        end_index=cursor,
                        duration_actual_s=0,
                        avg_heartrate=None,
                        actual_zone=None,
                    )
                )
                continue

            planned_elapsed_s += seg.duration_min * 60
            end_idx = min(
                _time_to_index(time_stream, t0, planned_elapsed_s), stream_len
            )
            start_idx = min(cursor, end_idx)
            results.append(
                _score_segment(seg, streams, start_idx, end_idx, zones, is_run)
            )
            cursor = end_idx

    else:
        # Fallback: global scale factor
        total_planned_s = sum(s.duration_min * 60 for s in timed)
        scale = activity_moving_time_s / total_planned_s if total_planned_s > 0 else 1.0
        cursor = 0

        for seg in segments:
            if seg.duration_min is None:
                results.append(
                    SegmentCompliance(
                        segment=seg,
                        start_index=cursor,
                        end_index=cursor,
                        duration_actual_s=0,
                        avg_heartrate=None,
                        actual_zone=None,
                    )
                )
                continue

            duration_s = max(1, int(seg.duration_min * 60 * scale))
            start_idx = min(cursor, max(stream_len - 1, 0))
            end_idx = min(cursor + duration_s, stream_len)
            results.append(
                _score_segment(seg, streams, start_idx, end_idx, zones, is_run)
            )
            cursor = end_idx

    return results


def overall_compliance_score(results: list[SegmentCompliance]) -> float | None:
    """Weighted average compliance score across all scored segments."""
    scored = [
        r
        for r in results
        if (r.has_heartrate and r.segment.target_zone is not None)
        or (r.has_heartrate and r.segment.target_focus_type == "hr_range")
        or (r.has_pace and r.segment.target_focus_type == "pace_range")
    ]
    if not scored:
        return None
    total_weight = sum(r.duration_actual_s for r in scored)
    if total_weight == 0:
        return None
    weighted = sum(r.compliance_score * r.duration_actual_s for r in scored)
    return round(weighted / total_weight, 3)
