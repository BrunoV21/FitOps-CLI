from __future__ import annotations

import asyncio
import datetime
import json

import typer

from fitops.dashboard.queries.race import (
    delete_course as _delete_course,
)
from fitops.dashboard.queries.race import (
    delete_race_plan as _delete_race_plan,
)
from fitops.dashboard.queries.race import (
    get_all_courses,
    get_all_race_plans,
    get_course,
    get_race_plan,
    save_course,
    save_race_plan,
)
from fitops.db.migrations import init_db
from fitops.db.session import get_async_session
from fitops.output.formatter import make_meta
from fitops.output.text_formatter import (
    print_course_detail,
    print_courses_list,
    print_race_plan_compare,
    print_race_plan_detail,
    print_race_plans_list,
    print_race_session_detail,
    print_race_session_events,
    print_race_session_gaps,
    print_race_session_segments,
    print_race_sessions_list,
    print_race_simulate,
)
from fitops.analytics.race_analysis import (
    compute_athlete_metrics,
    compute_delta_series,
    compute_gap_series,
    compute_segment_athlete_metrics,
    detect_events,
    detect_segments_from_altitude,
    detect_segments_from_km_segments,
    fetch_strava_comparison_streams,
    load_primary_streams,
    normalize_stream,
    normalized_stream_to_dict,
    parse_gpx_streams,
)
from fitops.dashboard.queries.race_session import (
    add_session_athlete,
    create_race_session,
    delete_race_session,
    get_all_race_sessions,
    get_events,
    get_gap_series,
    get_segments,
    get_session_athletes,
    get_session_detail,
    save_events,
    save_gap_series,
    save_segments,
)
from fitops.race.course_parser import (
    _parse_time,
    build_km_segments,
    compute_total_elevation_gain,
    detect_source,
    parse_gpx,
    parse_mapmyrun_url,
    parse_strava_activity,
    parse_tcx,
)
from fitops.race.simulation import simulate_pacer_mode, simulate_splits

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
    source: str = typer.Argument(
        ..., help="GPX/TCX file path, MapMyRun URL, or Strava activity ID."
    ),
    name: str = typer.Option(..., "--name", help="Course name (required)."),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
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
    elif source_type == "strava_url":
        from fitops.race.course_parser import parse_strava_url

        points = asyncio.run(parse_strava_url(source_value))
    elif source_type == "strava":

        async def _from_strava() -> list[dict]:
            async with get_async_session() as session:
                return await parse_strava_activity(int(source_value), session)

        points = asyncio.run(_from_strava())
    else:
        typer.echo(
            json.dumps({"error": f"Unknown source type: {source_type}"}, indent=2)
        )
        raise typer.Exit(1)

    if not points:
        typer.echo(json.dumps({"error": "No course points found in source."}, indent=2))
        raise typer.Exit(1)

    segments = build_km_segments(points)
    total_dist = points[-1]["distance_from_start_m"]
    elev_gain = compute_total_elevation_gain(points)
    file_format = source_type if source_type in ("gpx", "tcx") else None
    source_ref = (
        source_value if source_type in ("mapmyrun", "strava", "strava_url") else None
    )

    result = asyncio.run(
        save_course(
            name=name,
            source=source_type,
            source_ref=source_ref,
            file_format=file_format,
            course_points=points,
            km_segments=segments,
            total_distance_m=total_dist,
            total_elevation_gain_m=elev_gain,
        )
    )
    out = {"_meta": make_meta(), "course": result}
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        dist_m = result.get("total_distance_m") or 0
        elev = result.get("total_elevation_gain_m") or 0
        typer.echo(
            f"Imported: {result.get('name')}  ({dist_m / 1000:.2f} km  +{elev:.0f} m)  ID {result.get('id')}"
        )


# ---------------------------------------------------------------------------
# courses
# ---------------------------------------------------------------------------


