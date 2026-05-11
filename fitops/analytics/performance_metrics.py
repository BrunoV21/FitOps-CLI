from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select

from fitops.db.models.activity import Activity
from fitops.db.models.athlete import Athlete
from fitops.db.session import get_async_session

RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
RIDE_TYPES = {"Ride", "VirtualRide", "EBikeRide"}


def _percentile(values: list[float], pct: float) -> float | None:
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


def _format_pace_from_speed(speed_ms: float) -> str | None:
    if speed_ms <= 0:
        return None
    pace_s = 1000.0 / speed_ms
    return f"{int(pace_s // 60)}:{int(pace_s % 60):02d}/km"


def _weighted_mean(rows: list[dict], key: str) -> float | None:
    total_weight = sum(row["weight"] for row in rows)
    if total_weight <= 0:
        return None
    return sum(row[key] * row["weight"] for row in rows) / total_weight


def _compute_aerobic_efficiency_trend(activities: list[Activity]) -> dict | None:
    """Compare early-vs-recent speed per heartbeat for runs in the window."""
    rows = []
    fallback_date = datetime.min.replace(tzinfo=UTC)
    for activity in sorted(activities, key=lambda a: a.start_date or fallback_date):
        if (
            not activity.average_speed_ms
            or activity.average_speed_ms <= 0
            or not activity.average_heartrate
            or activity.average_heartrate <= 0
        ):
            continue
        rows.append(
            {
                "speed_ms": float(activity.average_speed_ms),
                "avg_hr_bpm": float(activity.average_heartrate),
                "weight": max(float(activity.distance_m or 0), 1.0),
            }
        )

    if len(rows) < 6:
        return None

    mid = len(rows) // 2
    baseline = rows[:mid]
    recent = rows[mid:]

    baseline_speed = _weighted_mean(baseline, "speed_ms")
    baseline_hr = _weighted_mean(baseline, "avg_hr_bpm")
    recent_speed = _weighted_mean(recent, "speed_ms")
    recent_hr = _weighted_mean(recent, "avg_hr_bpm")
    if not all([baseline_speed, baseline_hr, recent_speed, recent_hr]):
        return None

    baseline_efficiency = baseline_speed / baseline_hr
    recent_efficiency = recent_speed / recent_hr
    if baseline_efficiency <= 0 or recent_efficiency <= 0:
        return None

    benchmark_speed = recent_speed
    baseline_hr_at_benchmark = benchmark_speed / baseline_efficiency
    recent_hr_at_benchmark = benchmark_speed / recent_efficiency
    if baseline_hr_at_benchmark <= 0:
        return None

    hr_change_bpm = recent_hr_at_benchmark - baseline_hr_at_benchmark
    efficiency_change_pct = (recent_efficiency / baseline_efficiency - 1) * 100
    hr_change_pct = hr_change_bpm / baseline_hr_at_benchmark * 100

    if efficiency_change_pct >= 3:
        label = "improving"
    elif efficiency_change_pct <= -3:
        label = "declining"
    else:
        label = "stable"

    return {
        "activity_count": len(rows),
        "benchmark_pace_s_per_km": round(1000.0 / benchmark_speed, 1),
        "benchmark_pace_per_km": _format_pace_from_speed(benchmark_speed),
        "baseline_hr_at_benchmark_bpm": round(baseline_hr_at_benchmark, 1),
        "recent_hr_at_benchmark_bpm": round(recent_hr_at_benchmark, 1),
        "hr_change_bpm": round(hr_change_bpm, 1),
        "hr_change_pct": round(hr_change_pct, 1),
        "efficiency_change_pct": round(efficiency_change_pct, 1),
        "baseline_efficiency_factor": round(baseline_efficiency, 5),
        "recent_efficiency_factor": round(recent_efficiency, 5),
        "trend_label": label,
    }


@dataclass
class PerformanceMetricsResult:
    sport: str
    days: int
    activity_count: int
    running: dict | None
    cycling: dict | None
    overall_reliability: float | None


async def compute_performance_metrics(
    athlete_id: int,
    sport: str | None = None,
    days: int = 365,
) -> PerformanceMetricsResult | None:
    lookback = datetime.now(UTC) - timedelta(days=days)

    # Normalise sport arg
    sport_key = sport.lower() if sport else None
    if sport_key in ("run", "running"):
        sport_types = list(RUN_TYPES)
        target = "Run"
    elif sport_key in ("ride", "cycling", "bike"):
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
            for a in activities
            if a.average_speed_ms and a.average_speed_ms > 0
        ]
        avg_pace = sum(paces) / len(paces) if paces else None
        # Proper running economy: VO2 demand (ml/kg/min) / speed (km/min) = ml/kg/km
        # Uses Daniels VO2 demand quadratic, same formula as VDOT calculation
        if avg_pace and avg_pace > 0:
            v_mpm = 1000.0 / avg_pace  # m/min (avg_pace is min/km)
            vo2_demand = -4.6 + 0.182258 * v_mpm + 0.000104 * v_mpm**2
            economy = round(
                max(100.0, min(350.0, vo2_demand / (v_mpm / 1000))), 1
            )  # ml/kg/km
        else:
            economy = None
        pace_cv = _cv(paces)
        efficiency = round(max(0.0, 100 - pace_cv * 100), 1) if paces else None
        variability = round(pace_cv, 4) if paces else None

        running = {
            "running_economy_ml_kg_km": economy,
            "pace_efficiency_score": efficiency,
            "variability_index": variability,
            "aerobic_efficiency_trend": _compute_aerobic_efficiency_trend(activities),
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
        overall_reliability = (
            round(power_consistency / 100, 3) if power_consistency else None
        )
        running = None

    return PerformanceMetricsResult(
        sport=target,
        days=days,
        activity_count=len(activities),
        running=running,
        cycling=cycling,
        overall_reliability=overall_reliability,
    )
