"""Per-activity analytics: time-in-zone, LT2 inference, VO2max estimate."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.analytics.pace_zones import compute_pace_zones
from fitops.analytics.vo2max import _estimate_from_activity
from fitops.analytics.zones import compute_zones

RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}

# LT2 constants (from KineticRun)
_STEADY_MAX_HR_RANGE = 10  # bpm spread allowed in steady segment
_MIN_STEADY_SECONDS = 900  # 15 min minimum steady segment
_FINAL_WINDOW_SECONDS = 1200  # 20 min final averaging window
_MIN_AVG_HR = 140
_MIN_DURATION_SECONDS = 1800  # 30 min minimum activity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_seconds(s: int) -> str:
    h, rem = divmod(max(0, s), 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _find_steady_segment(
    hr_data: list[float],
    time_data: list[float],
    max_range: int = _STEADY_MAX_HR_RANGE,
) -> tuple[int, int, float]:
    """O(n) sliding window to find longest segment where HR max-min ≤ max_range."""
    n = min(len(hr_data), len(time_data))
    min_dq: deque[int] = deque()  # indices of ascending HR (front = min)
    max_dq: deque[int] = deque()  # indices of descending HR (front = max)

    left = 0
    best_start = best_end = 0
    best_dur = 0.0

    for right in range(n):
        h = hr_data[right]
        while min_dq and hr_data[min_dq[-1]] >= h:
            min_dq.pop()
        min_dq.append(right)
        while max_dq and hr_data[max_dq[-1]] <= h:
            max_dq.pop()
        max_dq.append(right)

        # Shrink window while range exceeds threshold
        while min_dq and max_dq and hr_data[max_dq[0]] - hr_data[min_dq[0]] > max_range:
            left += 1
            if min_dq[0] < left:
                min_dq.popleft()
            if max_dq[0] < left:
                max_dq.popleft()

        dur = time_data[right] - time_data[left]
        if dur > best_dur:
            best_dur = dur
            best_start = left
            best_end = right

    return best_start, best_end, best_dur


# ---------------------------------------------------------------------------
# HR zones
# ---------------------------------------------------------------------------


def compute_time_in_hr_zones(
    hr_data: list[float],
    time_data: list[float],
) -> list[dict] | None:
    """Map each stream point to its HR zone and sum durations."""
    settings = get_athlete_settings()
    method = settings.best_zone_method()
    if method == "none":
        return None

    zone_result = compute_zones(
        method=method,
        lthr=settings.lthr,
        max_hr=settings.max_hr,
        resting_hr=settings.resting_hr,
    )
    if zone_result is None:
        return None

    zones = zone_result.zones
    zone_times: dict[int, float] = {z.zone: 0.0 for z in zones}

    n = min(len(hr_data), len(time_data))
    for i in range(n - 1):
        hr = hr_data[i]
        dt = time_data[i + 1] - time_data[i]
        if dt <= 0:
            continue
        for z in zones:
            if hr >= z.min_bpm and (hr < z.max_bpm or z.max_bpm >= 999):
                zone_times[z.zone] += dt
                break

    total = sum(zone_times.values())
    return [
        {
            "zone": z.zone,
            "name": z.name,
            "min_bpm": z.min_bpm,
            "max_bpm": z.max_bpm if z.max_bpm < 999 else None,
            "time_s": round(zone_times[z.zone]),
            "time_fmt": _fmt_seconds(round(zone_times[z.zone])),
            "pct": round(zone_times[z.zone] / total * 100, 1) if total > 0 else 0.0,
        }
        for z in zones
    ]


# ---------------------------------------------------------------------------
# Pace zones
# ---------------------------------------------------------------------------


def compute_time_in_pace_zones(
    velocity_data: list[float],
    time_data: list[float],
) -> list[dict] | None:
    """Map each stream point to its pace zone and sum durations (running only)."""
    settings = get_athlete_settings()
    threshold_s = settings.threshold_pace_per_km_s
    if threshold_s is None:
        return None

    pace_result = compute_pace_zones(int(threshold_s))
    zones = pace_result.zones
    zone_times: dict[int, float] = {z["zone"]: 0.0 for z in zones}

    n = min(len(velocity_data), len(time_data))
    for i in range(n - 1):
        v = velocity_data[i]
        dt = time_data[i + 1] - time_data[i]
        if dt <= 0 or v <= 0:
            continue
        pace_s = 1000.0 / v  # m/s → sec/km
        for z in zones:
            min_s = z["min_s_per_km"]  # faster boundary (smaller number)
            max_s = z["max_s_per_km"]  # slower boundary (larger number)
            too_fast = min_s is not None and pace_s < min_s
            too_slow = max_s is not None and pace_s > max_s
            if not too_fast and not too_slow:
                zone_times[z["zone"]] += dt
                break

    total = sum(zone_times.values())
    return [
        {
            "zone": z["zone"],
            "name": z["name"],
            "min_pace": z["min_pace_fmt"],
            "max_pace": z["max_pace_fmt"],
            "time_s": round(zone_times[z["zone"]]),
            "time_fmt": _fmt_seconds(round(zone_times[z["zone"]])),
            "pct": round(zone_times[z["zone"]] / total * 100, 1) if total > 0 else 0.0,
        }
        for z in zones
    ]


# ---------------------------------------------------------------------------
# LT2 inference
# ---------------------------------------------------------------------------


def infer_lt2_from_streams(
    hr_data: list[float],
    time_data: list[float],
    velocity_data: list[float] | None = None,
) -> dict | None:
    """
    Detect LT2 from a steady-state effort segment (KineticRun algorithm).
    Requires a ≥30 min effort with avg HR ≥140 bpm and a ≥15 min steady segment.
    Returns {lthr_bpm, pace_s_per_km, pace_fmt} or None.
    """
    n = min(len(hr_data), len(time_data))
    if n < 2:
        return None

    total_duration = time_data[n - 1] - time_data[0]
    if total_duration < _MIN_DURATION_SECONDS:
        return None

    avg_hr = sum(hr_data[:n]) / n
    if avg_hr < _MIN_AVG_HR:
        return None

    settings = get_athlete_settings()
    if settings.max_hr:
        if not (settings.max_hr * 0.80 <= avg_hr <= settings.max_hr * 0.98):
            return None
    elif settings.lthr:
        if not (settings.lthr * 0.90 <= avg_hr <= settings.lthr * 1.05):
            return None

    best_start, best_end, best_dur = _find_steady_segment(hr_data[:n], time_data[:n])

    if best_dur < _MIN_STEADY_SECONDS:
        return None

    # Average HR over final 20 min of steady segment
    seg_end_time = time_data[best_end]
    window_start_t = max(time_data[best_start], seg_end_time - _FINAL_WINDOW_SECONDS)

    final_hr = [
        hr_data[i]
        for i in range(best_start, best_end + 1)
        if time_data[i] >= window_start_t
    ]
    if not final_hr:
        return None

    inferred_lthr = round(sum(final_hr) / len(final_hr))
    result: dict = {"lthr_bpm": inferred_lthr, "pace_s_per_km": None, "pace_fmt": None}

    # Infer pace from same window if velocity available
    if velocity_data:
        nv = min(len(velocity_data), len(time_data))
        final_v = [
            velocity_data[i]
            for i in range(min(best_start, nv - 1), min(best_end + 1, nv))
            if time_data[i] >= window_start_t and velocity_data[i] > 0
        ]
        if final_v:
            mean_v = sum(final_v) / len(final_v)
            pace_s = round(1000.0 / mean_v, 1)
            m, s = divmod(int(pace_s), 60)
            result["pace_s_per_km"] = pace_s
            result["pace_fmt"] = f"{m}:{s:02d}/km"

    return result


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


@dataclass
class ActivityAnalytics:
    hr_zones: list[dict] | None
    pace_zones: list[dict] | None
    lt2: dict | None
    vo2max: dict | None


def compute_activity_analytics(
    activity,
    streams: dict[str, list],
) -> ActivityAnalytics:
    """Compute all per-activity analytics from an Activity ORM object + stream dict."""
    hr_data = streams.get("heartrate", [])
    time_data = streams.get("time", [])
    velocity_data = streams.get("velocity_smooth", [])

    # For effort-normalised analytics prefer True Pace (GAP+WAP), then GAP, then actual
    pace_velocity = (
        streams.get("true_velocity")
        or streams.get("grade_adjusted_speed")
        or velocity_data
    )

    hr_zones = None
    pace_zones = None
    lt2 = None
    vo2max_dict = None

    if hr_data and time_data:
        hr_zones = compute_time_in_hr_zones(hr_data, time_data)
        lt2 = infer_lt2_from_streams(
            hr_data, time_data, pace_velocity if pace_velocity else None
        )

    is_run = getattr(activity, "sport_type", None) in RUN_TYPES
    if is_run and pace_velocity and time_data:
        pace_zones = compute_time_in_pace_zones(pace_velocity, time_data)

    if is_run:
        est = _estimate_from_activity(activity)
        if est:
            vo2max_dict = {
                "estimate": est.estimate,
                "confidence": est.confidence,
                "confidence_label": est.confidence_label,
                "vdot": est.vdot,
                "cooper": est.cooper,
            }

    return ActivityAnalytics(
        hr_zones=hr_zones,
        pace_zones=pace_zones,
        lt2=lt2,
        vo2max=vo2max_dict,
    )
