from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, desc

from fitops.db.models.activity import Activity
from fitops.db.models.athlete import Athlete
from fitops.db.session import get_async_session

RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
RIDE_TYPES = {"Ride", "VirtualRide", "EBikeRide"}


def _percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    sv = sorted(values)
    idx = (pct / 100) * (len(sv) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sv) - 1)
    return sv[lo] + (idx - lo) * (sv[hi] - sv[lo])


def _cv(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
    return std / mean


@dataclass
class PerformanceMetricsResult:
    sport: str
    activity_count: int
    running: Optional[dict]
    cycling: Optional[dict]
    overall_reliability: Optional[float]


async def compute_performance_metrics(
    athlete_id: int,
    sport: Optional[str] = None,
) -> Optional[PerformanceMetricsResult]:
    lookback = datetime.now(timezone.utc) - timedelta(days=365)

    # Normalise sport arg
    if sport and sport.lower() in ("run", "running"):
        sport_types = list(RUN_TYPES)
        target = "Run"
    elif sport and sport.lower() in ("ride", "cycling", "bike"):
        sport_types = list(RIDE_TYPES)
        target = "Ride"
    else:
        sport_types = list(RUN_TYPES)
        target = "Run"

    async with get_async_session() as session:
        ath_res = await session.execute(
            select(Athlete).where(Athlete.strava_id == athlete_id)
        )
        athlete = ath_res.scalar_one_or_none()
        weight_kg = athlete.weight_kg if athlete else None

        stmt = (
            select(Activity)
            .where(
                Activity.athlete_id == athlete_id,
                Activity.sport_type.in_(sport_types),
                Activity.start_date >= lookback,
            )
            .order_by(desc(Activity.start_date))
            .limit(50)
        )
        result = await session.execute(stmt)
        activities = result.scalars().all()

    if not activities:
        return None

    if target == "Run":
        paces = [
            1000 / a.average_speed_ms / 60
            for a in activities if a.average_speed_ms and a.average_speed_ms > 0
        ]
        # Only use peak HR (max_heartrate field), not average HR — pooling them biases 98th percentile low
        all_hr = [float(a.max_heartrate) for a in activities if a.max_heartrate]

        avg_pace = sum(paces) / len(paces) if paces else None
        # Proper running economy: VO2 demand (ml/kg/min) / speed (km/min) = ml/kg/km
        # Uses Daniels VO2 demand quadratic, same formula as VDOT calculation
        if avg_pace and avg_pace > 0:
            v_mpm = 1000.0 / avg_pace  # m/min (avg_pace is min/km)
            vo2_demand = -4.6 + 0.182258 * v_mpm + 0.000104 * v_mpm ** 2
            economy = round(max(100.0, min(350.0, vo2_demand / (v_mpm / 1000))), 1)  # ml/kg/km
        else:
            economy = None
        pace_cv = _cv(paces)
        efficiency = round(max(0.0, 100 - pace_cv * 100), 1) if paces else None
        variability = round(pace_cv, 4) if paces else None

        max_hr_est = aerobic_thr = anaerobic_thr = None
        if all_hr:
            raw = _percentile(all_hr, 98)
            if raw:
                max_hr_est = round(raw)
                aerobic_thr = round(max_hr_est * 0.75)
                anaerobic_thr = round(max_hr_est * 0.85)

        running = {
            "running_economy_ml_kg_km": economy,
            "pace_efficiency_score": efficiency,
            "variability_index": variability,
            "max_hr_estimate": max_hr_est,
            "aerobic_threshold_hr": aerobic_thr,
            "anaerobic_threshold_hr": anaerobic_thr,
        }
        overall_reliability = round(efficiency / 100, 3) if efficiency else None
        cycling = None

    else:
        powers = [a.average_watts for a in activities if a.average_watts]
        np_ratios = [
            a.weighted_average_watts / a.average_watts
            for a in activities
            if a.weighted_average_watts and a.average_watts and a.average_watts > 0
        ]

        ftp = ptw = np_ratio = power_consistency = variability = None
        if powers:
            mean_pow = sum(powers) / len(powers)
            ftp = round(mean_pow * 0.95, 1)
            if weight_kg and weight_kg > 0:
                ptw = round(ftp / weight_kg, 2)
        if np_ratios:
            np_ratio = round(sum(np_ratios) / len(np_ratios), 3)
        if powers:
            cv = _cv(powers)
            power_consistency = round(max(0.0, 100 - cv * 100), 1)
            variability = round(cv, 4)

        cycling = {
            "ftp_estimate_watts": ftp,
            "power_to_weight_w_kg": ptw,
            "normalized_power_ratio": np_ratio,
            "power_consistency": power_consistency,
            "variability_index": variability,
        }
        overall_reliability = round(power_consistency / 100, 3) if power_consistency else None
        running = None

    return PerformanceMetricsResult(
        sport=target,
        activity_count=len(activities),
        running=running,
        cycling=cycling,
        overall_reliability=overall_reliability,
    )
