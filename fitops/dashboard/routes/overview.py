from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from fitops.analytics.weather_pace import (
    deg_to_compass,
    pace_heat_factor,
    wbgt_approx,
    wbgt_flag,
    weather_condition_label,
)
from fitops.config.settings import get_settings
from fitops.dashboard.queries.activities import (
    get_activity_stats,
    get_recent_activities,
)
from fitops.dashboard.queries.analytics import (
    RIDING_SPORTS,
    RUNNING_SPORTS,
    get_current_training_load,
)
from fitops.dashboard.queries.athlete import get_athlete
from fitops.dashboard.queries.profile import get_activity_heatmap_data
from fitops.db.models.activity import Activity
from fitops.db.session import get_async_session
from fitops.weather.client import fetch_forecast_weather

router = APIRouter()


def _format_seconds(s: int | None) -> str:
    if s is None:
        return "—"
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _pace_per_km(speed_ms: float | None, sport_type: str) -> str:
    """Return pace string M:SS/km for run-like sports, speed km/h otherwise."""
    if speed_ms is None or speed_ms == 0:
        return "—"
    run_sports = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
    if sport_type in run_sports:
        pace_s = 1000 / speed_ms
        m, s = divmod(int(pace_s), 60)
        return f"{m}:{s:02d}/km"
    kmh = speed_ms * 3.6
    return f"{kmh:.1f} km/h"


def _format_activity(a) -> dict:
    return {
        "strava_id": a.strava_id,
        "name": a.name,
        "sport_type": a.sport_type,
        "date": a.start_date_local.strftime("%d %b %Y") if a.start_date_local else "—",
        "distance_km": round(a.distance_m / 1000, 2) if a.distance_m else None,
        "duration": _format_seconds(a.moving_time_s),
        "pace": _pace_per_km(a.average_speed_ms, a.sport_type),
        "avg_hr": round(a.average_heartrate) if a.average_heartrate else None,
        "tss": round(a.training_stress_score, 1) if a.training_stress_score else None,
    }


async def _get_today_weather(athlete_id: int | None) -> dict | None:
    """Fetch today's forecast using coordinates from the athlete's most recent GPS activity."""
    if not athlete_id:
        return None
    async with get_async_session() as session:
        result = await session.execute(
            select(Activity)
            .where(Activity.athlete_id == athlete_id)
            .where(Activity.start_latlng.isnot(None))
            .order_by(Activity.start_date.desc())
            .limit(1)
        )
        act = result.scalar_one_or_none()
    if not act or not act.start_latlng:
        return None
    try:
        coords = json.loads(act.start_latlng)
        lat, lng = float(coords[0]), float(coords[1])
    except (json.JSONDecodeError, TypeError, ValueError, IndexError):
        return None

    now = datetime.now(UTC)
    raw = await fetch_forecast_weather(lat, lng, now.strftime("%Y-%m-%d"), now.hour)
    if not raw:
        return None

    temp_c = raw.get("temperature_c")
    humidity = raw.get("humidity_pct")
    wind_speed = raw.get("wind_speed_ms") or 0.0
    wind_dir = raw.get("wind_direction_deg") or 0.0
    wcode = raw.get("weather_code")

    wbgt_val: float | None = None
    heat_factor: float | None = None
    if temp_c is not None and humidity is not None:
        wbgt_val = round(wbgt_approx(temp_c, humidity), 1)
        heat_factor = round(pace_heat_factor(temp_c, humidity), 4)

    return {
        "temperature_c": round(temp_c, 1) if temp_c is not None else None,
        "apparent_temp_c": round(raw.get("apparent_temp_c"), 1)
        if raw.get("apparent_temp_c") is not None
        else None,
        "humidity_pct": humidity,
        "precipitation_mm": raw.get("precipitation_mm"),
        "wind_speed_kmh": round(wind_speed * 3.6, 1),
        "wind_gusts_kmh": round((raw.get("wind_gusts_ms") or 0) * 3.6, 1),
        "wind_direction_compass": deg_to_compass(wind_dir),
        "condition": weather_condition_label(wcode) if wcode is not None else "—",
        "weather_code": wcode,
        "wbgt_c": wbgt_val,
        "wbgt_flag": wbgt_flag(wbgt_val) if wbgt_val is not None else None,
        "pace_heat_factor": heat_factor,
        "timezone": raw.get("_timezone", "UTC"),
        "lat": lat,
        "lng": lng,
    }


