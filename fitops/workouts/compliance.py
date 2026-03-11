from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

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
    avg_heartrate: Optional[float]
    actual_zone: Optional[int]
    hr_zone_distribution: dict[str, float] = field(default_factory=dict)

    # Compliance metrics
    target_achieved: bool = False
    deviation_pct: float = 0.0       # positive = above target, negative = below
    time_in_target_pct: float = 0.0
    time_above_pct: float = 0.0
    time_below_pct: float = 0.0
    compliance_score: float = 0.0    # 0.0–1.0

    # Data quality
    has_heartrate: bool = False
    data_completeness: float = 0.0   # fraction of slice with valid HR readings


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify_hr_to_zone(hr: float, zones: ZoneResult) -> int:
    """Return the zone number (1–5) for a given HR value."""
    for z in reversed(zones.zones):
        if hr >= z.min_bpm:
            return z.zone
    return 1


def _score_segment(
    seg: WorkoutSegmentDef,
    hr_stream: list,
    start_idx: int,
    end_idx: int,
    zones: Optional[ZoneResult],
) -> SegmentCompliance:
    """Score a single segment slice against its target zone."""
    slice_data = [h for h in hr_stream[start_idx:end_idx] if h and h > 0]
    duration_actual_s = end_idx - start_idx
    has_hr = len(slice_data) > 0

    base = SegmentCompliance(
        segment=seg,
        start_index=start_idx,
        end_index=end_idx,
        duration_actual_s=duration_actual_s,
        avg_heartrate=None,
        actual_zone=None,
        has_heartrate=has_hr,
        data_completeness=round(len(slice_data) / max(duration_actual_s, 1), 3),
    )

    if not has_hr or zones is None:
        return base

    avg_hr = sum(slice_data) / len(slice_data)
    actual_zone = _classify_hr_to_zone(avg_hr, zones)
    total = len(slice_data)

    # Per-second zone distribution
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
        # No target — report actuals only; cannot fail compliance
        base.compliance_score = 1.0
        return base

    time_in = zone_counts.get(target, 0)
    time_above = sum(v for k, v in zone_counts.items() if k > target)
    time_below = sum(v for k, v in zone_counts.items() if k < target)

    time_in_pct = round(time_in / total, 3)
    time_above_pct = round(time_above / total, 3)
    time_below_pct = round(time_below / total, 3)
    deviation_pct = round((actual_zone - target) / target * 100, 1)

    # Asymmetric compliance formula (from KineticRun):
    #   compliance = time_in_target * 0.6 + (1 - |deviation| / 2) * 0.4
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
# Public API
# ---------------------------------------------------------------------------

def compute_compliance(
    segments: list[WorkoutSegmentDef],
    hr_stream: list,
    activity_moving_time_s: int,
    zones: Optional[ZoneResult],
) -> list[SegmentCompliance]:
    """Slice the HR stream by segment durations and score each segment.

    Strategy:
    - Segments with duration_min defined are sliced proportionally using the
      ratio of planned_total_s → actual moving_time_s.
    - Segments without duration_min are skipped from stream slicing but still
      appear in the output (with null stream data).
    - If NO segments have durations, the stream is split evenly.
    """
    timed = [s for s in segments if s.duration_min is not None]

    if not timed:
        # Even split across all segments
        n = len(segments)
        return [
            _score_segment(
                seg,
                hr_stream,
                int(len(hr_stream) * i / n),
                int(len(hr_stream) * (i + 1) / n),
                zones,
            )
            for i, seg in enumerate(segments)
        ]

    # Scale planned durations to actual moving time
    total_planned_s = sum(s.duration_min * 60 for s in timed)
    scale = activity_moving_time_s / total_planned_s if total_planned_s > 0 else 1.0

    results: list[SegmentCompliance] = []
    cursor = 0

    for seg in segments:
        if seg.duration_min is None:
            # No duration — emit a placeholder with null stream data
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
        start_idx = min(cursor, max(len(hr_stream) - 1, 0))
        end_idx = min(cursor + duration_s, len(hr_stream))
        results.append(_score_segment(seg, hr_stream, start_idx, end_idx, zones))
        cursor = end_idx

    return results


def overall_compliance_score(results: list[SegmentCompliance]) -> Optional[float]:
    """Weighted average compliance score across all scored segments."""
    scored = [r for r in results if r.has_heartrate and r.segment.target_zone is not None]
    if not scored:
        return None
    # Weight by actual duration
    total_weight = sum(r.duration_actual_s for r in scored)
    if total_weight == 0:
        return None
    weighted = sum(r.compliance_score * r.duration_actual_s for r in scored)
    return round(weighted / total_weight, 3)
