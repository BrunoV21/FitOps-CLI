from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fitops.analytics.weather_pace import compute_bearing, compute_wap_factor
from fitops.db.models.activity import Activity
from fitops.db.models.activity_weather import ActivityWeather
from fitops.db.session import get_async_session
from fitops.weather.service import upsert_activity_weather as upsert_activity_weather


async def get_weather_for_activities(
    activity_ids: list[int],
) -> dict[int, ActivityWeather]:
    """Batch load weather rows keyed by provider-neutral local activity ID."""
    if not activity_ids:
        return {}
    async with get_async_session() as session:
        result = await session.execute(
            select(ActivityWeather).where(ActivityWeather.activity_id.in_(activity_ids))
        )
        return {w.activity_id: w for w in result.scalars().all()}


async def get_weather_for_activity(
    session: AsyncSession, activity_id: int
) -> ActivityWeather | None:
    result = await session.execute(
        select(ActivityWeather).where(ActivityWeather.activity_id == activity_id)
    )
    return result.scalar_one_or_none()


async def get_wap_history(
    athlete_id: int,
    days: int = 180,
    sport: str | None = None,
) -> list[dict]:
    """
    Return list of dicts with pace, WAP, and weather info for activities that have
    both weather data and average_speed_ms.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)

    async with get_async_session() as session:
        q = (
            select(Activity, ActivityWeather)
            .join(ActivityWeather, ActivityWeather.activity_id == Activity.id)
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

        # WAP is heat/humidity-only. Recompute it from weather inputs even when
        # an older persisted wap_factor exists, because historical rows may
        # include wind from the previous model.
        wap_factor = 1.0
        course_bearing = weather.course_bearing
        if course_bearing is None and act.start_latlng and act.end_latlng:
            try:
                s = json.loads(act.start_latlng)
                e = json.loads(act.end_latlng)
                if len(s) == 2 and len(e) == 2:
                    course_bearing = compute_bearing(s[0], s[1], e[0], e[1])
            except (json.JSONDecodeError, TypeError, IndexError):
                pass
        if weather.temperature_c is not None and weather.humidity_pct is not None:
            wap_factor = compute_wap_factor(
                temp_c=weather.temperature_c,
                rh_pct=weather.humidity_pct,
                wind_speed_ms_val=weather.wind_speed_ms or 0.0,
                wind_dir_deg=weather.wind_direction_deg or 0.0,
                course_bearing=course_bearing,
            )

        wap_s = actual_pace_s / wap_factor if wap_factor > 0 else actual_pace_s

        # Use persisted true_pace_s_per_km if available
        true_pace_s = (
            weather.true_pace_s_per_km if weather.true_pace_s_per_km else wap_s
        )

        history.append(
            {
                "date": act.start_date.strftime("%Y-%m-%d") if act.start_date else "",
                "name": act.name,
                "activity_id": act.id,
                "strava_id": act.strava_id,
                "sport_type": act.sport_type,
                "distance_km": round(act.distance_m / 1000, 2)
                if act.distance_m
                else None,
                "actual_pace_s": round(actual_pace_s, 1),
                "wap_s": round(wap_s, 1),
                "true_pace_s": round(true_pace_s, 1),
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
            .where(Activity.id.not_in(have_weather))
            .order_by(Activity.start_date.desc())
            .limit(limit)
        )
        result = await session.execute(q)
        return list(result.scalars().all())
