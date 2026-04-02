from __future__ import annotations

import json

from sqlalchemy import select

from fitops.db.models.race_course import RaceCourse
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
