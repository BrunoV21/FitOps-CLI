from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from fitops.db.models.activity import Activity
from fitops.db.session import get_async_session

TREND_WEAK = 0.1
TREND_MODERATE = 0.3
PACE_IMPROVING = -0.01
HR_IMPROVING = -0.5


def _linear_regression(x: list[float], y: list[float]) -> tuple[float, float]:
    n = len(x)
    if n < 2:
        return 0.0, (y[0] if y else 0.0)
    sx, sy = sum(x), sum(y)
    sxx = sum(xi * xi for xi in x)
    sxy = sum(xi * yi for xi, yi in zip(x, y))
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0, sy / n
    slope = (n * sxy - sx * sy) / denom
    return slope, (sy - slope * sx) / n


def _trend_strength(slope: float) -> str:
    a = abs(slope)
    if a < TREND_WEAK:
        return "weak"
    elif a < TREND_MODERATE:
        return "moderate"
    return "strong"


def _pace_direction(slope: float) -> str:
    if slope < PACE_IMPROVING:
        return "improving"
    elif slope > 0.01:
        return "declining"
    return "stable"


def _hr_direction(slope: float) -> str:
    if slope < HR_IMPROVING:
        return "improving"
    elif slope > 0.5:
        return "declining"
    return "stable"


def _season(month: int) -> str:
    if month in (3, 4, 5):
        return "Spring"
    elif month in (6, 7, 8):
        return "Summer"
    elif month in (9, 10, 11):
        return "Autumn"
    return "Winter"


@dataclass
class TrendResult:
    sport_filter: Optional[str]
    days: int
    activity_count: int
    volume_trend: dict
    consistency: dict
    seasonal: dict
    performance_trend: dict
    summary_label: str