_PERIOD_LABELS = {
    "week": "This Week",
    "month": "This Month",
    "year": "This Year",
    "all": "All Time",
}

_VIEW_SPORT_TYPES = {
    "run": RUNNING_SPORTS,
    "cycle": RIDING_SPORTS,
    "total": None,  # all sports
}


def _compute_rolling(period: str, since: datetime | None, stats: dict) -> dict | None:
    """Compute rolling averages for the selected period."""
    if not since or not stats:
        return None
    now = datetime.now(UTC)
    days_elapsed = max(1, (now - since).days + 1)
    weeks_elapsed = max(1.0, days_elapsed / 7.0)

    count = stats.get("total_count") or 0
    dist_km = float(stats.get("total_distance_km") or 0.0)
    dur_h = float(stats.get("total_duration_h") or 0.0)

    if period == "week":
        avg_dist = round(dist_km / count, 1) if count else 0.0
        avg_dur_min = round((dur_h / count) * 60) if count else 0
        return {
            "total_time_h": dur_h,
            "avg_distance_per_activity": avg_dist,
            "avg_duration_per_activity_min": avg_dur_min,
        }
    if period == "month":
        return {
            "total_time_h": dur_h,
            "avg_per_week": round(count / weeks_elapsed, 1),
            "avg_distance_per_week": round(dist_km / weeks_elapsed, 1),
            "avg_time_per_week_h": round(dur_h / weeks_elapsed, 1),
        }
    if period == "year":
        months_elapsed = max(1, now.month)
        return {
            "total_time_h": dur_h,
            "avg_per_week": round(count / weeks_elapsed, 1),
            "avg_per_month": round(count / months_elapsed, 1),
            "avg_distance_per_week": round(dist_km / weeks_elapsed, 1),
        }
    return None


def _period_since(period: str) -> datetime | None:
    now = datetime.now(UTC)
    if period == "week":
        return (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "year":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return None  # all time


def register(templates: Jinja2Templates) -> APIRouter:
    @router.get("/", response_class=HTMLResponse)
    async def overview(request: Request, period: str = "week", view: str = "total"):
        settings = get_settings()
        if not settings.is_authenticated:
            return RedirectResponse("/setup")

        if period not in _PERIOD_LABELS:
            period = "week"
        if view not in _VIEW_SPORT_TYPES:
            view = "total"
        since = _period_since(period)
        sport_types = _VIEW_SPORT_TYPES[view]

        athlete_id = settings.athlete_id

        athlete = await get_athlete(athlete_id) if athlete_id else None
        recent = (
            await get_recent_activities(
                athlete_id, limit=10, since=since, sport_types=sport_types
            )
            if athlete_id
            else []
        )
        stats = (
            await get_activity_stats(athlete_id, since=since, sport_types=sport_types)
            if athlete_id
            else {}
        )
        current_load = (
            await get_current_training_load(athlete_id)
            if athlete_id and period == "week"
            else None
        )
        heatmap_data = (
            await get_activity_heatmap_data(athlete_id, since=None)
            if athlete_id
            else []
        )
        today_weather = (
            await _get_today_weather(athlete_id) if period == "week" else None
        )
        rolling = _compute_rolling(period, since, stats)

        return templates.TemplateResponse(
            request,
            "overview.html",
            {
                "request": request,
                "athlete": athlete,
                "recent_activities": [_format_activity(a) for a in recent],
                "stats": stats,
                "current_load": current_load,
                "heatmap_json": json.dumps(heatmap_data),
                "period": period,
                "period_label": _PERIOD_LABELS[period],
                "today_weather": today_weather,
                "rolling": rolling,
                "active_page": "overview",
                "view": view,
            },
        )

    return router
