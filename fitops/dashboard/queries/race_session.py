from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select

from fitops.db.models.race_session import (
    RaceSession,
    RaceSessionAthlete,
    RaceSessionEvent,
    RaceSessionGap,
    RaceSessionSegment,
)
from fitops.db.session import get_async_session


# ---------------------------------------------------------------------------
# Race Session CRUD
# ---------------------------------------------------------------------------


async def create_race_session(
    name: str,
    primary_activity_id: int,
    course_id: int | None = None,
) -> dict:
    """Create a new RaceSession and return its summary dict."""
    session_obj = RaceSession(
        name=name,
        primary_activity_id=primary_activity_id,
        course_id=course_id,
    )
    async with get_async_session() as session:
        session.add(session_obj)
        await session.flush()
        session_id = session_obj.id

    async with get_async_session() as session:
        result = await session.execute(
            select(RaceSession).where(RaceSession.id == session_id)
        )
        saved = result.scalar_one()
        return saved.to_summary_dict()


async def get_race_session(session_id: int) -> RaceSession | None:
    async with get_async_session() as session:
        result = await session.execute(
            select(RaceSession).where(RaceSession.id == session_id)
        )
        return result.scalar_one_or_none()


async def get_all_race_sessions() -> list[dict]:
    """Return summary dicts for all sessions with athlete count, newest first."""
    async with get_async_session() as session:
        # Count athletes per session in a single query
        count_q = (
            select(
                RaceSessionAthlete.session_id,
                func.count(RaceSessionAthlete.id).label("athlete_count"),
            )
            .group_by(RaceSessionAthlete.session_id)
            .subquery()
        )
        result = await session.execute(
            select(RaceSession, count_q.c.athlete_count)
            .outerjoin(count_q, RaceSession.id == count_q.c.session_id)
            .order_by(RaceSession.created_at.desc())
        )
        rows = result.all()
    out = []
    for rs, athlete_count in rows:
        d = rs.to_summary_dict()
        d["athlete_count"] = athlete_count or 0
        out.append(d)
    return out


