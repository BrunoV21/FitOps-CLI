from __future__ import annotations

import datetime
import json
import os
import tempfile

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from fitops.analytics.weather_pace import headwind_ms
from fitops.dashboard.queries.race import (
    delete_course,
    delete_race_plan,
    get_all_courses,
    get_all_race_plans,
    get_course,
    get_plans_for_course,
    get_race_plan,
    save_course,
    save_race_plan,
    update_race_plan,
)
from fitops.db.migrations import create_all_tables
from fitops.race.course_parser import (
    build_km_segments,
    compute_total_elevation_gain,
    parse_gpx,
    parse_mapmyrun_url,
    parse_strava_url,
    parse_tcx,
)
from fitops.race.simulation import simulate_pacer_mode, simulate_splits

router = APIRouter()


def _sample_route_coords(
    course_points: list[dict], max_points: int = 400
) -> list[list[float]]:
    """Return [[lat, lon], ...] downsampled to at most max_points."""
    pts = [[p["lat"], p["lon"]] for p in course_points if "lat" in p and "lon" in p]
    if len(pts) <= max_points:
        return pts
    step = len(pts) / max_points
    return [pts[round(i * step)] for i in range(max_points)]


def _build_km_segment_coords(
    course, max_pts_per_seg: int = 60
) -> list[list[list[float]]]:
    """Return per-km lists of [[lat, lon], ...] for coloured map polylines.

    Index 0 → km 1 (0–1 km), index 1 → km 2, etc.
    Points without lat/lon are silently skipped.
    """
    points = course.get_course_points()
    segments = course.get_km_segments()
    if not points or not segments:
        return []

    result: list[list[list[float]]] = []
    for seg in segments:
        km = seg["km"]
        start_m = (km - 1) * 1000.0
        end_m = km * 1000.0
        seg_pts = [
            [p["lat"], p["lon"]]
            for p in points
            if "lat" in p
            and "lon" in p
            and p["distance_from_start_m"] >= start_m
            and p["distance_from_start_m"] <= end_m
        ]
        if not seg_pts:
            result.append([])
            continue
        if len(seg_pts) > max_pts_per_seg:
            step = len(seg_pts) / max_pts_per_seg
            seg_pts = [seg_pts[round(i * step)] for i in range(max_pts_per_seg)]
        result.append(seg_pts)
    return result


def _parse_finish_time(s: str) -> tuple[float, str]:
    """
    Parse a race finish time to (total_seconds, normalized_hh_mm_ss).

    Accepts: HH:MM:SS, H:MM (→ H:MM:00), or MM:SS (when first part > 23, e.g. '45:00' = 45 min race).
    Always returns the canonical HH:MM:SS string so the form can echo it back.
    """
    parts = s.strip().split(":")
    if len(parts) == 3:
        h, m, sec = int(parts[0]), int(parts[1]), float(parts[2])
        total = h * 3600 + m * 60 + sec
    elif len(parts) == 2:
        a, b = int(parts[0]), int(parts[1])
        if a <= 23:
            # H:MM  e.g. "1:29" → 1 h 29 m
            total = a * 3600 + b * 60
        else:
            # MM:SS for sub-hour races e.g. "45:00" → 45 min
            total = a * 60 + b
    else:
        raise ValueError(f"Cannot parse time: {s!r}. Use HH:MM:SS or H:MM.")
    h_out = int(total) // 3600
    m_out = (int(total) % 3600) // 60
    s_out = int(total) % 60
    return total, f"{h_out}:{m_out:02d}:{s_out:02d}"


def _parse_pace(s: str) -> float:
    """Parse pace MM:SS per km to total seconds. Used for pacer pace field."""
    parts = s.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    raise ValueError(f"Cannot parse pace: {s!r}. Use MM:SS (e.g. 5:00).")


def _wind_label(bearing_deg: float, wind_speed_ms: float, wind_dir_deg: float) -> dict:
    """
    Return a human-readable wind label and speed for a segment.
    Uses the headwind component (positive = into face, negative = from behind).
    Speed is converted to km/h.
    """
    if wind_speed_ms < 0.3:
        return {"label": "Calm", "speed_kmh": 0.0, "css_class": "wind-calm"}

    hw = headwind_ms(wind_speed_ms, wind_dir_deg, bearing_deg)
    speed_kmh = round(wind_speed_ms * 3.6, 1)
    # hw / wind_speed_ms gives cos of angle between runner and wind
    ratio = hw / wind_speed_ms  # -1 = pure tailwind, +1 = pure headwind

    if ratio >= 0.64:  # angle < ~50°
        label = "Headwind"
        css_class = "wind-head"
    elif ratio >= 0.17:  # angle < ~80°
        label = "Head-cross"
        css_class = "wind-headcross"
    elif ratio >= -0.17:  # angle ±80°
        label = "Crosswind"
        css_class = "wind-cross"
    elif ratio >= -0.64:  # angle < ~130°
        label = "Tail-cross"
        css_class = "wind-tailcross"
    else:
        label = "Tailwind"
        css_class = "wind-tail"

    return {"label": label, "speed_kmh": speed_kmh, "css_class": css_class}


