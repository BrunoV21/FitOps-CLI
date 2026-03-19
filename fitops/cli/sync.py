from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

import typer
from sqlalchemy import select

from fitops.analytics.weather_pace import wbgt_approx, pace_heat_factor as _pace_heat_factor
from fitops.config.state import get_sync_state
from fitops.config.settings import get_settings
from fitops.dashboard.queries.weather import upsert_activity_weather
from fitops.db.migrations import init_db
from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.session import get_async_session
from fitops.strava.sync_engine import SyncEngine
from fitops.utils.exceptions import FitOpsError, NotAuthenticatedError
from fitops.output.text_formatter import print_sync_result, print_sync_streams_result, print_sync_status
from fitops.weather.client import fetch_activity_weather

app = typer.Typer(no_args_is_help=True)


async def _fetch_streams_for_activities(
    activity_ids: list[int], strava_ids: list[int], force: bool = False
) -> dict:
    """Fetch and cache streams for a list of (internal_id, strava_id) pairs."""
    from sqlalchemy import delete as sa_delete
    from fitops.strava.client import StravaClient
    client = StravaClient()
    fetched = 0
    errors = 0
    total = len(activity_ids)
    for idx, (internal_id, strava_id) in enumerate(zip(activity_ids, strava_ids), 1):
        typer.echo(f"  [{idx}/{total}] activity {strava_id}...", err=True)
        try:
            if force:
                async with get_async_session() as session:
                    await session.execute(
                        sa_delete(ActivityStream).where(ActivityStream.activity_id == internal_id)
                    )
            stream_data = await client.get_activity_streams(strava_id)
            async with get_async_session() as session:
                for stream_type, stream_obj in stream_data.items():
                    data_list = stream_obj.get("data", []) if isinstance(stream_obj, dict) else stream_obj
                    if not force:
                        existing = await session.execute(
                            select(ActivityStream).where(
                                ActivityStream.activity_id == internal_id,
                                ActivityStream.stream_type == stream_type,
                            )
                        )
                        if existing.scalar_one_or_none() is not None:
                            continue
                    session.add(ActivityStream.from_strava_stream(internal_id, stream_type, data_list))
                activity_row = await session.execute(
                    select(Activity).where(Activity.id == internal_id)
                )
                row = activity_row.scalar_one_or_none()
                if row:
                    row.streams_fetched = True
            fetched += 1
        except Exception as e:
            typer.echo(f"    error: {e}", err=True)
            errors += 1
        # Rate limit: ~1 request/sec to stay under 100 req/15min
        if idx < total:
            await asyncio.sleep(1.0)
    return {"streams_fetched": fetched, "errors": errors}


async def _fetch_weather_for_strava_ids(strava_ids: list[int]) -> dict:
    """Fetch and store weather for a list of activity strava_ids."""
    import json as _json
    fetched = errors = 0
    async with get_async_session() as session:
        result = await session.execute(
            select(Activity).where(Activity.strava_id.in_(strava_ids))
        )
        acts = result.scalars().all()

    for act in acts:
        if not act.start_latlng or not act.start_date:
            continue
        typer.echo(f"  weather {act.strava_id}...", err=True)
        try:
            coords = _json.loads(act.start_latlng)
            if not (isinstance(coords, list) and len(coords) == 2):
                continue
            lat, lng = float(coords[0]), float(coords[1])
            weather = await fetch_activity_weather(lat, lng, act.start_date)
            if weather:
                tc = weather.get("temperature_c")
                hum = weather.get("humidity_pct")
                if tc is not None and hum is not None:
                    weather["wbgt_c"] = round(wbgt_approx(tc, hum), 2)
                    weather["pace_heat_factor"] = round(_pace_heat_factor(tc, hum), 4)
                await upsert_activity_weather(act.strava_id, weather, source="open-meteo")
                fetched += 1
        except Exception as e:
            typer.echo(f"    weather error: {e}", err=True)
            errors += 1
        await asyncio.sleep(0.1)

    return {"weather_fetched": fetched, "weather_errors": errors}


