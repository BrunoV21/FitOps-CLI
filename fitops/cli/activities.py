from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

import typer
from sqlalchemy import select, desc

from fitops.config.settings import get_settings
from fitops.db.migrations import init_db
from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.models.activity_laps import ActivityLap
from fitops.db.models.athlete import Athlete
from fitops.db.session import get_async_session
from fitops.output.formatter import format_activity_row, make_meta, _fmt_seconds, _round2
from fitops.output.text_formatter import (
    print_activities_table,
    print_activity_detail,
    print_laps_table,
    print_streams_summary,
)
from fitops.strava.client import StravaClient
from fitops.utils.exceptions import FitOpsError, NotAuthenticatedError

app = typer.Typer(no_args_is_help=True)


async def _get_gear_lookup() -> dict:
    settings = get_settings()
    athlete_id = settings.athlete_id
    if not athlete_id:
        return {}
    async with get_async_session() as session:
        result = await session.execute(
            select(Athlete).where(Athlete.strava_id == athlete_id)
        )
        athlete = result.scalar_one_or_none()
        if not athlete:
            return {}
        lookup: dict = {}
        for b in athlete.bikes:
            lookup[b["id"]] = {"name": b["name"], "type": "bike"}
        for s in athlete.shoes:
            lookup[s["id"]] = {"name": s["name"], "type": "shoes"}
        return lookup


