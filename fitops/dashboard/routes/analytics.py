from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fitops.analytics.training_load import _compute_overtraining_indicators
from fitops.config.settings import get_settings
from fitops.dashboard.queries.analytics import (
    get_training_load_data,
    get_trends_data,
    get_weekly_volume,
)

router = APIRouter()


def register(templates: Jinja2Templates) -> APIRouter:
    @router.get("/analytics/training-load", response_class=HTMLResponse)
    async def training_load(request: Request, days: int = 90, sport: Optional[str] = None):
        settings = get_settings()
        athlete_id = settings.athlete_id

        tl = None
        chart_data = []
        current_load = None
        overtraining = {}

        if athlete_id:
            tl = await get_training_load_data(athlete_id, days=days, sport=sport)

        if tl:
            chart_data = [
                {
                    "date": str(d.date),
                    "ctl": round(d.ctl, 2),
                    "atl": round(d.atl, 2),
                    "tsb": round(d.tsb, 2),
                    "daily_tss": round(d.daily_tss, 2) if d.daily_tss else 0,
                }
                for d in tl.history
            ]
            c = tl.current
            ramp = tl.ramp_rate_pct
            current_load = {
                "ctl": round(c.ctl, 1),
                "atl": round(c.atl, 1),
                "tsb": round(c.tsb, 1),
                "form_label": tl.form_label(c.tsb),
                "ramp_rate_pct": round(ramp, 1) if ramp is not None else None,
                "ramp_label": tl.ramp_label(ramp) if ramp is not None else None,
            }
            overtraining = _compute_overtraining_indicators(tl.history)

        return templates.TemplateResponse(
            "analytics/training_load.html",
            {
                "request": request,
                "chart_data_json": json.dumps(chart_data),
                "current_load": current_load,
                "overtraining": overtraining,
                "selected_days": days,
                "selected_sport": sport,
                "active_page": "analytics",
            },
        )

    @router.get("/analytics/trends", response_class=HTMLResponse)
    async def trends(request: Request, days: int = 180, sport: Optional[str] = None):
        settings = get_settings()
        athlete_id = settings.athlete_id

        trends_data = None
        weekly = []

        if athlete_id:
            trends_data = await get_trends_data(athlete_id, days=days, sport=sport)
            weekly = await get_weekly_volume(athlete_id, weeks=24, sport=sport)

        weekly_json = json.dumps(weekly)

        return templates.TemplateResponse(
            "analytics/trends.html",
            {
                "request": request,
                "trends": trends_data,
                "weekly_json": weekly_json,
                "selected_days": days,
                "selected_sport": sport,
                "active_page": "analytics",
            },
        )

    return router
