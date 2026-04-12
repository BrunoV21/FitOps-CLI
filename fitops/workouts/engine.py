"""Shared async compliance engine — callable from both CLI and dashboard."""

from __future__ import annotations

import json

from sqlalchemy import select

from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.models.workout import Workout
from fitops.db.models.workout_activity_link import WorkoutActivityLink
from fitops.db.models.workout_segment import WorkoutSegment
from fitops.db.session import get_async_session
from fitops.workouts.compliance import compute_compliance, overall_compliance_score
from fitops.workouts.json_parser import parse_segments_from_json
from fitops.workouts.segments import parse_segments_from_body


async def run_compliance_for_activity(
    activity_internal_id: int,
    recalculate: bool = False,
) -> tuple[dict | None, str | None]:
    """Compute and persist compliance for a workout linked to *activity_internal_id*.

    Returns ``(result_dict, None)`` on success or ``(None, error_key)`` on failure.

    Error keys:
      - ``"no_workout_linked"``
      - ``"no_streams"``
      - ``"no_segments_parsed"``
    """
    async with get_async_session() as session:
        # Resolve workout linked to this activity via the join table
        link_res = await session.execute(
            select(WorkoutActivityLink).where(
                WorkoutActivityLink.activity_id == activity_internal_id
            )
        )
        link = link_res.scalar_one_or_none()
        if link is None:
            return None, "no_workout_linked"

        workout_res = await session.execute(
            select(Workout).where(Workout.id == link.workout_id)
        )
        workout = workout_res.scalar_one_or_none()
        if workout is None:
            return None, "no_workout_linked"

        # Short-circuit if cached segments exist for this specific (workout, activity) pair
        if not recalculate:
            res_cache = await session.execute(
                select(WorkoutSegment)
                .where(
                    WorkoutSegment.workout_id == workout.id,
                    WorkoutSegment.activity_id == activity_internal_id,
                )
                .order_by(WorkoutSegment.segment_index)
            )
            cached = res_cache.scalars().all()
            if cached:
                return {"workout_id": workout.id, "cached": True}, None

        # Resolve activity row (for sport_type, moving_time_s)
        act = (
            await session.execute(
                select(Activity).where(Activity.id == activity_internal_id)
            )
        ).scalar_one_or_none()

        # Load streams from DB
        res_streams = await session.execute(
            select(ActivityStream).where(
                ActivityStream.activity_id == activity_internal_id
            )
        )
        all_stream_rows = res_streams.scalars().all()
        streams_dict: dict = {row.stream_type: row.data for row in all_stream_rows}

        if not streams_dict:
            # Try fetching from Strava
            if act is not None:
                try:
                    from fitops.strava.client import StravaClient

                    client = StravaClient()
                    stream_data = await client.get_activity_streams(act.strava_id)
                    for stream_type, stream_obj in stream_data.items():
                        data_list = (
                            stream_obj.get("data", [])
                            if isinstance(stream_obj, dict)
                            else stream_obj
                        )
                        existing = await session.execute(
                            select(ActivityStream).where(
                                ActivityStream.activity_id == activity_internal_id,
                                ActivityStream.stream_type == stream_type,
                            )
                        )
                        if existing.scalar_one_or_none() is None:
                            session.add(
                                ActivityStream.from_strava_stream(
                                    activity_internal_id, stream_type, data_list
                                )
                            )
                        streams_dict[stream_type] = data_list
                    if act:
                        act.streams_fetched = True
                    await session.flush()
                except Exception:
                    pass

        if "heartrate" not in streams_dict and "velocity_smooth" not in streams_dict:
            return None, "no_streams"

    # Pure computation — outside session
    fm = workout.get_workout_meta() or {}
    workout_json_raw = fm.get("workout_meta")
    workout_json = None
    if isinstance(workout_json_raw, str):
        try:
            workout_json = json.loads(workout_json_raw)
        except json.JSONDecodeError:
            pass
    elif isinstance(workout_json_raw, dict):
        workout_json = workout_json_raw

    # Also try workout.workout_meta directly (stored as JSON string on the model)
    if workout_json is None and workout.workout_meta:
        try:
            workout_json = json.loads(workout.workout_meta)
        except json.JSONDecodeError:
            pass

    if workout_json and workout_json.get("training"):
        segments = parse_segments_from_json(workout_json)
    else:
        body = workout.workout_markdown or ""
        segments = parse_segments_from_body(body)

    if not segments:
        return None, "no_segments_parsed"

    from fitops.analytics.athlete_settings import get_athlete_settings
    from fitops.analytics.zones import compute_zones

    athlete_s = get_athlete_settings()
    method = athlete_s.best_zone_method()
    zones = (
        compute_zones(
            method=method,
            lthr=athlete_s.lthr,
            max_hr=athlete_s.max_hr,
            resting_hr=athlete_s.resting_hr,
        )
        if method != "none"
        else None
    )

    sport = (act.sport_type or "Run") if act else "Run"
    is_run = sport in {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
    moving_time_s = (act.moving_time_s if act else None) or len(
        streams_dict.get("heartrate", streams_dict.get("velocity_smooth", []))
    )

    results = compute_compliance(
        segments, streams_dict, moving_time_s, zones, is_run=is_run
    )
    overall = overall_compliance_score(results)

    # Persist segment rows — upsert keyed on (workout_id, activity_id, segment_index)
    async with get_async_session() as session:
        for r in results:
            existing = await session.execute(
                select(WorkoutSegment).where(
                    WorkoutSegment.workout_id == workout.id,
                    WorkoutSegment.activity_id == activity_internal_id,
                    WorkoutSegment.segment_index == r.segment.index,
                )
            )
            existing_row = existing.scalar_one_or_none()
            new_row = WorkoutSegment.from_compliance_result(
                workout.id, activity_internal_id, r
            )
            if existing_row:
                for col in WorkoutSegment.__table__.columns:
                    if col.name != "id":
                        setattr(existing_row, col.name, getattr(new_row, col.name))
            else:
                session.add(new_row)

        # Write per-link compliance score to the WorkoutActivityLink row
        lnk_res = await session.execute(
            select(WorkoutActivityLink).where(
                WorkoutActivityLink.workout_id == workout.id,
                WorkoutActivityLink.activity_id == activity_internal_id,
            )
        )
        lnk = lnk_res.scalar_one_or_none()
        if lnk and overall is not None:
            lnk.compliance_score = overall

    return {
        "workout_id": workout.id,
        "segment_count": len(results),
        "overall": overall,
        "cached": False,
    }, None
