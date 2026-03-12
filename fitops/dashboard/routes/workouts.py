from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from fitops.config.settings import get_settings
from fitops.db.models.workout import Workout
from fitops.db.models.workout_segment import WorkoutSegment
from fitops.db.session import get_async_session

router = APIRouter()


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
                # Fetch segment count
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

    return router
