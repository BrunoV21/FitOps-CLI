from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from fitops.db.models.activity import Activity
from fitops.db.models.activity_laps import ActivityLap
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.session import get_async_session


_TAG_FILTERS: dict[str, tuple] = {
    "race": ("workout_type", 1),
    "trainer": ("trainer", True),
    "commute": ("commute", True),
    "manual": ("manual", True),
    "private": ("private", True),
}


async def get_recent_activities(
    athlete_id: int,
    limit: int = 50,
    offset: int = 0,
    sport: str | None = None,
    sport_types: frozenset | None = None,
    days: int | None = None,
    since: datetime | None = None,
    before: datetime | None = None,
    search: str | None = None,
    tag: str | None = None,
) -> list[Activity]:
    async with get_async_session() as session:
        q = select(Activity).where(Activity.athlete_id == athlete_id)
        if sport:
            q = q.where(Activity.sport_type == sport)
        elif sport_types:
            q = q.where(Activity.sport_type.in_(list(sport_types)))
        if since:
            q = q.where(Activity.start_date >= since)
        elif days:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            q = q.where(Activity.start_date >= cutoff)
        if before:
            q = q.where(Activity.start_date <= before)
        if search:
            q = q.where(Activity.name.ilike(f"%{search}%"))
        if tag and tag in _TAG_FILTERS:
            col_name, val = _TAG_FILTERS[tag]
            q = q.where(getattr(Activity, col_name) == val)
        q = q.order_by(Activity.start_date.desc()).offset(offset).limit(limit)
        result = await session.execute(q)
        return list(result.scalars().all())


async def count_activities(
    athlete_id: int,
    sport: str | None = None,
    days: int | None = None,
) -> int:
    async with get_async_session() as session:
        q = select(func.count(Activity.id)).where(Activity.athlete_id == athlete_id)
        if sport:
            q = q.where(Activity.sport_type == sport)
        if days:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            q = q.where(Activity.start_date >= cutoff)
        result = await session.execute(q)
        return result.scalar_one() or 0


async def get_activity_detail(athlete_id: int, strava_id: int) -> Activity | None:
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


async def get_activity_stats(
    athlete_id: int,
    days: int | None = None,
    since: datetime | None = None,
    sport_types: frozenset | None = None,
) -> dict:
    async with get_async_session() as session:
        q = select(
            func.count(Activity.id).label("total_count"),
            func.sum(Activity.distance_m).label("total_distance_m"),
            func.sum(Activity.total_elevation_gain_m).label("total_elevation_m"),
            func.sum(Activity.moving_time_s).label("total_moving_time_s"),
        ).where(Activity.athlete_id == athlete_id)
        if since:
            q = q.where(Activity.start_date >= since)
        elif days:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            q = q.where(Activity.start_date >= cutoff)
        if sport_types:
            q = q.where(Activity.sport_type.in_(list(sport_types)))
        result = await session.execute(q)
        row = result.one()
        total_s = row.total_moving_time_s or 0
        return {
            "total_count": row.total_count or 0,
            "total_distance_km": round((row.total_distance_m or 0) / 1000, 1),
            "total_elevation_m": round(row.total_elevation_m or 0),
            "total_duration_h": round(total_s / 3600, 1),
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
