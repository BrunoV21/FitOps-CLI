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

RUNNING_SPORTS = frozenset({"Run", "TrailRun", "Walk", "Hike", "VirtualRun"})
RIDING_SPORTS = frozenset({"Ride", "VirtualRide", "EBikeRide"})


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
    athlete_id: int,
    days: int = 180,
    sport: Optional[str] = None,
    sport_types: Optional[frozenset] = None,
) -> Optional[TrendResult]:
    return await compute_trends(
        athlete_id=athlete_id, days=days, sport_filter=sport, sport_types=sport_types
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
    athlete_id: int,
    weeks: int = 24,
    sport: Optional[str] = None,
    sport_types: Optional[frozenset] = None,
) -> list[dict]:
    """Return a list of {week_start, distance_km, duration_h, activity_count} dicts."""
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    async with get_async_session() as session:
        q = (
            select(Activity.start_date, Activity.distance_m, Activity.moving_time_s, Activity.sport_type)
            .where(
                Activity.athlete_id == athlete_id,
                Activity.start_date >= cutoff,
            )
            .order_by(Activity.start_date)
        )
        if sport:
            q = q.where(Activity.sport_type == sport)
        elif sport_types:
            q = q.where(Activity.sport_type.in_(list(sport_types)))
        result = await session.execute(q)
        rows = result.all()

    # Group by ISO week
    week_map: dict[str, dict] = {}
    for row in rows:
        if row.start_date is None:
            continue
        dt = row.start_date
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        monday = dt - timedelta(days=dt.weekday())
        key = monday.strftime("%Y-%m-%d")
        if key not in week_map:
            week_map[key] = {"week_start": key, "distance_km": 0.0, "duration_h": 0.0, "activity_count": 0}
        week_map[key]["distance_km"] += (row.distance_m or 0) / 1000
        week_map[key]["duration_h"] += (row.moving_time_s or 0) / 3600
        week_map[key]["activity_count"] += 1

    # Round accumulated values and fill missing weeks with zeros
    for v in week_map.values():
        v["distance_km"] = round(v["distance_km"], 2)
        v["duration_h"] = round(v["duration_h"], 3)

    all_weeks = []
    start = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    start = start - timedelta(days=start.weekday())
    for i in range(weeks):
        week_start = (start + timedelta(weeks=i)).strftime("%Y-%m-%d")
        if week_start in week_map:
            all_weeks.append(week_map[week_start])
        else:
            all_weeks.append({"week_start": week_start, "distance_km": 0.0, "duration_h": 0.0, "activity_count": 0})

    return all_weeks


async def get_volume_summary(
    athlete_id: int,
    sport: Optional[str] = None,
    sport_types: Optional[frozenset] = None,
) -> dict:
    """Return this/last week and this/last month volume with percentage changes.

    Week = Monday–Sunday (ISO week).
    Month = calendar month (1st to last day).
    Month % change = same day-of-month period in previous month (apples-to-apples).
    """
    today = datetime.now(timezone.utc)

    # --- Week boundaries (Monday 00:00 UTC) ---
    this_monday = (today - timedelta(days=today.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    last_monday = this_monday - timedelta(weeks=1)

    # --- Month boundaries ---
    first_of_this_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if first_of_this_month.month == 1:
        first_of_last_month = first_of_this_month.replace(
            year=first_of_this_month.year - 1, month=12
        )
    else:
        first_of_last_month = first_of_this_month.replace(
            month=first_of_this_month.month - 1
        )

    # Single query covers all four windows
    cutoff = min(last_monday, first_of_last_month)
    async with get_async_session() as session:
        q = (
            select(Activity.start_date, Activity.distance_m, Activity.moving_time_s)
            .where(
                Activity.athlete_id == athlete_id,
                Activity.start_date >= cutoff,
            )
        )
        if sport:
            q = q.where(Activity.sport_type == sport)
        elif sport_types:
            q = q.where(Activity.sport_type.in_(list(sport_types)))
        result = await session.execute(q)
        rows = result.all()

    def _empty() -> dict:
        return {"distance_km": 0.0, "duration_h": 0.0, "activity_count": 0}

    this_week = _empty()
    last_week = _empty()
    this_month = _empty()
    last_month = _empty()
    last_month_same_period = _empty()  # up to same day-of-month as today (for % calc)

    for row in rows:
        if row.start_date is None:
            continue
        dt = row.start_date
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        d_km = (row.distance_m or 0) / 1000
        d_h = (row.moving_time_s or 0) / 3600

        # Week dimension
        if dt >= this_monday:
            this_week["distance_km"] += d_km
            this_week["duration_h"] += d_h
            this_week["activity_count"] += 1
        elif dt >= last_monday:
            last_week["distance_km"] += d_km
            last_week["duration_h"] += d_h
            last_week["activity_count"] += 1

        # Month dimension (independent of week dimension)
        if dt >= first_of_this_month:
            this_month["distance_km"] += d_km
            this_month["duration_h"] += d_h
            this_month["activity_count"] += 1
        elif dt >= first_of_last_month:
            # Full previous calendar month for display
            last_month["distance_km"] += d_km
            last_month["duration_h"] += d_h
            last_month["activity_count"] += 1
            # Same-period slice for % comparison
            if dt.day <= today.day:
                last_month_same_period["distance_km"] += d_km
                last_month_same_period["duration_h"] += d_h
                last_month_same_period["activity_count"] += 1

    for bucket in (this_week, last_week, this_month, last_month, last_month_same_period):
        bucket["distance_km"] = round(bucket["distance_km"], 2)
        bucket["duration_h"] = round(bucket["duration_h"], 3)

    def _pct(current: float, previous: float) -> Optional[float]:
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    return {
        "this_week": this_week,
        "last_week": last_week,
        "this_month": this_month,
        "last_month": last_month,
        "pct_change_week": {
            "distance": _pct(this_week["distance_km"], last_week["distance_km"]),
            "duration": _pct(this_week["duration_h"], last_week["duration_h"]),
        },
        "pct_change_month": {
            # Compare Mar 1-14 vs Feb 1-14, not Mar 1-14 vs all of Feb
            "distance": _pct(this_month["distance_km"], last_month_same_period["distance_km"]),
            "duration": _pct(this_month["duration_h"], last_month_same_period["duration_h"]),
        },
    }
