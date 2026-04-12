from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select

from fitops.db.models.race_course import RaceCourse
from fitops.db.models.race_plan import RacePlan
from fitops.db.session import get_async_session


async def save_course(
    name: str,
    source: str,
    source_ref: str | None,
    file_format: str | None,
    course_points: list[dict],
    km_segments: list[dict],
    total_distance_m: float,
    total_elevation_gain_m: float,
) -> dict:
    """Persist a new RaceCourse row and return its summary dict."""
    start_lat: float | None = None
    start_lon: float | None = None
    if course_points:
        start_lat = course_points[0]["lat"]
        start_lon = course_points[0]["lon"]

    course = RaceCourse(
        name=name,
        source=source,
        source_ref=source_ref,
        file_format=file_format,
        total_distance_m=total_distance_m,
        total_elevation_gain_m=total_elevation_gain_m,
        num_points=len(course_points),
        start_lat=start_lat,
        start_lon=start_lon,
        course_points_json=json.dumps(course_points),
        km_segments_json=json.dumps(km_segments),
    )

    async with get_async_session() as session:
        session.add(course)
        await session.flush()
        course_id = course.id

    # Re-fetch to get generated id
    async with get_async_session() as session:
        result = await session.execute(
            select(RaceCourse).where(RaceCourse.id == course_id)
        )
        saved = result.scalar_one()
        return saved.to_summary_dict()


async def get_course(course_id: int) -> RaceCourse | None:
    """Load a RaceCourse by id. Returns None if not found."""
    async with get_async_session() as session:
        result = await session.execute(
            select(RaceCourse).where(RaceCourse.id == course_id)
        )
        return result.scalar_one_or_none()


async def get_all_courses() -> list[dict]:
    """Return summary dicts for all courses, newest first."""
    async with get_async_session() as session:
        result = await session.execute(
            select(RaceCourse).order_by(RaceCourse.imported_at.desc())
        )
        return [c.to_summary_dict() for c in result.scalars().all()]


async def delete_course(course_id: int) -> bool:
    """Delete course by id. Returns True if a row was deleted, False if not found."""
    async with get_async_session() as session:
        result = await session.execute(
            select(RaceCourse).where(RaceCourse.id == course_id)
        )
        course = result.scalar_one_or_none()
        if course is None:
            return False
        await session.delete(course)
    return True


# ---------------------------------------------------------------------------
# Race Plan CRUD
# ---------------------------------------------------------------------------


async def save_race_plan(
    course_id: int,
    name: str,
    race_date: str | None,
    race_hour: int,
    target_time: str | None,
    target_time_s: float | None,
    strategy: str,
    pacer_pace: str | None,
    drop_at_km: float | None,
    weather_temp_c: float | None,
    weather_humidity_pct: float | None,
    weather_wind_ms: float | None,
    weather_wind_dir_deg: float | None,
    weather_source: str | None,
    splits: list[dict],
) -> dict:
    """Persist a new RacePlan and return its summary dict."""
    plan = RacePlan(
        course_id=course_id,
        name=name,
        race_date=race_date,
        race_hour=race_hour,
        target_time=target_time,
        target_time_s=target_time_s,
        strategy=strategy,
        pacer_pace=pacer_pace,
        drop_at_km=drop_at_km,
        weather_temp_c=weather_temp_c,
        weather_humidity_pct=weather_humidity_pct,
        weather_wind_ms=weather_wind_ms,
        weather_wind_dir_deg=weather_wind_dir_deg,
        weather_source=weather_source,
        splits_json=json.dumps(splits),
    )
    async with get_async_session() as session:
        session.add(plan)
        await session.flush()
        plan_id = plan.id

    async with get_async_session() as session:
        result = await session.execute(select(RacePlan).where(RacePlan.id == plan_id))
        saved = result.scalar_one()
        return saved.to_summary_dict()


async def get_race_plan(plan_id: int) -> RacePlan | None:
    """Load a RacePlan by id.  Returns None if not found."""
    async with get_async_session() as session:
        result = await session.execute(select(RacePlan).where(RacePlan.id == plan_id))
        return result.scalar_one_or_none()


async def get_plans_for_course(course_id: int) -> list[dict]:
    """Return summary dicts for all plans on a course, newest first."""
    async with get_async_session() as session:
        result = await session.execute(
            select(RacePlan)
            .where(RacePlan.course_id == course_id)
            .order_by(RacePlan.created_at.desc())
        )
        return [p.to_summary_dict() for p in result.scalars().all()]


async def get_all_race_plans() -> list[dict]:
    """Return summary dicts for all race plans, newest first."""
    async with get_async_session() as session:
        result = await session.execute(
            select(RacePlan).order_by(RacePlan.created_at.desc())
        )
        return [p.to_summary_dict() for p in result.scalars().all()]


async def update_race_plan(plan_id: int, **fields) -> bool:
    """Update arbitrary fields on a RacePlan.  Returns True if found."""
    async with get_async_session() as session:
        result = await session.execute(select(RacePlan).where(RacePlan.id == plan_id))
        plan = result.scalar_one_or_none()
        if plan is None:
            return False
        for key, value in fields.items():
            if hasattr(plan, key):
                setattr(plan, key, value)
        plan.updated_at = datetime.now(UTC)
    return True


async def delete_race_plan(plan_id: int) -> bool:
    """Delete a RacePlan by id.  Returns True if a row was deleted."""
    async with get_async_session() as session:
        result = await session.execute(select(RacePlan).where(RacePlan.id == plan_id))
        plan = result.scalar_one_or_none()
        if plan is None:
            return False
        await session.delete(plan)
    return True


async def get_race_plan_for_activity(activity_id: int) -> RacePlan | None:
    """Return the RacePlan linked to the given activity, if any."""
    async with get_async_session() as session:
        result = await session.execute(
            select(RacePlan).where(RacePlan.activity_id == activity_id)
        )
        return result.scalar_one_or_none()


async def link_activity_to_plan(plan_id: int, activity_id: int) -> bool:
    """Set plan.activity_id.  Returns True if the plan was found and updated."""
    async with get_async_session() as session:
        result = await session.execute(select(RacePlan).where(RacePlan.id == plan_id))
        plan = result.scalar_one_or_none()
        if plan is None:
            return False
        plan.activity_id = activity_id
        plan.updated_at = datetime.now(UTC)
    return True
