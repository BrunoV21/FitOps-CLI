from __future__ import annotations

import datetime
import json
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.analytics.training_scores import (
    compute_aerobic_score,
    compute_anaerobic_score,
)
from fitops.analytics.weather_pace import weather_row_to_dict
from fitops.config.settings import get_settings
from fitops.dashboard.queries.race import get_all_courses, get_course
from fitops.dashboard.queries.weather import get_weather_for_activities
from fitops.dashboard.queries.workouts import (
    get_linked_activities_for_workout,
    get_workout_with_segments,
)
from fitops.db.models.workout import Workout
from fitops.db.models.workout_segment import WorkoutSegment
from fitops.db.session import get_async_session

router = APIRouter()


def _group_interval_segments(seg_rows: list[dict]) -> list[dict]:
    """Collapse repeated (N/M) interval/recovery segments into expandable group rows.

    Segments named like "30s interval (1/4)" / "1min recovery (1/4)" are bundled
    into a single group dict with type='group'. Everything else gets type='single'.
    """
    result = []
    i = 0
    while i < len(seg_rows):
        seg = seg_rows[i]
        m = re.match(r"^(.+?)\s+\((\d+)/(\d+)\)$", seg.get("segment_name", "") or "")
        if m and int(m.group(2)) == 1:
            total = int(m.group(3))
            # Collect all consecutive segments that share this (*/total) suffix
            group_segs: list[dict] = []
            j = i
            while j < len(seg_rows):
                s = seg_rows[j]
                gm = re.match(r"^.+?\s+\(\d+/(\d+)\)$", s.get("segment_name", "") or "")
                if gm and int(gm.group(1)) == total:
                    group_segs.append(s)
                    j += 1
                else:
                    break

            work_segs = [s for s in group_segs if s.get("step_type") == "interval"]
            rest_segs = [s for s in group_segs if s.get("step_type") == "recovery"]
            first_work = work_segs[0] if work_segs else group_segs[0]
            first_rest = rest_segs[0] if rest_segs else None

            # Duration labels: "30s interval (1/4)" → "30s"
            work_dur_m = re.match(r"^(\S+)", first_work.get("segment_name", "") or "")
            work_dur_label = work_dur_m.group(1) if work_dur_m else "?"
            rest_dur_label = None
            if first_rest:
                rest_dur_m = re.match(
                    r"^(\S+)", first_rest.get("segment_name", "") or ""
                )
                rest_dur_label = rest_dur_m.group(1) if rest_dur_m else None

            # Pace label — works for both simulate (pace dict) and detail (target_label)
            pace_label: str | None = None
            p = first_work.get("pace") or {}
            if p.get("adjusted_min") and p.get("adjusted_max"):
                pace_label = f"{p['adjusted_min']}–{p['adjusted_max']}/km"
            elif p.get("adjusted_min"):
                pace_label = f"{p['adjusted_min']}/km"
            elif (
                first_work.get("target_label") and first_work.get("target_label") != "—"
            ):
                pace_label = first_work["target_label"]

            # Total estimated time (simulate context; None in detail context)
            total_time_s = sum(s.get("est_segment_time_s", 0) or 0 for s in group_segs)
            total_time_fmt: str | None = None
            if total_time_s > 0:
                from fitops.race.course_parser import _fmt_duration as _fmt_dur

                total_time_fmt = _fmt_dur(total_time_s)

            label_parts = [f"{total}×{work_dur_label} intervals"]
            if pace_label:
                label_parts.append(f"@ {pace_label}")
            if rest_dur_label:
                label_parts.append(f"({rest_dur_label} rest)")

            result.append(
                {
                    "type": "group",
                    "rep_count": total,
                    "work_dur_label": work_dur_label,
                    "rest_dur_label": rest_dur_label,
                    "pace_label": pace_label,
                    "label": " ".join(label_parts),
                    "total_time_s": total_time_s,
                    "total_time_fmt": total_time_fmt,
                    "segments": group_segs,
                }
            )
            i = j
        else:
            result.append({"type": "single", **seg})
            i += 1
    return result


