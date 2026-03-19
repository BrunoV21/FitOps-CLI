from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fitops.dashboard.queries.race import get_all_courses, get_course
from fitops.db.migrations import create_all_tables
from fitops.race.simulation import simulate_pacer_mode, simulate_splits

router = APIRouter()


def _parse_time(s: str) -> float:
    """Parse HH:MM:SS or MM:SS string to total seconds. Raises ValueError on bad format."""
    parts = s.strip().split(":")
    if len(parts) == 3:
        h, m, sec = parts
        return int(h) * 3600 + int(m) * 60 + float(sec)
    elif len(parts) == 2:
        m, sec = parts
        return int(m) * 60 + float(sec)
    else:
        raise ValueError(f"Cannot parse time: {s!r}. Expected HH:MM:SS or MM:SS.")


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
        while ptr + 1 < n_pts and abs(points[ptr + 1]["distance_from_start_m"] - target_dist) <= abs(
            points[ptr]["distance_from_start_m"] - target_dist
        ):
            ptr += 1
        elevation_profile.append({"km": km_idx, "elevation_m": round(points[ptr]["elevation_m"], 1)})
    return elevation_profile


def register(templates: Jinja2Templates) -> APIRouter:

    @router.get("/race", response_class=HTMLResponse)
    async def race_index(request: Request):
        await create_all_tables()
        courses = await get_all_courses()
        return templates.TemplateResponse(
            "race/index.html",
            {
                "request": request,
                "courses": courses,
                "active_page": "race",
            },
        )

    @router.get("/race/{course_id}", response_class=HTMLResponse)
    async def race_course(request: Request, course_id: int):
        await create_all_tables()
        course = await get_course(course_id)
        if course is None:
            return HTMLResponse(content="<h1>404 — Course not found</h1>", status_code=404)

        segments = course.get_km_segments()
        elevation_profile = _build_elevation_profile(course)
        summary = course.to_summary_dict()

        return templates.TemplateResponse(
            "race/course.html",
            {
                "request": request,
                "course": summary,
                "segments": segments,
                "elevation_profile_json": json.dumps(elevation_profile),
                "active_page": "race",
            },
        )

    @router.get("/race/{course_id}/simulate", response_class=HTMLResponse)
    async def race_simulate_form(request: Request, course_id: int):
        await create_all_tables()
        course = await get_course(course_id)
        if course is None:
            return HTMLResponse(content="<h1>404 — Course not found</h1>", status_code=404)

        summary = course.to_summary_dict()
        return templates.TemplateResponse(
            "race/simulate.html",
            {
                "request": request,
                "course": summary,
                "splits": None,
                "pacer_data": None,
                "error": None,
                "form": {},
                "active_page": "race",
            },
        )

    @router.post("/race/{course_id}/simulate", response_class=HTMLResponse)
    async def race_simulate_post(
        request: Request,
        course_id: int,
        target_time: Optional[str] = Form(None),
        strategy: Optional[str] = Form(None),
        pacer_pace: Optional[str] = Form(None),
        drop_at_km: Optional[str] = Form(None),
        temp: Optional[str] = Form(None),
        humidity: Optional[str] = Form(None),
        wind: Optional[str] = Form(None),
        wind_dir: Optional[str] = Form(None),
    ):
        await create_all_tables()
        course = await get_course(course_id)
        if course is None:
            return HTMLResponse(content="<h1>404 — Course not found</h1>", status_code=404)

        summary = course.to_summary_dict()
        segments = course.get_km_segments()

        form_vals = {
            "target_time": target_time or "",
            "strategy": strategy or "even",
            "pacer_pace": pacer_pace or "",
            "drop_at_km": drop_at_km or "",
            "temp": temp or "",
            "humidity": humidity or "",
            "wind": wind or "",
            "wind_dir": wind_dir or "",
        }

        def _render_error(msg: str):
            return templates.TemplateResponse(
                "race/simulate.html",
                {
                    "request": request,
                    "course": summary,
                    "splits": None,
                    "pacer_data": None,
                    "error": msg,
                    "form": form_vals,
                    "active_page": "race",
                },
            )

        # Parse target time
        try:
            target_total_s = _parse_time(target_time or "")
        except (ValueError, AttributeError):
            return _render_error("Invalid target time. Use HH:MM:SS or MM:SS format.")

        strat = (strategy or "even").lower()
        if strat not in ("even", "negative", "positive"):
            strat = "even"

        # Weather resolution: manual if both temp and humidity provided, else neutral
        if temp and humidity:
            try:
                weather = {
                    "temperature_c": float(temp),
                    "humidity_pct": float(humidity),
                    "wind_speed_ms": float(wind) if wind else 0.0,
                    "wind_direction_deg": float(wind_dir) if wind_dir else 0.0,
                }
            except ValueError:
                return _render_error("Invalid weather values. Temperature and humidity must be numbers.")
        else:
            weather = {
                "temperature_c": 15.0,
                "humidity_pct": 40.0,
                "wind_speed_ms": 0.0,
                "wind_direction_deg": 0.0,
            }

        splits = None
        pacer_data = None

        # Pacer mode: both pacer_pace and drop_at_km provided
        use_pacer = bool(pacer_pace and drop_at_km)
        try:
            if use_pacer:
                pacer_pace_s = _parse_time(pacer_pace)
                drop_km = float(drop_at_km)
                pacer_data = simulate_pacer_mode(segments, target_total_s, pacer_pace_s, drop_km, weather)
                # Combine sit and push splits for the chart
                sit_dist_km = pacer_data["sit_phase"]["distance_km"]
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
                splits = simulate_splits(segments, target_total_s, weather, strategy=strat)
                pacer_pace_s_for_chart = None
                drop_km_for_chart = None
        except ValueError as exc:
            return _render_error(str(exc))

        # Compute avg pace for color coding
        if splits:
            total_time = sum(s["segment_time_s"] for s in splits)
            total_dist_km = sum(s["distance_m"] for s in splits) / 1000.0
            avg_pace_s = total_time / total_dist_km if total_dist_km > 0 else 0
        else:
            avg_pace_s = 0

        chart_labels = [s["km"] for s in splits] if splits else []
        chart_paces = [s["target_pace_s"] for s in splits] if splits else []

        return templates.TemplateResponse(
            "race/simulate.html",
            {
                "request": request,
                "course": summary,
                "splits": splits,
                "pacer_data": pacer_data,
                "error": None,
                "form": form_vals,
                "avg_pace_s": round(avg_pace_s, 1),
                "chart_labels_json": json.dumps(chart_labels),
                "chart_paces_json": json.dumps(chart_paces),
                "pacer_pace_s": pacer_pace_s_for_chart,
                "drop_at_km": drop_km_for_chart,
                "active_page": "race",
            },
        )

    return router