async def delete_race_session(session_id: int) -> bool:
    """Delete a session and all related data. Returns True if found."""
    async with get_async_session() as session:
        # Delete child rows first
        for model in [
            RaceSessionAthlete,
            RaceSessionGap,
            RaceSessionEvent,
            RaceSessionSegment,
        ]:
            rows = await session.execute(
                select(model).where(model.session_id == session_id)
            )
            for row in rows.scalars().all():
                await session.delete(row)

        result = await session.execute(
            select(RaceSession).where(RaceSession.id == session_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return False
        await session.delete(obj)
    return True


# ---------------------------------------------------------------------------
# Race Session Athletes
# ---------------------------------------------------------------------------


async def add_session_athlete(
    session_id: int,
    athlete_label: str,
    is_primary: bool,
    activity_id: int | None,
    stream_dict: dict,
    metrics_dict: dict,
) -> dict:
    """Persist an athlete's normalised stream and metrics."""
    athlete = RaceSessionAthlete(
        session_id=session_id,
        athlete_label=athlete_label,
        is_primary=is_primary,
        activity_id=activity_id,
        stream_json=json.dumps(stream_dict),
        metrics_json=json.dumps(metrics_dict),
    )
    async with get_async_session() as session:
        session.add(athlete)
        await session.flush()
        athlete_id = athlete.id

    async with get_async_session() as session:
        result = await session.execute(
            select(RaceSessionAthlete).where(RaceSessionAthlete.id == athlete_id)
        )
        saved = result.scalar_one()
        return saved.to_summary_dict()


async def get_session_athletes(session_id: int) -> list[RaceSessionAthlete]:
    async with get_async_session() as session:
        result = await session.execute(
            select(RaceSessionAthlete)
            .where(RaceSessionAthlete.session_id == session_id)
            .order_by(RaceSessionAthlete.is_primary.desc(), RaceSessionAthlete.added_at)
        )
        return result.scalars().all()


# ---------------------------------------------------------------------------
# Gap series
# ---------------------------------------------------------------------------


async def save_gap_series(
    session_id: int,
    gap_series: dict[str, list[dict]],
    delta_series: dict[str, list[dict]],
) -> None:
    """Persist gap and delta series for all athletes in a session."""
    async with get_async_session() as session:
        # Remove existing gap rows for this session
        existing = await session.execute(
            select(RaceSessionGap).where(RaceSessionGap.session_id == session_id)
        )
        for row in existing.scalars().all():
            await session.delete(row)

        for label, series in gap_series.items():
            deltas = delta_series.get(label, [])
            gap_row = RaceSessionGap(
                session_id=session_id,
                athlete_label=label,
                gap_series_json=json.dumps(series),
                delta_series_json=json.dumps(deltas),
            )
            session.add(gap_row)


async def get_gap_series(session_id: int) -> list[dict]:
    """Return [{athlete_label, gap_series, delta_series}] for all athletes."""
    async with get_async_session() as session:
        result = await session.execute(
            select(RaceSessionGap).where(RaceSessionGap.session_id == session_id)
        )
        rows = result.scalars().all()
    return [
        {
            "athlete_label": r.athlete_label,
            "gap_series": r.get_gap_series(),
            "delta_series": r.get_delta_series(),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


async def save_events(session_id: int, events: list) -> None:
    """Persist RaceEvent list. events are RaceEvent dataclass instances."""
    async with get_async_session() as session:
        # Remove existing
        existing = await session.execute(
            select(RaceSessionEvent).where(RaceSessionEvent.session_id == session_id)
        )
        for row in existing.scalars().all():
            await session.delete(row)

        for ev in events:
            row = RaceSessionEvent(
                session_id=session_id,
                event_type=ev.event_type,
                athlete_label=ev.athlete_label,
                distance_km=ev.distance_km,
                elapsed_s=ev.elapsed_s,
                impact_s=ev.impact_s,
                description=ev.description,
            )
            session.add(row)


async def get_events(session_id: int) -> list[dict]:
    async with get_async_session() as session:
        result = await session.execute(
            select(RaceSessionEvent)
            .where(RaceSessionEvent.session_id == session_id)
            .order_by(RaceSessionEvent.distance_km)
        )
        return [r.to_dict() for r in result.scalars().all()]


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------


async def save_segments(
    session_id: int,
    segments: list,  # DetectedSegment instances
    athlete_metrics: dict[str, dict[str, dict]],
) -> None:
    """Persist detected segments with per-athlete metrics."""
    async with get_async_session() as session:
        existing = await session.execute(
            select(RaceSessionSegment).where(
                RaceSessionSegment.session_id == session_id
            )
        )
        for row in existing.scalars().all():
            await session.delete(row)

        for seg in segments:
            metrics = athlete_metrics.get(seg.label, {})
            row = RaceSessionSegment(
                session_id=session_id,
                segment_label=seg.label,
                start_km=seg.start_km,
                end_km=seg.end_km,
                gradient_type=seg.gradient_type,
                avg_grade_pct=seg.avg_grade_pct,
                athlete_metrics_json=json.dumps(metrics),
            )
            session.add(row)


async def get_segments(session_id: int) -> list[dict]:
    async with get_async_session() as session:
        result = await session.execute(
            select(RaceSessionSegment)
            .where(RaceSessionSegment.session_id == session_id)
            .order_by(RaceSessionSegment.start_km)
        )
        return [r.to_dict() for r in result.scalars().all()]


# ---------------------------------------------------------------------------
# Full session detail
# ---------------------------------------------------------------------------


async def get_session_detail(session_id: int) -> dict | None:
    """Return a fully assembled session detail dict."""
    sess = await get_race_session(session_id)
    if sess is None:
        return None

    athletes = await get_session_athletes(session_id)
    gap_data = await get_gap_series(session_id)
    events = await get_events(session_id)
    segments = await get_segments(session_id)

    return {
        "session": sess.to_summary_dict(),
        "athletes": [a.to_summary_dict() for a in athletes],
        "gap_data": gap_data,
        "events": events,
        "segments": segments,
    }
