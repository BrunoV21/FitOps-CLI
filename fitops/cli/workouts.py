from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from sqlalchemy import select, desc

from fitops.config.settings import get_settings
from fitops.db.migrations import init_db
from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.models.workout import Workout
from fitops.db.models.workout_segment import WorkoutSegment
from fitops.db.session import get_async_session
from fitops.output.formatter import make_meta
from fitops.utils.exceptions import NotAuthenticatedError
from fitops.workouts.compliance import compute_compliance, overall_compliance_score
from fitops.workouts.loader import (
    WorkoutFile,
    get_workout_file,
    list_workout_files,
    workouts_dir,
)
from fitops.workouts.segments import parse_segments_from_body

app = typer.Typer(no_args_is_help=True)


# ---------------------------------------------------------------------------
# Physiology snapshot helper
# ---------------------------------------------------------------------------

async def _build_physiology_snapshot(athlete_id: int) -> dict:
    """Compute a physiology snapshot (CTL, ATL, TSB, VO2max, LT1/LT2)."""
    snapshot: dict = {}

    try:
        from fitops.analytics.training_load import compute_training_load
        tl = await compute_training_load(athlete_id=athlete_id, days=1)
        if tl.current:
            snapshot["ctl"] = tl.current.ctl
            snapshot["atl"] = tl.current.atl
            snapshot["tsb"] = tl.current.tsb
            snapshot["form_label"] = tl.form_label(tl.current.tsb)
    except Exception:
        pass

    try:
        from fitops.analytics.vo2max import estimate_vo2max
        vo2 = await estimate_vo2max(athlete_id=athlete_id)
        if vo2:
            snapshot["vo2max"] = vo2.estimate
            snapshot["vo2max_confidence"] = vo2.confidence_label
    except Exception:
        pass

    try:
        from fitops.analytics.athlete_settings import get_athlete_settings
        s = get_athlete_settings()
        if s.lthr:
            snapshot["lt2_hr"] = s.lthr
            snapshot["lt1_hr"] = int(s.lthr * 0.92)
        if s.max_hr:
            snapshot["max_hr"] = s.max_hr
        snapshot["zones_method"] = s.best_zone_method()
        if snapshot["zones_method"] != "none":
            from fitops.analytics.zones import compute_zones
            zr = compute_zones(
                method=snapshot["zones_method"],
                lthr=s.lthr,
                max_hr=s.max_hr,
                resting_hr=s.resting_hr,
            )
            if zr:
                snapshot["zones"] = zr.to_dict()
    except Exception:
        pass

    return snapshot


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command("list")
def list_workouts() -> None:
    """List workout definition files in ~/.fitops/workouts/."""
    d = workouts_dir()
    files = list_workout_files()

    if not files:
        typer.echo(
            json.dumps(
                {
                    "_meta": make_meta(total_count=0),
                    "workouts": [],
                    "hint": f"Add .md workout files to {d}",
                },
                indent=2,
            )
        )
        return

    typer.echo(
        json.dumps(
            {
                "_meta": make_meta(total_count=len(files)),
                "workouts_dir": str(d),
                "workouts": [
                    {
                        "file_name": w.file_name,
                        "name": w.name,
                        "sport": w.sport,
                        "target_duration_min": w.target_duration_min,
                        "tags": w.tags,
                    }
                    for w in files
                ],
            },
            indent=2,
        )
    )


@app.command("show")
def show_workout(
    name: str = typer.Argument(..., help="Workout filename or name (e.g. threshold-tuesday)"),
) -> None:
    """Display a workout definition file."""
    w = get_workout_file(name)
    if w is None:
        typer.echo(
            json.dumps(
                {
                    "error": f"Workout '{name}' not found.",
                    "hint": f"Run `fitops workouts list` to see available workouts.",
                },
                indent=2,
            )
        )
        raise typer.Exit(1)

    typer.echo(
        json.dumps(
            {
                "_meta": make_meta(),
                "workout": {
                    "file_name": w.file_name,
                    "name": w.name,
                    "sport": w.sport,
                    "target_duration_min": w.target_duration_min,
                    "tags": w.tags,
                    "meta": w.meta,
                    "body": w.body,
                },
            },
            indent=2,
        )
    )


