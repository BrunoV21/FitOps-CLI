from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from fitops.analytics.activity_performance_insights import (
    compute_activity_performance_insights,
)
from fitops.analytics.activity_splits import compute_avg_gap, compute_km_splits
from fitops.analytics.activity_zones import compute_activity_analytics
from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.analytics.race_results import (
    delete_calibrated_snapshot,
    is_supported_race_activity,
    parse_race_time_to_seconds,
    persist_calibrated_snapshot,
    summarize_race_result,
)
from fitops.analytics.training_scores import (
    aerobic_label,
    anaerobic_label,
    compute_aerobic_score,
    compute_anaerobic_score,
)
from fitops.analytics.weather_pace import (
    compute_bearing,
    compute_true_pace_stream,
    compute_wap_factor,
    compute_wap_stream_points,
    compute_weather_panel,
    weather_row_to_dict,
)
from fitops.config.settings import get_settings
from fitops.dashboard.queries.activities import (
    count_activities,
    get_activity_calibration,
    get_activity_detail,
    get_activity_laps,
    get_activity_streams,
    get_distinct_sports,
    get_distinct_workout_names,
    get_recent_activities,
)
from fitops.dashboard.queries.athlete import get_athlete
from fitops.dashboard.queries.race import get_race_plan_for_activity
from fitops.dashboard.queries.weather import get_weather_for_activities
from fitops.dashboard.queries.workouts import (
    get_all_workouts,
    get_workout_for_activity,
    get_workout_names_for_activities,
)
from fitops.db.models.activity import Activity
from fitops.db.session import get_async_session

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
    aerobic_score = (
        a.aerobic_score
        if a.aerobic_score is not None
        else compute_aerobic_score(a, _settings)
    )
    anaerobic_score = (
        a.anaerobic_score
        if a.anaerobic_score is not None
        else compute_anaerobic_score(a, _settings)
    )

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
        "avg_watts": round(a.average_watts)
        if a.average_watts
        else (
            round(a.est_power_avg_w) if getattr(a, "est_power_avg_w", None) else None
        ),
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
        "est_power_avg_w": round(a.est_power_avg_w)
        if getattr(a, "est_power_avg_w", None)
        else None,
        "est_power_max_w": round(a.est_power_max_w)
        if getattr(a, "est_power_max_w", None)
        else None,
        "est_power_np_w": round(a.est_power_np_w)
        if getattr(a, "est_power_np_w", None)
        else None,
        "est_kcal_model": getattr(a, "est_kcal_model", None),
        "est_power_source": getattr(a, "est_power_source", None),
    }


def _activity_with_overrides(activity, overrides: dict | None):
    if not overrides:
        return activity
    data = {c.name: getattr(activity, c.name) for c in activity.__table__.columns}
    _metadata_keys = {"description", "name", "stamped_at"}
    data.update({k: v for k, v in overrides.items() if k not in _metadata_keys})
    for key in (
        "start_date",
        "start_date_local",
        "created_at",
        "updated_at",
        "stamped_at",
    ):
        value = data.get(key)
        if isinstance(value, str):
            try:
                data[key] = datetime.fromisoformat(value)
            except ValueError:
                pass
    data["is_race"] = getattr(activity, "workout_type", None) == 1
    return SimpleNamespace(**data)


