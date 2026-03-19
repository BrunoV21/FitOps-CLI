from __future__ import annotations

import asyncio
import datetime
import json
from typing import Optional

import typer

from fitops.db.migrations import init_db
from fitops.db.session import get_async_session
from fitops.output.formatter import make_meta
from fitops.race.course_parser import (
    build_km_segments,
    compute_total_elevation_gain,
    detect_source,
    parse_gpx,
    parse_mapmyrun_url,
    parse_strava_activity,
    parse_tcx,
    _parse_time,
)
from fitops.race.simulation import simulate_pacer_mode, simulate_splits
from fitops.dashboard.queries.race import (
    delete_course as _delete_course,
    get_all_courses,
    get_course,
    save_course,
)

app = typer.Typer(no_args_is_help=True)

# ---------------------------------------------------------------------------
# Neutral weather defaults
# ---------------------------------------------------------------------------
_NEUTRAL_WEATHER = {
    "temperature_c": 15.0,
    "humidity_pct": 40.0,
    "wind_speed_ms": 0.0,
    "wind_direction_deg": 0.0,
}


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

@app.command("import")
def import_course(
    source: str = typer.Argument(..., help="GPX/TCX file path, MapMyRun URL, or Strava activity ID."),
    name: str = typer.Option(..., "--name", help="Course name (required)."),
) -> None:
    """Import a race course from a file, URL, or Strava activity ID."""
    init_db()

    try:
        source_type, source_value = detect_source(source)
    except ValueError as e:
        typer.echo(json.dumps({"error": str(e)}, indent=2))
        raise typer.Exit(1)

    if source_type == "gpx":
        points = parse_gpx(source_value)
    elif source_type == "tcx":
        points = parse_tcx(source_value)
    elif source_type == "mapmyrun":
        points = asyncio.run(parse_mapmyrun_url(source_value))
    elif source_type == "strava":
        async def _from_strava() -> list[dict]:
            async with get_async_session() as session:
                return await parse_strava_activity(int(source_value), session)
        points = asyncio.run(_from_strava())
    else:
        typer.echo(json.dumps({"error": f"Unknown source type: {source_type}"}, indent=2))
        raise typer.Exit(1)

    if not points:
        typer.echo(json.dumps({"error": "No course points found in source."}, indent=2))
        raise typer.Exit(1)

    segments = build_km_segments(points)
    total_dist = points[-1]["distance_from_start_m"]
    elev_gain = compute_total_elevation_gain(points)
    file_format = source_type if source_type in ("gpx", "tcx") else None
    source_ref = source_value if source_type in ("mapmyrun", "strava") else None

    result = asyncio.run(save_course(
        name=name,
        source=source_type,
        source_ref=source_ref,
        file_format=file_format,
        course_points=points,
        km_segments=segments,
        total_distance_m=total_dist,
        total_elevation_gain_m=elev_gain,
    ))
    typer.echo(json.dumps({"_meta": make_meta(), "course": result}, indent=2, default=str))


# ---------------------------------------------------------------------------
# courses
# ---------------------------------------------------------------------------

@app.command("courses")
def courses() -> None:
    """List all imported race courses."""
    init_db()
    result = asyncio.run(get_all_courses())
    typer.echo(json.dumps({
        "_meta": make_meta(total_count=len(result)),
        "courses": result,
    }, indent=2, default=str))


# ---------------------------------------------------------------------------
# course
# ---------------------------------------------------------------------------

@app.command("course")
def course_detail(
    course_id: int = typer.Argument(..., help="Course ID to retrieve."),
) -> None:
    """Show course details and per-km segments."""
    init_db()
    course = asyncio.run(get_course(course_id))
    if course is None:
        typer.echo(json.dumps({"error": f"Course {course_id} not found."}, indent=2))
        raise typer.Exit(1)

    typer.echo(json.dumps({
        "_meta": make_meta(),
        "course": course.to_summary_dict(),
        "km_segments": course.get_km_segments(),
    }, indent=2, default=str))


# ---------------------------------------------------------------------------
# simulate
# ---------------------------------------------------------------------------

