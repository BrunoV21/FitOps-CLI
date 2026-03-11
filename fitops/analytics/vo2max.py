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
    )


async def estimate_vo2max(athlete_id: int, max_activities: int = 10) -> Optional[VO2MaxResult]:
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
    best_score = -1.0
    for activity in activities:
        est = _estimate_from_activity(activity)
        if est is None:
            continue
        score = est.confidence * (est.distance_km ** 0.3)
        if score > best_score:
            best_score = score
            best = est
    return best
