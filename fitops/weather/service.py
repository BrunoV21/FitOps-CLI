from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from fitops.analytics.weather_pace import pace_heat_factor, wbgt_approx
from fitops.db.models.activity import Activity
from fitops.db.models.activity_weather import ActivityWeather
from fitops.db.session import get_async_session
from fitops.weather.client import fetch_activity_weather, fetch_forecast_weather


@dataclass(frozen=True)
class ActivityWeatherResult:
    status: str
    weather: dict | None = None


async def upsert_activity_weather(
    activity_id: int,
    weather_dict: dict,
    source: str = "open-meteo",
    activity=None,
    streams: dict | None = None,
) -> dict:
    """Insert or update weather and persist all weather-derived activity values."""
    async with get_async_session() as session:
        result = await session.execute(
            select(ActivityWeather).where(ActivityWeather.activity_id == activity_id)
        )
        row = result.scalar_one_or_none()

        fields = {
            "temperature_c": weather_dict.get("temperature_c"),
            "humidity_pct": weather_dict.get("humidity_pct"),
            "apparent_temp_c": weather_dict.get("apparent_temp_c"),
            "dew_point_c": weather_dict.get("dew_point_c"),
            "wind_speed_ms": weather_dict.get("wind_speed_ms"),
            "wind_direction_deg": weather_dict.get("wind_direction_deg"),
            "wind_gusts_ms": weather_dict.get("wind_gusts_ms"),
            "precipitation_mm": weather_dict.get("precipitation_mm"),
            "weather_code": weather_dict.get("weather_code"),
            "wbgt_c": weather_dict.get("wbgt_c"),
            "pace_heat_factor": weather_dict.get("pace_heat_factor"),
            "source": source,
            "fetched_at": datetime.now(UTC),
        }

        if row:
            for key, value in fields.items():
                setattr(row, key, value)
        else:
            row = ActivityWeather(activity_id=activity_id, **fields)
            session.add(row)

        await session.flush()

        if activity is None:
            activity = await session.get(Activity, activity_id)

        if activity is not None:
            if streams is None and activity.streams_fetched:
                from fitops.db.models.activity_stream import ActivityStream

                stream_types = [
                    "velocity_smooth",
                    "grade_smooth",
                    "latlng",
                    "grade_adjusted_speed",
                ]
                stream_result = await session.execute(
                    select(ActivityStream).where(
                        ActivityStream.activity_id == activity.id,
                        ActivityStream.stream_type.in_(stream_types),
                    )
                )
                streams = {
                    stream.stream_type: stream.data
                    for stream in stream_result.scalars().all()
                }

            try:
                from fitops.analytics.weather_pace import persist_derived_weather

                await persist_derived_weather(session, row, activity, streams)
            except Exception:
                # Weather remains useful even when an optional derived metric cannot
                # be computed for a sparse recording.
                pass

        return row.to_dict()


async def fetch_and_store_activity_weather(
    activity_id: int, *, force: bool = False
) -> ActivityWeatherResult:
    """Fetch weather for a local activity and persist its derived calculations."""
    async with get_async_session() as session:
        activity = await session.get(Activity, activity_id)
        if activity is None:
            return ActivityWeatherResult("activity_not_found")
        existing = (
            await session.execute(
                select(ActivityWeather).where(
                    ActivityWeather.activity_id == activity_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None and not force:
            return ActivityWeatherResult("already_available", existing.to_dict())

    if not activity.start_latlng:
        return ActivityWeatherResult("skipped_no_gps")
    if activity.start_date is None:
        return ActivityWeatherResult("skipped_no_start_date")
    try:
        coords = json.loads(activity.start_latlng)
        if not isinstance(coords, list) or len(coords) != 2:
            return ActivityWeatherResult("skipped_no_gps")
        lat, lng = float(coords[0]), float(coords[1])
    except (json.JSONDecodeError, TypeError, ValueError):
        return ActivityWeatherResult("skipped_no_gps")

    weather = await fetch_activity_weather(lat, lng, activity.start_date)
    if weather is None:
        weather = await fetch_forecast_weather(
            lat,
            lng,
            activity.start_date.strftime("%Y-%m-%d"),
            activity.start_date.hour,
        )
    if weather is None:
        return ActivityWeatherResult("unavailable")

    temperature_c = weather.get("temperature_c")
    humidity_pct = weather.get("humidity_pct")
    if temperature_c is not None and humidity_pct is not None:
        weather["wbgt_c"] = round(wbgt_approx(temperature_c, humidity_pct), 2)
        weather["pace_heat_factor"] = round(
            pace_heat_factor(temperature_c, humidity_pct), 4
        )

    stored = await upsert_activity_weather(
        activity.id,
        weather,
        source="open-meteo",
        activity=activity,
    )
    return ActivityWeatherResult("fetched", stored)