@app.command("simulate")
def simulate(
    course_id: int = typer.Argument(..., help="Course ID to simulate."),
    target_time: Optional[str] = typer.Option(None, "--target-time", help="Target finish time HH:MM:SS or MM:SS."),
    target_pace: Optional[str] = typer.Option(None, "--target-pace", help="Target pace MM:SS per km."),
    strategy: str = typer.Option("even", "--strategy", help="Pacing strategy: even | negative | positive."),
    pacer_pace: Optional[str] = typer.Option(None, "--pacer-pace", help="Pacer pace MM:SS per km."),
    drop_at_km: Optional[float] = typer.Option(None, "--drop-at-km", help="Km marker to break from pacer."),
    temp: Optional[float] = typer.Option(None, "--temp", help="Temperature °C (manual override)."),
    humidity: Optional[float] = typer.Option(None, "--humidity", help="Relative humidity % (manual override)."),
    wind: Optional[float] = typer.Option(None, "--wind", help="Wind speed m/s."),
    wind_dir: Optional[float] = typer.Option(None, "--wind-dir", help="Wind direction degrees (0=N)."),
    race_date: Optional[str] = typer.Option(None, "--date", help="Race date YYYY-MM-DD for weather fetch."),
    race_hour: int = typer.Option(9, "--hour", help="Race start hour local time (0-23)."),
) -> None:
    """Simulate race splits for a course with optional weather and strategy."""
    init_db()

    # 1. Resolve target total seconds
    if target_time is None and target_pace is None:
        typer.echo(json.dumps({"error": "Provide --target-time or --target-pace."}, indent=2))
        raise typer.Exit(1)

    course = asyncio.run(get_course(course_id))
    if course is None:
        typer.echo(json.dumps({"error": f"Course {course_id} not found."}, indent=2))
        raise typer.Exit(1)

    segs = course.get_km_segments()
    if not segs:
        typer.echo(json.dumps({"error": "Course has no segments. Re-import."}, indent=2))
        raise typer.Exit(1)

    total_dist_km = sum(s["distance_m"] for s in segs) / 1000.0

    if target_time is not None:
        target_total_s = _parse_time(target_time)
    else:
        # target_pace is per km; multiply by total km
        pace_s = _parse_time(target_pace)  # type: ignore[arg-type]
        target_total_s = pace_s * total_dist_km

    # 2. Resolve weather
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

    elif race_date is not None and course.start_lat is not None and course.start_lon is not None:
        from fitops.weather.client import fetch_forecast_weather, fetch_activity_weather

        try:
            parsed_date = datetime.date.fromisoformat(race_date)
        except ValueError:
            typer.echo(json.dumps({"error": f"Invalid date format: {race_date!r}. Use YYYY-MM-DD."}, indent=2))
            raise typer.Exit(1)

        today = datetime.date.today()

        if parsed_date > today:
            # Future: use forecast API
            fetched = fetch_forecast_weather(
                course.start_lat, course.start_lon, race_date, race_hour
            )
            if fetched is None:
                typer.echo(
                    json.dumps({"warning": "Forecast unavailable (beyond 16-day window). Using neutral conditions."}, indent=2),
                    err=True,
                )
                weather_source = "neutral"
            else:
                weather = {
                    "temperature_c": fetched.get("temperature_c", 15.0),
                    "humidity_pct": fetched.get("humidity_pct", 40.0),
                    "wind_speed_ms": fetched.get("wind_speed_ms", 0.0),
                    "wind_direction_deg": fetched.get("wind_direction_deg", 0.0),
                }
                weather_source = "forecast"
        else:
            # Past/today: use archive API
            race_datetime = datetime.datetime(
                parsed_date.year, parsed_date.month, parsed_date.day,
                race_hour, 0, 0, tzinfo=datetime.timezone.utc
            )
            fetched = asyncio.run(fetch_activity_weather(course.start_lat, course.start_lon, race_datetime))
            if fetched is None:
                typer.echo(
                    json.dumps({"warning": "Historical weather unavailable, using neutral conditions."}, indent=2),
                    err=True,
                )
                weather_source = "neutral"
            else:
                weather = {
                    "temperature_c": fetched.get("temperature_c", 15.0),
                    "humidity_pct": fetched.get("humidity_pct", 40.0),
                    "wind_speed_ms": fetched.get("wind_speed_ms", 0.0),
                    "wind_direction_deg": fetched.get("wind_direction_deg", 0.0),
                }
                weather_source = "archive"

    # 3. Simulate
    if pacer_pace is not None and drop_at_km is not None:
        pacer_pace_s = _parse_time(pacer_pace)
        try:
            sim_result = simulate_pacer_mode(
                segments=segs,
                target_total_s=target_total_s,
                pacer_pace_s=pacer_pace_s,
                drop_at_km=drop_at_km,
                weather=weather,
            )
        except ValueError as e:
            typer.echo(json.dumps({"error": str(e)}, indent=2))
            raise typer.Exit(1)

        typer.echo(json.dumps({
            "_meta": make_meta(),
            "course": course.to_summary_dict(),
            "simulation": {
                "mode": "pacer",
                "target_time": sim_result["projected_finish"],
                "weather": weather,
                "weather_source": weather_source,
                **sim_result,
            },
        }, indent=2, default=str))

    else:
        splits = simulate_splits(
            segments=segs,
            target_total_s=target_total_s,
            weather=weather,
            strategy=strategy,
        )

        from fitops.race.course_parser import _fmt_duration
        typer.echo(json.dumps({
            "_meta": make_meta(),
            "course": course.to_summary_dict(),
            "simulation": {
                "mode": "splits",
                "strategy": strategy,
                "target_time": _fmt_duration(target_total_s),
                "weather": weather,
                "weather_source": weather_source,
                "splits": splits,
            },
        }, indent=2, default=str))


