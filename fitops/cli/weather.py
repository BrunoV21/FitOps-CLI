from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

import typer
from sqlalchemy import select

from fitops.analytics.weather_pace import (
    compute_bearing,
    compute_wap_factor,
    deg_to_compass,
    vo2max_heat_factor,
    wbgt_approx,
    wbgt_flag,
    weather_condition_label,
    pace_heat_factor,
)
from fitops.dashboard.queries.weather import (
    get_activities_missing_weather,
    upsert_activity_weather,
)
from fitops.db.migrations import init_db
from fitops.db.models.activity import Activity
from fitops.db.session import get_async_session
from fitops.output.formatter import make_meta
from fitops.output.text_formatter import print_weather_forecast
from fitops.weather.client import fetch_activity_weather, fetch_forecast_weather

app = typer.Typer(no_args_is_help=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_latlng(latlng_json: Optional[str]) -> Optional[tuple[float, float]]:
    if not latlng_json:
        return None
    try:
        coords = json.loads(latlng_json)
        if isinstance(coords, list) and len(coords) == 2:
            return float(coords[0]), float(coords[1])
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _fmt_pace(s_per_km: float) -> str:
    mins = int(s_per_km) // 60
    secs = int(s_per_km) % 60
    return f"{mins}:{secs:02d}/km"


async def _fetch_and_store(activity_id: int) -> Optional[dict]:
    """Fetch weather for one activity by strava_id, store it, return result dict."""
    async with get_async_session() as session:
        result = await session.execute(
            select(Activity).where(Activity.strava_id == activity_id)
        )
        act = result.scalar_one_or_none()

    if act is None:
        return None

    latlng = _parse_latlng(act.start_latlng)
    if latlng is None:
        return {"error": "No GPS coordinates for this activity.", "activity_id": activity_id}

    lat, lng = latlng
    start_utc = act.start_date
    if start_utc is None:
        return {"error": "Activity has no start_date.", "activity_id": activity_id}

    weather = await fetch_activity_weather(lat, lng, start_utc)
    if weather is None:
        return {"error": "Failed to fetch weather from Open-Meteo.", "activity_id": activity_id}

    # Compute derived fields
    temp_c = weather.get("temperature_c")
    humidity = weather.get("humidity_pct")
    if temp_c is not None and humidity is not None:
        weather["wbgt_c"] = round(wbgt_approx(temp_c, humidity), 2)
        weather["pace_heat_factor"] = round(pace_heat_factor(temp_c, humidity), 4)

    stored = await upsert_activity_weather(activity_id, weather, source="open-meteo")
    return stored


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command("fetch")
def fetch_weather(
    activity_id: Optional[int] = typer.Argument(None, help="Strava activity ID to fetch weather for."),
    all_activities: bool = typer.Option(False, "--all", help="Backfill all GPS activities missing weather."),
    limit: int = typer.Option(50, "--limit", help="Max activities when using --all."),
) -> None:
    """Fetch weather from Open-Meteo and store it for one or all activities."""
    init_db()

    if all_activities:
        # Backfill mode
        missing = asyncio.run(get_activities_missing_weather(0, limit=limit))

        # We need athlete_id — get from first activity's athlete_id
        # Actually get_activities_missing_weather accepts athlete_id=0 which won't work.
        # Re-fetch with correct approach: get all activities missing weather regardless of athlete.
        async def _get_missing_any(lim: int) -> list[Activity]:
            from fitops.db.models.activity_weather import ActivityWeather
            from sqlalchemy import select
            async with get_async_session() as session:
                have = select(ActivityWeather.activity_id)
                q = (
                    select(Activity)
                    .where(Activity.start_latlng.isnot(None))
                    .where(Activity.strava_id.not_in(have))
                    .order_by(Activity.start_date.desc())
                    .limit(lim)
                )
                res = await session.execute(q)
                return list(res.scalars().all())

        missing = asyncio.run(_get_missing_any(limit))
        results = []
        for act in missing:
            typer.echo(f"  Fetching weather for activity {act.strava_id} ({act.name})...")
            result = asyncio.run(_fetch_and_store(act.strava_id))
            if result:
                results.append({"activity_id": act.strava_id, "name": act.name, "result": result})
            time.sleep(0.1)  # rate-limit respect

        typer.echo(
            json.dumps(
                {
                    "_meta": make_meta(total_count=len(results)),
                    "fetched": len(results),
                    "activities": results,
                },
                indent=2,
            )
        )
        return

    if activity_id is None:
        typer.echo(json.dumps({"error": "Provide an activity ID or use --all."}, indent=2))
        raise typer.Exit(1)

    result = asyncio.run(_fetch_and_store(activity_id))
    if result is None:
        typer.echo(
            json.dumps({"error": f"Activity {activity_id} not found in DB."}, indent=2)
        )
        raise typer.Exit(1)

    if "error" in result:
        typer.echo(json.dumps({"_meta": make_meta(), **result}, indent=2))
        raise typer.Exit(1)

    # Enrich output with labels
    wbgt = result.get("wbgt_c")
    wcode = result.get("weather_code")
    output = {
        "_meta": make_meta(),
        "weather": {
            **result,
            "condition": weather_condition_label(wcode) if wcode is not None else None,
            "wbgt_flag": wbgt_flag(wbgt) if wbgt is not None else None,
        },
    }
    typer.echo(json.dumps(output, indent=2))


@app.command("show")
def show_weather(
    activity_id: int = typer.Argument(..., help="Strava activity ID."),
) -> None:
    """Display stored weather and WAP factors for an activity."""
    init_db()

    async def _load() -> Optional[dict]:
        from fitops.db.models.activity_weather import ActivityWeather
        from fitops.db.session import get_async_session
        async with get_async_session() as session:
            # Load weather
            res = await session.execute(
                select(ActivityWeather).where(ActivityWeather.activity_id == activity_id)
            )
            weather = res.scalar_one_or_none()
            if weather is None:
                return None

            # Load activity for bearing
            act_res = await session.execute(
                select(Activity).where(Activity.strava_id == activity_id)
            )
            act = act_res.scalar_one_or_none()

        d = weather.to_dict()

        course_bearing: Optional[float] = None
        if act and act.start_latlng and act.end_latlng:
            s = _parse_latlng(act.start_latlng)
            e = _parse_latlng(act.end_latlng)
            if s and e:
                course_bearing = compute_bearing(s[0], s[1], e[0], e[1])

        wap_factor = 1.0
        if weather.temperature_c is not None and weather.humidity_pct is not None:
            wap_factor = compute_wap_factor(
                temp_c=weather.temperature_c,
                rh_pct=weather.humidity_pct,
                wind_speed_ms_val=weather.wind_speed_ms or 0.0,
                wind_dir_deg=weather.wind_direction_deg or 0.0,
                course_bearing=course_bearing,
            )

        actual_pace_s: Optional[float] = None
        wap_s: Optional[float] = None
        if act and act.average_speed_ms and act.average_speed_ms > 0:
            actual_pace_s = 1000.0 / act.average_speed_ms
            wap_s = actual_pace_s / wap_factor

        wbgt = d.get("wbgt_c")
        wcode = d.get("weather_code")
        temp_c = weather.temperature_c
        hum = weather.humidity_pct

        return {
            **d,
            "condition": weather_condition_label(wcode) if wcode is not None else None,
            "wbgt_flag": wbgt_flag(wbgt) if wbgt is not None else None,
            "wap_factor": round(wap_factor, 4),
            "course_bearing_deg": round(course_bearing, 1) if course_bearing is not None else None,
            "vo2max_heat_factor": round(vo2max_heat_factor(temp_c, hum), 4)
            if temp_c is not None and hum is not None
            else None,
            "actual_pace": _fmt_pace(actual_pace_s) if actual_pace_s else None,
            "wap": _fmt_pace(wap_s) if wap_s else None,
        }

    result = asyncio.run(_load())
    if result is None:
        typer.echo(
            json.dumps(
                {
                    "error": f"No weather data for activity {activity_id}.",
                    "hint": f"Run: fitops weather fetch {activity_id}",
                },
                indent=2,
            )
        )
        raise typer.Exit(1)

    typer.echo(json.dumps({"_meta": make_meta(), "weather": result}, indent=2))


@app.command("forecast")
def forecast_weather(
    lat: float = typer.Option(..., "--lat", help="Latitude of race location."),
    lng: float = typer.Option(..., "--lng", help="Longitude of race location."),
    date: str = typer.Option(..., "--date", help="Race date (YYYY-MM-DD)."),
    hour: int = typer.Option(9, "--hour", help="Race start hour in local time (0-23). Default: 9."),
    course_bearing: Optional[float] = typer.Option(
        None, "--course-bearing",
        help="Course bearing in degrees (0=N, 90=E) for headwind/tailwind calc.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Fetch race-day weather forecast and compute pace adjustment factors."""
    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        typer.echo(json.dumps({"error": "Date must be YYYY-MM-DD format."}, indent=2))
        raise typer.Exit(1)
    if not (0 <= hour <= 23):
        typer.echo(json.dumps({"error": "Hour must be 0-23."}, indent=2))
        raise typer.Exit(1)

    weather = asyncio.run(fetch_forecast_weather(lat, lng, date, hour))
    if weather is None:
        typer.echo(
            json.dumps(
                {"error": "Failed to fetch forecast from Open-Meteo. Date may be beyond 16-day window."},
                indent=2,
            )
        )
        raise typer.Exit(1)

    temp_c = weather.get("temperature_c")
    humidity = weather.get("humidity_pct")
    wind_speed = weather.get("wind_speed_ms") or 0.0
    wind_dir = weather.get("wind_direction_deg") or 0.0
    wcode = weather.get("weather_code")

    wbgt: Optional[float] = None
    if temp_c is not None and humidity is not None:
        wbgt = round(wbgt_approx(temp_c, humidity), 2)

    wap_factor: Optional[float] = None
    headwind: Optional[float] = None
    if temp_c is not None and humidity is not None:
        from fitops.analytics.weather_pace import headwind_ms
        if course_bearing is not None:
            headwind = round(headwind_ms(wind_speed, wind_dir, course_bearing), 2)
        wap_factor = round(
            compute_wap_factor(temp_c, humidity, wind_speed, wind_dir, course_bearing), 4
        )

    forecast_dict = {
        "date": date,
        "hour_local": hour,
        "timezone": weather.pop("_timezone", None),
        "lat": lat,
        "lng": lng,
        **weather,
        "condition": weather_condition_label(wcode) if wcode is not None else None,
        "wbgt_c": wbgt,
        "wbgt_flag": wbgt_flag(wbgt) if wbgt is not None else None,
        "pace_heat_factor": round(pace_heat_factor(temp_c, humidity), 4)
        if temp_c is not None and humidity is not None
        else None,
        "vo2max_heat_factor": round(vo2max_heat_factor(temp_c, humidity), 4)
        if temp_c is not None and humidity is not None
        else None,
        "headwind_ms": headwind,
        "wind_direction_compass": deg_to_compass(wind_dir) if wind_dir else None,
        "wap_factor": wap_factor,
        "course_bearing_deg": course_bearing,
    }

    if json_output:
        typer.echo(json.dumps({"_meta": make_meta(), "forecast": forecast_dict}, indent=2))
    else:
        print_weather_forecast(forecast_dict)


@app.command("set")
def set_weather(
    activity_id: int = typer.Argument(..., help="Strava activity ID."),
    temp: Optional[float] = typer.Option(None, "--temp", help="Temperature (°C)."),
    humidity: Optional[float] = typer.Option(None, "--humidity", help="Relative humidity (%)."),
    wind: Optional[float] = typer.Option(None, "--wind", help="Wind speed (m/s)."),
    wind_dir: Optional[float] = typer.Option(None, "--wind-dir", help="Wind direction (degrees, 0=N)."),
) -> None:
    """Manually set weather for an activity (source='manual')."""
    init_db()

    weather: dict = {}
    if temp is not None:
        weather["temperature_c"] = temp
    if humidity is not None:
        weather["humidity_pct"] = humidity
    if wind is not None:
        weather["wind_speed_ms"] = wind
    if wind_dir is not None:
        weather["wind_direction_deg"] = wind_dir

    if temp is not None and humidity is not None:
        weather["wbgt_c"] = round(wbgt_approx(temp, humidity), 2)
        weather["pace_heat_factor"] = round(pace_heat_factor(temp, humidity), 4)

    if not weather:
        typer.echo(json.dumps({"error": "Provide at least one weather field."}, indent=2))
        raise typer.Exit(1)

    result = asyncio.run(upsert_activity_weather(activity_id, weather, source="manual"))
    typer.echo(json.dumps({"_meta": make_meta(), "weather": result}, indent=2))
