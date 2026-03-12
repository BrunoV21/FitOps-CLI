from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select

from fitops.db.models.activity import Activity
from fitops.db.models.activity_laps import ActivityLap
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.session import get_async_session


async def get_recent_activities(
    athlete_id: int,
    limit: int = 50,
    sport: Optional[str] = None,
    days: Optional[int] = None,
) -> list[Activity]:
    async with get_async_session() as session:
        q = select(Activity).where(Activity.athlete_id == athlete_id)
        if sport:
            q = q.where(Activity.sport_type == sport)
        if days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            q = q.where(Activity.start_date >= cutoff)
        q = q.order_by(Activity.start_date.desc()).limit(limit)
        result = await session.execute(q)
        return list(result.scalars().all())


async def get_activity_detail(athlete_id: int, strava_id: int) -> Optional[Activity]:
    async with get_async_session() as session:
        result = await session.execute(
            select(Activity).where(
                Activity.athlete_id == athlete_id,
                Activity.strava_id == strava_id,
            )
        )
        return result.scalar_one_or_none()


async def get_activity_laps(activity_db_id: int) -> list[ActivityLap]:
    async with get_async_session() as session:
        result = await session.execute(
            select(ActivityLap)
            .where(ActivityLap.activity_id == activity_db_id)
            .order_by(ActivityLap.lap_index)
        )
        return list(result.scalars().all())


async def get_activity_stats(athlete_id: int, days: Optional[int] = None) -> dict:
    async with get_async_session() as session:
        q = select(
            func.count(Activity.id).label("total_count"),
            func.sum(Activity.distance_m).label("total_distance_m"),
            func.sum(Activity.total_elevation_gain_m).label("total_elevation_m"),
        ).where(Activity.athlete_id == athlete_id)
        if days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            q = q.where(Activity.start_date >= cutoff)
        result = await session.execute(q)
        row = result.one()
        return {
            "total_count": row.total_count or 0,
            "total_distance_km": round((row.total_distance_m or 0) / 1000, 1),
            "total_elevation_m": round(row.total_elevation_m or 0),
        }


async def get_activity_streams(activity_db_id: int) -> dict[str, list]:
    """Return all streams for an activity as {stream_type: [values]}."""
    async with get_async_session() as session:
        result = await session.execute(
            select(ActivityStream).where(ActivityStream.activity_id == activity_db_id)
        )
        rows = result.scalars().all()
    return {row.stream_type: row.data for row in rows}


async def get_distinct_sports(athlete_id: int) -> list[str]:
    async with get_async_session() as session:
        result = await session.execute(
            select(Activity.sport_type)
            .where(Activity.athlete_id == athlete_id)
            .distinct()
            .order_by(Activity.sport_type)
        )
        return [row[0] for row in result.all()]
