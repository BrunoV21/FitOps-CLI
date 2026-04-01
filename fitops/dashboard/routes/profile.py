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

    # Apply LT1/LT2 overrides (take precedence over computed values)
    lt1_is_override = False
    lt2_is_override = False
    if athlete_settings_data.get("lt1_hr"):
        lt1_bpm = athlete_settings_data["lt1_hr"]
        lt1_is_override = True
    if athlete_settings_data.get("lt2_hr"):
        lt2_bpm = athlete_settings_data["lt2_hr"]
        lt2_is_override = True

    # Custom HR zone overrides
    custom_hr_bounds = athlete_settings_data.get("custom_hr_zone_bounds")
    hr_zones_custom = bool(custom_hr_bounds and len(custom_hr_bounds) == 4)
    if hr_zones_custom:
        _names = ["Recovery", "Aerobic", "Tempo", "Threshold", "VO2max"]
        _descs = [
            "Active recovery — below aerobic threshold",
            "Aerobic base — low intensity endurance",
            "Tempo — comfortably hard aerobic work",
            "Threshold — lactate threshold effort",
            "VO2max — above threshold high intensity",
        ]
        _mins = [0] + list(custom_hr_bounds)
        _maxs = list(custom_hr_bounds) + [999]
        hr_zones = [
            {
                "zone": i + 1,
                "name": _names[i],
                "min_bpm": _mins[i],
                "max_bpm": _maxs[i] if _maxs[i] < 999 else None,
                "description": _descs[i],
            }
            for i in range(5)
        ]
    # Bounds for edit form pre-population
    if custom_hr_bounds and len(custom_hr_bounds) == 4:
        hr_edit_bounds = list(custom_hr_bounds)
    elif hr_zones:
        hr_edit_bounds = [z["max_bpm"] for z in hr_zones[:4]]
    else:
        hr_edit_bounds = [None, None, None, None]

    threshold_pace_s = athlete_settings_data.get("threshold_pace_per_km_s")
    pace_zones = None
    if threshold_pace_s:
        pz = compute_pace_zones(int(threshold_pace_s))
        pace_zones = pz.zones

    def _fmt_s(s: Optional[float]) -> Optional[str]:
        if s is None:
            return None
        si = int(s)
        return f"{si // 60}:{si % 60:02d}/km"

    lt1_pace_fmt = _fmt_s(athlete_settings_data.get("lt1_pace_s"))
    lt2_pace_fmt = _fmt_s(athlete_settings_data.get("threshold_pace_per_km_s"))
    vo2max_pace_fmt = _fmt_s(athlete_settings_data.get("vo2max_pace_s"))

    # Race predictions from Daniels VDOT using fractional utilization per distance
    race_predictions = None
    if vo2max_result and vo2max_result.vdot:
        vdot = vo2max_result.vdot

        def _vdot_race(frac: float, dist_m: int) -> dict:
            """Predict race pace and time for a given fractional utilization."""
            demand = vdot * frac
            a, b, c = 0.000104, 0.182258, -(demand + 4.6)
            v_mpm = (-b + (b ** 2 - 4 * a * c) ** 0.5) / (2 * a)
            pace_s = round(1000 / (v_mpm / 60))
            total_s = round(dist_m / (v_mpm / 60))
            h, rem = divmod(total_s, 3600)
            m, s = divmod(rem, 60)
            time_fmt = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            return {"pace": f"{pace_s // 60}:{pace_s % 60:02d}/km", "time": time_fmt}

        race_predictions = [
            {"label": "5 K",        **_vdot_race(0.979, 5000)},
            {"label": "10 K",       **_vdot_race(0.939, 10000)},
            {"label": "12 K",       **_vdot_race(0.922, 12000)},
            {"label": "Half (21K)", **_vdot_race(0.879, 21097)},
            {"label": "Marathon",   **_vdot_race(0.838, 42195)},
        ]

    # Custom pace zone overrides
    custom_pace_bounds = athlete_settings_data.get("custom_pace_zone_bounds")
    pace_zones_custom = bool(custom_pace_bounds and len(custom_pace_bounds) == 4)
    if pace_zones_custom:
        b = list(custom_pace_bounds)  # [b1, b2, b3, b4] slowest→fastest (desc seconds)
        pace_zones = [
            {"zone": 1, "name": "Easy",      "min_s_per_km": b[0], "max_s_per_km": None, "min_pace_fmt": _fmt_pace(b[0]), "max_pace_fmt": None},
            {"zone": 2, "name": "Aerobic",   "min_s_per_km": b[1], "max_s_per_km": b[0], "min_pace_fmt": _fmt_pace(b[1]), "max_pace_fmt": _fmt_pace(b[0])},
            {"zone": 3, "name": "Tempo",     "min_s_per_km": b[2], "max_s_per_km": b[1], "min_pace_fmt": _fmt_pace(b[2]), "max_pace_fmt": _fmt_pace(b[1])},
            {"zone": 4, "name": "Threshold", "min_s_per_km": b[3], "max_s_per_km": b[2], "min_pace_fmt": _fmt_pace(b[3]), "max_pace_fmt": _fmt_pace(b[2])},
            {"zone": 5, "name": "VO2max",    "min_s_per_km": None, "max_s_per_km": b[3], "min_pace_fmt": None,            "max_pace_fmt": _fmt_pace(b[3])},
        ]
    # Bounds for pace edit form pre-population
    if custom_pace_bounds and len(custom_pace_bounds) == 4:
        pace_edit_bounds = [_fmt_pace(b) for b in custom_pace_bounds]
    elif pace_zones:
        pace_edit_bounds = [z["min_pace_fmt"] for z in pace_zones[:4]]
    else:
        pace_edit_bounds = [None, None, None, None]

    shoes = [e for e in equipment if e["type"] == "shoes"]
    bikes = [e for e in equipment if e["type"] == "bike"]

    return {
        "athlete": athlete,
        "settings": athlete_settings_data,
        "threshold_pace_fmt": _fmt_pace(threshold_pace_s),
        "hr_zones": hr_zones,
        "hr_zones_custom": hr_zones_custom,
        "hr_edit_bounds": hr_edit_bounds,
        "lt1_bpm": lt1_bpm,
        "lt2_bpm": lt2_bpm,
        "lt1_is_override": lt1_is_override,
        "lt2_is_override": lt2_is_override,
        "zone_method": method,
        "pace_zones": pace_zones,
        "pace_zones_custom": pace_zones_custom,
        "pace_edit_bounds": pace_edit_bounds,
        "lt1_pace_fmt": lt1_pace_fmt,
        "lt2_pace_fmt": lt2_pace_fmt,
        "vo2max_pace_fmt": vo2max_pace_fmt,
        "race_predictions": race_predictions,
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
                "vo2max_override_val": s.vo2max_override,
                "vo2max_computed": vo2max_result,
            }
        )
        return templates.TemplateResponse(request, "profile.html", ctx)

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
            from fitops.db.migrations import create_all_tables
            from fitops.db.models.athlete import Athlete
            from fitops.db.session import get_async_session
            from sqlalchemy import select

            await create_all_tables()
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

    @router.post("/profile/hr-zones")
    async def save_hr_zones(
        request: Request,
        z1_max: Optional[str] = Form(default=None),
        z2_max: Optional[str] = Form(default=None),
        z3_max: Optional[str] = Form(default=None),
        z4_max: Optional[str] = Form(default=None),
        reset: Optional[str] = Form(default=None),
    ):
        s = get_athlete_settings()
        if reset:
            s.clear("custom_hr_zone_bounds")
            return RedirectResponse("/profile?saved=1", status_code=303)

        def _bpm(v: Optional[str]) -> Optional[int]:
            try:
                return int(v) if v and v.strip() else None
            except ValueError:
                return None

        bounds = [_bpm(z1_max), _bpm(z2_max), _bpm(z3_max), _bpm(z4_max)]
        if not all(b is not None for b in bounds) or bounds != sorted(bounds):
            return RedirectResponse("/profile?error=invalid_zones", status_code=303)

        s.set(custom_hr_zone_bounds=bounds)
        return RedirectResponse("/profile?saved=1", status_code=303)

    @router.post("/profile/estimates")
    async def save_estimates(
        request: Request,
        lt1_hr: Optional[str] = Form(default=None),
        lt2_hr: Optional[str] = Form(default=None),
        vo2max_override: Optional[str] = Form(default=None),
        clear_lt1: Optional[str] = Form(default=None),
        clear_lt2: Optional[str] = Form(default=None),
        clear_vo2max: Optional[str] = Form(default=None),
    ):
        s = get_athlete_settings()

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

        clear_keys = []
        if clear_lt1:
            clear_keys.append("lt1_hr")
        if clear_lt2:
            clear_keys.append("lt2_hr")
        if clear_vo2max:
            clear_keys.append("vo2max_override")
        if clear_keys:
            s.clear(*clear_keys)

        updates: dict = {}
        if (v := _int(lt1_hr)) is not None:
            updates["lt1_hr"] = v
        if (v := _int(lt2_hr)) is not None:
            updates["lt2_hr"] = v
        if (v := _float(vo2max_override)) is not None:
            updates["vo2max_override"] = round(v, 1)
        if updates:
            s.set(**updates)

        if not updates and not clear_keys:
            return RedirectResponse("/profile?error=no_changes", status_code=303)
        return RedirectResponse("/profile?saved=1", status_code=303)

    @router.post("/profile/recalculate-vo2max")
    async def recalculate_vo2max(
        request: Request,
        method: str = Form(default="composite"),
    ):
        cfg = get_settings()
        if not cfg.athlete_id:
            return RedirectResponse("/profile?error=no_auth", status_code=303)

        result = await estimate_vo2max(cfg.athlete_id)
        if result is None:
            return RedirectResponse("/profile?error=no_runs", status_code=303)

        if method == "daniels":
            value = result.vdot
        elif method == "cooper":
            value = result.cooper
        else:
            value = result.estimate

        if value is None:
            return RedirectResponse("/profile?error=no_estimate", status_code=303)

        s = get_athlete_settings()
        s.set(vo2max_override=round(float(value), 1))
        return RedirectResponse("/profile?saved=1", status_code=303)

    @router.post("/profile/pace-zones")
    async def save_pace_zones(
        request: Request,
        b1: Optional[str] = Form(default=None),
        b2: Optional[str] = Form(default=None),
        b3: Optional[str] = Form(default=None),
        b4: Optional[str] = Form(default=None),
        reset: Optional[str] = Form(default=None),
    ):
        s = get_athlete_settings()
        if reset:
            s.clear("custom_pace_zone_bounds")
            return RedirectResponse("/profile?saved=1", status_code=303)

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

        bounds = [_pace_s(b1), _pace_s(b2), _pace_s(b3), _pace_s(b4)]
        if not all(b is not None for b in bounds) or bounds != sorted(bounds, reverse=True):
            return RedirectResponse("/profile?error=invalid_zones", status_code=303)

        s.set(custom_pace_zone_bounds=bounds)
        return RedirectResponse("/profile?saved=1", status_code=303)

    return router