def _build_elevation_profile(course) -> list[dict]:
    """
    O(n+m) single-pass pointer scan.
    Returns list of {km, elevation_m} with one entry per km marker.
    """
    points = course.get_course_points()
    segments = course.get_km_segments()
    if not points:
        return []

    elevation_profile = []
    ptr = 0
    n_pts = len(points)
    for km_idx in range(len(segments) + 1):
        target_dist = km_idx * 1000.0
        # Advance ptr while the next point is closer to target_dist
        while ptr + 1 < n_pts and abs(
            points[ptr + 1]["distance_from_start_m"] - target_dist
        ) <= abs(points[ptr]["distance_from_start_m"] - target_dist):
            ptr += 1
        elevation_profile.append(
            {"km": km_idx, "elevation_m": round(points[ptr]["elevation_m"], 1)}
        )
    return elevation_profile


def register(templates: Jinja2Templates) -> APIRouter:

    @router.get("/race", response_class=HTMLResponse)
    async def race_index(request: Request):
        await create_all_tables()
        courses = await get_all_courses()
        return templates.TemplateResponse(
            request,
            "race/index.html",
            {
                "request": request,
                "courses": courses,
                "active_page": "race",
            },
        )

    @router.get("/race/import", response_class=HTMLResponse)
    async def race_import_form(request: Request):
        return templates.TemplateResponse(
            request,
            "race/import.html",
            {"request": request, "error": None, "active_page": "race"},
        )

    @router.post("/race/import", response_class=HTMLResponse)
    async def race_import_post(
        request: Request,
        name: str = Form(...),
        source_type: str = Form(...),  # "file" | "url"
        url: str | None = Form(None),
        file: UploadFile | None = File(None),
    ):
        await create_all_tables()
        error: str | None = None
        points = []

        try:
            if source_type == "mapmyrun":
                if not url or not url.strip():
                    raise ValueError("Please enter a MapMyRun URL.")
                points = await parse_mapmyrun_url(url.strip())

            elif source_type == "strava":
                if not url or not url.strip():
                    raise ValueError("Please enter a Strava activity URL.")
                points = await parse_strava_url(url.strip())

            elif source_type == "file":
                if file is None or not file.filename:
                    raise ValueError("Please select a GPX or TCX file.")
                content = await file.read()
                suffix = os.path.splitext(file.filename)[1].lower()
                if suffix not in (".gpx", ".tcx"):
                    raise ValueError(
                        f"Unsupported file type '{suffix}'. Use .gpx or .tcx."
                    )
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                try:
                    if suffix == ".gpx":
                        points = parse_gpx(tmp_path)
                    else:
                        points = parse_tcx(tmp_path)
                finally:
                    os.unlink(tmp_path)
            else:
                raise ValueError("Unknown source type.")

            if not points:
                raise ValueError("No course points found in source.")

            segments = build_km_segments(points)
            total_dist = points[-1]["distance_from_start_m"]
            elev_gain = compute_total_elevation_gain(points)
            file_fmt = (
                "gpx"
                if source_type == "file" and file and file.filename.endswith(".gpx")
                else ("tcx" if source_type == "file" else None)
            )
            src_ref = url.strip() if source_type in ("mapmyrun", "strava") else None
            src_label = source_type  # "file" | "mapmyrun" | "strava"

            result = await save_course(
                name=name.strip(),
                source=src_label,
                source_ref=src_ref,
                file_format=file_fmt,
                course_points=points,
                km_segments=segments,
                total_distance_m=total_dist,
                total_elevation_gain_m=elev_gain,
            )
            return RedirectResponse(url=f"/race/{result['id']}", status_code=303)

        except Exception as exc:
            error = str(exc)

        return templates.TemplateResponse(
            request,
            "race/import.html",
            {"request": request, "error": error, "active_page": "race"},
        )

    @router.post("/race/{course_id}/delete", response_class=HTMLResponse)
    async def race_delete(request: Request, course_id: int):
        await create_all_tables()
        await delete_course(course_id)
        return RedirectResponse(url="/race", status_code=303)

    @router.get("/race/{course_id}", response_class=HTMLResponse)
    async def race_course(request: Request, course_id: int):
        await create_all_tables()
        course = await get_course(course_id)
        if course is None:
            return HTMLResponse(
                content="<h1>404 — Course not found</h1>", status_code=404
            )

        segments = course.get_km_segments()
        elevation_profile = _build_elevation_profile(course)
        summary = course.to_summary_dict()

        route_coords = _sample_route_coords(course.get_course_points())
        return templates.TemplateResponse(
            request,
            "race/course.html",
            {
                "request": request,
                "course": summary,
                "segments": segments,
                "elevation_profile_json": json.dumps(elevation_profile),
                "route_coords_json": json.dumps(route_coords),
                "active_page": "race",
            },
        )

    @router.get("/race/{course_id}/simulate", response_class=HTMLResponse)
    async def race_simulate_form(request: Request, course_id: int):
        await create_all_tables()
        course = await get_course(course_id)
        if course is None:
            return HTMLResponse(
                content="<h1>404 — Course not found</h1>", status_code=404
            )

        summary = course.to_summary_dict()
        course_points = course.get_course_points()
        route_coords = _sample_route_coords(course_points)
        segment_coords = _build_km_segment_coords(course)
        existing_plans = await get_plans_for_course(course_id)
        return templates.TemplateResponse(
            request,
            "race/simulate.html",
            {
                "request": request,
                "course": summary,
                "splits": None,
                "pacer_data": None,
                "error": None,
                "form": {},
                "weather_info": None,
                "route_coords_json": json.dumps(route_coords),
                "segment_coords_json": json.dumps(segment_coords),
                "existing_plans": existing_plans,
                "active_page": "race",
            },
        )

    @router.post("/race/{course_id}/simulate", response_class=HTMLResponse)
    async def race_simulate_post(
        request: Request,
        course_id: int,
        target_time: str | None = Form(None),
        strategy: str | None = Form(None),
        pacer_pace: str | None = Form(None),
        drop_at_km: str | None = Form(None),
        race_date: str | None = Form(None),
        race_hour: str | None = Form(None),
        temp: str | None = Form(None),
        humidity: str | None = Form(None),
        wind: str | None = Form(None),
        wind_dir: str | None = Form(None),
    ):
        await create_all_tables()
        course = await get_course(course_id)
        if course is None:
            return HTMLResponse(
                content="<h1>404 — Course not found</h1>", status_code=404
            )

        summary = course.to_summary_dict()
        segments = course.get_km_segments()

        # Parse target time and normalize back to HH:MM:SS for display
        try:
            target_total_s, target_time_normalized = _parse_finish_time(
                target_time or ""
            )
        except (ValueError, AttributeError):
            normalized_placeholder = target_time or ""
            target_time_normalized = normalized_placeholder
            target_total_s = 0.0

        form_vals = {
            "target_time": target_time_normalized,
            "strategy": strategy or "even",
            "pacer_pace": pacer_pace or "",
            "drop_at_km": drop_at_km or "",
            "race_date": race_date or "",
            "race_hour": race_hour or "9",
            "temp": temp or "",
            "humidity": humidity or "",
            "wind": wind or "",
            "wind_dir": wind_dir or "",
        }

        course_points = course.get_course_points()
        route_coords = _sample_route_coords(course_points)
        route_coords_json = json.dumps(route_coords)
        segment_coords = _build_km_segment_coords(course)
        segment_coords_json = json.dumps(segment_coords)

        existing_plans = await get_plans_for_course(course_id)

        def _render_error(msg: str, weather_info: dict | None = None):
            return templates.TemplateResponse(
                request,
                "race/simulate.html",
                {
                    "request": request,
                    "course": summary,
                    "splits": None,
                    "pacer_data": None,
                    "error": msg,
                    "form": form_vals,
                    "weather_info": weather_info,
                    "route_coords_json": route_coords_json,
                    "segment_coords_json": segment_coords_json,
                    "existing_plans": existing_plans,
                    "active_page": "race",
                },
            )

        if target_total_s <= 0:
            return _render_error(
                "Invalid target time. Use H:MM or HH:MM:SS (e.g. 1:45:00)."
            )

        strat = (strategy or "even").lower()
        if strat not in ("even", "negative", "positive"):
            strat = "even"

        # Weather resolution priority:
        # 1. Manual temp+humidity override
        # 2. Auto-fetch by race date (forecast if future, archive if past)
        # 3. Neutral defaults
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
                    "Invalid weather values. Temperature and humidity must be numbers."
                )

        elif (
            race_date and course.start_lat is not None and course.start_lon is not None
        ):
            from fitops.weather.client import (
                fetch_activity_weather,
                fetch_forecast_weather,
            )

            try:
                parsed_date = datetime.date.fromisoformat(race_date)
            except ValueError:
                return _render_error(
                    f"Invalid race date: {race_date!r}. Use YYYY-MM-DD format."
                )

            hour = int(race_hour) if race_hour and race_hour.isdigit() else 9
            today = datetime.date.today()

            if parsed_date > today:
                fetched = await fetch_forecast_weather(
                    course.start_lat, course.start_lon, race_date, hour
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
                race_datetime = datetime.datetime(
                    parsed_date.year,
                    parsed_date.month,
                    parsed_date.day,
                    hour,
                    0,
                    0,
                    tzinfo=datetime.UTC,
                )
                fetched = await fetch_activity_weather(
                    course.start_lat, course.start_lon, race_datetime
                )
                if fetched:
                    weather = {
                        "temperature_c": fetched.get("temperature_c", 15.0),
                        "humidity_pct": fetched.get("humidity_pct", 40.0),
                        "wind_speed_ms": fetched.get("wind_speed_ms", 0.0),
                        "wind_direction_deg": fetched.get("wind_direction_deg", 0.0),
                    }
                    weather_source = "archive"

        splits = None
        pacer_data = None

        # Pacer mode: both pacer_pace and drop_at_km provided
        use_pacer = bool(pacer_pace and drop_at_km)
        try:
            if use_pacer:
                pacer_pace_s = _parse_pace(pacer_pace)
                drop_km = float(drop_at_km)
                pacer_data = simulate_pacer_mode(
                    segments, target_total_s, pacer_pace_s, drop_km, weather
                )
                # Combine sit and push splits for the chart
                sit_pace_s = pacer_pace_s
                sit_splits = [
                    {
                        "km": seg["km"],
                        "distance_m": seg["distance_m"],
                        "elevation_gain_m": seg.get("elevation_gain_m", 0),
                        "grade_pct": round(seg.get("grade", 0) * 100, 1),
                        "gap_factor": seg.get("gap_factor", 1.0),
                        "wap_factor": 1.0,
                        "target_pace_s": sit_pace_s,
                        "target_pace_fmt": pacer_data["sit_phase"]["pacer_pace_fmt"],
                        "segment_time_s": sit_pace_s * (seg["distance_m"] / 1000.0),
                        "cumulative_time_s": 0,
                        "cumulative_time_fmt": "—",
                        "phase": "sit",
                    }
                    for seg in segments
                    if seg["km"] <= drop_km
                ]
                # Fix cumulative times for sit splits
                cum = 0.0
                for sp in sit_splits:
                    cum += sp["segment_time_s"]
                    sp["cumulative_time_s"] = round(cum, 1)
                    from fitops.race.course_parser import _fmt_duration

                    sp["cumulative_time_fmt"] = _fmt_duration(cum)

                # Mark push splits
                push_splits = pacer_data["push_phase"]["splits"]
                for sp in push_splits:
                    sp["phase"] = "push"

                splits = sit_splits + push_splits
                pacer_pace_s_for_chart = sit_pace_s
                drop_km_for_chart = drop_km
            else:
                splits = simulate_splits(
                    segments, target_total_s, weather, strategy=strat
                )
                pacer_pace_s_for_chart = None
                drop_km_for_chart = None
        except ValueError as exc:
            return _render_error(str(exc))

        # Annotate splits with wind label
        wind_speed = weather.get("wind_speed_ms", 0.0)
        wind_dir = weather.get("wind_direction_deg", 0.0)
        if splits:
            for sp in splits:
                sp["wind"] = _wind_label(
                    sp.get("bearing_deg", 0.0), wind_speed, wind_dir
                )

        # Compute avg pace and chart data
        avg_pace_s = 0.0
        avg_pace_fmt = "—"
        chart_labels: list = []
        chart_paces: list = []
        cum_pace_profile: list = []
        wind_profile: list = []

        if splits:
            total_time = sum(s["segment_time_s"] for s in splits)
            total_dist_km = sum(s["distance_m"] for s in splits) / 1000.0
            if total_dist_km > 0:
                from fitops.race.course_parser import _fmt_duration

                avg_pace_s = total_time / total_dist_km
                avg_pace_fmt = _fmt_duration(avg_pace_s)

            chart_labels = [s["km"] for s in splits]
            chart_paces = [s["target_pace_s"] for s in splits]

            cum_time = 0.0
            cum_dist_m = 0.0
            for sp in splits:
                cum_time += sp["segment_time_s"]
                cum_dist_m += sp["distance_m"]
                cum_pace_profile.append(round(cum_time / (cum_dist_m / 1000.0), 1))

            for sp in splits:
                hw = headwind_ms(wind_speed, wind_dir, sp.get("bearing_deg", 0.0))
                wind_profile.append(round(hw * 3.6, 1))

        elevation_profile = _build_elevation_profile(course)

        return templates.TemplateResponse(
            request,
            "race/simulate.html",
            {
                "request": request,
                "course": summary,
                "splits": splits,
                "pacer_data": pacer_data,
                "error": None,
                "form": form_vals,
                "avg_pace_s": round(avg_pace_s, 1),
                "avg_pace_fmt": avg_pace_fmt,
                "chart_labels_json": json.dumps(chart_labels),
                "chart_paces_json": json.dumps(chart_paces),
                "cum_pace_profile_json": json.dumps(cum_pace_profile),
                "pacer_pace_s": pacer_pace_s_for_chart,
                "drop_at_km": drop_km_for_chart,
                "elevation_profile_json": json.dumps(elevation_profile),
                "wind_profile_json": json.dumps(wind_profile),
                "segment_coords_json": segment_coords_json,
                "weather_info": {
                    "source": weather_source,
                    "temperature_c": weather["temperature_c"],
                    "humidity_pct": weather["humidity_pct"],
                    "wind_speed_kmh": round(weather["wind_speed_ms"] * 3.6, 1),
                    "wind_direction_deg": weather["wind_direction_deg"],
                },
                "route_coords_json": route_coords_json,
                "existing_plans": existing_plans,
                "active_page": "race",
            },
        )

    # ------------------------------------------------------------------
    # Race Plan routes
    # ------------------------------------------------------------------

    @router.post("/race/{course_id}/plans", response_class=HTMLResponse)
    async def race_plan_save(
        request: Request,
        course_id: int,
        plan_name: str = Form(...),
        target_time: str | None = Form(None),
        strategy: str | None = Form(None),
        pacer_pace: str | None = Form(None),
        drop_at_km: str | None = Form(None),
        race_date: str | None = Form(None),
        race_hour: str | None = Form(None),
        temp: str | None = Form(None),
        humidity: str | None = Form(None),
        wind: str | None = Form(None),
        wind_dir: str | None = Form(None),
        override_plan_id: str | None = Form(None),
    ):
        """Save a simulation result as a named race plan."""
        await create_all_tables()
        course = await get_course(course_id)
        if course is None:
            return HTMLResponse(
                content="<h1>404 — Course not found</h1>", status_code=404
            )

        segments = course.get_km_segments()

        try:
            target_total_s, target_time_normalized = _parse_finish_time(
                target_time or ""
            )
        except (ValueError, AttributeError):
            return HTMLResponse(content="<p>Invalid target time.</p>", status_code=400)

        strat = (strategy or "even").lower()
        if strat not in ("even", "negative", "positive"):
            strat = "even"

        weather_source_val = "neutral"
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
                weather_source_val = "manual"
            except ValueError:
                pass

        elif (
            race_date and course.start_lat is not None and course.start_lon is not None
        ):
            from fitops.weather.client import (
                fetch_activity_weather,
                fetch_forecast_weather,
            )

            try:
                parsed_date = datetime.date.fromisoformat(race_date)
                hour = int(race_hour) if race_hour and race_hour.isdigit() else 9
                today = datetime.date.today()
                if parsed_date > today:
                    fetched = await fetch_forecast_weather(
                        course.start_lat, course.start_lon, race_date, hour
                    )
                    if fetched:
                        weather = {
                            "temperature_c": fetched.get("temperature_c", 15.0),
                            "humidity_pct": fetched.get("humidity_pct", 40.0),
                            "wind_speed_ms": fetched.get("wind_speed_ms", 0.0),
                            "wind_direction_deg": fetched.get(
                                "wind_direction_deg", 0.0
                            ),
                        }
                        weather_source_val = "forecast"
                else:
                    race_dt = datetime.datetime(
                        parsed_date.year,
                        parsed_date.month,
                        parsed_date.day,
                        hour,
                        0,
                        0,
                        tzinfo=datetime.UTC,
                    )
                    fetched = await fetch_activity_weather(
                        course.start_lat, course.start_lon, race_dt
                    )
                    if fetched:
                        weather = {
                            "temperature_c": fetched.get("temperature_c", 15.0),
                            "humidity_pct": fetched.get("humidity_pct", 40.0),
                            "wind_speed_ms": fetched.get("wind_speed_ms", 0.0),
                            "wind_direction_deg": fetched.get(
                                "wind_direction_deg", 0.0
                            ),
                        }
                        weather_source_val = "archive"
            except (ValueError, TypeError):
                pass

        use_pacer = bool(pacer_pace and drop_at_km)
        try:
            if use_pacer:
                pacer_pace_s = _parse_pace(pacer_pace)
                drop_km_f = float(drop_at_km)
                pacer_data = simulate_pacer_mode(
                    segments, target_total_s, pacer_pace_s, drop_km_f, weather
                )
                sit_pace_s = pacer_pace_s
                sit_splits = [
                    {
                        "km": seg["km"],
                        "distance_m": seg["distance_m"],
                        "target_pace_s": sit_pace_s,
                        "target_pace_fmt": pacer_data["sit_phase"]["pacer_pace_fmt"],
                        "segment_time_s": sit_pace_s * (seg["distance_m"] / 1000.0),
                        "phase": "sit",
                    }
                    for seg in segments
                    if seg["km"] <= drop_km_f
                ]
                splits_to_save = sit_splits + pacer_data["push_phase"]["splits"]
            else:
                splits_to_save = simulate_splits(
                    segments, target_total_s, weather, strategy=strat
                )
        except ValueError as exc:
            return HTMLResponse(
                content=f"<p>Simulation error: {exc}</p>", status_code=400
            )

        race_hour_int = int(race_hour) if race_hour and race_hour.isdigit() else 9
        drop_km_val = float(drop_at_km) if drop_at_km and use_pacer else None

        # Determine whether to overwrite an existing plan or create a new one
        override_id: int | None = None
        if override_plan_id and override_plan_id.strip().lstrip("-").isdigit():
            _oid = int(override_plan_id)
            if _oid > 0:
                override_id = _oid

        if override_id is not None:
            await update_race_plan(
                override_id,
                name=plan_name.strip(),
                race_date=race_date or None,
                race_hour=race_hour_int,
                target_time=target_time_normalized,
                target_time_s=target_total_s,
                strategy=strat,
                pacer_pace=pacer_pace or None,
                drop_at_km=drop_km_val,
                weather_temp_c=weather["temperature_c"],
                weather_humidity_pct=weather["humidity_pct"],
                weather_wind_ms=weather["wind_speed_ms"],
                weather_wind_dir_deg=weather["wind_direction_deg"],
                weather_source=weather_source_val,
                splits_json=json.dumps(splits_to_save),
                activity_id=None,  # reset link so sweep can re-match
            )
            saved_id = override_id
        else:
            plan = await save_race_plan(
                course_id=course_id,
                name=plan_name.strip(),
                race_date=race_date or None,
                race_hour=race_hour_int,
                target_time=target_time_normalized,
                target_time_s=target_total_s,
                strategy=strat,
                pacer_pace=pacer_pace or None,
                drop_at_km=drop_km_val,
                weather_temp_c=weather["temperature_c"],
                weather_humidity_pct=weather["humidity_pct"],
                weather_wind_ms=weather["wind_speed_ms"],
                weather_wind_dir_deg=weather["wind_direction_deg"],
                weather_source=weather_source_val,
                splits=splits_to_save,
            )
            saved_id = plan["id"]

        # Immediately try to associate this plan with an existing activity
        try:
            from fitops.analytics.race_plan import sweep_unlinked_plans

            await sweep_unlinked_plans()
        except Exception:
            pass

        return RedirectResponse(url=f"/race/plans/{saved_id}", status_code=303)

    @router.get("/race/plans", response_class=HTMLResponse)
    async def race_plans_list(request: Request):
        await create_all_tables()
        plans = await get_all_race_plans()
        # Enrich with course names
        course_cache: dict[int, str] = {}
        for p in plans:
            cid = p["course_id"]
            if cid not in course_cache:
                c = await get_course(cid)
                course_cache[cid] = c.name if c else f"Course {cid}"
            p["course_name"] = course_cache[cid]
        return templates.TemplateResponse(
            request,
            "race/plans.html",
            {"request": request, "plans": plans, "active_page": "race"},
        )

    @router.get("/race/plans/{plan_id}", response_class=HTMLResponse)
    async def race_plan_detail(request: Request, plan_id: int):
        await create_all_tables()
        plan = await get_race_plan(plan_id)
        if plan is None:
            return HTMLResponse(
                content="<h1>404 — Plan not found</h1>", status_code=404
            )

        course = await get_course(plan.course_id)
        if course is None:
            return HTMLResponse(
                content="<h1>404 — Course not found</h1>", status_code=404
            )

        plan_dict = plan.to_detail_dict()
        course_dict = course.to_summary_dict()

        # Annotate simulated splits with wind label
        wind_speed = plan.weather_wind_ms or 0.0
        wind_dir_deg = plan.weather_wind_dir_deg or 0.0
        for sp in plan_dict["splits"]:
            sp["wind"] = _wind_label(
                sp.get("bearing_deg", 0.0), wind_speed, wind_dir_deg
            )

        # Build chart data for simulated splits
        sim_chart_labels = [s["km"] for s in plan_dict["splits"]]
        sim_chart_paces = [s.get("target_pace_s", 0) for s in plan_dict["splits"]]

        # Compute avg pace
        from fitops.race.course_parser import _fmt_duration

        total_time = sum(s.get("segment_time_s", 0) for s in plan_dict["splits"])
        total_dist_km = (
            sum(s.get("distance_m", 0) for s in plan_dict["splits"]) / 1000.0
        )
        avg_pace_s = (total_time / total_dist_km) if total_dist_km > 0 else 0.0
        avg_pace_fmt = _fmt_duration(avg_pace_s) if avg_pace_s > 0 else "—"

        # Actual splits if activity is linked
        actual_splits = None
        actual_avg_pace_fmt = None
        actual_finish_fmt = None
        compare_chart_labels = None
        compare_sim_paces = None
        compare_actual_paces = None
        activity_strava_id = None

        if plan.activity_id is not None:
            from sqlalchemy import select as _select

            from fitops.analytics.activity_splits import compute_km_splits
            from fitops.db.models.activity import Activity as _Activity
            from fitops.db.models.activity_stream import ActivityStream
            from fitops.db.session import get_async_session

            async with get_async_session() as session:
                act_res = await session.execute(
                    _select(_Activity).where(_Activity.id == plan.activity_id)
                )
                act = act_res.scalar_one_or_none()
                if act:
                    activity_strava_id = act.strava_id
                streams_res = await session.execute(
                    _select(ActivityStream).where(
                        ActivityStream.activity_id == plan.activity_id
                    )
                )
                all_streams = {
                    row.stream_type: row.data for row in streams_res.scalars().all()
                }

            if act and all_streams:
                km_splits = compute_km_splits(all_streams, act.sport_type or "Run")
                if km_splits:
                    actual_splits = km_splits
                    act_total_s = sum(
                        s.get("pace_s", 0) * (s.get("distance_m", 1000) / 1000.0)
                        for s in actual_splits
                    )
                    act_total_dist = (
                        sum(s.get("distance_m", 0) for s in actual_splits) / 1000.0
                    )
                    act_avg_pace_s = (
                        (act_total_s / act_total_dist) if act_total_dist > 0 else 0.0
                    )
                    actual_avg_pace_fmt = (
                        _fmt_duration(act_avg_pace_s) if act_avg_pace_s > 0 else "—"
                    )
                    actual_finish_s = sum(
                        s.get("pace_s", 0) * (s.get("distance_m", 1000) / 1000.0)
                        for s in actual_splits
                    )
                    actual_finish_fmt = _fmt_duration(actual_finish_s)

                    # Build comparison chart (align by km index)
                    n = min(len(plan_dict["splits"]), len(actual_splits))
                    compare_chart_labels = [
                        plan_dict["splits"][i]["km"] for i in range(n)
                    ]
                    compare_sim_paces = [
                        plan_dict["splits"][i].get("target_pace_s", 0) for i in range(n)
                    ]
                    compare_actual_paces = [
                        actual_splits[i].get("pace_s", 0) for i in range(n)
                    ]

        elevation_profile = _build_elevation_profile(course)
        segment_coords = _build_km_segment_coords(course)
        route_coords = _sample_route_coords(course.get_course_points())

        return templates.TemplateResponse(
            request,
            "race/plan_detail.html",
            {
                "request": request,
                "plan": plan_dict,
                "course": course_dict,
                "avg_pace_s": round(avg_pace_s, 1),
                "avg_pace_fmt": avg_pace_fmt,
                "sim_chart_labels_json": json.dumps(sim_chart_labels),
                "sim_chart_paces_json": json.dumps(sim_chart_paces),
                "actual_splits": actual_splits,
                "actual_avg_pace_fmt": actual_avg_pace_fmt,
                "actual_finish_fmt": actual_finish_fmt,
                "compare_chart_labels_json": json.dumps(compare_chart_labels or []),
                "compare_sim_paces_json": json.dumps(compare_sim_paces or []),
                "compare_actual_paces_json": json.dumps(compare_actual_paces or []),
                "elevation_profile_json": json.dumps(elevation_profile),
                "segment_coords_json": json.dumps(segment_coords),
                "route_coords_json": json.dumps(route_coords),
                "activity_strava_id": activity_strava_id,
                "active_page": "race",
            },
        )

    @router.post("/race/plans/{plan_id}/edit", response_class=HTMLResponse)
    async def race_plan_edit(
        request: Request,
        plan_id: int,
        plan_name: str = Form(...),
        target_time: str | None = Form(None),
        strategy: str | None = Form(None),
        pacer_pace: str | None = Form(None),
        drop_at_km: str | None = Form(None),
        race_date: str | None = Form(None),
        race_hour: str | None = Form(None),
        temp: str | None = Form(None),
        humidity: str | None = Form(None),
        wind: str | None = Form(None),
        wind_dir: str | None = Form(None),
    ):
        """Re-simulate and update an existing plan."""
        await create_all_tables()
        plan = await get_race_plan(plan_id)
        if plan is None:
            return HTMLResponse(
                content="<h1>404 — Plan not found</h1>", status_code=404
            )

        course = await get_course(plan.course_id)
        if course is None:
            return HTMLResponse(
                content="<h1>404 — Course not found</h1>", status_code=404
            )

        segments = course.get_km_segments()
        try:
            target_total_s, target_time_normalized = _parse_finish_time(
                target_time or ""
            )
        except (ValueError, AttributeError):
            return HTMLResponse(content="<p>Invalid target time.</p>", status_code=400)

        strat = (strategy or "even").lower()
        if strat not in ("even", "negative", "positive"):
            strat = "even"

        weather = {
            "temperature_c": 15.0,
            "humidity_pct": 40.0,
            "wind_speed_ms": 0.0,
            "wind_direction_deg": 0.0,
        }
        weather_source_val = "neutral"
        if temp and humidity:
            try:
                weather = {
                    "temperature_c": float(temp),
                    "humidity_pct": float(humidity),
                    "wind_speed_ms": float(wind) if wind else 0.0,
                    "wind_direction_deg": float(wind_dir) if wind_dir else 0.0,
                }
                weather_source_val = "manual"
            except ValueError:
                pass

        use_pacer = bool(pacer_pace and drop_at_km)
        try:
            if use_pacer:
                pacer_pace_s = _parse_pace(pacer_pace)
                drop_km_f = float(drop_at_km)
                pacer_data = simulate_pacer_mode(
                    segments, target_total_s, pacer_pace_s, drop_km_f, weather
                )
                sit_splits = [
                    {
                        "km": seg["km"],
                        "distance_m": seg["distance_m"],
                        "target_pace_s": pacer_pace_s,
                        "target_pace_fmt": pacer_data["sit_phase"]["pacer_pace_fmt"],
                        "segment_time_s": pacer_pace_s * (seg["distance_m"] / 1000.0),
                        "phase": "sit",
                    }
                    for seg in segments
                    if seg["km"] <= drop_km_f
                ]
                splits_to_save = sit_splits + pacer_data["push_phase"]["splits"]
                drop_km_val = drop_km_f
            else:
                splits_to_save = simulate_splits(
                    segments, target_total_s, weather, strategy=strat
                )
                drop_km_val = None
        except ValueError as exc:
            return HTMLResponse(
                content=f"<p>Simulation error: {exc}</p>", status_code=400
            )

        import json as _json

        race_hour_int = int(race_hour) if race_hour and race_hour.isdigit() else 9
        await update_race_plan(
            plan_id,
            name=plan_name.strip(),
            race_date=race_date or None,
            race_hour=race_hour_int,
            target_time=target_time_normalized,
            target_time_s=target_total_s,
            strategy=strat,
            pacer_pace=pacer_pace or None,
            drop_at_km=drop_km_val,
            weather_temp_c=weather["temperature_c"],
            weather_humidity_pct=weather["humidity_pct"],
            weather_wind_ms=weather["wind_speed_ms"],
            weather_wind_dir_deg=weather["wind_direction_deg"],
            weather_source=weather_source_val,
            splits_json=_json.dumps(splits_to_save),
        )
        return RedirectResponse(url=f"/race/plans/{plan_id}", status_code=303)

    @router.post("/race/plans/{plan_id}/delete", response_class=HTMLResponse)
    async def race_plan_delete(request: Request, plan_id: int):
        await create_all_tables()
        await delete_race_plan(plan_id)
        return RedirectResponse(url="/race/plans", status_code=303)

    return router
