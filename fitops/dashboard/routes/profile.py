"""Profile dashboard route — view & edit physiological settings and equipment."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.analytics.pace_zones import compute_pace_zones
from fitops.analytics.vo2max import estimate_vo2max
from fitops.analytics.zones import compute_zones
from fitops.config.settings import get_settings
from fitops.dashboard.queries.profile import get_athlete, get_equipment_with_stats

router = APIRouter()


def _fmt_pace(s: Optional[float]) -> Optional[str]:
    if s is None:
        return None
    si = int(s)
    return f"{si // 60}:{si % 60:02d}"


def _build_profile_context(athlete, athlete_settings_data: dict, vo2max_result, equipment: list) -> dict:
    """Build template context dict for the profile page."""
    method = None
    hr_zones = None
    lt1_bpm = None
    lt2_bpm = None

    lthr = athlete_settings_data.get("lthr")
    max_hr = athlete_settings_data.get("max_hr")
    resting_hr = athlete_settings_data.get("resting_hr")

    if lthr:
        method = "lthr"
    elif max_hr and resting_hr:
        method = "hrr"
    elif max_hr:
        method = "max-hr"

    if method:
        zone_result = compute_zones(method=method, lthr=lthr, max_hr=max_hr, resting_hr=resting_hr)
        if zone_result:
            hr_zones = [
                {
                    "zone": z.zone,
                    "name": z.name,
                    "min_bpm": z.min_bpm,
                    "max_bpm": z.max_bpm if z.max_bpm < 999 else None,
                    "description": z.description,
                }
                for z in zone_result.zones
            ]
            lt1_bpm = zone_result.lt1_bpm
            lt2_bpm = zone_result.lt2_bpm

    threshold_pace_s = athlete_settings_data.get("threshold_pace_per_km_s")
    pace_zones = None
    if threshold_pace_s:
        pz = compute_pace_zones(int(threshold_pace_s))
        pace_zones = pz.zones

    shoes = [e for e in equipment if e["type"] == "shoes"]
    bikes = [e for e in equipment if e["type"] == "bike"]

    return {
        "athlete": athlete,
        "settings": athlete_settings_data,
        "threshold_pace_fmt": _fmt_pace(threshold_pace_s),
        "hr_zones": hr_zones,
        "lt1_bpm": lt1_bpm,
        "lt2_bpm": lt2_bpm,
        "zone_method": method,
        "pace_zones": pace_zones,
        "vo2max": vo2max_result,
        "shoes": shoes,
        "bikes": bikes,
    }


def register(templates: Jinja2Templates) -> APIRouter:
    @router.get("/profile", response_class=HTMLResponse)
    async def profile(request: Request, saved: Optional[str] = None, error: Optional[str] = None):
        cfg = get_settings()
        athlete_id = cfg.athlete_id

        athlete = await get_athlete(athlete_id) if athlete_id else None
        equipment = await get_equipment_with_stats(athlete_id) if athlete_id else []
        vo2max_result = await estimate_vo2max(athlete_id) if athlete_id else None

        s = get_athlete_settings()
        s.reload()
        settings_data = s.to_dict()

        ctx = _build_profile_context(athlete, settings_data, vo2max_result, equipment)
        ctx.update(
            {
                "request": request,
                "active_page": "profile",
                "saved": saved,
                "error": error,
            }
        )
        return templates.TemplateResponse("profile.html", ctx)

    @router.post("/profile/settings")
    async def save_settings(
        request: Request,
        weight_kg: Optional[str] = Form(default=None),
        height_cm: Optional[str] = Form(default=None),
        birthday: Optional[str] = Form(default=None),
        max_hr: Optional[str] = Form(default=None),
        resting_hr: Optional[str] = Form(default=None),
        lthr: Optional[str] = Form(default=None),
        ftp: Optional[str] = Form(default=None),
        threshold_pace: Optional[str] = Form(default=None),
    ):
        s = get_athlete_settings()
        updates: dict = {}

        def _int(v: Optional[str]) -> Optional[int]:
            try:
                return int(v) if v and v.strip() else None
            except ValueError:
                return None

        def _float(v: Optional[str]) -> Optional[float]:
            try:
                return float(v) if v and v.strip() else None
            except ValueError:
                return None

        def _pace_s(v: Optional[str]) -> Optional[int]:
            if not v or not v.strip():
                return None
            parts = v.strip().split(":")
            if len(parts) == 2:
                try:
                    return int(parts[0]) * 60 + int(parts[1])
                except ValueError:
                    pass
            return None

        if (w := _float(weight_kg)) is not None:
            updates["weight_kg"] = w
        if (h := _float(height_cm)) is not None:
            updates["height_cm"] = h
        if birthday and birthday.strip():
            updates["birthday"] = birthday.strip()
        if (m := _int(max_hr)) is not None:
            updates["max_hr"] = m
            updates["max_hr_source"] = "manual"
        if (r := _int(resting_hr)) is not None:
            updates["resting_hr"] = r
        if (l := _int(lthr)) is not None:
            updates["lthr"] = l
            updates["lthr_source"] = "manual"
        if (f := _float(ftp)) is not None:
            updates["ftp"] = f
        if (p := _pace_s(threshold_pace)) is not None:
            updates["threshold_pace_per_km_s"] = p
            updates["pace_zones_source"] = "manual"

        if not updates:
            return RedirectResponse("/profile?error=no_changes", status_code=303)

        s.set(**updates)

        # Mirror weight/birthday to the DB athlete record
        cfg = get_settings()
        if cfg.athlete_id and ("weight_kg" in updates or "birthday" in updates):
            from fitops.db.migrations import init_db
            from fitops.db.models.athlete import Athlete
            from fitops.db.session import get_async_session
            from sqlalchemy import select

            init_db()
            async with get_async_session() as session:
                result = await session.execute(
                    select(Athlete).where(Athlete.strava_id == cfg.athlete_id)
                )
                db_athlete = result.scalar_one_or_none()
                if db_athlete:
                    if "weight_kg" in updates:
                        db_athlete.weight_kg = updates["weight_kg"]
                    if "birthday" in updates:
                        db_athlete.birthday = updates["birthday"]

        return RedirectResponse("/profile?saved=1", status_code=303)

    return router