# ---------------------------------------------------------------------------
# splits (shorthand)
# ---------------------------------------------------------------------------

@app.command("splits")
def splits(
    course_id: int = typer.Argument(..., help="Course ID."),
    target_time: Optional[str] = typer.Option(None, "--target-time", help="Target finish time HH:MM:SS or MM:SS."),
    target_pace: Optional[str] = typer.Option(None, "--target-pace", help="Target pace MM:SS per km."),
) -> None:
    """Quick even-split plan for a course (no weather, no strategy options)."""
    init_db()

    if target_time is None and target_pace is None:
        typer.echo(json.dumps({"error": "Provide --target-time or --target-pace."}, indent=2))
        raise typer.Exit(1)

    course = asyncio.run(get_course(course_id))
    if course is None:
        typer.echo(json.dumps({"error": f"Course {course_id} not found."}, indent=2))
        raise typer.Exit(1)

    segs = course.get_km_segments()
    if not segs:
        typer.echo(json.dumps({"error": "Course has no segments. Re-import."}, indent=2))
        raise typer.Exit(1)

    total_dist_km = sum(s["distance_m"] for s in segs) / 1000.0

    if target_time is not None:
        target_total_s = _parse_time(target_time)
    else:
        pace_s = _parse_time(target_pace)  # type: ignore[arg-type]
        target_total_s = pace_s * total_dist_km

    result = simulate_splits(segs, target_total_s, _NEUTRAL_WEATHER, strategy="even")

    from fitops.race.course_parser import _fmt_duration
    typer.echo(json.dumps({
        "_meta": make_meta(),
        "course_id": course_id,
        "target_time": _fmt_duration(target_total_s),
        "splits": result,
    }, indent=2, default=str))


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@app.command("delete")
def delete(
    course_id: int = typer.Argument(..., help="Course ID to delete."),
) -> None:
    """Delete a race course from the database."""
    init_db()
    deleted = asyncio.run(_delete_course(course_id))
    if deleted:
        typer.echo(json.dumps({"deleted": True, "course_id": course_id}, indent=2))
    else:
        typer.echo(json.dumps({"deleted": False, "error": f"Course {course_id} not found."}, indent=2))
        raise typer.Exit(1)
