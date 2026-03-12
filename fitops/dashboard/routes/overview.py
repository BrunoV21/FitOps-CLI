from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fitops.config.settings import get_settings
from fitops.dashboard.queries.activities import get_activity_stats, get_recent_activities
from fitops.dashboard.queries.analytics import get_training_load_data
from fitops.dashboard.queries.athlete import get_athlete
from fitops.dashboard.queries.profile import get_activity_heatmap_data

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


_PERIOD_LABELS = {"month": "This Month", "year": "This Year", "all": "All Time"}


def _period_since(period: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "year":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return None  # all time


def register(templates: Jinja2Templates) -> APIRouter:
    @router.get("/", response_class=HTMLResponse)
    async def overview(request: Request, period: str = "month"):
        if period not in _PERIOD_LABELS:
            period = "month"
        since = _period_since(period)

        settings = get_settings()
        athlete_id = settings.athlete_id

        athlete = await get_athlete(athlete_id) if athlete_id else None
        recent = await get_recent_activities(athlete_id, limit=10, since=since) if athlete_id else []
        stats = await get_activity_stats(athlete_id, since=since) if athlete_id else {}
        tl = await get_training_load_data(athlete_id, days=1) if athlete_id else None
        heatmap_data = await get_activity_heatmap_data(athlete_id) if athlete_id else []

        current_load = None
        if tl and tl.current:
            c = tl.current
            current_load = {
                "ctl": round(c.ctl, 1),
                "atl": round(c.atl, 1),
                "tsb": round(c.tsb, 1),
                "form_label": tl.form_label(c.tsb),
            }

        return templates.TemplateResponse(
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
                "active_page": "overview",
            },
        )

    return router