async def compute_trends(
    athlete_id: int,
    days: int = 180,
    sport_filter: Optional[str] = None,
    sport_types: Optional[frozenset] = None,
) -> Optional[TrendResult]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_async_session() as session:
        stmt = select(Activity).where(
            Activity.athlete_id == athlete_id,
            Activity.start_date >= cutoff,
        )
        if sport_filter:
            stmt = stmt.where(Activity.sport_type == sport_filter)
        elif sport_types:
            stmt = stmt.where(Activity.sport_type.in_(list(sport_types)))
        stmt = stmt.order_by(Activity.start_date)
        result = await session.execute(stmt)
        activities = result.scalars().all()

    if not activities:
        return None

    # --- Weekly volume ---
    weekly: dict[tuple, list] = defaultdict(list)
    for act in activities:
        if act.start_date:
            iso = act.start_date.isocalendar()
            weekly[(iso.year, iso.week)].append(act)

    sorted_weeks = sorted(weekly.keys())
    weekly_data = []
    for wk in sorted_weeks:
        acts = weekly[wk]
        total_km = sum((a.distance_m or 0) / 1000 for a in acts)
        weekly_data.append({
            "week": f"{wk[0]}-W{wk[1]:02d}",
            "distance_km": round(total_km, 2),
            "activity_count": len(acts),
        })

    if len(weekly_data) >= 2:
        x = list(range(len(weekly_data)))
        y = [w["distance_km"] for w in weekly_data]
        vol_slope, _ = _linear_regression(x, y)
        vol_direction = "increasing" if vol_slope > 0.5 else ("decreasing" if vol_slope < -0.5 else "stable")
    else:
        vol_slope, vol_direction = 0.0, "stable"

    volume_trend = {
        "slope_km_per_week": round(vol_slope, 3),
        "direction": vol_direction,
        "strength": _trend_strength(vol_slope),
        "weekly_averages": weekly_data,
    }

    # --- Consistency ---
    dated = [a for a in activities if a.start_date]
    if len(dated) >= 2:
        gaps = [
            (dated[i].start_date - dated[i - 1].start_date).total_seconds() / 86400
            for i in range(1, len(dated))
        ]
        gap_std = statistics.stdev(gaps) if len(gaps) >= 2 else 0.0
        consistency_score = max(0.0, min(1.0, 1.0 - gap_std / 7.0))
        avg_gap = sum(gaps) / len(gaps)
    else:
        consistency_score, avg_gap = 0.0, None

    total_weeks = max(1, len(sorted_weeks))
    weeks_active = len([w for w in weekly_data if w["activity_count"] > 0])
    weekly_consistency = weeks_active / total_weeks

    activities_per_week = len(activities) / max(1, days / 7)
    consistency = {
        "consistency_score": round(consistency_score, 3),
        "weekly_consistency": round(weekly_consistency, 3),
        "regularity_score": round(weekly_consistency, 3),
        "activities_per_week": round(activities_per_week, 1),
        "avg_days_between_activities": round(avg_gap, 1) if avg_gap else None,
    }

    # --- Seasonal ---
    seasonal_acts: dict[str, list] = defaultdict(list)
    for act in activities:
        if act.start_date:
            seasonal_acts[_season(act.start_date.month)].append(act)

    season_stats: dict[str, dict] = {}
    for season, acts in seasonal_acts.items():
        total_km = sum((a.distance_m or 0) / 1000 for a in acts)
        paces = [
            1000 / a.average_speed_ms / 60
            for a in acts if a.average_speed_ms and a.average_speed_ms > 0
        ]
        season_stats[season] = {
            "activity_count": len(acts),
            "total_distance_km": round(total_km, 2),
            "avg_pace_min_per_km": round(sum(paces) / len(paces), 2) if paces else None,
        }

    peak_season = (
        max(seasonal_acts.keys(), key=lambda s: sum((a.distance_m or 0) for a in seasonal_acts[s]))
        if seasonal_acts else None
    )

    seasonal = {"seasons": season_stats, "peak_season": peak_season}

    # --- Performance trends (monthly) ---
    monthly_pace: dict[tuple, list] = defaultdict(list)
    monthly_hr: dict[tuple, list] = defaultdict(list)
    for act in activities:
        if act.start_date:
            key = (act.start_date.year, act.start_date.month)
            if act.average_speed_ms and act.average_speed_ms > 0:
                monthly_pace[key].append(1000 / act.average_speed_ms / 60)
            if act.average_heartrate:
                monthly_hr[key].append(act.average_heartrate)

    pace_slope = hr_slope = None
    pace_direction = hr_direction = improvement_rate = None

    if len(monthly_pace) >= 2:
        sm = sorted(monthly_pace.keys())
        x = list(range(len(sm)))
        y = [sum(monthly_pace[m]) / len(monthly_pace[m]) for m in sm]
        pace_slope, _ = _linear_regression(x, y)
        pace_direction = _pace_direction(pace_slope)
        if len(y) >= 2:
            improvement_rate = (y[-1] - y[0]) / max(y[0], 0.01) * 100 / max(1, len(y) - 1)

    if len(monthly_hr) >= 2:
        sh = sorted(monthly_hr.keys())
        xh = list(range(len(sh)))
        yh = [sum(monthly_hr[m]) / len(monthly_hr[m]) for m in sh]
        hr_slope, _ = _linear_regression(xh, yh)
        hr_direction = _hr_direction(hr_slope)

    performance_trend = {
        "pace_slope": round(pace_slope, 4) if pace_slope is not None else None,
        "pace_direction": pace_direction,
        "pace_trend": pace_direction,
        "pace_strength": _trend_strength(pace_slope) if pace_slope is not None else "weak",
        "hr_slope": round(hr_slope, 3) if hr_slope is not None else None,
        "hr_direction": hr_direction,
        "improvement_rate_pct_per_month": round(improvement_rate, 2) if improvement_rate is not None else None,
    }

    # Summary
    parts = []
    if vol_direction == "increasing" and _trend_strength(vol_slope) in ("moderate", "strong"):
        parts.append("volume building")
    elif vol_direction == "decreasing" and _trend_strength(vol_slope) in ("moderate", "strong"):
        parts.append("volume declining")
    if weekly_consistency >= 0.8:
        parts.append("consistent training")
    elif weekly_consistency < 0.5:
        parts.append("inconsistent schedule")
    if pace_direction == "improving":
        parts.append("pace improving")
    elif pace_direction == "declining":
        parts.append("pace declining")
    summary = ", ".join(parts) if parts else "stable training"

    return TrendResult(
        sport_filter=sport_filter,
        days=days,
        activity_count=len(activities),
        volume_trend=volume_trend,
        consistency=consistency,
        seasonal=seasonal,
        performance_trend=performance_trend,
        summary_label=summary,
    )