@app.command("run")
def run(
    full: bool = typer.Option(False, "--full", help="Full historical sync from the beginning."),
    after: Optional[str] = typer.Option(None, "--after", help="Sync from this date (YYYY-MM-DD)."),
    streams: bool = typer.Option(False, "--streams", help="Also fetch streams for newly synced activities."),
    force_streams: bool = typer.Option(False, "--force-streams", help="Re-fetch streams for all activities (slow — ~1 req/sec)."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Sync activities from Strava."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    after_dt: Optional[datetime] = None
    if after:
        try:
            after_dt = datetime.fromisoformat(after).replace(tzinfo=timezone.utc)
        except ValueError:
            typer.echo(f"Invalid date format: {after}. Use YYYY-MM-DD.", err=True)
            raise typer.Exit(1)

    engine = SyncEngine()
    try:
        sync_type = "full" if full else ("custom" if after_dt else "incremental")
        typer.echo(f"Starting {sync_type} sync...")
        result = asyncio.run(engine.run(full=full, after_override=after_dt))

        streams_result: Optional[dict] = None
        weather_result: Optional[dict] = None
        if force_streams:
            typer.echo("Fetching streams for all activities (force refresh)...")
            streams_result = asyncio.run(_fetch_and_cache_new_streams(limit=0, force=True))
        elif streams and result.activities_created > 0:
            typer.echo(f"Fetching streams for {result.activities_created} new activities...")
            streams_result = asyncio.run(_fetch_and_cache_new_streams(limit=result.activities_created))

        # Auto-fetch weather for new activities (when streams are also fetched)
        if (streams or force_streams) and result.activities_created > 0:
            typer.echo(f"Fetching weather for {result.activities_created} new activities...")
            async def _get_new_ids() -> list[int]:
                async with get_async_session() as session:
                    res = await session.execute(
                        select(Activity.strava_id)
                        .order_by(Activity.start_date.desc())
                        .limit(result.activities_created)
                    )
                    return [r[0] for r in res.all()]
            new_ids = asyncio.run(_get_new_ids())
            weather_result = asyncio.run(_fetch_weather_for_strava_ids(new_ids))

        out: dict = {
            "sync_type": sync_type,
            "activities_created": result.activities_created,
            "activities_updated": result.activities_updated,
            "pages_fetched": result.pages_fetched,
            "duration_s": round(result.duration_s, 2),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        if streams_result:
            out["streams"] = streams_result
        if weather_result:
            out["weather"] = weather_result
        if json_output:
            typer.echo(json.dumps(out, indent=2))
        else:
            print_sync_result(out)
    except FitOpsError as e:
        typer.echo(f"Sync failed: {e}", err=True)
        raise typer.Exit(1)


async def _fetch_and_cache_new_streams(limit: int = 0, force: bool = False) -> dict:
    """Fetch streams for activities that don't have them (or all, if force=True).

    limit=0 means no limit (fetch all matching activities).
    """
    async with get_async_session() as session:
        stmt = (
            select(Activity.id, Activity.strava_id)
            .order_by(Activity.start_date.desc())
        )
        if not force:
            stmt = stmt.where(Activity.streams_fetched == False)  # noqa: E712
        if limit > 0:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        rows = result.fetchall()
    if not rows:
        return {"streams_fetched": 0, "errors": 0}
    internal_ids = [r[0] for r in rows]
    strava_ids = [r[1] for r in rows]
    return await _fetch_streams_for_activities(internal_ids, strava_ids, force=force)


@app.command("streams")
def sync_streams(
    limit: int = typer.Option(0, "--limit", help="Max activities to fetch streams for. 0 = all (default)."),
    force: bool = typer.Option(False, "--force", help="Re-fetch streams even for activities that already have them."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Fetch and cache streams for all activities that don't have them yet."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    async def _run():
        async with get_async_session() as session:
            stmt = select(Activity.id, Activity.strava_id).order_by(Activity.start_date.desc())
            if not force:
                stmt = stmt.where(Activity.streams_fetched == False)  # noqa: E712
            if limit > 0:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            rows = result.fetchall()

        if not rows:
            return {"streams_fetched": 0, "errors": 0, "message": "No activities need streams."}

        typer.echo(f"Fetching streams for {len(rows)} activities (~1 req/sec)...", err=True)
        internal_ids = [r[0] for r in rows]
        strava_ids = [r[1] for r in rows]
        return await _fetch_streams_for_activities(internal_ids, strava_ids, force=force)

    try:
        result = asyncio.run(_run())
        if json_output:
            typer.echo(json.dumps(result, indent=2))
        else:
            print_sync_streams_result(result)
    except FitOpsError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("status")
def status(
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Show sync state."""
    state = get_sync_state()
    state_dict = {
        "last_sync_at": str(state.last_sync_at) if state.last_sync_at else None,
        "activities_synced_total": state.activities_synced_total,
        "recent_syncs": state.sync_history[:5],
    }
    if json_output:
        typer.echo(json.dumps(state_dict, indent=2))
    else:
        print_sync_status(state_dict)
