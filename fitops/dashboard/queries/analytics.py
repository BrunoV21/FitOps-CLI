from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select

from fitops.analytics.training_load import (
    TrainingLoadResult,
    _compute_overtraining_indicators,
    compute_training_load,
)
from fitops.analytics.trends import TrendResult, compute_trends
from fitops.analytics.vo2max import RUN_TYPES, _estimate_from_activity
from fitops.db.models.activity import Activity
from fitops.db.session import get_async_session


async def get_training_load_data(
    athlete_id: int, days: int = 90, sport: Optional[str] = None
) -> Optional[TrainingLoadResult]:
    result = await compute_training_load(
        athlete_id=athlete_id, days=days, sport_filter=sport
    )
    if not result.history:
        return None
    return result


async def get_trends_data(
    athlete_id: int, days: int = 180, sport: Optional[str] = None
) -> Optional[TrendResult]:
    return await compute_trends(
        athlete_id=athlete_id, days=days, sport_filter=sport
    )


async def get_vo2max_history(
    athlete_id: int, days: int = 365, max_activities: int = 30
) -> list[dict]:
    """Return VO2max estimates for recent run activities, oldest first."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with get_async_session() as session:
        result = await session.execute(
            select(Activity)
            .where(
                Activity.athlete_id == athlete_id,
                Activity.sport_type.in_(list(RUN_TYPES)),
                Activity.start_date >= cutoff,
                Activity.distance_m >= 1500,
                Activity.moving_time_s > 0,
            )
            .order_by(Activity.start_date.desc())
            .limit(max_activities)
        )
        activities = result.scalars().all()

    rows = []
    for a in activities:
        est = _estimate_from_activity(a)
        if est is None:
            continue
        rows.append(
            {
                "date": a.start_date.date().isoformat() if a.start_date else "unknown",
                "name": a.name,
                "strava_id": a.strava_id,
                "distance_km": round((a.distance_m or 0) / 1000, 2),
                "estimate": est.estimate,
                "confidence": est.confidence,
                "confidence_label": est.confidence_label,
                "vdot": est.vdot,
                "cooper": est.cooper,
            }
        )

    # Return oldest first (for chart rendering)
    return list(reversed(rows))


async def get_weekly_volume(
    athlete_id: int, weeks: int = 24, sport: Optional[str] = None
) -> list[dict]:
    """Return a list of {week_start, distance_km, activity_count} dicts."""
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    async with get_async_session() as session:
        q = (
            select(Activity.start_date, Activity.distance_m, Activity.sport_type)
            .where(
                Activity.athlete_id == athlete_id,
                Activity.start_date >= cutoff,
            )
            .order_by(Activity.start_date)
        )
        if sport:
            q = q.where(Activity.sport_type == sport)
        result = await session.execute(q)
        rows = result.all()

    # Group by ISO week
    week_map: dict[str, dict] = {}
    for row in rows:
        if row.start_date is None:
            continue
        # Monday of the week
        dt = row.start_date
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        monday = dt - timedelta(days=dt.weekday())
        key = monday.strftime("%Y-%m-%d")
        if key not in week_map:
            week_map[key] = {"week_start": key, "distance_km": 0.0, "activity_count": 0}
        week_map[key]["distance_km"] += round((row.distance_m or 0) / 1000, 2)
        week_map[key]["activity_count"] += 1

    # Fill missing weeks with zeros
    all_weeks = []
    start = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    start = start - timedelta(days=start.weekday())
    for i in range(weeks):
        week_start = (start + timedelta(weeks=i)).strftime("%Y-%m-%d")
        if week_start in week_map:
            all_weeks.append(week_map[week_start])
        else:
            all_weeks.append({"week_start": week_start, "distance_km": 0.0, "activity_count": 0})

    return all_weeks
