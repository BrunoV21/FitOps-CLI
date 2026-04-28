from __future__ import annotations

import asyncio
import json

import typer
from sqlalchemy import select

from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.analytics.pace_zones import compute_pace_zones
from fitops.analytics.zones import compute_zones
from fitops.config.settings import get_settings
from fitops.db.migrations import init_db
from fitops.db.models.athlete import Athlete
from fitops.db.session import get_async_session
from fitops.output.formatter import make_meta
from fitops.output.text_formatter import (
    print_athlete_computed_zones,
    print_athlete_profile,
    print_athlete_stats,
    print_equipment_table,
)
from fitops.strava.client import StravaClient
from fitops.utils.exceptions import NotAuthenticatedError

app = typer.Typer(no_args_is_help=True)


@app.command("profile")
def profile(
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
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
            typer.echo(
                "Athlete profile not found locally. Run `fitops sync run` first."
            )
            raise typer.Exit(1)

        # Load local physiology settings
        asettings = get_athlete_settings()
        sd = asettings.to_dict()

        def _fmt_pace(s: float | None) -> str | None:
            if s is None:
                return None
            si = int(s)
            return f"{si // 60}:{si % 60:02d}/km"

        # Estimate VO2max from recent activities
        from fitops.analytics.vo2max import estimate_vo2max

        vo2max_result = await estimate_vo2max(athlete_id=settings.athlete_id)

        physiology: dict = {
            "max_hr": sd.get("max_hr"),
            "resting_hr": sd.get("resting_hr"),
            "lthr": sd.get("lthr"),
            "ftp": sd.get("ftp"),
            "lt1_pace": _fmt_pace(sd.get("lt1_pace_s")),
            "lt2_pace": _fmt_pace(sd.get("threshold_pace_per_km_s")),
            "vo2max_pace": _fmt_pace(sd.get("vo2max_pace_s")),
        }
        if vo2max_result:
            physiology["vo2max"] = {
                "estimate": vo2max_result.estimate,
                "vdot": vo2max_result.vdot,
                "confidence": vo2max_result.confidence,
                "confidence_label": vo2max_result.confidence_label,
                "based_on_activity": {
                    "name": vo2max_result.activity_name,
                    "date": str(vo2max_result.activity_date)
                    if vo2max_result.activity_date
                    else None,
                    "distance_km": vo2max_result.distance_km,
                    "pace_per_km": vo2max_result.pace_per_km,
                },
            }
        else:
            physiology["vo2max"] = None

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
                "physiology": physiology,
            },
        }

    out = asyncio.run(_fetch())
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_athlete_profile(out["athlete"])


