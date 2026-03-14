from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fitops.analytics.training_load import _compute_overtraining_indicators
from fitops.analytics.vo2max import estimate_vo2max, compute_vo2max_rolling
from fitops.config.settings import get_settings
from fitops.analytics.vo2max import compute_race_predictions
from fitops.analytics.zone_inference import paces_from_vdot
from fitops.dashboard.queries.analytics import (
    get_training_load_data,
    get_vo2max_history,
    get_volume_summary,
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
        volume_summary = None

        weeks = min(52, max(12, days // 7))
        weekly: list = []

        if athlete_id:
            tl = await get_training_load_data(athlete_id, days=days, sport=sport)
            volume_summary = await get_volume_summary(athlete_id, sport=sport)
            weekly = await get_weekly_volume(athlete_id, weeks=weeks, sport=sport)

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
                "weekly_json": json.dumps(weekly),
                "current_load": current_load,
                "overtraining": overtraining,
                "volume_summary": volume_summary,
                "selected_days": days,
                "selected_sport": sport,
                "active_page": "analytics",
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
            # Anchor rolling model at the known best estimate so the starting
            # point isn't dragged down by the first easy run in the window.
            compute_vo2max_rolling(
                history, initial=best_vo2max.estimate if best_vo2max else None
            )

        from fitops.analytics.athlete_settings import get_athlete_settings
        athlete_settings = get_athlete_settings()
        lt2_pace_s = athlete_settings.threshold_pace_per_km_s
        lt1_pace_s = athlete_settings.lt1_pace_s
        vo2max_pace_s = athlete_settings.vo2max_pace_s

        def _fmt_pace(pace_s: Optional[float]) -> Optional[str]:
            if not pace_s:
                return None
            return f"{int(pace_s // 60)}:{int(pace_s % 60):02d}/km"

        race_predictions = None
        if best_vo2max:
            race_predictions = compute_race_predictions(best_vo2max, lt2_pace_s=lt2_pace_s)

        # Enrich each history row with derived pace thresholds from VDOT
        for row in history:
            vdot = row.get("vdot")
            if vdot:
                lt1_s, lt2_s, vo2s = paces_from_vdot(vdot)
                row["derived_lt1_pace_s"] = lt1_s
                row["derived_lt2_pace_s"] = lt2_s
                row["derived_vo2max_pace_s"] = vo2s

        history_json = json.dumps(history)

        return templates.TemplateResponse(
            "analytics/performance.html",
            {
                "request": request,
                "best_vo2max": best_vo2max,
                "history": history,
                "history_json": history_json,
                "selected_days": days,
                "lt1_pace_fmt": _fmt_pace(lt1_pace_s),
                "lt2_pace_fmt": _fmt_pace(lt2_pace_s),
                "vo2max_pace_fmt": _fmt_pace(vo2max_pace_s),
                "race_predictions": race_predictions,
                "active_page": "performance",
            },
        )

    return router