@app.command("courses")
def courses(
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """List all imported race courses."""
    init_db()
    result = asyncio.run(get_all_courses())
    out = {
        "_meta": make_meta(total_count=len(result)),
        "courses": result,
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_courses_list(out)


# ---------------------------------------------------------------------------
# course
# ---------------------------------------------------------------------------


@app.command("course")
def course_detail(
    course_id: int = typer.Argument(..., help="Course ID to retrieve."),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Show course details and per-km segments."""
    init_db()
    course = asyncio.run(get_course(course_id))
    if course is None:
        typer.echo(f"Course {course_id} not found.", err=True)
        raise typer.Exit(1)

    out = {
        "_meta": make_meta(),
        "course": course.to_summary_dict(),
        "km_segments": course.get_km_segments(),
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_course_detail(out)


# ---------------------------------------------------------------------------
# simulate
# ---------------------------------------------------------------------------


@app.command("simulate")
def simulate(
    course_id: int = typer.Argument(..., help="Course ID to simulate."),
    target_time: str | None = typer.Option(
        None, "--target-time", help="Target finish time HH:MM:SS or MM:SS."
    ),
    target_pace: str | None = typer.Option(
        None, "--target-pace", help="Target pace MM:SS per km."
    ),
    strategy: str = typer.Option(
        "even", "--strategy", help="Pacing strategy: even | negative | positive."
    ),
    pacer_pace: str | None = typer.Option(
        None, "--pacer-pace", help="Pacer pace MM:SS per km."
    ),
    drop_at_km: float | None = typer.Option(
        None, "--drop-at-km", help="Km marker to break from pacer."
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
    race_date: str | None = typer.Option(
        None, "--date", help="Race date YYYY-MM-DD for weather fetch."
    ),
    race_hour: int = typer.Option(
        9, "--hour", help="Race start hour local time (0-23)."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Simulate race splits for a course with optional weather and strategy."""
    init_db()

    # 1. Resolve target total seconds
    if target_time is None and target_pace is None:
        typer.echo(
            json.dumps({"error": "Provide --target-time or --target-pace."}, indent=2)
        )
        raise typer.Exit(1)

    course = asyncio.run(get_course(course_id))
    if course is None:
        typer.echo(json.dumps({"error": f"Course {course_id} not found."}, indent=2))
        raise typer.Exit(1)

    segs = course.get_km_segments()
    if not segs:
        typer.echo(
            json.dumps({"error": "Course has no segments. Re-import."}, indent=2)
        )
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

    elif (
        race_date is not None
        and course.start_lat is not None
        and course.start_lon is not None
    ):
        from fitops.weather.client import fetch_activity_weather, fetch_forecast_weather

        try:
            parsed_date = datetime.date.fromisoformat(race_date)
        except ValueError:
            typer.echo(
                json.dumps(
                    {"error": f"Invalid date format: {race_date!r}. Use YYYY-MM-DD."},
                    indent=2,
                )
            )
            raise typer.Exit(1)

        today = datetime.date.today()

        if parsed_date > today:
            # Future: use forecast API
            fetched = asyncio.run(
                fetch_forecast_weather(
                    course.start_lat, course.start_lon, race_date, race_hour
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
                parsed_date.year,
                parsed_date.month,
                parsed_date.day,
                race_hour,
                0,
                0,
                tzinfo=datetime.UTC,
            )
            fetched = asyncio.run(
                fetch_activity_weather(
                    course.start_lat, course.start_lon, race_datetime
                )
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

        out = {
            "_meta": make_meta(),
            "course": course.to_summary_dict(),
            "simulation": {
                "mode": "pacer",
                "target_time": sim_result["projected_finish"],
                "weather": weather,
                "weather_source": weather_source,
                **sim_result,
            },
        }
        if json_output:
            typer.echo(json.dumps(out, indent=2, default=str))
        else:
            print_race_simulate(out)

    else:
        splits = simulate_splits(
            segments=segs,
            target_total_s=target_total_s,
            weather=weather,
            strategy=strategy,
        )

        from fitops.race.course_parser import _fmt_duration

        out = {
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
        }
        if json_output:
            typer.echo(json.dumps(out, indent=2, default=str))
        else:
            print_race_simulate(out)


# ---------------------------------------------------------------------------
# splits (shorthand)
# ---------------------------------------------------------------------------


@app.command("splits")
def splits(
    course_id: int = typer.Argument(..., help="Course ID."),
    target_time: str | None = typer.Option(
        None, "--target-time", help="Target finish time HH:MM:SS or MM:SS."
    ),
    target_pace: str | None = typer.Option(
        None, "--target-pace", help="Target pace MM:SS per km."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Quick even-split plan for a course (no weather, no strategy options)."""
    init_db()

    if target_time is None and target_pace is None:
        typer.echo(
            json.dumps({"error": "Provide --target-time or --target-pace."}, indent=2)
        )
        raise typer.Exit(1)

    course = asyncio.run(get_course(course_id))
    if course is None:
        typer.echo(json.dumps({"error": f"Course {course_id} not found."}, indent=2))
        raise typer.Exit(1)

    segs = course.get_km_segments()
    if not segs:
        typer.echo(
            json.dumps({"error": "Course has no segments. Re-import."}, indent=2)
        )
        raise typer.Exit(1)

    total_dist_km = sum(s["distance_m"] for s in segs) / 1000.0

    if target_time is not None:
        target_total_s = _parse_time(target_time)
    else:
        pace_s = _parse_time(target_pace)  # type: ignore[arg-type]
        target_total_s = pace_s * total_dist_km

    result = simulate_splits(segs, target_total_s, _NEUTRAL_WEATHER, strategy="even")

    from fitops.race.course_parser import _fmt_duration

    out = {
        "_meta": make_meta(),
        "course": course.to_summary_dict(),
        "simulation": {
            "mode": "splits",
            "strategy": "even",
            "target_time": _fmt_duration(target_total_s),
            "weather": _NEUTRAL_WEATHER,
            "weather_source": "neutral",
            "splits": result,
        },
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_race_simulate(out)


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
        typer.echo(f"Deleted course {course_id}.")
    else:
        typer.echo(f"Course {course_id} not found.", err=True)
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# plan-save
# ---------------------------------------------------------------------------


@app.command("plan-save")
def plan_save(
    course_id: int = typer.Argument(..., help="Course ID to save a plan for."),
    name: str = typer.Option(..., "--name", help="Plan name."),
    target_time: str | None = typer.Option(
        None, "--target-time", help="Target finish time HH:MM:SS or MM:SS."
    ),
    target_pace: str | None = typer.Option(
        None, "--target-pace", help="Target pace MM:SS per km."
    ),
    strategy: str = typer.Option(
        "even", "--strategy", help="Pacing strategy: even | negative | positive."
    ),
    pacer_pace: str | None = typer.Option(
        None, "--pacer-pace", help="Pacer pace MM:SS per km."
    ),
    drop_at_km: float | None = typer.Option(
        None, "--drop-at-km", help="Km marker to break from pacer."
    ),
    race_date: str | None = typer.Option(None, "--date", help="Race date YYYY-MM-DD."),
    race_hour: int = typer.Option(
        9, "--hour", help="Race start hour local time (0-23)."
    ),
    temp: float | None = typer.Option(None, "--temp", help="Temperature °C."),
    humidity: float | None = typer.Option(
        None, "--humidity", help="Relative humidity %."
    ),
    wind: float | None = typer.Option(None, "--wind", help="Wind speed m/s."),
    wind_dir: float | None = typer.Option(
        None, "--wind-dir", help="Wind direction degrees (0=N)."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Save a race simulation as a named plan for future comparison."""
    init_db()

    if target_time is None and target_pace is None:
        typer.echo(
            json.dumps({"error": "Provide --target-time or --target-pace."}, indent=2)
        )
        raise typer.Exit(1)

    course = asyncio.run(get_course(course_id))
    if course is None:
        typer.echo(json.dumps({"error": f"Course {course_id} not found."}, indent=2))
        raise typer.Exit(1)

    segs = course.get_km_segments()
    if not segs:
        typer.echo(
            json.dumps({"error": "Course has no segments. Re-import."}, indent=2)
        )
        raise typer.Exit(1)

    total_dist_km = sum(s["distance_m"] for s in segs) / 1000.0

    if target_time is not None:
        target_total_s = _parse_time(target_time)
    else:
        pace_s = _parse_time(target_pace)  # type: ignore[arg-type]
        target_total_s = pace_s * total_dist_km

    # Resolve weather
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
        race_date is not None
        and course.start_lat is not None
        and course.start_lon is not None
    ):
        from fitops.weather.client import fetch_activity_weather, fetch_forecast_weather

        try:
            parsed_date = datetime.date.fromisoformat(race_date)
        except ValueError:
            typer.echo(
                json.dumps(
                    {"error": f"Invalid date format: {race_date!r}. Use YYYY-MM-DD."},
                    indent=2,
                )
            )
            raise typer.Exit(1)

        today = datetime.date.today()
        if parsed_date > today:
            fetched = asyncio.run(
                fetch_forecast_weather(
                    course.start_lat, course.start_lon, race_date, race_hour
                )
            )
            if fetched:
                weather = {
                    "temperature_c": fetched.get("temperature_c", 15.0),
                    "humidity_pct": fetched.get("humidity_pct", 40.0),
                    "wind_speed_ms": fetched.get("wind_speed_ms", 0.0),
                    "wind_direction_deg": fetched.get("wind_direction_deg", 0.0),
                }
                weather_source = "forecast"
        else:
            race_datetime = datetime.datetime(
                parsed_date.year,
                parsed_date.month,
                parsed_date.day,
                race_hour,
                0,
                0,
                tzinfo=datetime.UTC,
            )
            fetched = asyncio.run(
                fetch_activity_weather(
                    course.start_lat, course.start_lon, race_datetime
                )
            )
            if fetched:
                weather = {
                    "temperature_c": fetched.get("temperature_c", 15.0),
                    "humidity_pct": fetched.get("humidity_pct", 40.0),
                    "wind_speed_ms": fetched.get("wind_speed_ms", 0.0),
                    "wind_direction_deg": fetched.get("wind_direction_deg", 0.0),
                }
                weather_source = "archive"

    # Run simulation
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
        splits = sim_result.get("splits", [])
        target_time_display = sim_result.get("projected_finish")
    else:
        splits = simulate_splits(
            segments=segs,
            target_total_s=target_total_s,
            weather=weather,
            strategy=strategy,
        )
        from fitops.race.course_parser import _fmt_duration

        target_time_display = _fmt_duration(target_total_s)

    plan_dict = asyncio.run(
        save_race_plan(
            course_id=course_id,
            name=name,
            race_date=race_date,
            race_hour=race_hour,
            target_time=target_time_display,
            target_time_s=target_total_s,
            strategy=strategy,
            pacer_pace=pacer_pace,
            drop_at_km=drop_at_km,
            weather={
                "temperature_c": weather.get("temperature_c"),
                "humidity_pct": weather.get("humidity_pct"),
                "wind_speed_ms": weather.get("wind_speed_ms"),
                "wind_direction_deg": weather.get("wind_direction_deg"),
            },
            weather_source=weather_source,
            splits=splits,
        )
    )

    out = {"_meta": make_meta(), "plan": plan_dict}
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        typer.echo(
            f"Saved plan: {plan_dict.get('name')}  ID {plan_dict.get('id')}  target {plan_dict.get('target_time') or '—'}"
        )


# ---------------------------------------------------------------------------
# plans
# ---------------------------------------------------------------------------


@app.command("plans")
def plans_list(
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """List all saved race plans."""
    init_db()
    result = asyncio.run(get_all_race_plans())
    out = {"_meta": make_meta(total_count=len(result)), "plans": result}
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_race_plans_list(out)


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


@app.command("plan")
def plan_detail(
    plan_id: int = typer.Argument(..., help="Plan ID to retrieve."),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Show a saved race plan with simulated splits."""
    init_db()
    plan = asyncio.run(get_race_plan(plan_id))
    if plan is None:
        typer.echo(f"Plan {plan_id} not found.", err=True)
        raise typer.Exit(1)

    out = {"_meta": make_meta(), "plan": plan.to_detail_dict()}
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_race_plan_detail(out)


# ---------------------------------------------------------------------------
# plan-compare
# ---------------------------------------------------------------------------


@app.command("plan-compare")
def plan_compare(
    plan_id: int = typer.Argument(..., help="Plan ID to compare."),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Compare simulated splits vs actual activity splits for a linked plan."""
    init_db()
    plan = asyncio.run(get_race_plan(plan_id))
    if plan is None:
        typer.echo(f"Plan {plan_id} not found.", err=True)
        raise typer.Exit(1)

    if plan.activity_id is None:
        typer.echo(f"Plan {plan_id} has no linked activity yet.", err=True)
        raise typer.Exit(1)

    from sqlalchemy import select as _select

    from fitops.analytics.activity_splits import compute_km_splits
    from fitops.db.models.activity import Activity as _Activity
    from fitops.db.models.activity_stream import ActivityStream
    from fitops.race.course_parser import _fmt_duration

    async def _load_actual() -> tuple[list[dict], str | None, str | None]:
        async with get_async_session() as session:
            act_res = await session.execute(
                _select(_Activity).where(_Activity.id == plan.activity_id)
            )
            act = act_res.scalar_one_or_none()
            streams_res = await session.execute(
                _select(ActivityStream).where(
                    ActivityStream.activity_id == plan.activity_id
                )
            )
            all_streams = {
                row.stream_type: row.data for row in streams_res.scalars().all()
            }
        if not act or not all_streams:
            return [], None, None
        km_splits = compute_km_splits(all_streams, act.sport_type or "Run")
        if not km_splits:
            return [], None, None
        act_total_s = sum(
            s.get("pace_s", 0) * (s.get("distance_m", 1000) / 1000.0) for s in km_splits
        )
        act_total_dist = sum(s.get("distance_m", 0) for s in km_splits) / 1000.0
        act_avg_pace_s = (act_total_s / act_total_dist) if act_total_dist > 0 else 0.0
        avg_fmt = _fmt_duration(act_avg_pace_s) if act_avg_pace_s > 0 else None
        finish_fmt = _fmt_duration(act_total_s)
        return km_splits, avg_fmt, finish_fmt

    actual_splits, actual_avg_pace_fmt, actual_finish_fmt = asyncio.run(_load_actual())

    if not actual_splits:
        typer.echo(
            f"No activity streams found for activity #{plan.activity_id}. "
            "Run: fitops sync streams",
            err=True,
        )
        raise typer.Exit(1)

    plan_dict = plan.to_detail_dict()
    out = {
        "_meta": make_meta(),
        "plan": plan_dict,
        "actual_splits": actual_splits,
        "actual_avg_pace_fmt": actual_avg_pace_fmt,
        "actual_finish_fmt": actual_finish_fmt,
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_race_plan_compare(out)


# ---------------------------------------------------------------------------
# plan-delete
# ---------------------------------------------------------------------------


@app.command("plan-delete")
def plan_delete(
    plan_id: int = typer.Argument(..., help="Plan ID to delete."),
) -> None:
    """Delete a saved race plan."""
    init_db()
    deleted = asyncio.run(_delete_race_plan(plan_id))
    if deleted:
        typer.echo(f"Deleted plan {plan_id}.")
    else:
        typer.echo(f"Plan {plan_id} not found.", err=True)
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# session-create
# ---------------------------------------------------------------------------


@app.command("session-create")
def session_create(
    activity: int = typer.Option(..., "--activity", "-a", help="Primary Strava activity ID."),
    name: str = typer.Option(..., "--name", "-n", help="Session name."),
    course: int = typer.Option(None, "--course", "-c", help="Optional course ID to link."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Create a race session from a primary activity and run the full analysis pipeline."""
    init_db()

    async def _run() -> dict:
        # 1. Load primary athlete streams
        raw = await load_primary_streams(activity)
        if raw is None:
            return {"error": f"No streams found for activity {activity}. Run: fitops sync streams"}

        # 2. Normalise primary athlete stream
        primary_ns = normalize_stream(raw, athlete_label="You", is_primary=True, activity_id=activity)
        primary_metrics = compute_athlete_metrics(primary_ns)
        primary_stream_dict = normalized_stream_to_dict(primary_ns)

        # 3. Create session in DB
        session_dict = await create_race_session(
            name=name,
            primary_activity_id=activity,
            course_id=course,
        )
        session_id = session_dict["id"]

        # 4. Persist primary athlete
        await add_session_athlete(
            session_id=session_id,
            athlete_label="You",
            is_primary=True,
            activity_id=activity,
            stream_dict=primary_stream_dict,
            metrics_dict=primary_metrics,
        )

        # 5. Compute gap series (single athlete baseline)
        gap_series = compute_gap_series([primary_ns])
        delta_series = compute_delta_series(gap_series)
        await save_gap_series(session_id, gap_series, delta_series)

        # 6. Detect segments
        if course:
            from fitops.dashboard.queries.race import get_course as _get_course
            course_obj = await _get_course(course)
            if course_obj and course_obj.km_segments:
                import json as _json
                km_segs = _json.loads(course_obj.km_segments) if isinstance(course_obj.km_segments, str) else course_obj.km_segments
                segments = detect_segments_from_km_segments(km_segs)
            else:
                segments = detect_segments_from_altitude([primary_ns])
        else:
            segments = detect_segments_from_altitude([primary_ns])

        athlete_metrics = compute_segment_athlete_metrics([primary_ns], segments)
        await save_segments(session_id, segments, athlete_metrics)

        # 7. Detect events
        events = detect_events([primary_ns], gap_series)
        await save_events(session_id, events)

        return await get_session_detail(session_id) or {}

    result = asyncio.run(_run())
    if "error" in result:
        typer.echo(json.dumps({"error": result["error"]}, indent=2), err=True)
        raise typer.Exit(1)

    out = {"_meta": make_meta(), **result}
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_race_session_detail(out)


# ---------------------------------------------------------------------------
# session-add-athlete
# ---------------------------------------------------------------------------


@app.command("session-add-athlete")
def session_add_athlete(
    session_id: int = typer.Argument(..., help="Session ID."),
    label: str = typer.Option(..., "--label", "-l", help="Athlete display label."),
    activity: int = typer.Option(None, "--activity", "-a", help="Strava activity ID (public)."),
    gpx: str = typer.Option(None, "--gpx", "-g", help="Path to GPX file."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Add a comparison athlete to an existing race session."""
    init_db()
    if not activity and not gpx:
        typer.echo("Provide --activity or --gpx.", err=True)
        raise typer.Exit(1)

    async def _run() -> dict:
        # 1. Fetch raw streams
        if activity:
            raw = await fetch_strava_comparison_streams(activity)
            if raw is None:
                return {"error": f"Could not fetch streams for Strava activity {activity}."}
            act_id = activity
        else:
            import pathlib
            gpx_path = pathlib.Path(gpx)
            if not gpx_path.exists():
                return {"error": f"GPX file not found: {gpx}"}
            raw = parse_gpx_streams(gpx_path.read_text())
            act_id = None

        # 2. Normalise
        ns = normalize_stream(raw, athlete_label=label, is_primary=False, activity_id=act_id)
        metrics = compute_athlete_metrics(ns)
        stream_dict = normalized_stream_to_dict(ns)

        # 3. Persist
        await add_session_athlete(
            session_id=session_id,
            athlete_label=label,
            is_primary=False,
            activity_id=act_id,
            stream_dict=stream_dict,
            metrics_dict=metrics,
        )

        # 4. Recompute gap/delta/events with all athletes
        all_athletes_db = await get_session_athletes(session_id)
        from fitops.analytics.race_analysis import normalized_stream_from_dict
        all_ns = [normalized_stream_from_dict(a.get_stream()) for a in all_athletes_db]

        gap_series = compute_gap_series(all_ns)
        delta_series = compute_delta_series(gap_series)
        await save_gap_series(session_id, gap_series, delta_series)

        # Re-detect segments using primary
        primary_ns = next((a for a in all_ns if a.is_primary), all_ns[0])
        segs_raw = await _get_segments_for_recompute(session_id)
        if not segs_raw:
            segs = detect_segments_from_altitude([primary_ns])
        else:
            from fitops.analytics.race_analysis import DetectedSegment
            segs = [
                DetectedSegment(
                    label=s["segment_label"],
                    start_km=s["start_km"],
                    end_km=s["end_km"],
                    gradient_type=s["gradient_type"],
                    avg_grade_pct=s.get("avg_grade_pct") or 0.0,
                )
                for s in segs_raw
            ]

        athlete_metrics = compute_segment_athlete_metrics(all_ns, segs)
        await save_segments(session_id, segs, athlete_metrics)

        events = detect_events(all_ns, gap_series)
        await save_events(session_id, events)

        return await get_session_detail(session_id) or {}

    async def _get_segments_for_recompute(sid: int):
        return await get_segments(sid)

    result = asyncio.run(_run())
    if "error" in result:
        typer.echo(json.dumps({"error": result["error"]}, indent=2), err=True)
        raise typer.Exit(1)

    out = {"_meta": make_meta(), **result}
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_race_session_detail(out)


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------


@app.command("sessions")
def sessions_list(
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """List all race sessions."""
    init_db()
    sessions = asyncio.run(get_all_race_sessions())
    out = {"_meta": make_meta(), "sessions": sessions, "total_count": len(sessions)}
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_race_sessions_list(out)


# ---------------------------------------------------------------------------
# session (detail)
# ---------------------------------------------------------------------------


@app.command("session")
def session_detail(
    session_id: int = typer.Argument(..., help="Session ID."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Show full detail for a race session."""
    init_db()
    detail = asyncio.run(get_session_detail(session_id))
    if detail is None:
        typer.echo(json.dumps({"error": f"Session {session_id} not found."}), err=True)
        raise typer.Exit(1)

    out = {"_meta": make_meta(), **detail}
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_race_session_detail(out)


# ---------------------------------------------------------------------------
# session-gaps
# ---------------------------------------------------------------------------


@app.command("session-gaps")
def session_gaps(
    session_id: int = typer.Argument(..., help="Session ID."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Show gap series for a race session."""
    init_db()
    gaps = asyncio.run(get_gap_series(session_id))
    out = {"_meta": make_meta(), "session_id": session_id, "gap_data": gaps}
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_race_session_gaps(out)


# ---------------------------------------------------------------------------
# session-segments
# ---------------------------------------------------------------------------


@app.command("session-segments")
def session_segments(
    session_id: int = typer.Argument(..., help="Session ID."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Show segment breakdown for a race session."""
    init_db()
    segments = asyncio.run(get_segments(session_id))
    out = {"_meta": make_meta(), "session_id": session_id, "segments": segments}
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_race_session_segments(out)


# ---------------------------------------------------------------------------
# session-events
# ---------------------------------------------------------------------------


@app.command("session-events")
def session_events(
    session_id: int = typer.Argument(..., help="Session ID."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Show detected events for a race session."""
    init_db()
    events = asyncio.run(get_events(session_id))
    out = {"_meta": make_meta(), "session_id": session_id, "events": events}
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_race_session_events(out)


# ---------------------------------------------------------------------------
# session-delete
# ---------------------------------------------------------------------------


@app.command("session-delete")
def session_delete(
    session_id: int = typer.Argument(..., help="Session ID to delete."),
) -> None:
    """Delete a race session and all associated data."""
    init_db()
    deleted = asyncio.run(delete_race_session(session_id))
    if deleted:
        typer.echo(f"Deleted session {session_id}.")
    else:
        typer.echo(f"Session {session_id} not found.", err=True)
        raise typer.Exit(1)
