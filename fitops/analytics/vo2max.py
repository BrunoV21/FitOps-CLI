from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, desc

from fitops.db.models.activity import Activity
from fitops.db.session import get_async_session

RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
VO2_AGE_DECLINE_RATE = 0.008
VO2_AGE_FACTOR_FLOOR = 0.5


def apply_age_adjustment(estimate: float, age: int) -> tuple[float, float]:
    """Returns (age_adjusted_estimate, age_factor)."""
    age_factor = max(VO2_AGE_FACTOR_FLOOR, 1.0 - (age - 25) * VO2_AGE_DECLINE_RATE)
    return round(estimate * age_factor, 1), round(age_factor, 3)


def _daniels_vdot(distance_m: float, time_s: float) -> Optional[float]:
    """
    Jack Daniels' VDOT — velocity-based VO2max estimate.
    Uses fractional utilization based on event duration.
    """
    if time_s <= 0 or distance_m < 1500:
        return None

    v = (distance_m / time_s) * 60  # m/min

    duration_min = time_s / 60
    if duration_min <= 3:
        frac = 1.0
    elif duration_min <= 10:
        frac = 0.98
    elif duration_min <= 20:
        frac = 0.96
    elif duration_min <= 40:
        frac = 0.94
    elif duration_min <= 60:
        frac = 0.92
    elif duration_min <= 120:
        frac = 0.88
    else:
        frac = 0.84

    vo2_demand = -4.6 + 0.182258 * v + 0.000104 * (v ** 2)
    vo2max = vo2_demand / frac
    return max(28.0, min(90.0, vo2max))


def _cooper_vo2max(distance_m: float, time_s: float) -> Optional[float]:
    """Cooper 12-min test extrapolation (for efforts > 6 min)."""
    if time_s <= 0 or distance_m < 1500:
        return None
    dist_12min = distance_m * (720 / time_s)
    vo2max = (dist_12min - 504.9) / 44.73
    return max(28.0, min(90.0, vo2max))


# Keep old names as aliases so existing test imports don't break
def _vdot(distance_m: float, time_s: float) -> Optional[float]:
    """Alias for _daniels_vdot for backward compatibility."""
    return _daniels_vdot(distance_m, time_s)


def _mcardle(distance_m: float, time_s: float) -> Optional[float]:
    """Kept for backward compatibility; delegates to _cooper_vo2max."""
    return _cooper_vo2max(distance_m, time_s)


def _costill(distance_m: float, time_s: float) -> Optional[float]:
    """Kept for backward compatibility; returns None (method removed)."""
    return None


def _confidence(distance_m: float, estimates: list[float]) -> float:
    c = 0.5
    if distance_m >= 5000:
        c += 0.2
    elif distance_m >= 3000:
        c += 0.1
    if len(estimates) >= 2:
        mean = sum(estimates) / len(estimates)
        if mean > 0:
            std = (sum((e - mean) ** 2 for e in estimates) / len(estimates)) ** 0.5
            cv = std / mean
            if cv < 0.1:
                c += 0.2
            elif cv < 0.2:
                c += 0.1
    return min(1.0, c)


@dataclass
class VO2MaxResult:
    estimate: float
    confidence: float
    vdot: Optional[float]       # daniels_vdot estimate
    cooper: Optional[float]     # cooper estimate
    activity_strava_id: int
    activity_name: str
    activity_date: str
    distance_km: float
    pace_per_km: str
    best_time_s: float = 0.0

    @property
    def confidence_label(self) -> str:
        if self.confidence >= 0.8:
            return "High"
        elif self.confidence >= 0.6:
            return "Moderate"
        return "Low"


def _fmt_pace(speed_ms: float) -> str:
    if speed_ms <= 0:
        return "N/A"
    spk = 1000 / speed_ms
    return f"{int(spk // 60)}:{int(spk % 60):02d}"


def _estimate_from_activity(activity: Activity) -> Optional[VO2MaxResult]:
    dist = activity.distance_m
    time_s = activity.moving_time_s
    if not dist or not time_s or dist < 1500:
        return None

    d_est = _daniels_vdot(dist, time_s)
    c_est = _cooper_vo2max(dist, time_s)

    # For distances >= 5km use Daniels 60% + Cooper 40%; for <5km use Daniels 100%
    if dist >= 5000:
        estimates = [e for e in [d_est, c_est] if e is not None]
        pairs = [(d_est, 0.60), (c_est, 0.40)]
    else:
        estimates = [e for e in [d_est] if e is not None]
        pairs = [(d_est, 1.0)]

    if not estimates:
        return None

    weighted = total_w = 0.0
    for est, w in pairs:
        if est is not None:
            weighted += est * w
            total_w += w
    if total_w == 0:
        return None

    return VO2MaxResult(
        estimate=round(weighted / total_w, 1),
        confidence=round(_confidence(dist, estimates), 2),
        vdot=round(d_est, 1) if d_est is not None else None,
        cooper=round(c_est, 1) if c_est is not None else None,
        activity_strava_id=activity.strava_id,
        activity_name=activity.name,
        activity_date=activity.start_date.date().isoformat() if activity.start_date else "unknown",
        distance_km=round(dist / 1000, 2),
        pace_per_km=_fmt_pace(activity.average_speed_ms) if activity.average_speed_ms else "N/A",
        best_time_s=float(time_s),
    )


