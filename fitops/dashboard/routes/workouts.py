from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from fitops.config.settings import get_settings
from fitops.db.models.workout import Workout
from fitops.db.models.workout_segment import WorkoutSegment
from fitops.db.session import get_async_session
from fitops.dashboard.queries.workouts import (
    get_activity_for_workout,
    get_workout_with_segments,
)

router = APIRouter()


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
    @router.get("/workouts", response_class=HTMLResponse)
    async def workouts_list(request: Request):
        settings = get_settings()
        athlete_id = settings.athlete_id

        rows = []
        if athlete_id:
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

                rows.append({
                    "id": w.id,
                    "name": w.name,
                    "sport_type": w.sport_type,
                    "status": w.status,
                    "linked_at": w.linked_at.strftime("%d %b %Y") if w.linked_at else "—",
                    "compliance_score": (
                        f"{w.compliance_score * 100:.0f}%" if w.compliance_score is not None else "—"
                    ),
                    "compliance_pct": round(w.compliance_score * 100) if w.compliance_score is not None else None,
                    "segment_count": len(segments),
                    "segments": [s.to_dict() for s in segments],
                })

        return templates.TemplateResponse(
            "workouts/list.html",
            {
                "request": request,
                "workouts": rows,
                "active_page": "workouts",
            },
        )

    @router.get("/workouts/{workout_id}", response_class=HTMLResponse)
    async def workout_detail(request: Request, workout_id: int):
        settings = get_settings()
        athlete_id = settings.athlete_id

        if not athlete_id:
            return templates.TemplateResponse(
                "workouts/detail.html",
                {"request": request, "workout": None, "active_page": "workouts"},
                status_code=404,
            )

        result = await get_workout_with_segments(workout_id, athlete_id)
        if result is None:
            return templates.TemplateResponse(
                "workouts/detail.html",
                {"request": request, "workout": None, "active_page": "workouts"},
                status_code=404,
            )

        workout, segments = result

        # Linked activity info
        linked_activity = None
        if workout.activity_id:
            act = await get_activity_for_workout(workout.activity_id)
            if act:
                linked_activity = {
                    "strava_id": act.strava_id,
                    "name": act.name,
                    "date": act.start_date_local.strftime("%d %b %Y") if act.start_date_local else "—",
                    "sport_type": act.sport_type,
                }

        # Physiology snapshot
        physiology = workout.get_physiology_snapshot() or {}

        # Build segment rows for template
        seg_rows = []
        for s in segments:
            d = s.to_dict()
            seg_rows.append({
                **d,
                "target_label": _segment_target_label(d),
                "compliance_pct": round(s.compliance_score * 100) if s.compliance_score is not None else None,
                "score_class": (
                    "green" if s.compliance_score and s.compliance_score >= 0.8
                    else "amber" if s.compliance_score and s.compliance_score >= 0.6
                    else "red" if s.compliance_score is not None
                    else "dim"
                ),
            })

        overall_pct = round(workout.compliance_score * 100) if workout.compliance_score is not None else None

        return templates.TemplateResponse(
            "workouts/detail.html",
            {
                "request": request,
                "workout": {
                    "id": workout.id,
                    "name": workout.name,
                    "sport_type": workout.sport_type,
                    "status": workout.status,
                    "linked_at": workout.linked_at.strftime("%d %b %Y") if workout.linked_at else None,
                    "compliance_score": workout.compliance_score,
                    "compliance_pct": overall_pct,
                    "score_class": (
                        "green" if overall_pct and overall_pct >= 80
                        else "amber" if overall_pct and overall_pct >= 60
                        else "red" if overall_pct is not None
                        else "dim"
                    ),
                    "notes": workout.notes,
                },
                "linked_activity": linked_activity,
                "physiology": physiology,
                "segments": seg_rows,
                "active_page": "workouts",
            },
        )

    return router