def _weather_summary(w) -> dict:
    """Convert an ActivityWeather row into a template-ready dict."""
    return weather_row_to_dict(w)


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
        workout_tags = []
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
            workout_tags = await get_distinct_workout_names(athlete_id)
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
                "workout_tags": workout_tags,
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
        calibration = await get_activity_calibration(activity.id) if activity else None
        if calibration is not None:
            streams = calibration.streams

        activity_view = _activity_with_overrides(
            activity, calibration.summary if calibration is not None else None
        )

        run_sports = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
        is_run = activity_view.sport_type in run_sports if activity_view else False

        # Load weather early — True Pace stream must be injected before analytics
        _weather_map = await get_weather_for_activities([strava_id])
        _weather_obj = _weather_map.get(strava_id)

        if streams and _weather_obj:
            wap_s = compute_wap_stream_points(streams, _weather_obj)
            if wap_s:
                streams["wap_pace"] = wap_s
            tp_s = compute_true_pace_stream(streams, _weather_obj)
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

        # Running power — compute + persist when streams are available
        if (
            activity
            and streams
            and activity.est_power_avg_w is None
            and calibration is None
        ):
            from fitops.analytics.athlete_settings import (
                get_athlete_settings as _get_athlete_settings_pw,
            )
            from fitops.analytics.running_power import persist_power_for_activity
            from fitops.db.models.activity import Activity as _Activity
            from fitops.db.session import get_async_session

            _pw_settings = _get_athlete_settings_pw()
            _weight_kg = _pw_settings.weight_kg
            if _weight_kg:
                async with get_async_session() as _pw_session:
                    from sqlalchemy import select as _select

                    _pw_result = await _pw_session.execute(
                        _select(_Activity).where(_Activity.id == activity.id)
                    )
                    _pw_row = _pw_result.scalar_one_or_none()
                    if _pw_row:
                        await persist_power_for_activity(
                            _pw_session, _pw_row.id, _pw_row, streams, _weight_kg
                        )
                        activity.est_power_avg_w = _pw_row.est_power_avg_w
                        activity.est_power_max_w = _pw_row.est_power_max_w
                        activity.est_power_np_w = _pw_row.est_power_np_w
                        activity.est_kcal_model = _pw_row.est_kcal_model
                        activity.est_power_source = _pw_row.est_power_source

        if activity_view and streams:
            analytics = compute_activity_analytics(activity_view, streams)

        insights = []
        if activity_view and streams:
            insights = compute_activity_performance_insights(
                activity_view, streams, get_athlete_settings()
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
                    "pace": _pace_str(spd, activity_view.sport_type),
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

        race_result = (
            calibration.race_result
            if calibration is not None
            else summarize_race_result(activity, streams)
        )
        km_splits = compute_km_splits(
            streams, activity_view.sport_type, true_pace=streams.get("true_pace")
        )
        avg_gap = compute_avg_gap(streams, activity_view.sport_type)

        # Overall true pace — comes from compute_weather_panel below
        true_pace_fmt = None

        # Fetch all workouts for the assign selector
        all_workouts = []
        if athlete_id:
            all_workouts = await get_all_workouts(athlete_id)

        # Fetch linked workout + segments if any
        workout_data = None
        if activity.id:
            linked = await get_workout_for_activity(activity.id)
            if linked:
                w, lnk, segs = linked

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
                    "compliance_score": lnk.compliance_score,
                    "compliance_pct": round(lnk.compliance_score * 100)
                    if lnk.compliance_score is not None
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

        # Look up linked race plan (if this activity is a planned race)
        linked_race_plan: dict | None = None
        if activity.id:
            rp = await get_race_plan_for_activity(activity.id)
            if rp is not None:
                from fitops.dashboard.queries.race import get_course

                rp_course = await get_course(rp.course_id)
                linked_race_plan = {
                    **rp.to_summary_dict(),
                    "course_name": rp_course.name if rp_course else None,
                }

        # Build weather panel (shared computation with stamp)
        # If derived values not yet persisted, lazy-compute and store them
        weather_panel = None
        w = _weather_obj
        if w and w.wap_factor is None:
            # Lazy-persist derived values on first read
            try:
                from fitops.analytics.weather_pace import persist_derived_weather
                async with get_async_session() as _wp_session:
                    from sqlalchemy import select as _sel
                    _wp_result = await _wp_session.execute(
                        _sel(ActivityWeather).where(ActivityWeather.activity_id == strava_id)
                    )
                    _wp_row = _wp_result.scalar_one_or_none()
                    if _wp_row:
                        await persist_derived_weather(
                            _wp_session, _wp_row, activity, streams or None
                        )
                        # Refresh the weather object
                        w = _wp_row
                        _weather_map[strava_id] = w
            except Exception:
                pass

        if w:
            weather_panel = compute_weather_panel(
                w,
                streams,
                average_speed_ms=activity_view.average_speed_ms,
                is_run=is_run,
                start_latlng=activity.start_latlng,
                end_latlng=activity.end_latlng,
                average_heartrate=activity_view.average_heartrate,
            )
            # Inject the true_pace stream back into streams for charts/analysis
            tp_s = weather_panel.pop("true_pace_stream", None)
            if tp_s:
                streams["true_pace"] = tp_s
            # Also update the standalone true_pace_fmt variable for the template
            true_pace_fmt = weather_panel.get("true_pace_fmt")

        return templates.TemplateResponse(
            request,
            "activities/detail.html",
            {
                "request": request,
                "activity": _activity_row(activity_view),
                "activity_raw": activity,
                "race_result": race_result,
                "laps": lap_rows,
                "km_splits": km_splits,
                "analytics": analytics,
                "avg_gap": avg_gap,
                "true_pace_fmt": true_pace_fmt,
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
                "linked_race_plan": linked_race_plan,
                "weather": weather_panel,
                "insights": insights,
                "lt2_hr": get_athlete_settings().lthr,
                "lt1_hr": round(get_athlete_settings().lthr * 0.92)
                if get_athlete_settings().lthr
                else None,
                "has_write_scope": settings.has_write_scope,
                "race_result_notice": request.query_params.get("race_result_notice"),
                "race_result_error": request.query_params.get("race_result_error"),
                "active_page": "activities",
            },
        )

    @router.post("/activities/{strava_id}/race-result")
    async def activity_race_result_post(
        request: Request,
        strava_id: int,
        chip_time: str | None = Form(None),
        race_distance_km: str | None = Form(None),
    ):
        parsed_chip_time_s = None
        parsed_race_distance_m = None

        chip_time_raw = (chip_time or "").strip()
        race_distance_raw = (race_distance_km or "").strip()

        if chip_time_raw:
            try:
                parsed_chip_time_s = parse_race_time_to_seconds(chip_time_raw)
            except ValueError as exc:
                return RedirectResponse(
                    url=f"/activities/{strava_id}?race_result_error={str(exc)}",
                    status_code=303,
                )

        if race_distance_raw:
            try:
                distance_km = float(race_distance_raw)
            except ValueError:
                return RedirectResponse(
                    url=f"/activities/{strava_id}?race_result_error=Race distance must be numeric.",
                    status_code=303,
                )
            if distance_km <= 0:
                return RedirectResponse(
                    url=f"/activities/{strava_id}?race_result_error=Race distance must be greater than zero.",
                    status_code=303,
                )
            parsed_race_distance_m = distance_km * 1000.0

        async with get_async_session() as session:
            result = await session.execute(
                select(Activity).where(Activity.strava_id == strava_id)
            )
            activity = result.scalar_one_or_none()
            if activity is None:
                return RedirectResponse(
                    url="/activities?race_result_error=Activity not found.",
                    status_code=303,
                )
            if not is_supported_race_activity(activity):
                return RedirectResponse(
                    url=(
                        f"/activities/{strava_id}"
                        "?race_result_error=Race result overrides are only supported for running race activities."
                    ),
                    status_code=303,
                )
            activity.chip_time_s = parsed_chip_time_s
            activity.race_distance_m = parsed_race_distance_m
            streams = (
                await get_activity_streams(activity.id)
                if activity.streams_fetched
                else {}
            )
            if activity.chip_time_s or activity.race_distance_m:
                await persist_calibrated_snapshot(session, activity, streams)
            else:
                await delete_calibrated_snapshot(session, activity.id)

        return RedirectResponse(
            url=f"/activities/{strava_id}?race_result_notice=Official race result saved.",
            status_code=303,
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
        calibration = await get_activity_calibration(activity.id) if activity else None
        if calibration is not None:
            streams = calibration.streams
        activity_view = _activity_with_overrides(
            activity, calibration.summary if calibration is not None else None
        )

        run_sports = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
        is_run = activity_view.sport_type in run_sports if activity_view else False

        _weather_map = await get_weather_for_activities([strava_id])
        _weather_obj = _weather_map.get(strava_id)

        if streams and _weather_obj:
            wap_s = compute_wap_stream_points(streams, _weather_obj)
            if wap_s:
                streams["wap_pace"] = wap_s
            tp_s = compute_true_pace_stream(streams, _weather_obj)
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

        if activity_view and streams:
            analytics = compute_activity_analytics(activity_view, streams)

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
                    "pace": _pace_str(spd, activity_view.sport_type),
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

        avg_gap = compute_avg_gap(streams, activity_view.sport_type)

        # Linked workout + segments
        workout_data = None
        segments_for_map: list[dict] = []
        if activity.id:
            linked = await get_workout_for_activity(activity.id)
            if linked:
                w, lnk, segs = linked

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
                    "compliance_score": lnk.compliance_score,
                    "compliance_pct": round(lnk.compliance_score * 100)
                    if lnk.compliance_score is not None
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
                "activity": _activity_row(activity_view),
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

    @router.post("/api/activities/{strava_id}/stamp")
    async def stamp_activity_api(request: Request, strava_id: int):
        from fastapi.responses import JSONResponse
        from sqlalchemy import select

        from fitops.analytics.stamp import stamp_activity
        from fitops.config.settings import get_settings as _get_settings
        from fitops.db.models.activity import Activity as _Activity
        from fitops.db.session import get_async_session
        from fitops.strava.client import StravaClient

        cfg = _get_settings()
        if not cfg.is_authenticated:
            return JSONResponse({"error": "not authenticated"}, status_code=401)
        if not cfg.has_write_scope:
            return JSONResponse(
                {
                    "error": "activity:write scope required — run: fitops auth login --force"
                },
                status_code=403,
            )

        body = (
            await request.json()
            if request.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        body.get("force", False) if isinstance(body, dict) else False

        client = StravaClient()
        async with get_async_session() as session:
            result = await session.execute(
                select(_Activity).where(_Activity.strava_id == strava_id)
            )
            activity = result.scalar_one_or_none()
            if activity is None:
                return JSONResponse({"error": "activity not found"}, status_code=404)
            try:
                await stamp_activity(client, session, activity, fetch_fresh_desc=True)
            except Exception as exc:
                return JSONResponse({"error": str(exc)}, status_code=500)

        return JSONResponse({"ok": True, "strava_id": strava_id})

    @router.post("/api/activities/stamp-all")
    async def stamp_all_activities_api(request: Request):
        from fastapi.responses import JSONResponse
        from sqlalchemy import select

        from fitops.analytics.stamp import stamp_activity
        from fitops.config.settings import get_settings as _get_settings
        from fitops.db.models.activity import Activity as _Activity
        from fitops.db.session import get_async_session
        from fitops.strava.client import StravaClient

        cfg = _get_settings()
        if not cfg.is_authenticated:
            return JSONResponse({"error": "not authenticated"}, status_code=401)
        if not cfg.has_write_scope:
            return JSONResponse(
                {
                    "error": "activity:write scope required — run: fitops auth login --force"
                },
                status_code=403,
            )

        client = StravaClient()
        stamped, skipped, failed = [], [], []

        async with get_async_session() as session:
            result = await session.execute(select(_Activity))
            activities = result.scalars().all()
            for activity in activities:
                try:
                    await stamp_activity(
                        client, session, activity, fetch_fresh_desc=True
                    )
                    stamped.append(activity.strava_id)
                except Exception:
                    failed.append(activity.strava_id)

        return JSONResponse(
            {"ok": True, "stamped": stamped, "skipped": skipped, "failed": failed}
        )

    return router
