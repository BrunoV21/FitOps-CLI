from __future__ import annotations

import json
import math
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fitops.analytics.activity_performance_insights import (
    compute_activity_performance_insights,
)
from fitops.analytics.activity_splits import compute_avg_gap, compute_km_splits
from fitops.analytics.activity_zones import compute_activity_analytics
from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.analytics.training_scores import (
    aerobic_label,
    anaerobic_label,
    compute_aerobic_score,
    compute_anaerobic_score,
)
from fitops.analytics.weather_pace import (
    compute_bearing,
    compute_wap_factor,
    headwind_ms,
    pace_wind_factor,
    vo2max_heat_factor,
    weather_row_to_dict,
)
from fitops.analytics.weather_pace import (
    pace_heat_factor as _pace_heat_factor,
)
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
from fitops.dashboard.queries.weather import get_weather_for_activities
from fitops.dashboard.queries.workouts import (
    get_all_workouts,
    get_workout_for_activity,
    get_workout_names_for_activities,
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


def _aerobic_label(score: float) -> str:
    return aerobic_label(score)


def _anaerobic_label(score: float) -> str:
    return anaerobic_label(score)


def _activity_row(a) -> dict:
    sport = a.sport_type
    is_run = sport in {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}

    elapsed = None
    efficiency_pct = None
    if a.elapsed_time_s and a.moving_time_s and a.elapsed_time_s > 0:
        elapsed = _fmt_seconds(a.elapsed_time_s)
        efficiency_pct = round(a.moving_time_s / a.elapsed_time_s * 100)

    _settings = get_athlete_settings()
    aerobic_score = compute_aerobic_score(a, _settings)
    anaerobic_score = compute_anaerobic_score(a, _settings)

    return {
        "strava_id": a.strava_id,
        "name": a.name,
        "sport_type": sport,
        "is_run": is_run,
        "date": a.start_date_local.strftime("%Y-%m-%d") if a.start_date_local else "—",
        "date_pretty": a.start_date_local.strftime("%d %b %Y")
        if a.start_date_local
        else "—",
        "distance_km": round(a.distance_m / 1000, 2) if a.distance_m else None,
        "duration": _fmt_seconds(a.moving_time_s),
        "elapsed": elapsed,
        "efficiency_pct": efficiency_pct,
        "pace": _pace_str(a.average_speed_ms, sport),
        "avg_hr": round(a.average_heartrate) if a.average_heartrate else None,
        "max_hr": a.max_heartrate,
        "avg_watts": round(a.average_watts) if a.average_watts else None,
        "weighted_avg_watts": round(a.weighted_average_watts)
        if a.weighted_average_watts
        else None,
        "max_watts": a.max_watts,
        "tss": round(a.training_stress_score, 1) if a.training_stress_score else None,
        "elevation_m": round(a.total_elevation_gain_m)
        if a.total_elevation_gain_m
        else None,
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
        "aerobic_score": aerobic_score,
        "anaerobic_score": anaerobic_score,
        "aerobic_score_int": int(aerobic_score),
        "anaerobic_score_int": int(anaerobic_score),
        "aerobic_label": _aerobic_label(aerobic_score),
        "anaerobic_label": _anaerobic_label(anaerobic_score),
    }


def _weather_summary(w) -> dict:
    """Convert an ActivityWeather row into a template-ready dict."""
    return weather_row_to_dict(w)


def _compute_true_pace_stream(streams: dict, weather) -> list | None:
    """
    True Pace (s/km) = GAP adjusted for weather.
    Normalises both gradient and conditions — the best single effort metric.
    Requires both latlng data AND gradient data (grade_adjusted_speed or grade_smooth).
    """
    latlng_pts = streams.get("latlng", [])
    vel = streams.get("velocity_smooth", [])
    if not latlng_pts or not vel or not weather:
        return None

    # Build GAP speed (m/s): prefer Strava's stream, fall back to computed
    gap_raw = streams.get("grade_adjusted_speed", [])
    grade = streams.get("grade_smooth", [])
    n_v = len(vel)
    if gap_raw and len(gap_raw) >= n_v * 0.8:
        gap_speed = gap_raw
    elif grade and len(grade) >= n_v * 0.8:
        gap_speed = [
            v * (1 + 0.033 * g) if (v and v > 0.1) else 0.0
            for v, g in zip(vel, grade, strict=False)
        ]
    else:
        return None  # No gradient data available

    heat_f = 1.0
    if weather.temperature_c is not None and weather.humidity_pct is not None:
        heat_f = _pace_heat_factor(weather.temperature_c, weather.humidity_pct)

    wind_ms = weather.wind_speed_ms or 0.0
    wind_dir = weather.wind_direction_deg or 0.0

    n = min(len(latlng_pts), len(vel), len(gap_speed))
    _LOOK = 7
    last_bearing = 0.0
    result: list = []

    for i in range(n):
        gs = gap_speed[i] if i < len(gap_speed) else 0.0
        if not gs or gs <= 0.1:
            result.append(None)
            continue

        j = min(i + _LOOK, n - 1)
        pt1, pt2 = latlng_pts[i], latlng_pts[j]
        if pt1[0] != pt2[0] or pt1[1] != pt2[1]:
            last_bearing = compute_bearing(pt1[0], pt1[1], pt2[0], pt2[1])

        hw = headwind_ms(wind_ms, wind_dir, last_bearing)
        weather_f = heat_f * pace_wind_factor(hw)
        result.append((1000.0 / gs) / weather_f if weather_f > 0 else None)

    return result if any(x is not None for x in result) else None


def _compute_wap_stream(streams: dict, weather) -> list | None:
    """
    Compute per-GPS-point WAP pace (s/km) by resolving the headwind component
    at each moment using local course bearing from the latlng stream.

    Heat factor is constant for the activity; wind factor varies per GPS segment.
    Uses a 7-point lookahead window to stabilise noisy 1-second GPS bearings.
    """
    latlng_pts = streams.get("latlng", [])
    vel = streams.get("velocity_smooth", [])
    if not latlng_pts or not vel or not weather:
        return None

    heat_f = 1.0
    if weather.temperature_c is not None and weather.humidity_pct is not None:
        heat_f = _pace_heat_factor(weather.temperature_c, weather.humidity_pct)

    wind_ms = weather.wind_speed_ms or 0.0
    wind_dir = weather.wind_direction_deg or 0.0

    n = min(len(latlng_pts), len(vel))
    _LOOK = 7  # lookahead window (seconds ≈ ~25 m at 3.5 m/s)

    last_bearing = 0.0
    wap: list = []

    for i in range(n):
        v = vel[i]
        if not v or v <= 0.1:
            wap.append(None)
            continue

        # Bearing over a short forward window to reduce GPS noise
        j = min(i + _LOOK, n - 1)
        pt1, pt2 = latlng_pts[i], latlng_pts[j]
        if pt1[0] != pt2[0] or pt1[1] != pt2[1]:
            last_bearing = compute_bearing(pt1[0], pt1[1], pt2[0], pt2[1])

        hw = headwind_ms(wind_ms, wind_dir, last_bearing)
        total_f = heat_f * pace_wind_factor(hw)
        wap.append((1000.0 / v) / total_f if total_f > 0 else None)

    return wap if any(x is not None for x in wap) else None




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
        sport: str | None = None,
        after: str | None = None,
        before: str | None = None,
        search: str | None = None,
        tag: str | None = None,
        limit: int = 50,
        page: int = 1,
    ):
        settings = get_settings()
        athlete_id = settings.athlete_id

        page = max(1, page)
        offset = (page - 1) * limit

        since_dt: datetime | None = None
        before_dt: datetime | None = None
        if after:
            try:
                since_dt = datetime.fromisoformat(after).replace(tzinfo=UTC)
            except ValueError:
                after = None
        if before:
            try:
                before_dt = datetime.fromisoformat(before).replace(tzinfo=UTC)
            except ValueError:
                before = None

        activities = []
        sports = []
        total = 0
        if athlete_id:
            activities = await get_recent_activities(
                athlete_id,
                limit=limit,
                offset=offset,
                sport=sport,
                since=since_dt,
                before=before_dt,
                search=search,
                tag=tag,
            )
            sports = await get_distinct_sports(athlete_id)
            total = await count_activities(
                athlete_id,
                sport=sport,
                since=since_dt,
                before=before_dt,
                search=search,
                tag=tag,
            )

        total_pages = max(1, math.ceil(total / limit)) if total else 1

        # Batch-load weather for all listed activities
        strava_ids = [a.strava_id for a in activities]
        weather_map = await get_weather_for_activities(strava_ids)

        # Batch-load linked workout names
        db_ids = [a.id for a in activities]
        workout_name_map = await get_workout_names_for_activities(db_ids)
        rows = []
        for a in activities:
            row = _activity_row(a)
            w = weather_map.get(a.strava_id)
            if w:
                row["weather"] = _weather_summary(w)
            wname = workout_name_map.get(a.id)
            if wname:
                row["workout_name"] = wname[:20] + "…" if len(wname) > 20 else wname
            rows.append(row)

        return templates.TemplateResponse(
            request,
            "activities/list.html",
            {
                "request": request,
                "activities": rows,
                "sports": sports,
                "selected_sport": sport,
                "selected_after": after,
                "selected_before": before,
                "selected_search": search,
                "selected_tag": tag,
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

        run_sports = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
        is_run = activity.sport_type in run_sports if activity else False

        # Load weather early — True Pace stream must be injected before analytics
        _weather_map = await get_weather_for_activities([strava_id])
        _weather_obj = _weather_map.get(strava_id)

        if streams and _weather_obj:
            wap_s = _compute_wap_stream(streams, _weather_obj)
            if wap_s:
                streams["wap_pace"] = wap_s
            tp_s = _compute_true_pace_stream(streams, _weather_obj)
            if tp_s:
                streams["true_pace"] = tp_s
                # true_velocity (m/s) consumed by analytics engine
                streams["true_velocity"] = [
                    1000.0 / p if p and p > 0 else 0.0 for p in tp_s
                ]

        # Fallback: if true_pace wasn't computed (no weather), derive from velocity_smooth
        # so pace-based insights always have a stream to read.
        if streams and "true_pace" not in streams:
            vel_raw = streams.get("velocity_smooth", [])
            if vel_raw:
                streams["true_pace"] = [
                    round(1000.0 / v, 1) if v and v > 0.1 else None for v in vel_raw
                ]

        if activity and streams:
            analytics = compute_activity_analytics(activity, streams)

        insights = []
        if activity and streams:
            insights = compute_activity_performance_insights(
                activity, streams, get_athlete_settings()
            )

        if activity is None:
            return templates.TemplateResponse(
                request,
                "activities/detail.html",
                {"request": request, "activity": None, "active_page": "activities"},
                status_code=404,
            )

        gear_name = None
        if activity.gear_id:
            athlete = await get_athlete(athlete_id)
            if athlete:
                gear_name = athlete.get_gear_name(activity.gear_id)

        lap_rows = []
        for lap in laps:
            spd = lap.average_speed_ms
            pace_s = round(1000.0 / spd, 1) if spd and spd > 0 and is_run else None
            lap_rows.append(
                {
                    "index": (lap.lap_index or 0) + 1,
                    "name": lap.name or f"Lap {(lap.lap_index or 0) + 1}",
                    "duration": _fmt_seconds(lap.moving_time_s),
                    "distance_km": round(lap.distance_m / 1000, 2)
                    if lap.distance_m
                    else None,
                    "pace": _pace_str(spd, activity.sport_type),
                    "pace_s": pace_s,
                    "avg_hr": round(lap.average_heartrate)
                    if lap.average_heartrate
                    else None,
                    "max_hr": lap.max_heartrate,
                    "avg_watts": round(lap.average_watts)
                    if lap.average_watts
                    else None,
                }
            )

        km_splits = compute_km_splits(streams, activity.sport_type)
        avg_gap = compute_avg_gap(streams, activity.sport_type)

        # Fetch all workouts for the assign selector
        all_workouts = []
        if athlete_id:
            all_workouts = await get_all_workouts(athlete_id)

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
                        return (
                            f"HR {int(lo)}–{int(hi)} bpm" if lo and hi else "HR target"
                        )
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
                    "compliance_pct": round(w.compliance_score * 100)
                    if w.compliance_score is not None
                    else None,
                    "segments": [
                        {
                            **s.to_dict(),
                            "target_label": _seg_target_label(s),
                            "compliance_pct": round(s.compliance_score * 100)
                            if s.compliance_score is not None
                            else None,
                            "score_class": (
                                "green"
                                if s.compliance_score and s.compliance_score >= 0.8
                                else "amber"
                                if s.compliance_score and s.compliance_score >= 0.6
                                else "red"
                                if s.compliance_score is not None
                                else "dim"
                            ),
                        }
                        for s in segs
                    ],
                }

        # Build weather panel (weather already loaded above)
        weather_panel = None
        w = _weather_obj
        if w:
            ws = _weather_summary(w)

            # Compute course bearing for wind component
            course_bearing: float | None = None
            if activity.start_latlng and activity.end_latlng:
                try:
                    s = json.loads(activity.start_latlng)
                    e = json.loads(activity.end_latlng)
                    if len(s) == 2 and len(e) == 2:
                        course_bearing = compute_bearing(s[0], s[1], e[0], e[1])
                except (json.JSONDecodeError, TypeError, IndexError):
                    pass

            wap_factor = 1.0
            if w.temperature_c is not None and w.humidity_pct is not None:
                wap_factor = compute_wap_factor(
                    temp_c=w.temperature_c,
                    rh_pct=w.humidity_pct,
                    wind_speed_ms_val=w.wind_speed_ms or 0.0,
                    wind_dir_deg=w.wind_direction_deg or 0.0,
                    course_bearing=course_bearing,
                )

            wap_fmt = None
            if activity.average_speed_ms and activity.average_speed_ms > 0:
                if is_run:
                    actual_pace_s = 1000.0 / activity.average_speed_ms
                    wap_s = actual_pace_s / wap_factor
                    m, s_rem = divmod(int(wap_s), 60)
                    wap_fmt = f"{m}:{s_rem:02d}/km"
                else:
                    wap_speed_kmh = activity.average_speed_ms * 3.6 * wap_factor
                    wap_fmt = f"{wap_speed_kmh:.1f} km/h"

            # HR heat/humidity impact
            hr_heat_pct: float | None = None
            hr_heat_bpm: int | None = None
            if w.temperature_c is not None and w.humidity_pct is not None:
                vo2_factor = vo2max_heat_factor(w.temperature_c, w.humidity_pct)
                if vo2_factor < 0.99:  # meaningful reduction (>1%)
                    hr_heat_pct = round((1.0 / vo2_factor - 1.0) * 100, 1)
                    if activity.average_heartrate and activity.average_heartrate > 0:
                        hr_heat_bpm = round(
                            activity.average_heartrate * (1.0 / vo2_factor - 1.0)
                        )

            # True Pace summary: distance-weighted mean of true_pace stream.
            # velocity_smooth (m/s at 1 Hz) ≈ metres per sample → use as distance weight
            # so fast sections aren't under-represented (arithmetic mean biases toward slow).
            # Fallback: distance-weighted mean of our computed GAP then apply heat factor.
            true_pace_fmt = None
            tp_stream = streams.get("true_pace", [])
            vel_stream = streams.get("velocity_smooth", [])
            tp_pairs = [
                (p, v)
                for p, v in zip(tp_stream, vel_stream, strict=False)
                if p and p > 0 and v and v > 0.1
            ]
            if tp_pairs:
                paces, vels = zip(*tp_pairs)
                total_w = sum(vels)
                mean_tp = sum(p * v for p, v in zip(paces, vels)) / total_w
                m_tp, s_tp = divmod(int(round(mean_tp)), 60)
                true_pace_fmt = f"{m_tp}:{s_tp:02d}/km"
            else:
                vel_raw = streams.get("velocity_smooth", [])
                grade_raw = streams.get("grade_smooth", [])
                if vel_raw and grade_raw:
                    wt_pairs = [
                        (v * (1 + 0.033 * g), v)
                        for v, g in zip(vel_raw, grade_raw, strict=False)
                        if v and v > 0.1
                    ]
                else:
                    wt_pairs = [(v, v) for v in vel_raw if v and v > 0.1]
                if wt_pairs:
                    gap_speeds, weights = zip(*wt_pairs)
                    total_w = sum(weights)
                    mean_gap_ms = sum(gs * wt for gs, wt in zip(gap_speeds, weights)) / total_w
                    gap_pace_s = 1000.0 / mean_gap_ms
                    heat_f = (
                        _pace_heat_factor(w.temperature_c, w.humidity_pct)
                        if w.temperature_c is not None and w.humidity_pct is not None
                        else 1.0
                    )
                    m_tp, s_tp = divmod(int(round(gap_pace_s / heat_f)), 60)
                    true_pace_fmt = f"{m_tp}:{s_tp:02d}/km"

            weather_panel = {
                **ws,
                "wap_factor": round(wap_factor, 4),
                "wap_factor_pct": round((wap_factor - 1.0) * 100, 1),
                "wap_fmt": wap_fmt,
                "true_pace_fmt": true_pace_fmt,
                "course_bearing": round(course_bearing, 0)
                if course_bearing is not None
                else None,
                "hr_heat_pct": hr_heat_pct,
                "hr_heat_bpm": hr_heat_bpm,
            }

        return templates.TemplateResponse(
            request,
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
                "is_run": is_run,
                "gear_name": gear_name,
                "workout": workout_data,
                "all_workouts": [
                    {"id": w.id, "name": w.name, "sport_type": w.sport_type}
                    for w in all_workouts
                ],
                "weather": weather_panel,
                "insights": insights,
                "lt2_hr": get_athlete_settings().lthr,
                "lt1_hr": round(get_athlete_settings().lthr * 0.92)
                if get_athlete_settings().lthr
                else None,
                "active_page": "activities",
            },
        )

    @router.get("/activities/{strava_id}/analysis", response_class=HTMLResponse)
    async def activity_analysis(request: Request, strava_id: int):
        import bisect

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

        run_sports = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
        is_run = activity.sport_type in run_sports if activity else False

        _weather_map = await get_weather_for_activities([strava_id])
        _weather_obj = _weather_map.get(strava_id)

        if streams and _weather_obj:
            wap_s = _compute_wap_stream(streams, _weather_obj)
            if wap_s:
                streams["wap_pace"] = wap_s
            tp_s = _compute_true_pace_stream(streams, _weather_obj)
            if tp_s:
                streams["true_pace"] = tp_s
                streams["true_velocity"] = [
                    1000.0 / p if p and p > 0 else 0.0 for p in tp_s
                ]

        if streams and "true_pace" not in streams:
            vel_raw = streams.get("velocity_smooth", [])
            if vel_raw:
                streams["true_pace"] = [
                    round(1000.0 / v, 1) if v and v > 0.1 else None for v in vel_raw
                ]

        if activity and streams:
            analytics = compute_activity_analytics(activity, streams)

        if activity is None:
            return templates.TemplateResponse(
                request,
                "activities/detail.html",
                {"request": request, "activity": None, "active_page": "activities"},
                status_code=404,
            )

        # Downsample to 1000 points for better resolution
        raw_n = max((len(v) for v in streams.values()), default=0)
        ds_target = 1000
        ds_step = max(1, raw_n // ds_target) if raw_n > ds_target else 1

        def _downsample_analysis(s: dict, step: int) -> dict:
            return {k: v[::step] for k, v in s.items()}

        streams_ds = _downsample_analysis(streams, ds_step) if streams else {}

        # Gear name
        gear_name = None
        if activity.gear_id:
            athlete = await get_athlete(athlete_id)
            if athlete:
                gear_name = athlete.get_gear_name(activity.gear_id)

        # Lap rows
        lap_rows = []
        for lap in laps:
            spd = lap.average_speed_ms
            pace_s = round(1000.0 / spd, 1) if spd and spd > 0 and is_run else None
            lap_rows.append(
                {
                    "index": (lap.lap_index or 0) + 1,
                    "name": lap.name or f"Lap {(lap.lap_index or 0) + 1}",
                    "duration": _fmt_seconds(lap.moving_time_s),
                    "distance_km": round(lap.distance_m / 1000, 2)
                    if lap.distance_m
                    else None,
                    "pace": _pace_str(spd, activity.sport_type),
                    "pace_s": pace_s,
                    "avg_hr": round(lap.average_heartrate)
                    if lap.average_heartrate
                    else None,
                    "max_hr": lap.max_heartrate,
                    "avg_watts": round(lap.average_watts)
                    if lap.average_watts
                    else None,
                }
            )

        avg_gap = compute_avg_gap(streams, activity.sport_type)

        # Linked workout + segments
        workout_data = None
        segments_for_map: list[dict] = []
        if activity.id:
            linked = await get_workout_for_activity(activity.id)
            if linked:
                w, segs = linked

                def _fmt_pace_local(pace_s_val):
                    if pace_s_val is None:
                        return None
                    m, s = divmod(int(pace_s_val), 60)
                    return f"{m}:{s:02d}"

                def _derive_zone(avg_hr_val, lthr_val):
                    if not avg_hr_val or not lthr_val:
                        return None
                    ratio = avg_hr_val / lthr_val
                    if ratio < 0.81:
                        return 1
                    if ratio < 0.90:
                        return 2
                    if ratio < 0.95:
                        return 3
                    if ratio < 1.00:
                        return 4
                    return 5

                _lthr = get_athlete_settings().lthr
                workout_data = {
                    "id": w.id,
                    "name": w.name,
                    "compliance_score": w.compliance_score,
                    "compliance_pct": round(w.compliance_score * 100)
                    if w.compliance_score is not None
                    else None,
                    "segments": [
                        {
                            **s.to_dict(),
                            "target_label": (
                                f"HR {int(s.target_hr_min_bpm)}–{int(s.target_hr_max_bpm)} bpm"
                                if s.target_focus_type == "hr_range"
                                and s.target_hr_min_bpm
                                and s.target_hr_max_bpm
                                else f"{_fmt_pace_local(s.target_pace_min_s_per_km)}–{_fmt_pace_local(s.target_pace_max_s_per_km)}/km"
                                if s.target_focus_type == "pace_range"
                                else f"Zone {s.target_zone}"
                                if s.target_focus_type == "hr_zone" and s.target_zone
                                else "—"
                            ),
                            "actual_zone": _derive_zone(s.avg_heartrate, _lthr),
                            "compliance_pct": round(s.compliance_score * 100)
                            if s.compliance_score is not None
                            else None,
                        }
                        for s in segs
                    ],
                }
                segments_for_map = [
                    {
                        "name": s.segment_name,
                        "step_type": s.step_type,
                        "start_index": s.start_index,
                        "end_index": s.end_index,
                        "actual_zone": _derive_zone(s.avg_heartrate, _lthr),
                        "avg_heartrate": s.avg_heartrate,
                        "compliance_score": s.compliance_score,
                    }
                    for s in segs
                ]

        # Compute lap stream indices from downsampled distance stream
        dist_ds = streams_ds.get("distance", [])
        laps_json_list = []
        if lap_rows and dist_ds:
            cumulative = 0.0
            for i, lap in enumerate(laps):
                start_dist = cumulative
                end_dist = cumulative + (lap.distance_m or 0)
                start_idx = bisect.bisect_left(dist_ds, start_dist)
                end_idx = min(
                    bisect.bisect_left(dist_ds, end_dist),
                    len(dist_ds) - 1,
                )
                laps_json_list.append(
                    {
                        **lap_rows[i],
                        "start_idx": start_idx,
                        "end_idx": end_idx,
                    }
                )
                cumulative = end_dist
        else:
            laps_json_list = lap_rows

        # Performance metrics
        def _compute_perf_metrics(act, strms, is_run_flag):
            metrics: dict = {}
            vel = strms.get("velocity_smooth", [])
            hr = strms.get("heartrate", [])

            # Aerobic decoupling: compare HR:pace ratio in first vs second half
            if vel and hr and len(vel) > 20 and len(hr) > 20:
                n = min(len(vel), len(hr))
                mid = n // 2
                first_v = [v for v in vel[:mid] if v and v > 0.1]
                first_h = [h for h in hr[:mid] if h and h > 0]
                second_v = [v for v in vel[mid:n] if v and v > 0.1]
                second_h = [h for h in hr[mid:n] if h and h > 0]
                if first_v and first_h and second_v and second_h:
                    ef1 = (sum(first_v) / len(first_v)) / (sum(first_h) / len(first_h))
                    ef2 = (sum(second_v) / len(second_v)) / (
                        sum(second_h) / len(second_h)
                    )
                    if ef1 > 0:
                        metrics["decoupling_pct"] = round((ef2 / ef1 - 1) * 100, 1)

            # Efficiency factor
            avg_hr_act = act.average_heartrate
            if avg_hr_act and avg_hr_act > 0:
                if is_run_flag and act.average_speed_ms:
                    gap_stream = strms.get("grade_adjusted_speed", vel)
                    valid_gap = [v for v in gap_stream if v and v > 0.1]
                    if valid_gap:
                        avg_gap_ms = sum(valid_gap) / len(valid_gap)
                        metrics["ef"] = round(avg_gap_ms / avg_hr_act, 4)
                elif not is_run_flag:
                    np_val = act.weighted_average_watts
                    if np_val and np_val > 0:
                        metrics["ef"] = round(np_val / avg_hr_act, 2)

            # Cycling: NP, IF, VI
            if not is_run_flag:
                np_val = act.weighted_average_watts
                avg_w = act.average_watts
                _settings = get_athlete_settings()
                ftp = _settings.ftp
                if np_val:
                    metrics["np"] = round(np_val)
                if np_val and ftp and ftp > 0:
                    metrics["if_pct"] = round(np_val / ftp * 100, 1)
                if np_val and avg_w and avg_w > 0:
                    metrics["vi"] = round(np_val / avg_w, 3)

            return metrics

        perf_metrics = (
            _compute_perf_metrics(activity, streams, is_run) if streams else {}
        )

        # Power-duration curve (cycling only)
        power_curve_json = None
        if not is_run and streams:
            watts_stream = streams.get("watts", [])
            if watts_stream and len(watts_stream) > 10:
                durations = [5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600]
                dur_labels = [
                    "5s",
                    "10s",
                    "30s",
                    "1m",
                    "2m",
                    "5m",
                    "10m",
                    "20m",
                    "30m",
                    "60m",
                ]
                curve = []
                for dur, label in zip(durations, dur_labels, strict=False):
                    if dur > len(watts_stream):
                        break
                    best = max(
                        sum(watts_stream[i : i + dur]) / dur
                        for i in range(len(watts_stream) - dur + 1)
                    )
                    curve.append(
                        {
                            "duration_label": label,
                            "duration_s": dur,
                            "best_watts": round(best, 1),
                        }
                    )
                if curve:
                    power_curve_json = json.dumps(curve)

        # Weather panel
        weather_panel = None
        _ath_settings = get_athlete_settings()
        w = _weather_obj
        if w:
            weather_panel = _weather_summary(w)

        return templates.TemplateResponse(
            request,
            "activities/analysis.html",
            {
                "request": request,
                "activity": _activity_row(activity),
                "activity_raw": activity,
                "laps": laps_json_list,
                "analytics": analytics,
                "avg_gap": avg_gap,
                "has_polyline": bool(activity.map_summary_polyline),
                "streams_json": json.dumps(streams_ds),
                "has_streams": bool(streams),
                "sport_type": activity.sport_type,
                "is_run": is_run,
                "gear_name": gear_name,
                "workout": workout_data,
                "segments_json": json.dumps(segments_for_map),
                "laps_json": json.dumps(laps_json_list),
                "ds_step": ds_step,
                "performance_metrics": perf_metrics,
                "power_curve_json": power_curve_json or "null",
                "weather": weather_panel,
                "lt2_hr": _ath_settings.lthr,
                "lt1_hr": round(_ath_settings.lthr * 0.92)
                if _ath_settings.lthr
                else None,
                "active_page": "activities",
            },
        )

    return router
