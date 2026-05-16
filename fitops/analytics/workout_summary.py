from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from fitops.db.models.activity import Activity
from fitops.db.models.workout import Workout
from fitops.db.models.workout_activity_link import WorkoutActivityLink
from fitops.db.models.workout_segment import WorkoutSegment
from fitops.db.session import get_async_session

RUNNING_SPORTS = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
RIDING_SPORTS = {"Ride", "VirtualRide", "EBikeRide", "MountainBikeRide", "GravelRide"}

PERIOD_LABELS = {
    "week": "This Week",
    "month": "This Month",
    "year": "This Year",
    "all": "All Time",
}


def period_since(period: str) -> datetime | None:
    now = datetime.now(UTC)
    if period == "week":
        return (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "year":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


def normalize_period(period: str | None) -> str:
    return period if period in PERIOD_LABELS else "month"


def sport_types_for_filter(sport: str | None) -> set[str] | None:
    if not sport or sport == "total":
        return None
    if sport == "run":
        return RUNNING_SPORTS
    if sport in {"cycle", "ride"}:
        return RIDING_SPORTS
    return {sport}


def _sport_matches(sport_type: str | None, sport_filter: set[str] | None) -> bool:
    if sport_filter is None:
        return True
    if not sport_type:
        return False
    lowered = {s.lower() for s in sport_filter}
    return sport_type in sport_filter or sport_type.lower() in lowered


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return "0:00"
    hours, rem = divmod(int(seconds), 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _pct(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 100)


async def get_workout_summary(
    athlete_id: int,
    *,
    period: str = "month",
    sport: str | None = None,
) -> dict[str, Any]:
    """Summarize workout history from stored rows only.

    This intentionally does not fetch streams, recompute compliance, or write data.
    Missing stored scores are counted as unscored rather than recomputed.
    """
    period = normalize_period(period)
    since = period_since(period)
    sport_filter = sport_types_for_filter(sport)

    async with get_async_session() as session:
        definitions_res = await session.execute(
            select(
                Workout.id,
                Workout.name,
                Workout.sport_type,
                Workout.status,
            ).where(Workout.athlete_id == athlete_id)
        )
        definition_rows = [
            row
            for row in definitions_res.all()
            if _sport_matches(row.sport_type, sport_filter)
        ]
        definition_ids = {row.id for row in definition_rows}
        all_linked_workout_ids: set[int] = set()
        if definition_ids:
            all_linked_res = await session.execute(
                select(WorkoutActivityLink.workout_id).where(
                    WorkoutActivityLink.workout_id.in_(definition_ids)
                )
            )
            all_linked_workout_ids = {row.workout_id for row in all_linked_res.all()}

        session_stmt = (
            select(
                WorkoutActivityLink.workout_id,
                WorkoutActivityLink.activity_id,
                WorkoutActivityLink.linked_at,
                WorkoutActivityLink.compliance_score,
                Workout.name.label("workout_name"),
                Activity.strava_id,
                Activity.sport_type.label("activity_sport_type"),
                Activity.start_date_local,
                Activity.moving_time_s,
                Activity.distance_m,
            )
            .join(Workout, Workout.id == WorkoutActivityLink.workout_id)
            .join(Activity, Activity.id == WorkoutActivityLink.activity_id)
            .where(Workout.athlete_id == athlete_id)
        )
        if since is not None:
            session_stmt = session_stmt.where(Activity.start_date_local >= since)
        if sport_filter is not None:
            session_stmt = session_stmt.where(Activity.sport_type.in_(sport_filter))
        session_res = await session.execute(
            session_stmt.order_by(Activity.start_date_local.desc())
        )
        session_rows = list(session_res.all())

        segment_stmt = (
            select(
                func.count(WorkoutSegment.id).label("segment_count"),
                func.sum(func.coalesce(WorkoutSegment.target_achieved, 0)).label(
                    "segments_in_target"
                ),
                func.avg(WorkoutSegment.time_in_target_pct).label(
                    "avg_time_in_target_pct"
                ),
                func.avg(WorkoutSegment.compliance_score).label(
                    "avg_segment_compliance"
                ),
            )
            .join(
                WorkoutActivityLink,
                (WorkoutActivityLink.workout_id == WorkoutSegment.workout_id)
                & (WorkoutActivityLink.activity_id == WorkoutSegment.activity_id),
            )
            .join(Workout, Workout.id == WorkoutSegment.workout_id)
            .join(Activity, Activity.id == WorkoutSegment.activity_id)
            .where(Workout.athlete_id == athlete_id)
        )
        if since is not None:
            segment_stmt = segment_stmt.where(Activity.start_date_local >= since)
        if sport_filter is not None:
            segment_stmt = segment_stmt.where(Activity.sport_type.in_(sport_filter))
        segment_row = (await session.execute(segment_stmt)).one()

    completed_sessions = len(session_rows)
    unique_completed_workouts = len({row.workout_id for row in session_rows})
    scored_sessions = [row for row in session_rows if row.compliance_score is not None]
    avg_compliance = (
        sum(float(row.compliance_score) for row in scored_sessions)
        / len(scored_sessions)
        if scored_sessions
        else None
    )
    total_duration_seconds = sum(row.moving_time_s or 0 for row in session_rows)
    total_distance_km = round(
        sum((row.distance_m or 0.0) for row in session_rows) / 1000, 1
    )

    by_workout_counts = Counter(row.workout_id for row in session_rows)
    names_by_workout = {row.workout_id: row.workout_name for row in session_rows}
    most_repeated = None
    if by_workout_counts:
        workout_id, count = by_workout_counts.most_common(1)[0]
        most_repeated = {
            "id": workout_id,
            "name": names_by_workout.get(workout_id),
            "sessions": count,
        }

    compliance_by_workout: dict[int, list[float]] = defaultdict(list)
    for row in scored_sessions:
        compliance_by_workout[row.workout_id].append(float(row.compliance_score))
    best_compliance = None
    if compliance_by_workout:
        best_id, scores = max(
            compliance_by_workout.items(),
            key=lambda item: (sum(item[1]) / len(item[1]), len(item[1])),
        )
        best_compliance = {
            "id": best_id,
            "name": names_by_workout.get(best_id),
            "avg_compliance_pct": _pct(sum(scores) / len(scores)),
            "sessions": len(scores),
        }

    latest = None
    if session_rows:
        latest_row = session_rows[0]
        latest = {
            "workout_id": latest_row.workout_id,
            "name": latest_row.workout_name,
            "activity_id": latest_row.strava_id,
            "completed_at": latest_row.start_date_local.isoformat()
            if latest_row.start_date_local
            else None,
        }

    sport_counts = Counter(row.activity_sport_type for row in session_rows)
    compliance_bands = {
        "green_80_plus": sum(
            1 for row in scored_sessions if float(row.compliance_score) >= 0.8
        ),
        "amber_50_79": sum(
            1 for row in scored_sessions if 0.5 <= float(row.compliance_score) < 0.8
        ),
        "red_under_50": sum(
            1 for row in scored_sessions if float(row.compliance_score) < 0.5
        ),
        "unscored": completed_sessions - len(scored_sessions),
    }

    segment_count = int(segment_row.segment_count or 0)
    segments_in_target = int(segment_row.segments_in_target or 0)

    return {
        "period": period,
        "period_label": PERIOD_LABELS[period],
        "sport": sport or "total",
        "summary": {
            "completed_sessions": completed_sessions,
            "unique_completed_workouts": unique_completed_workouts,
            "total_definitions": len(definition_rows),
            "planned_definitions": sum(
                1 for row in definition_rows if row.status == "planned"
            ),
            "unlinked_definitions": len(definition_ids - all_linked_workout_ids),
            "total_duration_seconds": total_duration_seconds,
            "total_duration_formatted": _format_duration(total_duration_seconds),
            "total_distance_km": total_distance_km,
            "avg_compliance_pct": _pct(avg_compliance),
            "scored_sessions": len(scored_sessions),
            "compliance_coverage_pct": round(
                (len(scored_sessions) / completed_sessions) * 100
            )
            if completed_sessions
            else 0,
            "segment_count": segment_count,
            "segments_in_target_pct": round((segments_in_target / segment_count) * 100)
            if segment_count
            else None,
            "avg_time_in_target_pct": round(segment_row.avg_time_in_target_pct)
            if segment_row.avg_time_in_target_pct is not None
            else None,
            "avg_segment_compliance_pct": _pct(segment_row.avg_segment_compliance),
            "most_repeated_workout": most_repeated,
            "best_compliance_workout": best_compliance,
            "latest_completed": latest,
        },
        "distributions": {
            "by_sport": [
                {"sport_type": sport_type, "sessions": count}
                for sport_type, count in sorted(sport_counts.items())
                if sport_type
            ],
            "compliance_bands": compliance_bands,
        },
    }
