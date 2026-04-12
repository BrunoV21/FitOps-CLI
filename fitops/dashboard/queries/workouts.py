from __future__ import annotations

from sqlalchemy import desc, select

from fitops.db.models.activity import Activity
from fitops.db.models.workout import Workout
from fitops.db.models.workout_activity_link import WorkoutActivityLink
from fitops.db.models.workout_segment import WorkoutSegment
from fitops.db.session import get_async_session


async def get_workout_with_segments(
    workout_id: int,
    athlete_id: int,
) -> tuple[Workout, list[WorkoutSegment]] | None:
    """Fetch a workout and its segments by workout id (guarded by athlete_id).

    Returns the most-recently-linked activity's segments when multiple activities
    are linked to the same workout.
    """
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

        # Find the most recently linked activity to scope the segments
        link_res = await session.execute(
            select(WorkoutActivityLink)
            .where(WorkoutActivityLink.workout_id == workout_id)
            .order_by(desc(WorkoutActivityLink.linked_at))
            .limit(1)
        )
        latest_link = link_res.scalar_one_or_none()

        seg_query = select(WorkoutSegment).where(
            WorkoutSegment.workout_id == workout_id
        )
        if latest_link is not None:
            seg_query = seg_query.where(
                WorkoutSegment.activity_id == latest_link.activity_id
            )
        seg_res = await session.execute(
            seg_query.order_by(WorkoutSegment.segment_index)
        )
        segments = list(seg_res.scalars().all())
        return workout, segments


async def get_linked_activities_for_workout(
    workout_id: int,
) -> list[tuple[WorkoutActivityLink, Activity]]:
    """Return all (link, activity) pairs for a workout, newest activity date first."""
    async with get_async_session() as session:
        res = await session.execute(
            select(WorkoutActivityLink, Activity)
            .join(Activity, Activity.id == WorkoutActivityLink.activity_id)
            .where(WorkoutActivityLink.workout_id == workout_id)
            .order_by(desc(Activity.start_date_local))
        )
        return list(res.all())


async def get_workout_for_activity(
    activity_id: int,
) -> tuple[Workout, WorkoutActivityLink, list[WorkoutSegment]] | None:
    """Fetch the workout (and its segments) linked to an internal activity id.

    Returns ``(workout, link, segments)`` so callers can read per-activity
    compliance metadata from the link row rather than the workout row.
    """
    async with get_async_session() as session:
        link_res = await session.execute(
            select(WorkoutActivityLink).where(
                WorkoutActivityLink.activity_id == activity_id
            )
        )
        link = link_res.scalar_one_or_none()
        if link is None:
            return None

        workout_res = await session.execute(
            select(Workout).where(Workout.id == link.workout_id)
        )
        workout = workout_res.scalar_one_or_none()
        if workout is None:
            return None

        seg_res = await session.execute(
            select(WorkoutSegment)
            .where(
                WorkoutSegment.workout_id == link.workout_id,
                WorkoutSegment.activity_id == activity_id,
            )
            .order_by(WorkoutSegment.segment_index)
        )
        segments = list(seg_res.scalars().all())
        return workout, link, segments


async def get_workout_names_for_activities(activity_ids: list[int]) -> dict[int, str]:
    """Return {activity_id: workout_name} for a batch of internal activity IDs."""
    if not activity_ids:
        return {}
    async with get_async_session() as session:
        res = await session.execute(
            select(WorkoutActivityLink.activity_id, Workout.name)
            .join(Workout, Workout.id == WorkoutActivityLink.workout_id)
            .where(WorkoutActivityLink.activity_id.in_(activity_ids))
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


async def get_activity_for_workout(activity_id: int) -> Activity | None:
    """Fetch the Activity linked to a workout's activity_id (internal id)."""
    if activity_id is None:
        return None
    async with get_async_session() as session:
        res = await session.execute(select(Activity).where(Activity.id == activity_id))
        return res.scalar_one_or_none()
