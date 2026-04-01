from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fitops.analytics.weather_pace import weather_condition_label, wbgt_flag
from fitops.config.settings import get_settings
from fitops.dashboard.queries.activities import get_distinct_sports
from fitops.dashboard.queries.weather import get_activities_missing_weather, get_wap_history
from fitops.db.migrations import create_all_tables
from fitops.db.models.athlete import Athlete
from fitops.db.session import get_async_session
from sqlalchemy import select

router = APIRouter()


def _fmt_pace(s_per_km: Optional[float]) -> str:
    if s_per_km is None:
        return "—"
    mins = int(s_per_km) // 60
    secs = int(s_per_km) % 60
    return f"{mins}:{secs:02d}"


def register(templates: Jinja2Templates) -> APIRouter:

    @router.get("/weather", response_class=HTMLResponse)
    async def weather_index(
        request: Request,
        days: int = 180,
        sport: str = "",
    ):
        await create_all_tables()

        # Resolve athlete_id
        async with get_async_session() as session:
            res = await session.execute(select(Athlete).limit(1))
            athlete = res.scalar_one_or_none()

        athlete_id = athlete.strava_id if athlete else 0
        sport_filter: Optional[str] = sport or None

        history = await get_wap_history(athlete_id, days=days, sport=sport_filter)
        missing = await get_activities_missing_weather(athlete_id, limit=500)
        sports = await get_distinct_sports(athlete_id)

        # Enrich rows for template
        rows = []
        for h in history:
            wcode = h.get("weather_code")
            wbgt = h.get("wbgt_c")
            rows.append(
                {
                    **h,
                    "actual_pace_fmt": _fmt_pace(h["actual_pace_s"]),
                    "wap_fmt": _fmt_pace(h["wap_s"]),
                    "true_pace_fmt": _fmt_pace(h["true_pace_s"]),
                    "condition": weather_condition_label(wcode) if wcode is not None else "—",
                    "wbgt_flag": wbgt_flag(wbgt) if wbgt is not None else "green",
                    "factor_pct": round((h["wap_factor"] - 1.0) * 100, 1),
                }
            )

        return templates.TemplateResponse(
            request,
            "weather/index.html",
            {
                "request": request,
                "history": rows,
                "missing_count": len(missing),
                "active_page": "weather",
                "days": days,
                "sport": sport,
                "sports": sports,
            },
        )

    return router
