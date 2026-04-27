from __future__ import annotations

import asyncio

import typer

from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.config.settings import get_settings
from fitops.db.migrations import init_db

app = typer.Typer(no_args_is_help=True)


@app.command("recompute-power")
def recompute_power(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be computed without writing."),
    limit: int = typer.Option(0, "--limit", help="Max activities to process (0 = all)."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Recompute all eligible running activities, even when an estimate already exists.",
    ),
) -> None:
    """Backfill or recompute estimated running power for running activities with streams."""
    init_db()
    asyncio.run(_recompute_power(dry_run=dry_run, limit=limit or None, force=force))


async def _recompute_power(dry_run: bool, limit: int | None, force: bool) -> None:
    from sqlalchemy import select

    from fitops.analytics.running_power import persist_power_for_activity
    from fitops.dashboard.queries.activities import get_activity_streams
    from fitops.db.models.activity import RUN_SPORT_TYPES, Activity
    from fitops.db.session import get_async_session

    settings = get_settings()
    athlete_id = settings.athlete_id
    if not athlete_id:
        typer.echo("No athlete configured — run `fitops auth login` first.", err=True)
        raise typer.Exit(1)

    athlete_settings = get_athlete_settings()
    weight_kg = athlete_settings.weight_kg
    if not weight_kg:
        typer.echo("Body weight not set — run `fitops athlete set weight_kg <value>` first.", err=True)
        raise typer.Exit(1)

    async with get_async_session() as session:
        q = (
            select(Activity)
            .where(Activity.athlete_id == athlete_id)
            .where(Activity.sport_type.in_(list(RUN_SPORT_TYPES)))
            .where(Activity.streams_fetched == True)  # noqa: E712
            .order_by(Activity.start_date.desc())
        )
        if not force:
            q = q.where(Activity.est_power_avg_w == None)  # noqa: E711
        if limit:
            q = q.limit(limit)
        result = await session.execute(q)
        candidates = result.scalars().all()

    total = len(candidates)
    if total == 0:
        if force:
            typer.echo("No activities to process — no running activities with streams matched the request.")
        else:
            typer.echo("No activities to process — all runs with streams already have power estimates.")
        return

    typer.echo(f"Found {total} activit{'y' if total == 1 else 'ies'} to process{' (dry run)' if dry_run else ''}.")

    processed = skipped = 0
    for activity in candidates:
        streams = await get_activity_streams(activity.id)
        if not streams:
            skipped += 1
            continue

        if dry_run:
            typer.echo(f"  [dry-run] {activity.start_date_local or activity.start_date} — {activity.name}")
            processed += 1
            continue

        async with get_async_session() as session:
            result = await session.execute(
                select(Activity).where(Activity.id == activity.id)
            )
            row = result.scalar_one_or_none()
            if row:
                ok = await persist_power_for_activity(session, row.id, row, streams, weight_kg)
                avg_w = row.est_power_avg_w
            else:
                ok = False
                avg_w = None

        if ok and avg_w is not None:
            processed += 1
            typer.echo(f"  ✓ {activity.start_date_local or activity.start_date} — {activity.name} ({avg_w:.0f} W avg)")
        else:
            skipped += 1

    action = "Would process" if dry_run else "Processed"
    typer.echo(f"\n{action} {processed}/{total} activities. Skipped {skipped}.")