@app.command("stats")
def stats(
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
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
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_athlete_stats(out["stats"])


@app.command("zones")
def zones(
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Show computed HR and pace zones from local physiology settings."""
    asettings = get_athlete_settings()
    method = asettings.best_zone_method()

    if method == "none":
        typer.echo(
            "No zone parameters configured. Set LTHR: fitops analytics zones --set-lthr 165",
            err=True,
        )
        raise typer.Exit(1)

    zone_result = compute_zones(
        method=method,
        lthr=asettings.lthr,
        max_hr=asettings.max_hr,
        resting_hr=asettings.resting_hr,
    )
    if zone_result is None:
        typer.echo(f"Missing parameters for method '{method}'.", err=True)
        raise typer.Exit(1)

    out: dict = {"_meta": make_meta(), "zones": zone_result.to_dict()}

    def _inject_pace(key_fmt: str, key_s: str, pace_s: float | None) -> None:
        if pace_s is not None:
            out["zones"]["thresholds"][key_fmt] = (
                f"{int(pace_s // 60)}:{int(pace_s % 60):02d}/km"
            )
            out["zones"]["thresholds"][key_s] = pace_s

    _inject_pace("lt1_pace_fmt", "lt1_pace_s", asettings.lt1_pace_s)
    _inject_pace("lt2_pace_fmt", "lt2_pace_s", asettings.threshold_pace_per_km_s)
    _inject_pace("vo2max_pace_fmt", "vo2max_pace_s", asettings.vo2max_pace_s)

    threshold_pace_s = asettings.threshold_pace_per_km_s
    if threshold_pace_s:
        pz = compute_pace_zones(int(threshold_pace_s))
        out["pace_zones"] = [
            {
                "zone": z["zone"],
                "name": z["name"],
                "min_s_per_km": z.get("min_s_per_km"),
                "max_s_per_km": z.get("max_s_per_km"),
                "min_pace_fmt": z.get("min_pace_fmt"),
                "max_pace_fmt": z.get("max_pace_fmt"),
            }
            for z in pz.zones
        ]

    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_athlete_computed_zones(out)


@app.command("set")
def set_physiology(
    weight: float | None = typer.Option(None, "--weight", help="Body weight in kg."),
    height: float | None = typer.Option(None, "--height", help="Height in cm."),
    birthday: str | None = typer.Option(
        None, "--birthday", help="Date of birth (YYYY-MM-DD)."
    ),
    ftp: float | None = typer.Option(None, "--ftp", help="FTP in watts (cyclists)."),
) -> None:
    """Set physiology values (weight, height, birthday, ftp) used for analytics."""
    if weight is None and height is None and birthday is None and ftp is None:
        typer.echo(
            "Provide at least one of: --weight, --height, --birthday, --ftp", err=True
        )
        raise typer.Exit(1)

    from fitops.analytics.athlete_settings import get_athlete_settings

    s = get_athlete_settings()
    updates = {}
    if weight is not None:
        updates["weight_kg"] = weight
    if height is not None:
        updates["height_cm"] = height
    if birthday is not None:
        updates["birthday"] = birthday
    if ftp is not None:
        updates["ftp"] = ftp
    s.set(**updates)

    # Mirror weight/birthday to the DB athlete record so profile shows them
    settings = get_settings()
    if settings.athlete_id and (weight is not None or birthday is not None):
        init_db()

        async def _update_db():
            async with get_async_session() as session:
                result = await session.execute(
                    select(Athlete).where(Athlete.strava_id == settings.athlete_id)
                )
                athlete = result.scalar_one_or_none()
                if athlete:
                    if weight is not None:
                        athlete.weight_kg = weight
                    if birthday is not None:
                        athlete.birthday = birthday

        asyncio.run(_update_db())

    parts = ", ".join(f"{k}={v}" for k, v in updates.items())
    typer.echo(f"Saved: {parts}")


@app.command("equipment")
def equipment(
    type_filter: str | None = typer.Option(
        None, "--type", help="Filter by type: shoes or bikes."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
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

        from sqlalchemy import func

        from fitops.db.models.activity import Activity

        async with get_async_session() as session:
            act_res = await session.execute(
                select(
                    Activity.gear_id,
                    func.count(Activity.id).label("count"),
                    func.sum(Activity.distance_m).label("total_m"),
                )
                .where(
                    Activity.athlete_id == settings.athlete_id,
                    Activity.gear_id.isnot(None),
                )
                .group_by(Activity.gear_id)
            )
            gear_stats = {
                row.gear_id: {
                    "activity_count": row.count,
                    "distance_m": row.total_m or 0,
                }
                for row in act_res.fetchall()
            }

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
            result.append(
                {
                    "gear_id": gid,
                    "name": item.get("name"),
                    "type": entry["type"],
                    "strava_total_distance_km": strava_dist_km,
                    "local_activity_distance_km": local_dist_km,
                    "local_activity_count": stats.get("activity_count", 0),
                    "primary": item.get("primary", False),
                }
            )

        return result

    items = asyncio.run(_fetch())
    if items is None:
        typer.echo(
            "Athlete profile not found locally. Run `fitops sync run` first.", err=True
        )
        raise typer.Exit(1)

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "_meta": make_meta(
                        total_count=len(items), filters_applied={"type": type_filter}
                    ),
                    "equipment": items,
                },
                indent=2,
                default=str,
            )
        )
    else:
        print_equipment_table(items)
