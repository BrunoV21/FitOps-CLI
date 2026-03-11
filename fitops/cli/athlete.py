from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from sqlalchemy import select

from fitops.config.settings import get_settings
from fitops.db.migrations import init_db
from fitops.db.models.athlete import Athlete
from fitops.db.session import get_async_session
from fitops.output.formatter import make_meta
from fitops.strava.client import StravaClient
from fitops.utils.exceptions import NotAuthenticatedError

app = typer.Typer(no_args_is_help=True)


@app.command("profile")
def profile() -> None:
    """Show athlete profile and equipment."""
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
                select(Athlete).where(Athlete.strava_id == settings.athlete_id)
            )
            athlete = result.scalar_one_or_none()

        if athlete is None:
            typer.echo("Athlete profile not found locally. Run `fitops sync run` first.")
            raise typer.Exit(1)

        return {
            "_meta": make_meta(),
            "athlete": {
                "strava_id": athlete.strava_id,
                "name": f"{athlete.firstname or ''} {athlete.lastname or ''}".strip(),
                "username": athlete.username,
                "city": athlete.city,
                "country": athlete.country,
                "sex": athlete.sex,
                "weight_kg": athlete.weight_kg,
                "premium": athlete.premium,
                "profile_url": athlete.profile_url,
                "equipment": {
                    "bikes": athlete.bikes,
                    "shoes": athlete.shoes,
                },
            },
        }

    out = asyncio.run(_fetch())
    typer.echo(json.dumps(out, indent=2, default=str))


@app.command("stats")
def stats() -> None:
    """Show Strava cumulative athlete statistics."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    async def _fetch():
        client = StravaClient()
        data = await client.get_athlete_stats(settings.athlete_id)
        return {"_meta": make_meta(), "stats": data}

    out = asyncio.run(_fetch())
    typer.echo(json.dumps(out, indent=2, default=str))


@app.command("zones")
def zones() -> None:
    """Show HR and power zones configured in Strava."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    async def _fetch():
        client = StravaClient()
        data = await client.get_athlete_zones()
        return {"_meta": make_meta(), "zones": data}

    out = asyncio.run(_fetch())
    typer.echo(json.dumps(out, indent=2, default=str))


@app.command("equipment")
def equipment(
    type_filter: Optional[str] = typer.Option(None, "--type", help="Filter by type: shoes or bikes."),
) -> None:
    """Show equipment (shoes/bikes) with distance and activity counts."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    async def _fetch():
        async with get_async_session() as session:
            ath_res = await session.execute(
                select(Athlete).where(Athlete.strava_id == settings.athlete_id)
            )
            athlete = ath_res.scalar_one_or_none()

        if athlete is None:
            return None

        from fitops.db.models.activity import Activity
        from sqlalchemy import func

        async with get_async_session() as session:
            act_res = await session.execute(
                select(Activity.gear_id, func.count(Activity.id).label("count"),
                       func.sum(Activity.distance_m).label("total_m"))
                .where(Activity.athlete_id == settings.athlete_id, Activity.gear_id.isnot(None))
                .group_by(Activity.gear_id)
            )
            gear_stats = {row.gear_id: {"activity_count": row.count, "distance_m": row.total_m or 0}
                          for row in act_res.fetchall()}

        result = []
        items = []
        if type_filter != "bikes":
            items += [{"item": s, "type": "shoes"} for s in athlete.shoes]
        if type_filter != "shoes":
            items += [{"item": b, "type": "bikes"} for b in athlete.bikes]

        for entry in items:
            item = entry["item"]
            gid = item.get("id")
            stats = gear_stats.get(gid, {})
            strava_dist_km = round(item.get("distance_m", 0) / 1000, 2)
            local_dist_km = round(stats.get("distance_m", 0) / 1000, 2)
            result.append({
                "gear_id": gid,
                "name": item.get("name"),
                "type": entry["type"],
                "strava_total_distance_km": strava_dist_km,
                "local_activity_distance_km": local_dist_km,
                "local_activity_count": stats.get("activity_count", 0),
                "primary": item.get("primary", False),
            })

        return result

    items = asyncio.run(_fetch())
    if items is None:
        typer.echo("Athlete profile not found locally. Run `fitops sync run` first.", err=True)
        raise typer.Exit(1)

    typer.echo(json.dumps({
        "_meta": make_meta(total_count=len(items), filters_applied={"type": type_filter}),
        "equipment": items,
    }, indent=2, default=str))
