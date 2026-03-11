from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, desc

from fitops.db.models.activity import Activity
from fitops.db.session import get_async_session

RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
VDOT_DISTANCE_FACTORS = {1500: 1.00, 3000: 0.98, 5000: 0.96, 10000: 0.94, 21097: 0.92, 42195: 0.90}
VO2_AGE_DECLINE_RATE = 0.008
VO2_AGE_FACTOR_FLOOR = 0.5


def apply_age_adjustment(estimate: float, age: int) -> tuple[float, float]:
    """Returns (age_adjusted_estimate, age_factor)."""
    age_factor = max(VO2_AGE_FACTOR_FLOOR, 1.0 - (age - 25) * VO2_AGE_DECLINE_RATE)
    return round(estimate * age_factor, 1), round(age_factor, 3)


def _get_distance_factor(distance_m: float) -> float:
    for t in sorted(VDOT_DISTANCE_FACTORS):
        if distance_m <= t * 1.05:
            return VDOT_DISTANCE_FACTORS[t]
    return VDOT_DISTANCE_FACTORS[42195]


def _vdot(distance_m: float, time_s: float) -> Optional[float]:
    if time_s <= 0 or distance_m <= 0:
        return None
    v = (distance_m / time_s) * 60
    raw = -4.6 + 0.182258 * v + 0.000104 * (v ** 2)
    return max(30.0, min(85.0, raw * _get_distance_factor(distance_m)))


def _mcardle(distance_m: float, time_s: float) -> Optional[float]:
    if time_s <= 0 or distance_m <= 0:
        return None
    return max(30.0, min(85.0, 15.0 + 0.2 * (distance_m / time_s) * 60))


def _costill(distance_m: float, time_s: float) -> Optional[float]:
    if time_s <= 0 or distance_m < 1500:
        return None
    base = 15.3 * (distance_m / time_s) - 5.0
    correction = 0.95 if distance_m >= 10000 else (0.97 if distance_m >= 5000 else 1.0)
    return max(30.0, min(85.0, base * correction))


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
    vdot: Optional[float]
    mcardle: Optional[float]
    costill: Optional[float]
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
    v_est = _vdot(dist, time_s)
    m_est = _mcardle(dist, time_s)
    c_est = _costill(dist, time_s)
    estimates = [e for e in [v_est, m_est, c_est] if e is not None]
    if not estimates:
        return None
    weights = [0.50, 0.20, 0.30] if dist >= 5000 else [0.50, 0.30, 0.20]
    weighted = total_w = 0.0
    for est, w in zip([v_est, m_est, c_est], weights):
        if est is not None:
            weighted += est * w
            total_w += w
    if total_w == 0:
        return None
    return VO2MaxResult(
        estimate=round(weighted / total_w, 1),
        confidence=round(_confidence(dist, estimates), 2),
        vdot=round(v_est, 1) if v_est else None,
        mcardle=round(m_est, 1) if m_est else None,
        costill=round(c_est, 1) if c_est else None,
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