@app.command("link")
def link_workout(
    name: str = typer.Argument(..., help="Workout filename or name."),
    activity_id: int = typer.Argument(..., help="Strava activity ID to link to."),
    notes: Optional[str] = typer.Option(None, "--notes", help="Optional notes for this workout instance."),
) -> None:
    """Link a workout definition to a synced activity and capture a physiology snapshot."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    w = get_workout_file(name)
    if w is None:
        typer.echo(
            json.dumps(
                {"error": f"Workout file '{name}' not found in {workouts_dir()}"},
                indent=2,
            )
        )
        raise typer.Exit(1)

    init_db()

    async def _link():
        from datetime import datetime, timezone

        async with get_async_session() as session:
            # Verify the activity exists locally
            res = await session.execute(
                select(Activity).where(Activity.strava_id == activity_id)
            )
            activity = res.scalar_one_or_none()
            if activity is None:
                typer.echo(
                    json.dumps(
                        {
                            "error": f"Activity {activity_id} not found locally.",
                            "hint": "Run `fitops sync run` first.",
                        },
                        indent=2,
                    )
                )
                raise typer.Exit(1)

            # Compute physiology snapshot
            snapshot = await _build_physiology_snapshot(settings.athlete_id)

            # Check for an existing link for this activity
            res2 = await session.execute(
                select(Workout).where(Workout.activity_id == activity.id)
            )
            existing = res2.scalar_one_or_none()

            now = datetime.now(timezone.utc)

            if existing:
                # Update the existing link
                existing.name = w.name
                existing.sport_type = w.sport or activity.sport_type or "unknown"
                existing.athlete_id = settings.athlete_id
                existing.workout_file_name = w.file_name
                existing.workout_markdown = w.raw
                existing.workout_meta = json.dumps(w.meta)
                existing.physiology_snapshot = json.dumps(snapshot)
                existing.linked_at = now
                existing.status = "completed"
                if notes:
                    existing.notes = notes
                existing.updated_at = now
                workout = existing
            else:
                workout = Workout(
                    name=w.name,
                    sport_type=w.sport or activity.sport_type or "unknown",
                    athlete_id=settings.athlete_id,
                    activity_id=activity.id,
                    workout_file_name=w.file_name,
                    workout_markdown=w.raw,
                    workout_meta=json.dumps(w.meta),
                    physiology_snapshot=json.dumps(snapshot),
                    linked_at=now,
                    status="completed",
                    notes=notes,
                )
                session.add(workout)

        return {
            "workout_name": w.name,
            "activity_id": activity_id,
            "activity_name": activity.name,
            "sport_type": workout.sport_type,
            "linked_at": now.isoformat(),
            "physiology_snapshot": snapshot,
        }

    result = asyncio.run(_link())
    typer.echo(
        json.dumps(
            {"_meta": make_meta(), "linked": result},
            indent=2,
            default=str,
        )
    )


@app.command("get")
def get_workout(
    activity_id: int = typer.Argument(..., help="Strava activity ID."),
) -> None:
    """Retrieve the workout linked to a specific activity."""
    init_db()

    async def _fetch():
        async with get_async_session() as session:
            # Resolve strava_id → internal activity id
            res = await session.execute(
                select(Activity).where(Activity.strava_id == activity_id)
            )
            activity = res.scalar_one_or_none()
            if activity is None:
                return None, "activity_not_found"

            res2 = await session.execute(
                select(Workout).where(Workout.activity_id == activity.id)
            )
            workout = res2.scalar_one_or_none()
            if workout is None:
                return None, "no_workout_linked"

            return workout, None

    workout, err = asyncio.run(_fetch())

    if err == "activity_not_found":
        typer.echo(
            json.dumps(
                {
                    "error": f"Activity {activity_id} not found locally.",
                    "hint": "Run `fitops sync run` first.",
                },
                indent=2,
            )
        )
        raise typer.Exit(1)

    if err == "no_workout_linked":
        typer.echo(
            json.dumps(
                {
                    "error": f"No workout linked to activity {activity_id}.",
                    "hint": "Use `fitops workouts link <name> <activity_id>` to link one.",
                },
                indent=2,
            )
        )
        raise typer.Exit(1)

    typer.echo(
        json.dumps(
            {
                "_meta": make_meta(),
                "workout": {
                    "id": workout.id,
                    "name": workout.name,
                    "sport_type": workout.sport_type,
                    "file_name": workout.workout_file_name,
                    "linked_at": str(workout.linked_at),
                    "status": workout.status,
                    "notes": workout.notes,
                    "compliance_score": workout.compliance_score,
                    "meta": workout.get_workout_meta(),
                    "physiology_snapshot": workout.get_physiology_snapshot(),
                    "body": workout.workout_markdown,
                },
            },
            indent=2,
            default=str,
        )
    )


@app.command("history")
def history(
    limit: int = typer.Option(20, "--limit", help="Max number of linked workouts to show."),
    sport: Optional[str] = typer.Option(None, "--sport", help="Filter by sport type."),
) -> None:
    """List workouts that have been linked to activities."""
    init_db()

    async def _fetch():
        async with get_async_session() as session:
            stmt = (
                select(Workout)
                .where(Workout.activity_id.isnot(None))
                .order_by(desc(Workout.linked_at))
                .limit(limit)
            )
            if sport:
                stmt = stmt.where(Workout.sport_type == sport)
            res = await session.execute(stmt)
            return res.scalars().all()

    workouts = asyncio.run(_fetch())

    filters: dict = {"limit": limit}
    if sport:
        filters["sport"] = sport

    typer.echo(
        json.dumps(
            {
                "_meta": make_meta(total_count=len(workouts), filters_applied=filters),
                "workouts": [w.to_summary_dict() for w in workouts],
            },
            indent=2,
            default=str,
        )
    )


@app.command("compliance")
def compliance(
    activity_id: int = typer.Argument(..., help="Strava activity ID."),
    recalculate: bool = typer.Option(False, "--recalculate", help="Force re-score even if segments already exist."),
) -> None:
    """Score each workout segment against the activity's heart rate stream."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    async def _run():
        async with get_async_session() as session:
            # 1. Resolve activity
            res = await session.execute(
                select(Activity).where(Activity.strava_id == activity_id)
            )
            activity = res.scalar_one_or_none()
            if activity is None:
                return None, "activity_not_found"

            # 2. Resolve linked workout
            res2 = await session.execute(
                select(Workout).where(Workout.activity_id == activity.id)
            )
            workout = res2.scalar_one_or_none()
            if workout is None:
                return None, "no_workout_linked"

            # 3. Check for cached segment results (unless --recalculate)
            if not recalculate:
                res3 = await session.execute(
                    select(WorkoutSegment)
                    .where(WorkoutSegment.workout_id == workout.id)
                    .order_by(WorkoutSegment.segment_index)
                )
                cached = res3.scalars().all()
                if cached:
                    return {"workout": workout, "segments": cached, "cached": True}, None

            # 4. Get HR stream — fetch from Strava if not cached locally
            res4 = await session.execute(
                select(ActivityStream).where(
                    ActivityStream.activity_id == activity.id,
                    ActivityStream.stream_type == "heartrate",
                )
            )
            stream_row = res4.scalar_one_or_none()

            if stream_row is None:
                # Fetch streams from Strava
                from fitops.strava.client import StravaClient
                client = StravaClient()
                stream_data = await client.get_activity_streams(activity_id)
                for stream_type, stream_obj in stream_data.items():
                    data_list = (
                        stream_obj.get("data", [])
                        if isinstance(stream_obj, dict)
                        else stream_obj
                    )
                    existing = await session.execute(
                        select(ActivityStream).where(
                            ActivityStream.activity_id == activity.id,
                            ActivityStream.stream_type == stream_type,
                        )
                    )
                    if existing.scalar_one_or_none() is None:
                        session.add(
                            ActivityStream.from_strava_stream(activity.id, stream_type, data_list)
                        )
                activity.streams_fetched = True
                await session.flush()

                # Re-fetch heartrate
                res4b = await session.execute(
                    select(ActivityStream).where(
                        ActivityStream.activity_id == activity.id,
                        ActivityStream.stream_type == "heartrate",
                    )
                )
                stream_row = res4b.scalar_one_or_none()

            if stream_row is None:
                return None, "no_heartrate_stream"

            hr_stream = stream_row.data

        # 5. Parse workout segments and zones (outside session — pure computation)
        body = workout.workout_markdown or ""
        segments = parse_segments_from_body(body)
        if not segments:
            return None, "no_segments_parsed"

        from fitops.analytics.athlete_settings import get_athlete_settings
        from fitops.analytics.zones import compute_zones
        athlete_s = get_athlete_settings()
        method = athlete_s.best_zone_method()
        zones = compute_zones(
            method=method,
            lthr=athlete_s.lthr,
            max_hr=athlete_s.max_hr,
            resting_hr=athlete_s.resting_hr,
        ) if method != "none" else None

        moving_time_s = activity.moving_time_s or len(hr_stream)
        results = compute_compliance(segments, hr_stream, moving_time_s, zones)
        overall = overall_compliance_score(results)

        # 6. Persist segment rows (upsert by workout_id + segment_index)
        async with get_async_session() as session:
            for r in results:
                existing = await session.execute(
                    select(WorkoutSegment).where(
                        WorkoutSegment.workout_id == workout.id,
                        WorkoutSegment.segment_index == r.segment.index,
                    )
                )
                existing_row = existing.scalar_one_or_none()
                new_row = WorkoutSegment.from_compliance_result(workout.id, activity.id, r)
                if existing_row:
                    for col in WorkoutSegment.__table__.columns:
                        if col.name not in ("id",):
                            setattr(existing_row, col.name, getattr(new_row, col.name))
                else:
                    session.add(new_row)

            # Update overall compliance score on workout
            res_w = await session.execute(
                select(Workout).where(Workout.id == workout.id)
            )
            w = res_w.scalar_one_or_none()
            if w and overall is not None:
                w.compliance_score = overall

        return {"workout": workout, "results": results, "overall": overall, "cached": False}, None

    data, err = asyncio.run(_run())

    if err == "activity_not_found":
        typer.echo(json.dumps({"error": f"Activity {activity_id} not found locally.", "hint": "Run `fitops sync run` first."}, indent=2))
        raise typer.Exit(1)
    if err == "no_workout_linked":
        typer.echo(json.dumps({"error": f"No workout linked to activity {activity_id}.", "hint": "Use `fitops workouts link <name> <activity_id>` first."}, indent=2))
        raise typer.Exit(1)
    if err == "no_heartrate_stream":
        typer.echo(json.dumps({"error": "No heart rate data for this activity. Compliance requires an HR stream."}, indent=2))
        raise typer.Exit(1)
    if err == "no_segments_parsed":
        typer.echo(json.dumps({"error": "No ## segments found in the workout file.", "hint": "Add ## Warmup / ## Main Set / ## Cooldown headings to your workout .md file."}, indent=2))
        raise typer.Exit(1)

    workout = data["workout"]

    if data.get("cached"):
        segments_out = [s.to_dict() for s in data["segments"]]
        overall_score = (
            workout.compliance_score
            if hasattr(workout, "compliance_score")
            else None
        )
    else:
        segments_out = [
            r.segment.__dict__ | {
                "start_index": r.start_index,
                "end_index": r.end_index,
                "duration_actual_s": r.duration_actual_s,
                "actuals": {
                    "avg_heartrate_bpm": r.avg_heartrate,
                    "actual_zone": r.actual_zone,
                    "hr_zone_distribution": r.hr_zone_distribution,
                },
                "compliance": {
                    "target_achieved": r.target_achieved,
                    "compliance_score": r.compliance_score,
                    "deviation_pct": r.deviation_pct,
                    "time_in_target_pct": r.time_in_target_pct,
                    "time_above_pct": r.time_above_pct,
                    "time_below_pct": r.time_below_pct,
                },
                "data_quality": {
                    "has_heartrate": r.has_heartrate,
                    "data_completeness": r.data_completeness,
                },
            }
            for r in data["results"]
        ]
        overall_score = data["overall"]

    typer.echo(
        json.dumps(
            {
                "_meta": make_meta(total_count=len(segments_out)),
                "workout_name": workout.name,
                "activity_strava_id": activity_id,
                "overall_compliance_score": overall_score,
                "zones_method": (
                    workout.get_physiology_snapshot().get("zones_method")
                    if hasattr(workout, "get_physiology_snapshot")
                    else None
                ),
                "segments": segments_out,
            },
            indent=2,
            default=str,
        )
    )