def _fmt_pace(pace_s: float | None) -> str | None:
    if pace_s is None:
        return None
    m, s = divmod(int(pace_s), 60)
    return f"{m}:{s:02d}"


def _segment_target_label(seg_dict: dict) -> str:
    """Produce a human-readable target label for a segment."""
    focus = seg_dict.get("target_focus_type") or "none"
    if focus == "hr_range":
        hr = seg_dict.get("target_hr_range") or {}
        lo = hr.get("min_bpm")
        hi = hr.get("max_bpm")
        if lo and hi:
            return f"HR {int(lo)}–{int(hi)} bpm"
        return "HR target"
    if focus == "pace_range":
        pr = seg_dict.get("target_pace_range") or {}
        lo = pr.get("min_formatted")
        hi = pr.get("max_formatted")
        if lo and hi:
            return f"{lo}–{hi}/km"
        return "Pace target"
    if focus == "hr_zone":
        z = seg_dict.get("target_zone")
        return f"Zone {z}" if z else "—"
    return "—"


def register(templates: Jinja2Templates) -> APIRouter:

    @router.get("/workouts/simulate", response_class=HTMLResponse)
    async def workout_simulate_form(request: Request):
        from fitops.workouts.loader import list_workout_files

        workout_files = list_workout_files()
        courses = await get_all_courses()
        return templates.TemplateResponse(
            request,
            "workouts/simulate.html",
            {
                "request": request,
                "workout_files": [
                    {"name": wf.name, "filename": wf.file_name} for wf in workout_files
                ],
                "courses": courses,
                "form": {},
                "error": None,
                "grouped_segments": None,
                "course_info": None,
                "weather_info": None,
                "active_page": "workouts",
            },
        )

    @router.post("/workouts/simulate", response_class=HTMLResponse)
    async def workout_simulate_post(
        request: Request,
        workout_name: str = Form(...),
        course_source: str = Form("course"),  # "course" | "activity"
        course_id: str | None = Form(None),
        activity_id: str | None = Form(None),
        base_pace: str | None = Form(None),
        sim_date: str | None = Form(None),
        sim_hour: str | None = Form(None),
        temp: str | None = Form(None),
        humidity: str | None = Form(None),
        wind: str | None = Form(None),
        wind_dir: str | None = Form(None),
    ):
        from fitops.race.course_parser import (
            _parse_time as _parse_pace_s,
        )
        from fitops.race.course_parser import (
            build_km_segments,
            compute_total_elevation_gain,
            parse_strava_activity,
        )
        from fitops.workouts.json_parser import parse_segments_from_json
        from fitops.workouts.loader import get_workout_file, list_workout_files
        from fitops.workouts.segments import parse_segments_from_body
        from fitops.workouts.simulate import (
            result_to_dict,
            simulate_workout_on_course,
            validate_distance_mismatch,
        )

        workout_files = list_workout_files()
        courses = await get_all_courses()

        form_vals = {
            "workout_name": workout_name,
            "course_source": course_source,
            "course_id": course_id or "",
            "activity_id": activity_id or "",
            "base_pace": base_pace or "",
            "sim_date": sim_date or "",
            "sim_hour": sim_hour or "9",
            "temp": temp or "",
            "humidity": humidity or "",
            "wind": wind or "",
            "wind_dir": wind_dir or "",
        }

        def _render_error(msg: str):
            return templates.TemplateResponse(
                request,
                "workouts/simulate.html",
                {
                    "request": request,
                    "workout_files": [
                        {"name": wf.name, "filename": wf.file_name}
                        for wf in workout_files
                    ],
                    "courses": courses,
                    "form": form_vals,
                    "error": msg,
                    "grouped_segments": None,
                    "course_info": None,
                    "weather_info": None,
                    "active_page": "workouts",
                },
            )

        # --- load workout file ---
        wf = get_workout_file(workout_name)
        if wf is None:
            return _render_error(
                f"Workout {workout_name!r} not found in ~/.fitops/workouts/."
            )

        # wf.meta["workout_meta"] is stored as a raw JSON string by the frontmatter
        # parser (simple key:value parser can't detect JSON objects). Parse it here.
        workout_json_meta = None
        if wf.meta.get("training"):
            workout_json_meta = wf.meta
        elif wf.meta.get("workout_meta"):
            try:
                workout_json_meta = json.loads(wf.meta["workout_meta"])
            except (json.JSONDecodeError, TypeError):
                pass

        if workout_json_meta:
            segments = parse_segments_from_json(workout_json_meta)
        else:
            segments = parse_segments_from_body(wf.body)

        if not segments:
            return _render_error(f"No segments found in workout {workout_name!r}.")

        # --- parse base pace ---
        base_pace_s: float | None = None
        if base_pace and base_pace.strip():
            try:
                base_pace_s = _parse_pace_s(base_pace.strip())
            except (ValueError, IndexError):
                return _render_error(
                    f"Invalid base pace {base_pace!r}. Use MM:SS format."
                )

        # --- load course km-segments ---
        km_segs: list[dict] = []
        course_info: dict = {}
        course_start_lat: float | None = None
        course_start_lon: float | None = None

        if course_source == "course":
            if not course_id or not course_id.strip():
                return _render_error("Please select a course.")
            try:
                cid = int(course_id.strip())
            except ValueError:
                return _render_error(f"Invalid course ID {course_id!r}.")

            course = await get_course(cid)
            if course is None:
                return _render_error(f"Course {cid} not found.")
            km_segs = course.get_km_segments()
            if not km_segs:
                return _render_error("Course has no segments. Re-import the course.")
            course_start_lat = course.start_lat
            course_start_lon = course.start_lon
            course_info = course.to_summary_dict()

        else:  # activity
            if not activity_id or not activity_id.strip():
                return _render_error("Please enter a Strava activity ID.")
            try:
                act_strava_id = int(activity_id.strip())
            except ValueError:
                return _render_error(
                    f"Invalid activity ID {activity_id!r}. Must be a number."
                )

            try:
                async with get_async_session() as session:
                    points = await parse_strava_activity(act_strava_id, session)
                km_segs = build_km_segments(points)
                course_start_lat = points[0]["lat"] if points else None
                course_start_lon = points[0]["lon"] if points else None
                total_m = points[-1]["distance_from_start_m"] if points else 0.0
                elev_gain = compute_total_elevation_gain(points)
                course_info = {
                    "name": f"Activity {act_strava_id}",
                    "activity_strava_id": act_strava_id,
                    "source": "activity_streams",
                    "total_distance_km": round(total_m / 1000, 2),
                    "total_elevation_gain_m": round(elev_gain, 1),
                }
            except ValueError as exc:
                return _render_error(str(exc))

        if not km_segs:
            return _render_error("No course segments available.")

        # --- weather resolution ---
        weather_source = "neutral"
        weather = {
            "temperature_c": 15.0,
            "humidity_pct": 40.0,
            "wind_speed_ms": 0.0,
            "wind_direction_deg": 0.0,
        }

        if temp and humidity:
            try:
                weather = {
                    "temperature_c": float(temp),
                    "humidity_pct": float(humidity),
                    "wind_speed_ms": float(wind) if wind else 0.0,
                    "wind_direction_deg": float(wind_dir) if wind_dir else 0.0,
                }
                weather_source = "manual"
            except ValueError:
                return _render_error(
                    "Invalid weather values — temperature and humidity must be numbers."
                )

        elif (
            sim_date
            and sim_date.strip()
            and course_start_lat is not None
            and course_start_lon is not None
        ):
            from fitops.weather.client import (
                fetch_activity_weather,
                fetch_forecast_weather,
            )

            try:
                parsed_date = datetime.date.fromisoformat(sim_date.strip())
            except ValueError:
                return _render_error(
                    f"Invalid date {sim_date!r}. Use YYYY-MM-DD format."
                )

            hour = int(sim_hour) if sim_hour and sim_hour.isdigit() else 9
            today = datetime.date.today()

            if parsed_date > today:
                fetched = await fetch_forecast_weather(
                    course_start_lat, course_start_lon, sim_date.strip(), hour
                )
                if fetched:
                    weather = {
                        "temperature_c": fetched.get("temperature_c", 15.0),
                        "humidity_pct": fetched.get("humidity_pct", 40.0),
                        "wind_speed_ms": fetched.get("wind_speed_ms", 0.0),
                        "wind_direction_deg": fetched.get("wind_direction_deg", 0.0),
                    }
                    weather_source = "forecast"
            else:
                sim_datetime = datetime.datetime(
                    parsed_date.year,
                    parsed_date.month,
                    parsed_date.day,
                    hour,
                    0,
                    0,
                    tzinfo=datetime.UTC,
                )
                fetched = await fetch_activity_weather(
                    course_start_lat, course_start_lon, sim_datetime
                )
                if fetched:
                    weather = {
                        "temperature_c": fetched.get("temperature_c", 15.0),
                        "humidity_pct": fetched.get("humidity_pct", 40.0),
                        "wind_speed_ms": fetched.get("wind_speed_ms", 0.0),
                        "wind_direction_deg": fetched.get("wind_direction_deg", 0.0),
                    }
                    weather_source = "archive"

        # --- simulate ---
        results = simulate_workout_on_course(segments, km_segs, weather, base_pace_s)
        course_total_m = sum(s["distance_m"] for s in km_segs)
        mismatch_warning = validate_distance_mismatch(results, course_total_m)

        seg_dicts = [result_to_dict(r) for r in results]

        total_est_km = round(sum(r.est_distance_m for r in results) / 1000, 2)
        total_est_s = round(sum(r.est_segment_time_s for r in results), 1)

        from fitops.race.course_parser import _fmt_duration

        return templates.TemplateResponse(
            request,
            "workouts/simulate.html",
            {
                "request": request,
                "workout_files": [
                    {"name": wf.name, "filename": wf.file_name} for wf in workout_files
                ],
                "courses": courses,
                "form": form_vals,
                "error": None,
                "workout_name": wf.name,
                "course_info": course_info,
                "weather_info": {
                    "source": weather_source,
                    "temperature_c": weather["temperature_c"],
                    "humidity_pct": weather["humidity_pct"],
                    "wind_speed_kmh": round(weather["wind_speed_ms"] * 3.6, 1),
                    "wind_direction_deg": weather["wind_direction_deg"],
                },
                "grouped_segments": _group_interval_segments(seg_dicts),
                "total_est_km": total_est_km,
                "total_est_time_fmt": _fmt_duration(total_est_s),
                "mismatch_warning": mismatch_warning,
                "active_page": "workouts",
            },
        )

    @router.get("/workouts", response_class=HTMLResponse)
    async def workouts_list(request: Request):
        from fitops.workouts.loader import list_workout_files

        settings = get_settings()
        athlete_id = settings.athlete_id

        rows = []
        if athlete_id:
            # Auto-import any markdown-only workouts that have no DB record yet
            async with get_async_session() as session:
                existing_result = await session.execute(
                    select(Workout.workout_file_name).where(
                        Workout.athlete_id == athlete_id
                    )
                )
                existing_file_names = {r[0] for r in existing_result.fetchall() if r[0]}

            for wf in list_workout_files():
                if wf.file_name not in existing_file_names:
                    # workout_meta is stored as a JSON string in frontmatter
                    raw_meta = wf.meta.get("workout_meta")
                    meta_line = (
                        raw_meta
                        if isinstance(raw_meta, str)
                        else (json.dumps(raw_meta) if raw_meta else None)
                    )
                    async with get_async_session() as session:
                        session.add(
                            Workout(
                                name=wf.name,
                                sport_type=wf.sport or "run",
                                athlete_id=athlete_id,
                                workout_file_name=wf.file_name,
                                workout_meta=meta_line,
                                status="planned",
                            )
                        )
                        await session.commit()

            async with get_async_session() as session:
                result = await session.execute(
                    select(Workout)
                    .where(Workout.athlete_id == athlete_id)
                    .order_by(Workout.linked_at.desc().nullslast())
                )
                workouts = list(result.scalars().all())

            for w in workouts:
                async with get_async_session() as session:
                    seg_result = await session.execute(
                        select(WorkoutSegment).where(WorkoutSegment.workout_id == w.id)
                    )
                    segments = list(seg_result.scalars().all())

                seg_rows = []
                for s in segments:
                    d = s.to_dict()
                    seg_rows.append(
                        {
                            **d,
                            "target_label": _segment_target_label(d),
                            "compliance_pct": round(s.compliance_score * 100)
                            if s.compliance_score is not None
                            else None,
                        }
                    )
                rows.append(
                    {
                        "id": w.id,
                        "name": w.name,
                        "sport_type": w.sport_type,
                        "status": w.status,
                        "linked_at": w.linked_at.strftime("%d %b %Y")
                        if w.linked_at
                        else "—",
                        "compliance_score": (
                            f"{w.compliance_score * 100:.0f}%"
                            if w.compliance_score is not None
                            else "—"
                        ),
                        "compliance_pct": round(w.compliance_score * 100)
                        if w.compliance_score is not None
                        else None,
                        "segment_count": len(segments),
                        "segments": seg_rows,
                    }
                )

        return templates.TemplateResponse(
            request,
            "workouts/list.html",
            {
                "request": request,
                "workouts": rows,
                "active_page": "workouts",
            },
        )

    @router.get("/workouts/create", response_class=HTMLResponse)
    async def workout_create_form(request: Request):
        return templates.TemplateResponse(
            request,
            "workouts/create.html",
            {
                "request": request,
                "form": {},
                "error": None,
                "created": None,
                "active_page": "workouts",
            },
        )

    @router.post("/workouts/create", response_class=HTMLResponse)
    async def workout_create_post(
        request: Request,
        name: str = Form(...),
        sport: str = Form("run"),
        workout_json_str: str = Form(...),
    ):
        from fitops.workouts.json_parser import (
            generate_markdown_body,
            parse_segments_from_json,
        )
        from fitops.workouts.loader import workouts_dir

        form_vals = {"name": name, "sport": sport, "workout_json_str": workout_json_str}

        def _render_error(msg: str):
            return templates.TemplateResponse(
                request,
                "workouts/create.html",
                {
                    "request": request,
                    "form": form_vals,
                    "error": msg,
                    "created": None,
                    "active_page": "workouts",
                },
            )

        try:
            workout_json = json.loads(workout_json_str)
        except json.JSONDecodeError as e:
            return _render_error(f"Invalid JSON: {e}")

        try:
            segments = parse_segments_from_json(workout_json)
        except Exception as e:
            return _render_error(f"Failed to parse workout: {e}")

        if not segments:
            return _render_error("No segments found in workout JSON.")

        total_min = sum(s.duration_min for s in segments if s.duration_min)
        slug = re.sub(r"[^\w\s-]", "", name.lower())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-") or "workout"

        meta_line = json.dumps(workout_json)
        body = generate_markdown_body(workout_json, name)
        markdown = (
            f"---\n"
            f"name: {name}\n"
            f"sport: {sport}\n"
            f"target_duration_min: {round(total_min)}\n"
            f"tags: []\n"
            f"workout_meta: {meta_line}\n"
            f"---\n\n"
            f"{body}"
        )

        d = workouts_dir()
        file_path = d / f"{slug}.md"
        file_path.write_text(markdown, encoding="utf-8")

        # Also insert a Workout DB record so it appears in lists and assign dropdowns
        settings = get_settings()
        if settings.athlete_id:
            async with get_async_session() as session:
                db_workout = Workout(
                    name=name,
                    sport_type=sport,
                    athlete_id=settings.athlete_id,
                    workout_file_name=file_path.name,
                    workout_meta=meta_line,
                    status="planned",
                )
                session.add(db_workout)
                await session.commit()

        created = {
            "name": name,
            "file_name": file_path.name,
            "sport": sport,
            "total_duration_min": round(total_min, 1),
            "segment_count": len(segments),
            "segments": [
                {
                    "name": s.name,
                    "step_type": s.step_type,
                    "duration_min": round(s.duration_min, 1)
                    if s.duration_min
                    else None,
                }
                for s in segments
            ],
        }
        return templates.TemplateResponse(
            request,
            "workouts/create.html",
            {
                "request": request,
                "form": form_vals,
                "error": None,
                "created": created,
                "active_page": "workouts",
            },
        )

    @router.get("/workouts/{workout_id}", response_class=HTMLResponse)
    async def workout_detail(request: Request, workout_id: int):
        settings = get_settings()
        athlete_id = settings.athlete_id

        if not athlete_id:
            return templates.TemplateResponse(
                request,
                "workouts/detail.html",
                {"request": request, "workout": None, "active_page": "workouts"},
                status_code=404,
            )

        result = await get_workout_with_segments(workout_id, athlete_id)
        if result is None:
            return templates.TemplateResponse(
                request,
                "workouts/detail.html",
                {"request": request, "workout": None, "active_page": "workouts"},
                status_code=404,
            )

        workout, segments = result

        # All linked activities (newest first)
        raw_links = await get_linked_activities_for_workout(workout_id)

        # Batch-load weather for all linked activities
        linked_strava_ids = [act.strava_id for _, act in raw_links]
        weather_map = (
            await get_weather_for_activities(linked_strava_ids)
            if linked_strava_ids
            else {}
        )

        _athlete_settings = get_athlete_settings()

        linked_activities = []
        for lnk, act in raw_links:
            dist_km = round(act.distance_m / 1000, 2) if act.distance_m else None
            dur_s = act.moving_time_s or 0
            if dur_s >= 3600:
                h, rem = divmod(dur_s, 3600)
                m, s = divmod(rem, 60)
                dur_fmt = f"{h}:{m:02d}:{s:02d}"
            else:
                m, s = divmod(dur_s, 60)
                dur_fmt = f"{m}:{s:02d}"
            pace_fmt = None
            if act.distance_m and act.moving_time_s and act.distance_m > 0:
                pace_s = act.moving_time_s / (act.distance_m / 1000)
                pm, ps = divmod(int(pace_s), 60)
                pace_fmt = f"{pm}:{ps:02d}/km"
            comp_pct = (
                round(lnk.compliance_score * 100)
                if lnk.compliance_score is not None
                else None
            )
            aerobic_score = compute_aerobic_score(act, _athlete_settings)
            anaerobic_score = compute_anaerobic_score(act, _athlete_settings)
            w = weather_map.get(act.strava_id)
            weather_info = weather_row_to_dict(w) if w else None
            linked_activities.append(
                {
                    "strava_id": act.strava_id,
                    "name": act.name,
                    "date": act.start_date_local.strftime("%d %b %Y")
                    if act.start_date_local
                    else "—",
                    "sport_type": act.sport_type,
                    "distance_km": dist_km,
                    "duration": dur_fmt,
                    "pace": pace_fmt,
                    "avg_hr": round(act.average_heartrate)
                    if act.average_heartrate
                    else None,
                    "elevation_m": round(act.total_elevation_gain_m)
                    if act.total_elevation_gain_m
                    else None,
                    "compliance_pct": comp_pct,
                    "linked_at": lnk.linked_at.strftime("%d %b %Y")
                    if lnk.linked_at
                    else None,
                    "aerobic_score": aerobic_score,
                    "aerobic_score_int": int(aerobic_score),
                    "anaerobic_score": anaerobic_score,
                    "anaerobic_score_int": int(anaerobic_score),
                    "weather": weather_info,
                }
            )

        # Most recent link for header compliance + physiology
        most_recent_link = raw_links[0][0] if raw_links else None

        # Physiology snapshot — prefer most recent link's snapshot
        physiology = (
            most_recent_link.get_physiology_snapshot()
            if most_recent_link and most_recent_link.physiology_snapshot
            else workout.get_physiology_snapshot()
        ) or {}

        # Build segment rows for template
        seg_rows = []
        for s in segments:
            d = s.to_dict()
            seg_rows.append(
                {
                    **d,
                    "target_label": _segment_target_label(d),
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
            )

        # If no WorkoutSegment records exist yet, build a plain structure preview
        # from the workout_meta JSON so unlinked workouts still show their composition.
        planned_segments = []
        if not segments and workout.workout_meta:
            try:
                from fitops.workouts.json_parser import parse_segments_from_json

                meta_dict = json.loads(workout.workout_meta)
                defs = parse_segments_from_json(meta_dict)
                for d in defs:
                    target_hr_range = None
                    target_pace_range = None
                    if (
                        d.target_hr_min_bpm is not None
                        or d.target_hr_max_bpm is not None
                    ):
                        target_hr_range = {
                            "min_bpm": d.target_hr_min_bpm,
                            "max_bpm": d.target_hr_max_bpm,
                        }
                    if (
                        d.target_pace_min_s_per_km is not None
                        or d.target_pace_max_s_per_km is not None
                    ):
                        target_pace_range = {
                            "min_formatted": _fmt_pace(d.target_pace_min_s_per_km),
                            "max_formatted": _fmt_pace(d.target_pace_max_s_per_km),
                        }
                    seg_dict = {
                        "target_focus_type": d.target_focus_type,
                        "target_hr_range": target_hr_range,
                        "target_pace_range": target_pace_range,
                        "target_zone": d.target_zone,
                    }
                    planned_segments.append(
                        {
                            "name": d.name,
                            "step_type": d.step_type,
                            "duration_min": round(d.duration_min, 1)
                            if d.duration_min
                            else None,
                            "target_label": _segment_target_label(seg_dict),
                        }
                    )
            except Exception:
                pass

        # Overall compliance: most recent link's score, fallback to workout row
        best_compliance = (
            most_recent_link.compliance_score
            if most_recent_link and most_recent_link.compliance_score is not None
            else workout.compliance_score
        )
        overall_pct = (
            round(best_compliance * 100) if best_compliance is not None else None
        )

        return templates.TemplateResponse(
            request,
            "workouts/detail.html",
            {
                "request": request,
                "planned_segments": planned_segments,
                "workout": {
                    "id": workout.id,
                    "name": workout.name,
                    "sport_type": workout.sport_type,
                    "status": workout.status,
                    "linked_at": linked_activities[0]["linked_at"]
                    if linked_activities
                    else None,
                    "compliance_score": best_compliance,
                    "compliance_pct": overall_pct,
                    "score_class": (
                        "green"
                        if overall_pct and overall_pct >= 80
                        else "amber"
                        if overall_pct and overall_pct >= 60
                        else "red"
                        if overall_pct is not None
                        else "dim"
                    ),
                    "notes": workout.notes,
                },
                "linked_activities": linked_activities,
                "physiology": physiology,
                "grouped_segments": _group_interval_segments(seg_rows),
                "active_page": "workouts",
            },
        )

    return router
