from __future__ import annotations

import asyncio
import json

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
