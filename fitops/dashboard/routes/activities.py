from __future__ import annotations

import json
import math
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fitops.analytics.activity_zones import compute_activity_analytics
from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.config.settings import get_settings
from fitops.dashboard.queries.activities import (
    count_activities,
    get_activity_detail,
    get_activity_laps,
    get_activity_streams,
    get_distinct_sports,
    get_recent_activities,
)
from fitops.dashboard.queries.athlete import get_athlete
from fitops.dashboard.queries.workouts import get_workout_for_activity

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
    sport = a.sport_type
    is_run = sport in {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}

    elapsed = None
    efficiency_pct = None
    if a.elapsed_time_s and a.moving_time_s and a.elapsed_time_s > 0:
        elapsed = _fmt_seconds(a.elapsed_time_s)
        efficiency_pct = round(a.moving_time_s / a.elapsed_time_s * 100)

    return {
        "strava_id": a.strava_id,
        "name": a.name,
        "sport_type": sport,
        "is_run": is_run,
        "date": a.start_date_local.strftime("%Y-%m-%d") if a.start_date_local else "—",
        "date_pretty": a.start_date_local.strftime("%d %b %Y") if a.start_date_local else "—",
        "distance_km": round(a.distance_m / 1000, 2) if a.distance_m else None,
        "duration": _fmt_seconds(a.moving_time_s),
        "elapsed": elapsed,
        "efficiency_pct": efficiency_pct,
        "pace": _pace_str(a.average_speed_ms, sport),
        "avg_hr": round(a.average_heartrate) if a.average_heartrate else None,
        "max_hr": a.max_heartrate,
        "avg_watts": round(a.average_watts) if a.average_watts else None,
        "weighted_avg_watts": round(a.weighted_average_watts) if a.weighted_average_watts else None,
        "max_watts": a.max_watts,
        "tss": round(a.training_stress_score, 1) if a.training_stress_score else None,
        "elevation_m": round(a.total_elevation_gain_m) if a.total_elevation_gain_m else None,
        "is_race": a.is_race,
        "trainer": a.trainer,
        "commute": a.commute,
        "avg_cadence": round(a.average_cadence) if a.average_cadence else None,
        "cadence_unit": "spm" if is_run else "rpm",
        "calories": a.calories,
        "suffer_score": a.suffer_score,
        "description": (a.description or "").strip() or None,
        "device_name": a.device_name,
        "gear_id": a.gear_id,
    }


def _compute_km_splits(streams: dict, sport_type: str) -> list[dict] | None:
    """Compute per-km splits from distance/velocity/heartrate/cadence/altitude streams."""
    if sport_type not in {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}:
        return None

    dist = streams.get("distance", [])
    vel  = streams.get("velocity_smooth", [])
    hr   = streams.get("heartrate", [])
    cad  = streams.get("cadence", [])
    alt  = streams.get("altitude", [])

    if len(dist) < 10 or len(vel) < 10 or (dist[-1] if dist else 0) < 1000:
        return None

    is_run = sport_type in {"Run", "TrailRun", "VirtualRun"}

    def _seg_stats(start: int, end: int) -> dict:
        seg_vel = vel[start : end + 1]
        valid_vels = [v for v in seg_vel if v and v > 0.1]
        if not valid_vels:
            return {}
        avg_vel = sum(valid_vels) / len(valid_vels)
        pace_s = round(1000.0 / avg_vel, 1)
        m, s_rem = divmod(int(pace_s), 60)

        avg_hr_val = None
        if hr and len(hr) > start:
            hr_slice = [h for h in hr[start : end + 1] if h and h > 0]
            if hr_slice:
                avg_hr_val = round(sum(hr_slice) / len(hr_slice))

        avg_cad = None
        if cad and len(cad) > start:
            cad_slice = [c for c in cad[start : end + 1] if c and c > 0]
            if cad_slice:
                raw = sum(cad_slice) / len(cad_slice)
                avg_cad = round(raw * 2 if is_run else raw)

        elev_gain = None
        if alt and len(alt) > start:
            alt_slice = alt[start : end + 1]
            gain = sum(
                max(0.0, alt_slice[j] - alt_slice[j - 1])
                for j in range(1, len(alt_slice))
            )
            elev_gain = round(gain)

        return {
            "pace": f"{m}:{s_rem:02d}",
            "pace_s": pace_s,
            "avg_hr": avg_hr_val,
            "avg_cad": avg_cad,
            "elev_gain": elev_gain,
        }

    splits = []
    km_target = 1000.0
    seg_start = 0

    for i in range(1, len(dist)):
        if dist[i] < km_target:
            continue

        stats = _seg_stats(seg_start, i)
        if not stats:
            km_target += 1000.0
            continue

        splits.append({
            "km": len(splits) + 1,
            "label": str(len(splits) + 1),
            "partial": False,
            **stats,
        })

        seg_start = i
        km_target += 1000.0
        if len(splits) >= 100:
            break

    # Partial last km
    if seg_start < len(dist) - 1 and (dist[-1] - dist[seg_start]) >= 100:
        remaining = dist[-1] - dist[seg_start]
        stats = _seg_stats(seg_start, len(dist) - 1)
        if stats:
            splits.append({
                "km": len(splits) + 1,
                "label": f"{len(splits) + 1} ({remaining / 1000:.2f}km)",
                "partial": True,
                **stats,
            })

    return splits if splits else None