async def estimate_vo2max(athlete_id: int, max_activities: int = 50) -> Optional[VO2MaxResult]:
    lookback = datetime.now(timezone.utc) - timedelta(days=365)
    async with get_async_session() as session:
        stmt = (
            select(Activity)
            .where(
                Activity.athlete_id == athlete_id,
                Activity.sport_type.in_(list(RUN_TYPES)),
                Activity.start_date >= lookback,
                Activity.distance_m >= 1500,
                Activity.moving_time_s > 0,
            )
            .order_by(desc(Activity.start_date))
            .limit(max_activities)
        )
        result = await session.execute(stmt)
        activities = result.scalars().all()

    best: Optional[VO2MaxResult] = None
    for activity in activities:
        est = _estimate_from_activity(activity)
        if est is None:
            continue
        # Pick the activity with the highest VO2max estimate — that's the hardest effort
        # and the best signal for true aerobic ceiling. Confidence acts as a tiebreaker
        # only when estimates are within 1 ml/kg/min of each other.
        if best is None or est.estimate > best.estimate + 1.0 or (
            abs(est.estimate - best.estimate) <= 1.0 and est.confidence > best.confidence
        ):
            best = est
    return best


# ---------------------------------------------------------------------------
# Race Predictions
# ---------------------------------------------------------------------------

RIEGEL_EXP = 1.06
RACE_DISTANCES = {
    "5K": 5000.0,
    "10K": 10000.0,
    "Half": 21097.5,
    "Marathon": 42195.0,
}


def _riegel(d1_m: float, t1_s: float, d2_m: float) -> float:
    return t1_s * (d2_m / d1_m) ** RIEGEL_EXP


