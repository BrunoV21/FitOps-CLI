from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fitops.analytics.weather_pace import compute_bearing, compute_wap_factor
from fitops.db.models.activity import Activity
from fitops.db.models.activity_weather import ActivityWeather
from fitops.db.session import get_async_session


async def get_weather_for_activities(strava_ids: list[int]) -> dict[int, ActivityWeather]:
    """Batch load weather rows for a list of strava_ids. Returns {strava_id: ActivityWeather}."""
    if not strava_ids:
        return {}
    async with get_async_session() as session:
        result = await session.execute(
            select(ActivityWeather).where(ActivityWeather.activity_id.in_(strava_ids))
        )
        return {w.activity_id: w for w in result.scalars().all()}


async def get_weather_for_activity(
    session: AsyncSession, activity_id: int
) -> Optional[ActivityWeather]:
    result = await session.execute(
        select(ActivityWeather).where(ActivityWeather.activity_id == activity_id)
    )
    return result.scalar_one_or_none()


async def get_wap_history(
    athlete_id: int,
    days: int = 180,
    sport: Optional[str] = None,
) -> list[dict]:
    """
    Return list of dicts with pace, WAP, and weather info for activities that have
    both weather data and average_speed_ms.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_async_session() as session:
        q = (
            select(Activity, ActivityWeather)
            .join(ActivityWeather, ActivityWeather.activity_id == Activity.strava_id)
            .where(Activity.athlete_id == athlete_id)
            .where(Activity.start_date >= cutoff)
            .where(Activity.average_speed_ms.isnot(None))
            .where(Activity.average_speed_ms > 0)
        )
        if sport:
            q = q.where(Activity.sport_type == sport)
        q = q.order_by(Activity.start_date.desc())

        result = await session.execute(q)
        rows = result.all()

    history = []
    for act, weather in rows:
        if not act.average_speed_ms:
            continue

        actual_pace_s = 1000.0 / act.average_speed_ms  # s/km

        # Compute course bearing from start→end latlng if available
        course_bearing: Optional[float] = None
        if act.start_latlng and act.end_latlng:
            try:
                s = json.loads(act.start_latlng)
                e = json.loads(act.end_latlng)
                if len(s) == 2 and len(e) == 2:
                    course_bearing = compute_bearing(s[0], s[1], e[0], e[1])
            except (json.JSONDecodeError, TypeError, IndexError):
                pass

        wap_factor = 1.0
        if weather.temperature_c is not None and weather.humidity_pct is not None:
            wap_factor = compute_wap_factor(
                temp_c=weather.temperature_c,
                rh_pct=weather.humidity_pct,
                wind_speed_ms_val=weather.wind_speed_ms or 0.0,
                wind_dir_deg=weather.wind_direction_deg or 0.0,
                course_bearing=course_bearing,
            )

        wap_s = actual_pace_s / wap_factor if wap_factor > 0 else actual_pace_s

        history.append(
            {
                "date": act.start_date.strftime("%Y-%m-%d") if act.start_date else "",
                "name": act.name,
                "strava_id": act.strava_id,
                "sport_type": act.sport_type,
                "distance_km": round(act.distance_m / 1000, 2) if act.distance_m else None,
                "actual_pace_s": round(actual_pace_s, 1),
                "wap_s": round(wap_s, 1),
                "true_pace_s": round(wap_s, 1),  # same as WAP (GAP streams not stored yet)
                "wap_factor": round(wap_factor, 4),
                "temp_c": weather.temperature_c,
                "humidity_pct": weather.humidity_pct,
                "wind_speed_ms": weather.wind_speed_ms,
                "weather_code": weather.weather_code,
                "wbgt_c": weather.wbgt_c,
            }
        )

    return history


async def get_activities_missing_weather(
    athlete_id: int, limit: int = 500
) -> list[Activity]:
    """Activities with start_latlng but no matching activity_weather row."""
    async with get_async_session() as session:
        # Subquery: activity_ids that already have weather
        have_weather = select(ActivityWeather.activity_id)

        q = (
            select(Activity)
            .where(Activity.athlete_id == athlete_id)
            .where(Activity.start_latlng.isnot(None))
            .where(Activity.strava_id.not_in(have_weather))
            .order_by(Activity.start_date.desc())
            .limit(limit)
        )
        result = await session.execute(q)
        return list(result.scalars().all())


async def upsert_activity_weather(
    activity_id: int,
    weather_dict: dict,
    source: str = "open-meteo",
) -> ActivityWeather:
    """Insert or update ActivityWeather row."""
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
            "fetched_at": datetime.now(timezone.utc),
        }

        if row:
            for k, v in fields.items():
                setattr(row, k, v)
        else:
            row = ActivityWeather(activity_id=activity_id, **fields)
            session.add(row)

        await session.flush()
        row_dict = row.to_dict()

    return row_dict