def _compute_avg_gap(streams: dict, sport_type: str) -> str | None:
    """Compute average grade-adjusted pace from stream data (running only)."""
    if sport_type not in {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}:
        return None

    gas = streams.get("grade_adjusted_speed", [])
    if not gas:
        vel = streams.get("velocity_smooth", [])
        grade = streams.get("grade_smooth", [])
        if vel and grade:
            gas = [
                v * (1 + 0.033 * g) if v and v > 0.1 else 0.0
                for v, g in zip(vel, grade)
            ]

    valid = [v for v in gas if v and v > 0.1]
    if not valid:
        return None

    avg_v = sum(valid) / len(valid)
    pace_s = 1000.0 / avg_v
    m, s = divmod(int(pace_s), 60)
    return f"{m}:{s:02d}/km"


def _downsample_streams(streams: dict, target: int = 500) -> dict:
    n = max((len(v) for v in streams.values()), default=0)
    if n <= target:
        return streams
    step = max(1, n // target)
    return {k: v[::step] for k, v in streams.items()}


def register(templates: Jinja2Templates) -> APIRouter:
    @router.get("/activities", response_class=HTMLResponse)
    async def activity_list(
        request: Request,
        sport: Optional[str] = None,
        days: Optional[int] = None,
        limit: int = 50,
        page: int = 1,
    ):
        settings = get_settings()
        athlete_id = settings.athlete_id

        page = max(1, page)
        offset = (page - 1) * limit

        activities = []
        sports = []
        total = 0
        if athlete_id:
            activities = await get_recent_activities(
                athlete_id, limit=limit, offset=offset, sport=sport, days=days
            )
            sports = await get_distinct_sports(athlete_id)
            total = await count_activities(athlete_id, sport=sport, days=days)

        total_pages = max(1, math.ceil(total / limit)) if total else 1

        return templates.TemplateResponse(
            "activities/list.html",
            {
                "request": request,
                "activities": [_activity_row(a) for a in activities],
                "sports": sports,
                "selected_sport": sport,
                "selected_days": days,
                "selected_limit": limit,
                "current_page": page,
                "total_pages": total_pages,
                "total": total,
                "active_page": "activities",
            },
        )

    @router.get("/activities/{strava_id}", response_class=HTMLResponse)
    async def activity_detail(request: Request, strava_id: int):
        settings = get_settings()
        athlete_id = settings.athlete_id

        streams = {}
        activity = None
        laps = []
        analytics = None
        if athlete_id:
            activity = await get_activity_detail(athlete_id, strava_id)
            if activity and activity.laps_fetched:
                laps = await get_activity_laps(activity.id)
            if activity and activity.streams_fetched:
                streams = await get_activity_streams(activity.id)
                analytics = compute_activity_analytics(activity, streams)

        if activity is None:
            return templates.TemplateResponse(
                "activities/detail.html",
                {"request": request, "activity": None, "active_page": "activities"},
                status_code=404,
            )

        run_sports = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
        is_run = activity.sport_type in run_sports

        gear_name = None
        if activity.gear_id:
            athlete = await get_athlete(athlete_id)
            if athlete:
                gear_name = athlete.get_gear_name(activity.gear_id)

        lap_rows = []
        for lap in laps:
            spd = lap.average_speed_ms
            pace_s = round(1000.0 / spd, 1) if spd and spd > 0 and is_run else None
            lap_rows.append({
                "index": (lap.lap_index or 0) + 1,
                "name": lap.name or f"Lap {(lap.lap_index or 0) + 1}",
                "duration": _fmt_seconds(lap.moving_time_s),
                "distance_km": round(lap.distance_m / 1000, 2) if lap.distance_m else None,
                "pace": _pace_str(spd, activity.sport_type),
                "pace_s": pace_s,
                "avg_hr": round(lap.average_heartrate) if lap.average_heartrate else None,
                "max_hr": lap.max_heartrate,
                "avg_watts": round(lap.average_watts) if lap.average_watts else None,
            })

        km_splits = _compute_km_splits(streams, activity.sport_type)
        avg_gap = _compute_avg_gap(streams, activity.sport_type)

        # Fetch linked workout + segments if any
        workout_data = None
        if activity.id:
            linked = await get_workout_for_activity(activity.id)
            if linked:
                w, segs = linked

                def _fmt_pace_local(pace_s):
                    if pace_s is None:
                        return None
                    m, s = divmod(int(pace_s), 60)
                    return f"{m}:{s:02d}"

                def _seg_target_label(s):
                    focus = s.target_focus_type or "none"
                    if focus == "hr_range":
                        lo, hi = s.target_hr_min_bpm, s.target_hr_max_bpm
                        return f"HR {int(lo)}–{int(hi)} bpm" if lo and hi else "HR target"
                    if focus == "pace_range":
                        lo = _fmt_pace_local(s.target_pace_min_s_per_km)
                        hi = _fmt_pace_local(s.target_pace_max_s_per_km)
                        return f"{lo}–{hi}/km" if lo and hi else "Pace target"
                    if focus == "hr_zone" and s.target_zone:
                        return f"Zone {s.target_zone}"
                    return "—"

                workout_data = {
                    "id": w.id,
                    "name": w.name,
                    "compliance_score": w.compliance_score,
                    "compliance_pct": round(w.compliance_score * 100) if w.compliance_score is not None else None,
                    "segments": [
                        {
                            **s.to_dict(),
                            "target_label": _seg_target_label(s),
                            "compliance_pct": round(s.compliance_score * 100) if s.compliance_score is not None else None,
                            "score_class": (
                                "green" if s.compliance_score and s.compliance_score >= 0.8
                                else "amber" if s.compliance_score and s.compliance_score >= 0.6
                                else "red" if s.compliance_score is not None
                                else "dim"
                            ),
                        }
                        for s in segs
                    ],
                }

        return templates.TemplateResponse(
            "activities/detail.html",
            {
                "request": request,
                "activity": _activity_row(activity),
                "activity_raw": activity,
                "laps": lap_rows,
                "km_splits": km_splits,
                "analytics": analytics,
                "avg_gap": avg_gap,
                "has_polyline": bool(activity.map_summary_polyline),
                "streams_json": json.dumps(_downsample_streams(streams)),
                "has_streams": bool(streams),
                "sport_type": activity.sport_type,
                "gear_name": gear_name,
                "workout": workout_data,
                "lt2_hr": get_athlete_settings().lthr,
                "lt1_hr": round(get_athlete_settings().lthr * 0.92) if get_athlete_settings().lthr else None,
                "active_page": "activities",
            },
        )

    return router
