from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

import typer

from fitops.config.state import get_sync_state
from fitops.config.settings import get_settings
from fitops.db.migrations import init_db
from fitops.strava.sync_engine import SyncEngine
from fitops.utils.exceptions import FitOpsError, NotAuthenticatedError

app = typer.Typer(no_args_is_help=True)


@app.command("run")
def run(
    full: bool = typer.Option(False, "--full", help="Full historical sync from the beginning."),
    after: Optional[str] = typer.Option(None, "--after", help="Sync from this date (YYYY-MM-DD)."),
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
        typer.echo(
            json.dumps(
                {
                    "sync_type": sync_type,
                    "activities_created": result.activities_created,
                    "activities_updated": result.activities_updated,
                    "pages_fetched": result.pages_fetched,
                    "duration_s": round(result.duration_s, 2),
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
        )
    except FitOpsError as e:
        typer.echo(f"Sync failed: {e}", err=True)
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