def _fmt_hms(total_s: float) -> str:
    h = int(total_s // 3600)
    m = int((total_s % 3600) // 60)
    s = int(total_s % 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_pace_from_s(time_s: float, dist_m: float) -> str:
    pace_s = time_s / (dist_m / 1000)
    return f"{int(pace_s // 60)}:{int(pace_s % 60):02d}"


# ---------------------------------------------------------------------------
# Rolling VO2max — ratchet model
# ---------------------------------------------------------------------------

# Minimum confidence for an activity to *update* the rolling estimate.
# confidence ≥ 0.6 requires distance ≥ 5 km plus consistent VDOT/Cooper agreement.
_QUALIFY_CONFIDENCE = 0.6

# After GRACE_DAYS of no qualifying effort, VO2max starts to decay.
_DECAY_GRACE_DAYS = 14

# Exponential decay rate per week beyond the grace period (~0.5%/week; full
# detraining is ~1-2%/week, regular easy training halves that).
_DECAY_RATE_PER_WEEK = 0.005

# How much of a qualifying activity's downward signal to absorb (0.2 = damped).
# Upward signals are absorbed fully.
_DECREASE_DAMPING = 0.2


def compute_vo2max_rolling(history: list[dict], initial: Optional[float] = None) -> list[dict]:
    """
    Apply a ratchet model to the per-activity VO2max history (oldest first).

    Rules:
    - Only "qualifying" activities (confidence ≥ 0.6, i.e. ≥5 km good-effort runs)
      can move the rolling estimate.
    - A qualifying activity raises the rolling value immediately and fully.
    - A qualifying activity that is lower than the current value only damps it down
      by DECREASE_DAMPING (20%) of the gap — a single easy 5km doesn't wipe fitness.
    - Non-qualifying activities (short, slow, easy) leave the rolling value unchanged.
    - After DECAY_GRACE_DAYS with no qualifying effort, the estimate decays at
      DECAY_RATE_PER_WEEK — modelling real detraining.

    Adds ``rolling_vo2max`` and ``is_qualifying`` to each entry in-place.
    Returns the same list.

    ``initial`` should be the athlete's known best VO2max estimate (e.g. from the
    all-time best qualifying effort).  This anchors the rolling value so it starts
    from peak fitness rather than from whichever easy run happens to be first in the
    selected time window.  When None the first qualifying activity bootstraps the value.
    """
    if not history:
        return history

    from datetime import date as _date

    def _parse(d: str) -> _date:
        try:
            return _date.fromisoformat(d)
        except ValueError:
            return _date.today()

    rolling: Optional[float] = initial
    last_qualifying_date: Optional[_date] = None

    for row in history:
        activity_date = _parse(row["date"])
        estimate = row.get("estimate", 0.0)
        confidence = row.get("confidence", 0.0)
        is_qualifying = confidence >= _QUALIFY_CONFIDENCE

        # Apply decay if we have an established estimate and qualifying activity is overdue
        if rolling is not None and last_qualifying_date is not None:
            days_gap = (activity_date - last_qualifying_date).days
            if days_gap > _DECAY_GRACE_DAYS:
                extra_weeks = (days_gap - _DECAY_GRACE_DAYS) / 7.0
                rolling = rolling * (1 - _DECAY_RATE_PER_WEEK) ** extra_weeks

        if rolling is None:
            # No initial given: bootstrap from first qualifying activity only
            if is_qualifying:
                rolling = estimate
                last_qualifying_date = activity_date
        elif is_qualifying:
            if estimate >= rolling:
                rolling = estimate  # full increase
            else:
                rolling = rolling + _DECREASE_DAMPING * (estimate - rolling)  # damped decrease
            last_qualifying_date = activity_date
        # else: non-qualifying — rolling stays as is (possibly already decayed above)

        row["rolling_vo2max"] = round(rolling, 1)
        row["is_qualifying"] = is_qualifying

    return history


# ---------------------------------------------------------------------------
# Race Predictions
# ---------------------------------------------------------------------------
#
# Industry standard (Jack Daniels VDOT system, Pfitzinger):
#   Everything derives from ONE consistent effort.  When a measured LT2 pace
#   is available it is the most reliable anchor because it reflects how the
#   individual athlete's aerobic system actually performs, not a theoretical
#   estimate from a training run.
#
# LT2 → race pace ratios from Daniels VDOT tables (averaged VDOT 40–65):
#   5K ≈ 7.6% faster than LT2 pace/km
#   10K ≈ 3.8% faster
#   Half ≈ 2.0% slower
#   Marathon ≈ 7.0% slower
#
# Riegel (T2 = T1 × (D2/D1)^1.06) is shown alongside for reference but is
# only reliable when the source effort was near-maximal (race or time-trial).
# It is NOT reliable from easy or moderate training runs.

_LT2_RACE_PACE_RATIOS: dict[str, float] = {
    "5K":       0.924,
    "10K":      0.962,
    "Half":     1.020,
    "Marathon": 1.070,
}


def vo2max_from_lt2_pace(lt2_pace_s: float) -> float:
    """
    Back-calculate VO2max from a measured LT2 pace (sec/km).

    LT2 is assumed to occur at 88% of VO2max (Daniels standard).
    Uses the same VO2-demand quadratic as _daniels_vdot, solved at LT2 speed.
    """
    v_mpm = (1000.0 / lt2_pace_s) * 60.0  # m/min
    vo2_demand = -4.6 + 0.182258 * v_mpm + 0.000104 * v_mpm ** 2
    return round(max(28.0, min(90.0, vo2_demand / 0.88)), 1)


def _pred_entry(pred_s: float, d2_m: float) -> dict:
    return {
        "distance_km": round(d2_m / 1000, 4),
        "predicted_time_s": round(pred_s),
        "predicted_pace": _fmt_pace_from_s(pred_s, d2_m),
        "hms": _fmt_hms(pred_s),
    }


def compute_race_predictions(
    vo2_result: "VO2MaxResult",
    lt2_pace_s: Optional[float] = None,
) -> dict:
    """
    Predict race times using two complementary methods.

    LT2-anchored (primary when lt2_pace_s is set):
        Derives race paces from the measured threshold pace via Daniels VDOT
        table ratios.  This is internally consistent — if your LT2 pace hasn't
        changed, your race predictions won't change either, regardless of what
        any individual training run suggests about your VO2max.

    Riegel (always computed as secondary / reference):
        T2 = T1 × (D2/D1)^1.06 from the best recorded effort.
        Only accurate when the source effort was near-maximal.  Shown dimmed
        in the UI so the user can compare.
    """
    out: dict = {}

    # --- LT2-anchored predictions ---
    if lt2_pace_s is not None:
        lt2_preds = {}
        for label, d2_m in RACE_DISTANCES.items():
            pace_s = lt2_pace_s * _LT2_RACE_PACE_RATIOS[label]
            lt2_preds[label] = _pred_entry(pace_s * (d2_m / 1000), d2_m)
        out["lt2_predictions"] = lt2_preds
        out["lt2_source_pace"] = f"{int(lt2_pace_s // 60)}:{int(lt2_pace_s % 60):02d}"
        out["lt2_implied_vo2max"] = vo2max_from_lt2_pace(lt2_pace_s)

    # --- Riegel predictions ---
    d1_m = vo2_result.distance_km * 1000
    t1_s = vo2_result.best_time_s
    if t1_s > 0 and d1_m > 0:
        riegel_preds = {}
        for label, d2_m in RACE_DISTANCES.items():
            riegel_preds[label] = _pred_entry(_riegel(d1_m, t1_s, d2_m), d2_m)
        out["riegel_predictions"] = riegel_preds
        out["riegel_source_distance_km"] = vo2_result.distance_km
        out["riegel_source_pace"] = vo2_result.pace_per_km
        out["riegel_source_confidence"] = vo2_result.confidence_label

    # Back-compat: expose ``predictions`` pointing at the most reliable method
    if "lt2_predictions" in out:
        out["predictions"] = out["lt2_predictions"]
        out["method"] = "lt2"
    elif "riegel_predictions" in out:
        out["predictions"] = out["riegel_predictions"]
        out["method"] = "riegel"

    return out
