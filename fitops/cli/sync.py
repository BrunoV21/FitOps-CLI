from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

import typer
from sqlalchemy import select

from fitops.config.state import get_sync_state
from fitops.config.settings import get_settings
from fitops.db.migrations import init_db
from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.session import get_async_session
from fitops.strava.sync_engine import SyncEngine
from fitops.utils.exceptions import FitOpsError, NotAuthenticatedError

app = typer.Typer(no_args_is_help=True)

STREAMS_BATCH_LIMIT = 50  # cap per run to stay within Strava rate limits


async def _fetch_streams_for_activities(activity_ids: list[int], strava_ids: list[int]) -> dict:
    """Fetch and cache streams for a list of (internal_id, strava_id) pairs."""
    from fitops.strava.client import StravaClient
    client = StravaClient()
    fetched = 0
    errors = 0
    for internal_id, strava_id in zip(activity_ids, strava_ids):
        try:
            stream_data = await client.get_activity_streams(strava_id)
            async with get_async_session() as session:
                for stream_type, stream_obj in stream_data.items():
                    data_list = stream_obj.get("data", []) if isinstance(stream_obj, dict) else stream_obj
                    existing = await session.execute(
                        select(ActivityStream).where(
                            ActivityStream.activity_id == internal_id,
                            ActivityStream.stream_type == stream_type,
                        )
                    )
                    if existing.scalar_one_or_none() is None:
                        session.add(ActivityStream.from_strava_stream(internal_id, stream_type, data_list))
                activity_row = await session.execute(
                    select(Activity).where(Activity.id == internal_id)
                )
                row = activity_row.scalar_one_or_none()
                if row:
                    row.streams_fetched = True
            fetched += 1
        except Exception:
            errors += 1
    return {"streams_fetched": fetched, "errors": errors}


@app.command("run")
def run(
    full: bool = typer.Option(False, "--full", help="Full historical sync from the beginning."),
    after: Optional[str] = typer.Option(None, "--after", help="Sync from this date (YYYY-MM-DD)."),
    streams: bool = typer.Option(False, "--streams", help="Also fetch HR streams for newly synced activities (up to 50)."),
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
        if streams and result.activities_created > 0:
            typer.echo(f"Fetching streams for up to {STREAMS_BATCH_LIMIT} new activities...")
            streams_result = asyncio.run(_fetch_and_cache_new_streams(limit=STREAMS_BATCH_LIMIT))

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
        typer.echo(json.dumps(out, indent=2))
    except FitOpsError as e:
        typer.echo(f"Sync failed: {e}", err=True)
        raise typer.Exit(1)


async def _fetch_and_cache_new_streams(limit: int) -> dict:
    """Fetch streams for activities with HR data that don't have streams yet."""
    async with get_async_session() as session:
        result = await session.execute(
            select(Activity.id, Activity.strava_id)
            .where(Activity.streams_fetched == False)  # noqa: E712
            .where(Activity.average_heartrate.isnot(None))
            .order_by(Activity.start_date.desc())
            .limit(limit)
        )
        rows = result.fetchall()
    if not rows:
        return {"streams_fetched": 0, "errors": 0}
    internal_ids = [r[0] for r in rows]
    strava_ids = [r[1] for r in rows]
    return await _fetch_streams_for_activities(internal_ids, strava_ids)


@app.command("streams")
def sync_streams(
    limit: int = typer.Option(50, "--limit", help="Max activities to fetch streams for (default 50, Strava rate limit safe)."),
    all_sports: bool = typer.Option(False, "--all", help="Include activities without HR data too."),
) -> None:
    """Fetch and cache streams for activities that don't have them yet."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    async def _run():
        async with get_async_session() as session:
            stmt = (
                select(Activity.id, Activity.strava_id)
                .where(Activity.streams_fetched == False)  # noqa: E712
                .order_by(Activity.start_date.desc())
                .limit(limit)
            )
            if not all_sports:
                stmt = stmt.where(Activity.average_heartrate.isnot(None))
            result = await session.execute(stmt)
            rows = result.fetchall()

        if not rows:
            return {"streams_fetched": 0, "errors": 0, "message": "No activities need streams."}

        typer.echo(f"Fetching streams for {len(rows)} activities...", err=True)
        internal_ids = [r[0] for r in rows]
        strava_ids = [r[1] for r in rows]
        return await _fetch_streams_for_activities(internal_ids, strava_ids)

    try:
        result = asyncio.run(_run())
        typer.echo(json.dumps(result, indent=2))
    except FitOpsError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("status")
def status() -> None:
    """Show sync state."""
    state = get_sync_state()
    typer.echo(
        json.dumps(
            {
                "last_sync_at": str(state.last_sync_at) if state.last_sync_at else None,
                "activities_synced_total": state.activities_synced_total,
                "recent_syncs": state.sync_history[:5],
            },
            indent=2,
        )
    )
