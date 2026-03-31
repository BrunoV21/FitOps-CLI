from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from fitops.db.models.activity import Activity
from fitops.db.models.workout import Workout
from fitops.db.models.workout_segment import WorkoutSegment
from fitops.db.session import get_async_session


async def get_workout_with_segments(
    workout_id: int,
    athlete_id: int,
) -> Optional[tuple[Workout, list[WorkoutSegment]]]:
    """Fetch a workout and its segments by workout id (guarded by athlete_id)."""
    async with get_async_session() as session:
        res = await session.execute(
            select(Workout).where(
                Workout.id == workout_id,
                Workout.athlete_id == athlete_id,
            )
        )
        workout = res.scalar_one_or_none()
        if workout is None:
            return None

        seg_res = await session.execute(
            select(WorkoutSegment)
            .where(WorkoutSegment.workout_id == workout_id)
            .order_by(WorkoutSegment.segment_index)
        )
        segments = list(seg_res.scalars().all())
        return workout, segments


async def get_workout_for_activity(
    activity_id: int,
) -> Optional[tuple[Workout, list[WorkoutSegment]]]:
    """Fetch the workout (and its segments) linked to an internal activity id."""
    async with get_async_session() as session:
        res = await session.execute(
            select(Workout).where(Workout.activity_id == activity_id)
        )
        workout = res.scalar_one_or_none()
        if workout is None:
            return None

        seg_res = await session.execute(
            select(WorkoutSegment)
            .where(WorkoutSegment.workout_id == workout.id)
            .order_by(WorkoutSegment.segment_index)
        )
        segments = list(seg_res.scalars().all())
        return workout, segments


async def get_workout_names_for_activities(activity_ids: list[int]) -> dict[int, str]:
    """Return {activity_id: workout_name} for a batch of internal activity IDs."""
    if not activity_ids:
        return {}
    async with get_async_session() as session:
        res = await session.execute(
            select(Workout.activity_id, Workout.name).where(
                Workout.activity_id.in_(activity_ids)
            )
        )
        return {row.activity_id: row.name for row in res.all()}


async def get_all_workouts(athlete_id: int) -> list[Workout]:
    """Return all workouts for an athlete, newest first (for the assign selector)."""
    async with get_async_session() as session:
        res = await session.execute(
            select(Workout)
            .where(Workout.athlete_id == athlete_id)
            .order_by(Workout.created_at.desc())
        )
        return list(res.scalars().all())


async def get_activity_for_workout(activity_id: int) -> Optional[Activity]:
    """Fetch the Activity linked to a workout's activity_id (internal id)."""
    if activity_id is None:
        return None
    async with get_async_session() as session:
        res = await session.execute(
            select(Activity).where(Activity.id == activity_id)
        )
        return res.scalar_one_or_none()
