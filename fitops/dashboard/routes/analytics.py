from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fitops.analytics.training_load import _compute_overtraining_indicators
from fitops.analytics.vo2max import estimate_vo2max
from fitops.config.settings import get_settings
from fitops.dashboard.queries.analytics import (
    RIDING_SPORTS,
    RUNNING_SPORTS,
    get_training_load_data,
    get_trends_data,
    get_vo2max_history,
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
    async def trends(
        request: Request,
        days: int = 180,
        sport: Optional[str] = None,
        metric: str = "distance",
        sport_group: str = "all",
    ):
        settings = get_settings()
        athlete_id = settings.athlete_id

        trends_data = None
        weekly: list = []
        weekly_run: list = []
        weekly_ride: list = []

        weeks = min(52, max(12, days // 7))

        if athlete_id:
            if sport_group == "run":
                sport_types = RUNNING_SPORTS
            elif sport_group == "ride":
                sport_types = RIDING_SPORTS
            else:
                sport_types = None

            trends_data = await get_trends_data(
                athlete_id, days=days, sport=sport, sport_types=sport_types
            )

            if sport_group == "split":
                weekly = await get_weekly_volume(athlete_id, weeks=weeks)
                weekly_run = await get_weekly_volume(athlete_id, weeks=weeks, sport_types=RUNNING_SPORTS)
                weekly_ride = await get_weekly_volume(athlete_id, weeks=weeks, sport_types=RIDING_SPORTS)
            elif sport_group == "run":
                weekly = await get_weekly_volume(athlete_id, weeks=weeks, sport_types=RUNNING_SPORTS)
            elif sport_group == "ride":
                weekly = await get_weekly_volume(athlete_id, weeks=weeks, sport_types=RIDING_SPORTS)
            else:
                weekly = await get_weekly_volume(athlete_id, weeks=weeks, sport=sport)

        return templates.TemplateResponse(
            "analytics/trends.html",
            {
                "request": request,
                "trends": trends_data,
                "weekly_json": json.dumps(weekly),
                "weekly_run_json": json.dumps(weekly_run),
                "weekly_ride_json": json.dumps(weekly_ride),
                "selected_days": days,
                "selected_sport": sport,
                "selected_metric": metric,
                "selected_sport_group": sport_group,
                "active_page": "trends",
            },
        )

    @router.get("/analytics/performance", response_class=HTMLResponse)
    async def performance(request: Request, days: int = 365):
        settings = get_settings()
        athlete_id = settings.athlete_id

        best_vo2max = None
        history = []

        if athlete_id:
            best_vo2max = await estimate_vo2max(athlete_id, max_activities=50)
            history = await get_vo2max_history(athlete_id, days=days)

        from fitops.analytics.athlete_settings import get_athlete_settings
        athlete_settings = get_athlete_settings()
        lt2_pace_s = athlete_settings.threshold_pace_per_km_s
        lt2_pace_fmt = None
        if lt2_pace_s:
            m_int = int(lt2_pace_s // 60)
            s_int = int(lt2_pace_s % 60)
            lt2_pace_fmt = f"{m_int}:{s_int:02d}/km"

        history_json = json.dumps(history)

        return templates.TemplateResponse(
            "analytics/performance.html",
            {
                "request": request,
                "best_vo2max": best_vo2max,
                "history": history,
                "history_json": history_json,
                "selected_days": days,
                "lt2_pace_fmt": lt2_pace_fmt,
                "active_page": "performance",
            },
        )

    return router
