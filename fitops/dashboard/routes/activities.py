from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fitops.config.settings import get_settings
from fitops.dashboard.queries.activities import (
    get_activity_detail,
    get_activity_laps,
    get_distinct_sports,
    get_recent_activities,
)

router = APIRouter()


def _fmt_seconds(s: int | None) -> str:
    if s is None:
        return "—"
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _pace_str(speed_ms: float | None, sport_type: str) -> str:
    if speed_ms is None or speed_ms == 0:
        return "—"
    run_sports = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
    if sport_type in run_sports:
        pace_s = 1000 / speed_ms
        m, s = divmod(int(pace_s), 60)
        return f"{m}:{s:02d}/km"
    return f"{speed_ms * 3.6:.1f} km/h"


def _activity_row(a) -> dict:
    return {
        "strava_id": a.strava_id,
        "name": a.name,
        "sport_type": a.sport_type,
        "date": a.start_date_local.strftime("%Y-%m-%d") if a.start_date_local else "—",
        "date_pretty": a.start_date_local.strftime("%d %b %Y") if a.start_date_local else "—",
        "distance_km": round(a.distance_m / 1000, 2) if a.distance_m else None,
        "duration": _fmt_seconds(a.moving_time_s),
        "pace": _pace_str(a.average_speed_ms, a.sport_type),
        "avg_hr": round(a.average_heartrate) if a.average_heartrate else None,
        "max_hr": a.max_heartrate,
        "avg_watts": round(a.average_watts) if a.average_watts else None,
        "tss": round(a.training_stress_score, 1) if a.training_stress_score else None,
        "elevation_m": round(a.total_elevation_gain_m) if a.total_elevation_gain_m else None,
        "is_race": a.is_race,
        "trainer": a.trainer,
    }


def register(templates: Jinja2Templates) -> APIRouter:
    @router.get("/activities", response_class=HTMLResponse)
    async def activity_list(
        request: Request,
        sport: Optional[str] = None,
        days: Optional[int] = None,
        limit: int = 50,
    ):
        settings = get_settings()
        athlete_id = settings.athlete_id

        activities = []
        sports = []
        if athlete_id:
            activities = await get_recent_activities(
                athlete_id, limit=limit, sport=sport, days=days
            )
            sports = await get_distinct_sports(athlete_id)

        return templates.TemplateResponse(
            "activities/list.html",
            {
                "request": request,
                "activities": [_activity_row(a) for a in activities],
                "sports": sports,
                "selected_sport": sport,
                "selected_days": days,
                "selected_limit": limit,
                "active_page": "activities",
            },
        )

    @router.get("/activities/{strava_id}", response_class=HTMLResponse)
    async def activity_detail(request: Request, strava_id: int):
        settings = get_settings()
        athlete_id = settings.athlete_id

        activity = None
        laps = []
        if athlete_id:
            activity = await get_activity_detail(athlete_id, strava_id)
            if activity and activity.laps_fetched:
                laps = await get_activity_laps(activity.id)

        if activity is None:
            return templates.TemplateResponse(
                "activities/detail.html",
                {"request": request, "activity": None, "active_page": "activities"},
                status_code=404,
            )

        lap_rows = []
        for lap in laps:
            lap_rows.append({
                "index": (lap.lap_index or 0) + 1,
                "name": lap.name or f"Lap {(lap.lap_index or 0) + 1}",
                "duration": _fmt_seconds(lap.moving_time_s),
                "distance_km": round(lap.distance_m / 1000, 2) if lap.distance_m else None,
                "pace": _pace_str(lap.average_speed_ms, activity.sport_type),
                "avg_hr": round(lap.average_heartrate) if lap.average_heartrate else None,
                "max_hr": lap.max_heartrate,
                "avg_watts": round(lap.average_watts) if lap.average_watts else None,
            })

        return templates.TemplateResponse(
            "activities/detail.html",
            {
                "request": request,
                "activity": _activity_row(activity),
                "activity_raw": activity,
                "laps": lap_rows,
                "has_polyline": bool(activity.map_summary_polyline),
                "active_page": "activities",
            },
        )

    return router
