"""Per-activity performance insights: detect new PRs and regressions vs athlete settings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fitops.analytics.vo2max import _effort_qualifies, _estimate_from_activity

RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
_ROLLING_WINDOW_S = 20 * 60  # 20 minutes


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class PerformanceInsight:
    metric: str           # "max_hr" | "lt2_hr" | "lt1_hr" | "vo2max" | "lt2_pace" | "lt1_pace"
    label: str
    setting_key: str      # key in athlete_settings.json
    current_value: Optional[float]
    detected_value: float
    delta_pct: float      # >0 = improvement, <0 = regression
    action: str           # "prompt_update" | "warn" | "ignore"
    detected_fmt: str
    current_fmt: Optional[str]
    unit: str
    explanation: str


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _fmt_hr(bpm: float) -> str:
    return f"{int(round(bpm))} bpm"


def _fmt_pace(s_per_km: float) -> str:
    m, s = divmod(int(s_per_km), 60)
    return f"{m}:{s:02d}/km"


def _fmt_vo2max(v: float) -> str:
    return f"{v:.1f} ml/kg/min"


# ---------------------------------------------------------------------------
# Action classifiers (science-based thresholds)
# ---------------------------------------------------------------------------

def _classify_hr(delta_pct: float) -> str:
    """Any improvement prompts; ignore within ±3%; warn if >5% regression.
    Day-to-day HR variability ~2-3% (Achten & Jeukendrup 2004).
    """
    if delta_pct > 0.0:
        return "prompt_update"
    if abs(delta_pct) <= 0.03:
        return "ignore"
    if delta_pct < -0.05:
        return "warn"
    return "ignore"


def _classify_vo2max(delta_pct: float) -> str:
    """±2% = noise floor for Daniels VDOT; >8% regression ≈ 1 fitness tier drop."""
    if delta_pct > 0.02:
        return "prompt_update"
    if abs(delta_pct) <= 0.02:
        return "ignore"
    if delta_pct < -0.08:
        return "warn"
    return "ignore"


def _classify_pace(delta_pct: float) -> str:
    """Pace more variable than HR; ≥2% faster = improvement; within 5% slower = noise."""
    if delta_pct > 0.02:
        return "prompt_update"
    if abs(delta_pct) <= 0.05:
        return "ignore"
    if delta_pct < -0.10:
        return "warn"
    return "ignore"


# ---------------------------------------------------------------------------
# Effort classification
# ---------------------------------------------------------------------------

def _is_hard_effort(activity, settings) -> bool:
    """True if avg HR qualifies as a threshold-level effort."""
    hr = activity.average_heartrate
    if not hr:
        return False
    if settings.lthr is not None:
        return hr >= settings.lthr * 0.90
    if settings.max_hr is not None:
        return hr >= settings.max_hr * 0.80
    return False


def _is_easy_run(activity, settings) -> bool:
    """True if this is a run with avg HR clearly below lactate threshold."""
    if activity.sport_type not in RUN_TYPES:
        return False
    hr = activity.average_heartrate
    if not hr:
        return False
    if settings.lthr is not None:
        return hr < settings.lthr * 0.85
    if settings.max_hr is not None:
        return hr < settings.max_hr * 0.75
    return False


# ---------------------------------------------------------------------------
# Stream utilities
# ---------------------------------------------------------------------------

def _p90_rolling_20min_hr(
    hr_data: list,
    time_data: list,
    intensity_floor: float = 0.0,
) -> Optional[float]:
    """90th-percentile of valid 20-min rolling HR averages where avg >= intensity_floor.

    Taking the maximum window overestimates LTHR when the athlete goes out too hard.
    The 90th percentile matches zone_inference.py's cross-activity approach (Achten &
    Jeukendrup 2004) and gives a more conservative, reproducible threshold estimate.
    """
    n = min(len(hr_data), len(time_data))
    if n < 10:
        return None

    left = 0
    valid_avgs: list[float] = []

    for right in range(n):
        t_right = time_data[right]
        if t_right is None:
            continue
        while time_data[left] is not None and time_data[left] < t_right - _ROLLING_WINDOW_S:
            left += 1
        window = [h for h in hr_data[left:right + 1] if h and h > 0]
        if len(window) < 10:
            continue
        avg = sum(window) / len(window)
        if avg >= intensity_floor:
            valid_avgs.append(avg)

    if not valid_avgs:
        return None

    valid_avgs.sort()
    idx = (0.90 * (len(valid_avgs) - 1))
    lo = int(idx)
    hi = min(lo + 1, len(valid_avgs) - 1)
    p90 = valid_avgs[lo] + (idx - lo) * (valid_avgs[hi] - valid_avgs[lo])
    return round(p90, 1)


def _median_pace_at_hr_floor(
    hr_data: list,
    true_pace_data: list,
    hr_floor: float,
    min_samples: int = 120,
) -> Optional[float]:
    """Median true pace (sec/km) where HR >= hr_floor. true_pace_data is already in sec/km."""
    values = []
    for hr, pace in zip(hr_data, true_pace_data):
        if hr is None or pace is None:
            continue
        if hr >= hr_floor and 0 < pace < 2000:  # 2000 s/km = ~0.5 m/s, filters stationary
            values.append(pace)
    if len(values) < min_samples:
        return None
    values.sort()
    return round(values[len(values) // 2], 1)


def _median_pace_in_hr_band(
    hr_data: list,
    true_pace_data: list,
    hr_lo: float,
    hr_hi: float,
    min_samples: int = 120,
) -> Optional[float]:
    """Median true pace (sec/km) where hr_lo <= HR <= hr_hi. true_pace_data is already in sec/km."""
    values = []
    for hr, pace in zip(hr_data, true_pace_data):
        if hr is None or pace is None:
            continue
        if hr_lo <= hr <= hr_hi and 0 < pace < 2000:
            values.append(pace)
    if len(values) < min_samples:
        return None
    values.sort()
    return round(values[len(values) // 2], 1)


# ---------------------------------------------------------------------------
# Per-metric detectors
# ---------------------------------------------------------------------------

def _detect_max_hr(activity, streams: dict, settings) -> Optional[PerformanceInsight]:
    """New max HR — only meaningful from hard efforts."""
    if not _is_hard_effort(activity, settings):
        return None
    detected = activity.max_heartrate
    if not detected:
        return None
    current = settings.max_hr
    if current is None:
        return PerformanceInsight(
            metric="max_hr",
            label="Max Heart Rate",
            setting_key="max_hr",
            current_value=None,
            detected_value=float(detected),
            delta_pct=1.0,
            action="prompt_update",
            detected_fmt=_fmt_hr(detected),
            current_fmt=None,
            unit="bpm",
            explanation="New max HR recorded — no baseline set yet",
        )
    delta = (detected - current) / current
    # No downward warning for max HR: lower max in one activity is expected and uninformative
    if delta <= 0.0:
        return None
    return PerformanceInsight(
        metric="max_hr",
        label="Max Heart Rate",
        setting_key="max_hr",
        current_value=float(current),
        detected_value=float(detected),
        delta_pct=delta,
        action="prompt_update",
        detected_fmt=_fmt_hr(detected),
        current_fmt=_fmt_hr(current),
        unit="bpm",
        explanation="New highest HR observed during a hard effort",
    )


def _detect_lt2_hr(activity, streams: dict, settings) -> Optional[PerformanceInsight]:
    """LTHR estimate from best 20-min rolling HR — only for hard efforts with stream data."""
    if not _is_hard_effort(activity, settings):
        return None
    hr_data = streams.get("heartrate", [])
    time_data = streams.get("time", [])
    if not hr_data or not time_data:
        return None
    current = settings.lthr
    if current is None:
        return None
    # Intensity floor: only count samples from genuinely hard portions
    max_hr_ref = settings.max_hr or round(current / 0.88)
    intensity_floor = max_hr_ref * 0.80
    detected = _p90_rolling_20min_hr(hr_data, time_data, intensity_floor)
    if detected is None:
        return None
    delta = (detected - current) / current
    action = _classify_hr(delta)
    if action == "ignore":
        return None
    return PerformanceInsight(
        metric="lt2_hr",
        label="LT2 Heart Rate (LTHR)",
        setting_key="lthr",
        current_value=float(current),
        detected_value=detected,
        delta_pct=delta,
        action=action,
        detected_fmt=_fmt_hr(detected),
        current_fmt=_fmt_hr(current),
        unit="bpm",
        explanation="90th-pct of 20-min rolling HR windows from hard effort (conservative LTHR proxy)",
    )


def _detect_lt1_hr(activity, streams: dict, settings) -> Optional[PerformanceInsight]:
    """LT1 HR from steady-state easy run — only for clearly aerobic efforts."""
    if not _is_easy_run(activity, settings):
        return None
    hr_data = streams.get("heartrate", [])
    time_data = streams.get("time", [])
    if not hr_data or not time_data:
        return None

    # Resolve current LT1 HR: stored or derived from LTHR (LT1 ≈ 83% LTHR, Seiler)
    current = settings.lt1_hr
    current_for_compare = current if current is not None else (
        round(settings.lthr * 0.83) if settings.lthr else None
    )
    if current_for_compare is None:
        return None

    # Skip warmup (first 600 s)
    warmup_end = 0
    for i, t in enumerate(time_data):
        if t is not None and t >= 600:
            warmup_end = i
            break
    if warmup_end == 0 or warmup_end >= len(hr_data):
        return None

    hr_post_warmup = [h for h in hr_data[warmup_end:] if h and h > 0]
    if len(hr_post_warmup) < 600:  # need ≥10 min of post-warmup data
        return None

    # Steady-state band: samples within ±5 bpm of median (filters drift and surges)
    sorted_hr = sorted(hr_post_warmup)
    median_hr = sorted_hr[len(sorted_hr) // 2]
    hr_steady = [h for h in hr_post_warmup if abs(h - median_hr) <= 5]
    if len(hr_steady) < 300:
        return None

    detected = round(sum(hr_steady) / len(hr_steady), 1)
    delta = (detected - current_for_compare) / current_for_compare
    action = _classify_hr(delta)
    if action == "ignore":
        return None
    return PerformanceInsight(
        metric="lt1_hr",
        label="LT1 Heart Rate",
        setting_key="lt1_hr",
        current_value=float(current) if current is not None else None,
        detected_value=detected,
        delta_pct=delta,
        action=action,
        detected_fmt=_fmt_hr(detected),
        current_fmt=_fmt_hr(current_for_compare),
        unit="bpm",
        explanation="Steady-state avg HR from aerobic run (post-warmup, ±5 bpm band)",
    )


def _detect_vo2max(activity, streams: dict, settings) -> Optional[PerformanceInsight]:
    """VO2max from Daniels VDOT — all qualifying hard efforts (not just races)."""
    if activity.sport_type not in RUN_TYPES:
        return None
    qualifies, _ = _effort_qualifies(
        activity.average_heartrate,
        settings.lthr,
        settings.max_hr,
    )
    if not qualifies:
        return None
    result = _estimate_from_activity(activity)
    if result is None or result.confidence < 0.5:
        return None

    detected = result.estimate
    current = settings.vo2max_override

    if current is None:
        return PerformanceInsight(
            metric="vo2max",
            label="VO2max",
            setting_key="vo2max_override",
            current_value=None,
            detected_value=detected,
            delta_pct=1.0,
            action="prompt_update",
            detected_fmt=_fmt_vo2max(detected),
            current_fmt=None,
            unit="ml/kg/min",
            explanation=f"Estimated from qualifying effort (confidence: {result.confidence_label})",
        )

    delta = (detected - current) / current
    action = _classify_vo2max(delta)
    if action == "ignore":
        return None
    return PerformanceInsight(
        metric="vo2max",
        label="VO2max",
        setting_key="vo2max_override",
        current_value=float(current),
        detected_value=detected,
        delta_pct=delta,
        action=action,
        detected_fmt=_fmt_vo2max(detected),
        current_fmt=_fmt_vo2max(current),
        unit="ml/kg/min",
        explanation=f"Daniels VDOT from qualifying effort (confidence: {result.confidence_label})",
    )


def _detect_lt2_pace(activity, streams: dict, settings) -> Optional[PerformanceInsight]:
    """LT2 pace from median true pace at HR >= 97% LTHR — only for hard running efforts."""
    if activity.sport_type not in RUN_TYPES:
        return None
    if not _is_hard_effort(activity, settings):
        return None
    lthr = settings.lthr
    if lthr is None:
        return None
    hr_data = streams.get("heartrate", [])
    pace_data = streams.get("true_pace", [])
    if not hr_data or not pace_data:
        return None
    detected = _median_pace_at_hr_floor(hr_data, pace_data, lthr * 0.97)
    if detected is None:
        return None
    current = settings.threshold_pace_per_km_s
    if current is None:
        return PerformanceInsight(
            metric="lt2_pace",
            label="LT2 Pace (Threshold)",
            setting_key="threshold_pace_per_km_s",
            current_value=None,
            detected_value=detected,
            delta_pct=1.0,
            action="prompt_update",
            detected_fmt=_fmt_pace(detected),
            current_fmt=None,
            unit="/km",
            explanation="True pace at HR >= 97% LTHR — no threshold pace baseline set yet",
        )
    # For pace: positive delta = faster (improvement)
    delta = (current - detected) / current
    action = _classify_pace(delta)
    if action == "ignore":
        return None
    return PerformanceInsight(
        metric="lt2_pace",
        label="LT2 Pace (Threshold)",
        setting_key="threshold_pace_per_km_s",
        current_value=float(current),
        detected_value=detected,
        delta_pct=delta,
        action=action,
        detected_fmt=_fmt_pace(detected),
        current_fmt=_fmt_pace(current),
        unit="/km",
        explanation="Median true pace at HR >= 97% LTHR during hard effort",
    )


def _detect_lt1_pace(activity, streams: dict, settings) -> Optional[PerformanceInsight]:
    """LT1 pace from median true pace in the LT1 HR band — only for easy runs."""
    if not _is_easy_run(activity, settings):
        return None
    # Resolve LT1 HR: stored explicitly, or derive from LTHR (LT1 ≈ 83% LTHR)
    lt1_hr = settings.lt1_hr
    if lt1_hr is None:
        lt1_hr = round(settings.lthr * 0.83) if settings.lthr else None
    if lt1_hr is None:
        return None
    hr_data = streams.get("heartrate", [])
    pace_data = streams.get("true_pace", [])
    if not hr_data or not pace_data:
        return None
    detected = _median_pace_in_hr_band(hr_data, pace_data, lt1_hr - 8, lt1_hr + 8)
    if detected is None:
        return None
    current = settings.lt1_pace_s
    if current is None:
        return PerformanceInsight(
            metric="lt1_pace",
            label="LT1 Pace (Aerobic Threshold)",
            setting_key="lt1_pace_s",
            current_value=None,
            detected_value=detected,
            delta_pct=1.0,
            action="prompt_update",
            detected_fmt=_fmt_pace(detected),
            current_fmt=None,
            unit="/km",
            explanation="True pace in LT1 HR zone (±8 bpm) — no aerobic pace baseline set yet",
        )
    delta = (current - detected) / current
    action = _classify_pace(delta)
    if action == "ignore":
        return None
    return PerformanceInsight(
        metric="lt1_pace",
        label="LT1 Pace (Aerobic Threshold)",
        setting_key="lt1_pace_s",
        current_value=float(current),
        detected_value=detected,
        delta_pct=delta,
        action=action,
        detected_fmt=_fmt_pace(detected),
        current_fmt=_fmt_pace(current),
        unit="/km",
        explanation="Median true pace in LT1 HR zone (±8 bpm) during easy run",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_activity_performance_insights(
    activity,
    streams: dict,
    settings,
) -> list[PerformanceInsight]:
    """Compute all applicable performance insights for a single activity.

    Compares this activity's observed data against the athlete's current settings.
    Only returns insights with action "prompt_update" or "warn" — "ignore" items
    are filtered out. Never raises: any detection error is silently swallowed so
    the activity detail page is never broken by an insight computation failure.
    """
    insights: list[PerformanceInsight] = []
    for fn in (
        _detect_max_hr,
        _detect_lt2_hr,
        _detect_lt1_hr,
        _detect_vo2max,
        _detect_lt2_pace,
        _detect_lt1_pace,
    ):
        try:
            result = fn(activity, streams, settings)
            if result is not None and result.action != "ignore":
                insights.append(result)
        except Exception:
            pass
    return insights