@app.command("list")
def list_activities(
    sport: Optional[str] = typer.Option(None, "--sport", help="Filter by sport type (e.g. Run, Ride)."),
    limit: int = typer.Option(20, "--limit", help="Max number of activities to return."),
    after: Optional[str] = typer.Option(None, "--after", help="Filter activities after date (YYYY-MM-DD)."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """List synced activities."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    async def _fetch():
        gear_lookup = await _get_gear_lookup()
        async with get_async_session() as session:
            stmt = select(Activity).order_by(desc(Activity.start_date))
            if sport:
                stmt = stmt.where(Activity.sport_type == sport)
            if after:
                try:
                    after_dt = datetime.fromisoformat(after).replace(tzinfo=timezone.utc)
                    stmt = stmt.where(Activity.start_date >= after_dt)
                except ValueError:
                    pass
            stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        formatted = [
            format_activity_row(
                {c.name: getattr(r, c.name) for c in r.__table__.columns},
                gear_lookup,
            )
            for r in rows
        ]
        filters: dict = {"limit": limit}
        if sport:
            filters["sport_type"] = sport
        if after:
            filters["after"] = after
        return {"_meta": make_meta(total_count=len(formatted), filters_applied=filters), "activities": formatted}

    output = asyncio.run(_fetch())
    if json_output:
        typer.echo(json.dumps(output, indent=2, default=str))
    else:
        print_activities_table(output["activities"])


@app.command("get")
def get_activity(
    activity_id: int = typer.Argument(..., help="Strava activity ID."),
    fetch_fresh: bool = typer.Option(False, "--fresh", help="Re-fetch detail from Strava API."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Get detailed info for a single activity."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    async def _fetch():
        gear_lookup = await _get_gear_lookup()
        async with get_async_session() as session:
            result = await session.execute(
                select(Activity).where(Activity.strava_id == activity_id)
            )
            row = result.scalar_one_or_none()

        if row is None:
            typer.echo(f"Activity {activity_id} not found locally. Run `fitops sync run` first.", err=True)
            raise typer.Exit(1)

        client = StravaClient()

        if fetch_fresh or not row.detail_fetched:
            data = await client.get_activity(activity_id)
            async with get_async_session() as session:
                result2 = await session.execute(
                    select(Activity).where(Activity.strava_id == activity_id)
                )
                row2 = result2.scalar_one_or_none()
                if row2:
                    row2.update_from_strava_data(data)
                    row2.detail_fetched = True
                    row = row2

        if fetch_fresh or not row.streams_fetched:
            try:
                stream_data = await client.get_activity_streams(activity_id)
                async with get_async_session() as session:
                    result3 = await session.execute(
                        select(Activity).where(Activity.strava_id == activity_id)
                    )
                    row3 = result3.scalar_one_or_none()
                    if row3:
                        for stream_type, stream_obj in stream_data.items():
                            data_list = stream_obj.get("data", []) if isinstance(stream_obj, dict) else stream_obj
                            existing = await session.execute(
                                select(ActivityStream).where(
                                    ActivityStream.activity_id == row3.id,
                                    ActivityStream.stream_type == stream_type,
                                )
                            )
                            if existing.scalar_one_or_none() is None:
                                session.add(ActivityStream.from_strava_stream(row3.id, stream_type, data_list))
                        row3.streams_fetched = True
                        row = row3
            except Exception:
                pass  # streams are best-effort; don't block the activity output

        row_dict = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        formatted = format_activity_row(row_dict, gear_lookup)

        # Enrich with HR drift if streams are available
        if row.streams_fetched:
            from fitops.analytics.activity_insights import compute_hr_drift
            async with get_async_session() as session:
                hr_res = await session.execute(
                    select(ActivityStream).where(
                        ActivityStream.activity_id == row.id,
                        ActivityStream.stream_type == "heartrate",
                    )
                )
                vel_res = await session.execute(
                    select(ActivityStream).where(
                        ActivityStream.activity_id == row.id,
                        ActivityStream.stream_type == "velocity_smooth",
                    )
                )
                hr_row = hr_res.scalar_one_or_none()
                vel_row = vel_res.scalar_one_or_none()
            if hr_row and vel_row:
                drift = compute_hr_drift(hr_row.data or [], vel_row.data or [])
                if drift:
                    formatted["insights"] = {"hr_drift": drift}

        return {"_meta": make_meta(total_count=1), "activity": formatted}

    output = asyncio.run(_fetch())
    if json_output:
        typer.echo(json.dumps(output, indent=2, default=str))
    else:
        print_activity_detail(output["activity"])


@app.command("streams")
def get_streams(
    activity_id: int = typer.Argument(..., help="Strava activity ID."),
    fetch_fresh: bool = typer.Option(False, "--fresh", help="Re-fetch streams from Strava API."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Get activity stream data (heartrate, pace, power, etc.)."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    async def _fetch():
        async with get_async_session() as session:
            result = await session.execute(
                select(Activity).where(Activity.strava_id == activity_id)
            )
            activity = result.scalar_one_or_none()
            if not activity:
                typer.echo(f"Activity {activity_id} not found locally.", err=True)
                raise typer.Exit(1)

            if fetch_fresh or not activity.streams_fetched:
                client = StravaClient()
                stream_data = await client.get_activity_streams(activity_id)
                for stream_type, stream_obj in stream_data.items():
                    data_list = stream_obj.get("data", []) if isinstance(stream_obj, dict) else stream_obj
                    existing = await session.execute(
                        select(ActivityStream).where(
                            ActivityStream.activity_id == activity.id,
                            ActivityStream.stream_type == stream_type,
                        )
                    )
                    existing_row = existing.scalar_one_or_none()
                    if existing_row is None:
                        session.add(ActivityStream.from_strava_stream(activity.id, stream_type, data_list))
                activity.streams_fetched = True

            streams_result = await session.execute(
                select(ActivityStream).where(ActivityStream.activity_id == activity.id)
            )
            streams = streams_result.scalars().all()
            activity_id_val = activity_id

        return {
            "_meta": make_meta(),
            "activity_strava_id": activity_id_val,
            "streams": {
                s.stream_type: {"data_length": s.data_length, "data": s.data}
                for s in streams
            },
        }

    out = asyncio.run(_fetch())
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_streams_summary(out["streams"], activity_id)


@app.command("laps")
def get_laps(
    activity_id: int = typer.Argument(..., help="Strava activity ID."),
    fetch_fresh: bool = typer.Option(False, "--fresh", help="Re-fetch laps from Strava API."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Get lap splits for an activity."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    async def _fetch():
        async with get_async_session() as session:
            result = await session.execute(
                select(Activity).where(Activity.strava_id == activity_id)
            )
            activity = result.scalar_one_or_none()
            if not activity:
                typer.echo(f"Activity {activity_id} not found locally.", err=True)
                raise typer.Exit(1)

            if fetch_fresh or not activity.laps_fetched:
                client = StravaClient()
                laps_data = await client.get_activity_laps(activity_id)
                for lap in laps_data:
                    session.add(ActivityLap.from_strava_data(activity.id, lap))
                activity.laps_fetched = True

            laps_result = await session.execute(
                select(ActivityLap)
                .where(ActivityLap.activity_id == activity.id)
                .order_by(ActivityLap.lap_index)
            )
            laps = laps_result.scalars().all()

        return {
            "_meta": make_meta(total_count=len(laps)),
            "activity_strava_id": activity_id,
            "laps": [
                {
                    "lap_index": lap.lap_index,
                    "name": lap.name,
                    "duration": {
                        "moving_time_seconds": lap.moving_time_s,
                        "moving_time_formatted": _fmt_seconds(lap.moving_time_s),
                    },
                    "distance": {
                        "meters": _round2(lap.distance_m),
                        "km": _round2(lap.distance_m / 1000) if lap.distance_m else None,
                    },
                    "average_speed_ms": _round2(lap.average_speed_ms),
                    "heart_rate": {
                        "average_bpm": _round2(lap.average_heartrate),
                        "max_bpm": lap.max_heartrate,
                    } if lap.average_heartrate else None,
                    "average_watts": _round2(lap.average_watts),
                }
                for lap in laps
            ],
        }

    out = asyncio.run(_fetch())
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_laps_table(out["laps"], activity_id)
