from __future__ import annotations

import asyncio
import json
from datetime import UTC

import typer
from sqlalchemy import desc, select

from fitops.config.settings import get_settings
from fitops.db.migrations import init_db
from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.models.workout import Workout
from fitops.db.models.workout_segment import WorkoutSegment
from fitops.db.session import get_async_session
from fitops.output.formatter import make_meta
from fitops.output.text_formatter import (
    print_workout_compliance,
    print_workout_detail,
    print_workout_history,
    print_workout_simulate,
    print_workouts_list,
)
from fitops.utils.exceptions import NotAuthenticatedError
from fitops.workouts.compliance import compute_compliance, overall_compliance_score
from fitops.workouts.json_parser import generate_markdown_body, parse_segments_from_json
from fitops.workouts.loader import (
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
def list_workouts(
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """List workout definition files in ~/.fitops/workouts/."""
    d = workouts_dir()
    files = list_workout_files()

    out = {
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
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2))
    else:
        print_workouts_list(out)


@app.command("show")
def show_workout(
    name: str = typer.Argument(
        ..., help="Workout filename or name (e.g. threshold-tuesday)"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Display a workout definition file."""
    w = get_workout_file(name)
    if w is None:
        typer.echo(
            f"Workout '{name}' not found. Run `fitops workouts list` to see available workouts.",
            err=True,
        )
        raise typer.Exit(1)

    out = {
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
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2))
    else:
        print_workout_detail(out)


@app.command("link")
def link_workout(
    name: str = typer.Argument(..., help="Workout filename or name."),
    activity_id: int = typer.Argument(..., help="Strava activity ID to link to."),
    notes: str | None = typer.Option(
        None, "--notes", help="Optional notes for this workout instance."
    ),
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
        from datetime import datetime

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

            now = datetime.now(UTC)

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
    limit: int = typer.Option(
        20, "--limit", help="Max number of linked workouts to show."
    ),
    sport: str | None = typer.Option(None, "--sport", help="Filter by sport type."),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
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

    out = {
        "_meta": make_meta(total_count=len(workouts), filters_applied=filters),
        "workouts": [w.to_summary_dict() for w in workouts],
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_workout_history(out)


@app.command("compliance")
def compliance(
    activity_id: int = typer.Argument(..., help="Strava activity ID."),
    recalculate: bool = typer.Option(
        False, "--recalculate", help="Force re-score even if segments already exist."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
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
                    return {
                        "workout": workout,
                        "segments": cached,
                        "cached": True,
                    }, None

            # 4. Fetch all streams from Strava if not cached locally
            res_streams = await session.execute(
                select(ActivityStream).where(ActivityStream.activity_id == activity.id)
            )
            all_stream_rows = res_streams.scalars().all()
            streams_dict = {row.stream_type: row.data for row in all_stream_rows}

            if not streams_dict:
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
                            ActivityStream.from_strava_stream(
                                activity.id, stream_type, data_list
                            )
                        )
                        streams_dict[stream_type] = data_list
                activity.streams_fetched = True
                await session.flush()

            if (
                "heartrate" not in streams_dict
                and "velocity_smooth" not in streams_dict
            ):
                return None, "no_heartrate_stream"

        # 5. Parse workout segments and zones (outside session — pure computation)
        # Prefer JSON-structured segments (from workout_meta) over markdown parsing.
        # The frontmatter stores the JSON as a string under the "workout_meta" key.
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

        is_run = (activity.sport_type or "Run") in {
            "Run",
            "TrailRun",
            "Walk",
            "Hike",
            "VirtualRun",
        }
        moving_time_s = activity.moving_time_s or len(
            streams_dict.get("heartrate", streams_dict.get("velocity_smooth", []))
        )
        results = compute_compliance(
            segments, streams_dict, moving_time_s, zones, is_run=is_run
        )
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
                new_row = WorkoutSegment.from_compliance_result(
                    workout.id, activity.id, r
                )
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

        return {
            "workout": workout,
            "results": results,
            "overall": overall,
            "cached": False,
        }, None

    data, err = asyncio.run(_run())

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
                    "hint": "Use `fitops workouts link <name> <activity_id>` first.",
                },
                indent=2,
            )
        )
        raise typer.Exit(1)
    if err == "no_heartrate_stream":
        typer.echo(
            json.dumps(
                {
                    "error": "No heart rate data for this activity. Compliance requires an HR stream."
                },
                indent=2,
            )
        )
        raise typer.Exit(1)
    if err == "no_segments_parsed":
        typer.echo(
            json.dumps(
                {
                    "error": "No ## segments found in the workout file.",
                    "hint": "Add ## Warmup / ## Main Set / ## Cooldown headings to your workout .md file.",
                },
                indent=2,
            )
        )
        raise typer.Exit(1)

    workout = data["workout"]

    if data.get("cached"):
        segments_out = [s.to_dict() for s in data["segments"]]
        overall_score = (
            workout.compliance_score if hasattr(workout, "compliance_score") else None
        )
    else:

        def _fmt_pace(pace_s):
            if pace_s is None:
                return None
            m, s = divmod(int(pace_s), 60)
            return f"{m}:{s:02d}"

        segments_out = [
            {
                "segment_index": r.segment.index,
                "segment_name": r.segment.name,
                "step_type": r.segment.step_type,
                "target_focus_type": r.segment.target_focus_type,
                "target_zone": r.segment.target_zone,
                "target_hr_range": (
                    {
                        "min_bpm": r.segment.target_hr_min_bpm,
                        "max_bpm": r.segment.target_hr_max_bpm,
                    }
                    if r.segment.target_hr_min_bpm is not None
                    else None
                ),
                "target_pace_range": (
                    {
                        "min_s_per_km": r.segment.target_pace_min_s_per_km,
                        "max_s_per_km": r.segment.target_pace_max_s_per_km,
                        "min_formatted": _fmt_pace(r.segment.target_pace_min_s_per_km),
                        "max_formatted": _fmt_pace(r.segment.target_pace_max_s_per_km),
                    }
                    if r.segment.target_pace_min_s_per_km is not None
                    else None
                ),
                "start_index": r.start_index,
                "end_index": r.end_index,
                "duration_actual_s": r.duration_actual_s,
                "actuals": {
                    "avg_heartrate_bpm": r.avg_heartrate,
                    "actual_zone": r.actual_zone,
                    "avg_pace_per_km": r.avg_pace_per_km,
                    "avg_pace_formatted": _fmt_pace(r.avg_pace_per_km),
                    "avg_speed_ms": r.avg_speed_ms,
                    "avg_speed_kmh": round(r.avg_speed_ms * 3.6, 2)
                    if r.avg_speed_ms
                    else None,
                    "avg_cadence": r.avg_cadence,
                    "avg_gap_per_km": r.avg_gap_per_km,
                    "avg_gap_formatted": _fmt_pace(r.avg_gap_per_km),
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
                    "has_pace": r.has_pace,
                    "data_completeness": r.data_completeness,
                },
            }
            for r in data["results"]
        ]
        overall_score = data["overall"]

    out = {
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
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_workout_compliance(out)


@app.command("create")
def create_workout(
    name: str = typer.Argument(
        ..., help="Workout display name (e.g. '10 Mar Intervals')."
    ),
    source: str = typer.Argument(
        "-",
        help="Path to JSON file, or '-' to read from stdin.",
    ),
) -> None:
    """Create a workout file from a JSON definition.

    Reads the workout JSON from a file or stdin and saves it as a .md file
    in ~/.fitops/workouts/.

    Example (from stdin):
      cat workout.json | fitops workouts create "My Workout" -

    Example (from file):
      fitops workouts create "My Workout" workout.json
    """
    import re
    import sys

    # Read JSON
    try:
        if source == "-":
            raw = sys.stdin.read()
        else:
            with open(source) as f:
                raw = f.read()
        workout_json = json.loads(raw)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        typer.echo(json.dumps({"error": f"Failed to read JSON: {e}"}, indent=2))
        raise typer.Exit(1)

    # Parse and validate segments
    try:
        segments = parse_segments_from_json(workout_json)
    except Exception as e:
        typer.echo(
            json.dumps({"error": f"Failed to parse workout JSON: {e}"}, indent=2)
        )
        raise typer.Exit(1)

    if not segments:
        typer.echo(
            json.dumps({"error": "No segments found in workout JSON."}, indent=2)
        )
        raise typer.Exit(1)

    # Compute total planned duration
    total_min = sum(s.duration_min for s in segments if s.duration_min)

    # Generate slug filename
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    if not slug:
        slug = "workout"

    # Determine sport (from JSON if provided, else default "run")
    sport = workout_json.get("sport", "run")

    # Generate frontmatter + markdown body
    meta_line = json.dumps(workout_json)
    body = generate_markdown_body(workout_json, name)
    markdown = (
        f"---\n"
        f"name: {name}\n"
        f"sport: {sport}\n"
        f"target_duration_min: {round(total_min)}\n"
        f"tags: []\n"
        f"workout_meta: {meta_line}\n"
        f"---\n\n"
        f"{body}"
    )

    # Save to workouts dir
    d = workouts_dir()
    file_path = d / f"{slug}.md"
    file_path.write_text(markdown, encoding="utf-8")

    typer.echo(
        json.dumps(
            {
                "_meta": make_meta(),
                "created": {
                    "name": name,
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "sport": sport,
                    "total_duration_min": round(total_min, 1),
                    "segment_count": len(segments),
                    "segments": [
                        {
                            "name": s.name,
                            "step_type": s.step_type,
                            "duration_min": round(s.duration_min, 1)
                            if s.duration_min
                            else None,
                            "target_focus_type": s.target_focus_type,
                        }
                        for s in segments
                    ],
                },
            },
            indent=2,
        )
    )


@app.command("simulate")
def simulate_workout(
    name: str = typer.Argument(
        ..., help="Workout name or filename (e.g. threshold-tuesday)."
    ),
    course_id: int | None = typer.Option(
        None, "--course", help="RaceCourse ID (from `fitops race courses`)."
    ),
    activity_id: int | None = typer.Option(
        None,
        "--activity",
        help="Strava activity ID — build course on the fly from cached streams.",
    ),
    base_pace: str | None = typer.Option(
        None,
        "--base-pace",
        help="Base pace MM:SS/km for HR-zone segments with no pace target.",
    ),
    temp: float | None = typer.Option(
        None, "--temp", help="Temperature °C (manual override)."
    ),
    humidity: float | None = typer.Option(
        None, "--humidity", help="Relative humidity % (manual override)."
    ),
    wind: float | None = typer.Option(None, "--wind", help="Wind speed m/s."),
    wind_dir: float | None = typer.Option(
        None, "--wind-dir", help="Wind direction degrees (0=N)."
    ),
    sim_date: str | None = typer.Option(
        None, "--date", help="Date YYYY-MM-DD for weather fetch."
    ),
    sim_hour: int = typer.Option(
        9, "--hour", help="Start hour local time (0-23) for weather fetch."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Simulate a workout on a course: per-segment terrain + weather adjusted paces."""
    import datetime as _dt

    from fitops.dashboard.queries.race import get_course
    from fitops.race.course_parser import (
        _parse_time as _parse_pace_time,
    )
    from fitops.race.course_parser import (
        build_km_segments,
        compute_total_elevation_gain,
        parse_strava_activity,
    )
    from fitops.workouts.json_parser import parse_segments_from_json
    from fitops.workouts.simulate import (
        result_to_dict,
        simulate_workout_on_course,
        validate_distance_mismatch,
    )

    init_db()

    # --- validate options ---
    if course_id is None and activity_id is None:
        typer.echo(
            json.dumps(
                {"error": "Provide --course <id> or --activity <strava_id>."}, indent=2
            )
        )
        raise typer.Exit(1)
    if course_id is not None and activity_id is not None:
        typer.echo(
            json.dumps(
                {"error": "Provide only one of --course or --activity, not both."},
                indent=2,
            )
        )
        raise typer.Exit(1)
    if (temp is None) != (humidity is None):
        typer.echo(
            json.dumps(
                {"error": "--temp and --humidity must be used together."}, indent=2
            )
        )
        raise typer.Exit(1)

    # --- load workout ---
    wf = get_workout_file(name)
    if wf is None:
        typer.echo(
            json.dumps(
                {"error": f"Workout {name!r} not found in ~/.fitops/workouts/."},
                indent=2,
            )
        )
        raise typer.Exit(1)

    if wf.meta.get("training"):
        segments = parse_segments_from_json(wf.meta)
    else:
        segments = parse_segments_from_body(wf.body)

    if not segments:
        typer.echo(
            json.dumps({"error": f"No segments found in workout {name!r}."}, indent=2)
        )
        raise typer.Exit(1)

    # --- base pace ---
    base_pace_s: float | None = None
    if base_pace is not None:
        try:
            base_pace_s = _parse_pace_time(base_pace)
        except (ValueError, IndexError):
            typer.echo(
                json.dumps(
                    {"error": f"Invalid --base-pace format: {base_pace!r}. Use MM:SS."},
                    indent=2,
                )
            )
            raise typer.Exit(1)

    # --- load / build course km-segments ---
    course_summary: dict = {}
    km_segs: list[dict] = []
    course_start_lat: float | None = None
    course_start_lon: float | None = None

    if course_id is not None:
        course = asyncio.run(get_course(course_id))
        if course is None:
            typer.echo(
                json.dumps({"error": f"Course {course_id} not found."}, indent=2)
            )
            raise typer.Exit(1)
        km_segs = course.get_km_segments()
        if not km_segs:
            typer.echo(
                json.dumps(
                    {"error": "Course has no segments. Re-import the course."}, indent=2
                )
            )
            raise typer.Exit(1)
        course_start_lat = course.start_lat
        course_start_lon = course.start_lon
        course_summary = course.to_summary_dict()

    else:
        # Build course on the fly from Strava activity streams
        async def _build_from_activity() -> tuple[
            list[dict], float | None, float | None
        ]:
            async with get_async_session() as session:
                try:
                    points = await parse_strava_activity(activity_id, session)  # type: ignore[arg-type]
                except ValueError as exc:
                    raise exc
                segs = build_km_segments(points)
                lat = points[0]["lat"] if points else None
                lon = points[0]["lon"] if points else None
                total_m = points[-1]["distance_from_start_m"] if points else 0.0
                elev_gain = compute_total_elevation_gain(points)
                return segs, lat, lon, total_m, elev_gain

        try:
            km_segs, course_start_lat, course_start_lon, _total_m, _elev_gain = (
                asyncio.run(_build_from_activity())
            )
        except ValueError as exc:
            typer.echo(json.dumps({"error": str(exc)}, indent=2))
            raise typer.Exit(1)

        if not km_segs:
            typer.echo(
                json.dumps(
                    {"error": f"No course points found for activity {activity_id}."},
                    indent=2,
                )
            )
            raise typer.Exit(1)

        course_summary = {
            "activity_strava_id": activity_id,
            "source": "activity_streams",
            "total_distance_km": round(_total_m / 1000, 2),
            "total_elevation_gain_m": round(_elev_gain, 1),
        }

    # --- resolve weather (same pattern as race.py simulate) ---
    _NEUTRAL_WEATHER = {
        "temperature_c": 15.0,
        "humidity_pct": 40.0,
        "wind_speed_ms": 0.0,
        "wind_direction_deg": 0.0,
    }

    weather_source = "neutral"
    weather = dict(_NEUTRAL_WEATHER)

    if temp is not None and humidity is not None:
        weather = {
            "temperature_c": temp,
            "humidity_pct": humidity,
            "wind_speed_ms": wind if wind is not None else 0.0,
            "wind_direction_deg": wind_dir if wind_dir is not None else 0.0,
        }
        weather_source = "manual"

    elif (
        sim_date is not None
        and course_start_lat is not None
        and course_start_lon is not None
    ):
        from fitops.weather.client import fetch_activity_weather, fetch_forecast_weather

        try:
            parsed_date = _dt.date.fromisoformat(sim_date)
        except ValueError:
            typer.echo(
                json.dumps(
                    {"error": f"Invalid date format: {sim_date!r}. Use YYYY-MM-DD."},
                    indent=2,
                )
            )
            raise typer.Exit(1)

        today = _dt.date.today()

        if parsed_date > today:
            fetched = asyncio.run(
                fetch_forecast_weather(
                    course_start_lat, course_start_lon, sim_date, sim_hour
                )
            )
            if fetched is None:
                typer.echo(
                    json.dumps(
                        {
                            "warning": "Forecast unavailable (beyond 16-day window). Using neutral conditions."
                        },
                        indent=2,
                    ),
                    err=True,
                )
            else:
                weather = {
                    "temperature_c": fetched.get("temperature_c", 15.0),
                    "humidity_pct": fetched.get("humidity_pct", 40.0),
                    "wind_speed_ms": fetched.get("wind_speed_ms", 0.0),
                    "wind_direction_deg": fetched.get("wind_direction_deg", 0.0),
                }
                weather_source = "forecast"
        else:
            sim_datetime = _dt.datetime(
                parsed_date.year,
                parsed_date.month,
                parsed_date.day,
                sim_hour,
                0,
                0,
                tzinfo=_dt.UTC,
            )
            fetched = asyncio.run(
                fetch_activity_weather(course_start_lat, course_start_lon, sim_datetime)
            )
            if fetched is None:
                typer.echo(
                    json.dumps(
                        {
                            "warning": "Historical weather unavailable, using neutral conditions."
                        },
                        indent=2,
                    ),
                    err=True,
                )
            else:
                weather = {
                    "temperature_c": fetched.get("temperature_c", 15.0),
                    "humidity_pct": fetched.get("humidity_pct", 40.0),
                    "wind_speed_ms": fetched.get("wind_speed_ms", 0.0),
                    "wind_direction_deg": fetched.get("wind_direction_deg", 0.0),
                }
                weather_source = "archive"

    # --- simulate ---
    results = simulate_workout_on_course(segments, km_segs, weather, base_pace_s)

    course_total_m = sum(s["distance_m"] for s in km_segs)
    mismatch_warning = validate_distance_mismatch(results, course_total_m)

    total_est_km = round(sum(r.est_distance_m for r in results) / 1000, 2)
    total_est_s = sum(r.est_segment_time_s for r in results)

    from fitops.race.course_parser import _fmt_duration

    out = {
        "_meta": make_meta(),
        "workout_name": wf.name,
        "course": course_summary,
        "weather": weather,
        "weather_source": weather_source,
        "total_est_workout_distance_km": total_est_km,
        "total_est_workout_time_fmt": _fmt_duration(total_est_s),
        "distance_mismatch_warning": mismatch_warning,
        "segments": [result_to_dict(r) for r in results],
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_workout_simulate(out)


@app.command("unlink")
def unlink_workout(
    activity_id: int = typer.Argument(..., help="Strava activity ID to unlink from."),
) -> None:
    """Remove the link between a workout and an activity."""
    init_db()

    async def _unlink():
        from datetime import datetime

        async with get_async_session() as session:
            # Resolve strava_id → internal activity_id
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

            workout_name = workout.name

            # Delete all segment rows for this workout
            res3 = await session.execute(
                select(WorkoutSegment).where(WorkoutSegment.workout_id == workout.id)
            )
            old_segments = res3.scalars().all()
            for seg in old_segments:
                await session.delete(seg)

            # Clear the link fields
            workout.activity_id = None
            workout.linked_at = None
            workout.status = "planned"
            workout.compliance_score = None
            workout.physiology_snapshot = None
            from datetime import datetime

            workout.updated_at = datetime.now(UTC)

            return workout_name, None

    workout_name, err = asyncio.run(_unlink())

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
                {"error": f"No workout linked to activity {activity_id}."}, indent=2
            )
        )
        raise typer.Exit(1)

    typer.echo(
        json.dumps(
            {
                "_meta": make_meta(),
                "unlinked": {
                    "workout_name": workout_name,
                    "activity_strava_id": activity_id,
                    "status": "planned",
                },
            },
            indent=2,
        )
    )
