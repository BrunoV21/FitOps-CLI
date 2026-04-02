from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.analytics.weather_pace import pace_heat_factor, wbgt_approx
from fitops.config.settings import get_settings
from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.models.workout import Workout
from fitops.db.session import get_async_session
from fitops.strava.client import StravaClient
from fitops.strava.sync_engine import SyncEngine
from fitops.weather.client import fetch_activity_weather

router = APIRouter()


async def _fetch_streams(limit: int = 0, force: bool = False) -> dict:
    """Fetch and cache streams for activities missing them (or all if force=True).

    limit=0 fetches all matching activities.
    """
    async with get_async_session() as session:
        stmt = select(Activity.id, Activity.strava_id).order_by(
            Activity.start_date.desc()
        )
        if not force:
            stmt = stmt.where(Activity.streams_fetched == False)  # noqa: E712
        if limit > 0:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        rows = result.fetchall()

    if not rows:
        return {"streams_fetched": 0, "errors": 0}

    client = StravaClient()
    fetched = errors = 0
    total = len(rows)
    for idx, (internal_id, strava_id) in enumerate(rows, 1):
        try:
            if force:
                async with get_async_session() as session:
                    await session.execute(
                        sa_delete(ActivityStream).where(
                            ActivityStream.activity_id == internal_id
                        )
                    )
            stream_data = await client.get_activity_streams(strava_id)
            async with get_async_session() as session:
                for stream_type, stream_obj in stream_data.items():
                    data_list = (
                        stream_obj.get("data", [])
                        if isinstance(stream_obj, dict)
                        else stream_obj
                    )
                    if not force:
                        existing = await session.execute(
                            select(ActivityStream).where(
                                ActivityStream.activity_id == internal_id,
                                ActivityStream.stream_type == stream_type,
                            )
                        )
                        if existing.scalar_one_or_none() is not None:
                            continue
                    session.add(
                        ActivityStream.from_strava_stream(
                            internal_id, stream_type, data_list
                        )
                    )
                row = (
                    await session.execute(
                        select(Activity).where(Activity.id == internal_id)
                    )
                ).scalar_one_or_none()
                if row:
                    row.streams_fetched = True
            fetched += 1
        except Exception:
            errors += 1
        # Rate limit: ~1 req/sec to stay under 100 req/15min
        if idx < total:
            await asyncio.sleep(1.0)
    return {"streams_fetched": fetched, "errors": errors}


async def _fetch_weather_for_new_activities(strava_ids: list[int]) -> dict:
    """Fetch and store weather for a list of strava_ids that were just synced."""
    import json as _json

    from fitops.dashboard.queries.weather import upsert_activity_weather

    fetched = errors = 0
    async with get_async_session() as session:
        result = await session.execute(
            select(Activity).where(Activity.strava_id.in_(strava_ids))
        )
        acts = result.scalars().all()

    for act in acts:
        if not act.start_latlng or not act.start_date:
            continue
        try:
            coords = _json.loads(act.start_latlng)
            if not (isinstance(coords, list) and len(coords) == 2):
                continue
            lat, lng = float(coords[0]), float(coords[1])
            weather = await fetch_activity_weather(lat, lng, act.start_date)
            if weather:
                tc = weather.get("temperature_c")
                hum = weather.get("humidity_pct")
                if tc is not None and hum is not None:
                    weather["wbgt_c"] = round(wbgt_approx(tc, hum), 2)
                    weather["pace_heat_factor"] = round(pace_heat_factor(tc, hum), 4)
                await upsert_activity_weather(
                    act.strava_id, weather, source="open-meteo"
                )
                fetched += 1
        except Exception:
            errors += 1
        await asyncio.sleep(0.1)

    return {"weather_fetched": fetched, "weather_errors": errors}


def register() -> APIRouter:
    @router.post("/api/sync")
    async def api_sync():
        settings = get_settings()
        if not settings.athlete_id:
            return JSONResponse(
                {"error": "Not authenticated. Run fitops auth login first."},
                status_code=401,
            )

        engine = SyncEngine()
        result = await engine.run(full=False)

        streams_result = None
        weather_result = None
        if result.activities_created > 0:
            streams_result = await _fetch_streams(limit=result.activities_created)
            # Get strava_ids of the newest activities (same count as created)
            async with get_async_session() as session:
                newest = await session.execute(
                    select(Activity.strava_id)
                    .where(Activity.athlete_id == settings.athlete_id)
                    .order_by(Activity.start_date.desc())
                    .limit(result.activities_created)
                )
                new_strava_ids = [r[0] for r in newest.all()]
            weather_result = await _fetch_weather_for_new_activities(new_strava_ids)

        return JSONResponse(
            {
                "activities_created": result.activities_created,
                "activities_updated": result.activities_updated,
                "pages_fetched": result.pages_fetched,
                "duration_s": round(result.duration_s, 2),
                "streams": streams_result,
                "weather": weather_result,
                "synced_at": datetime.now(UTC).isoformat(),
            }
        )

    @router.post("/api/sync/streams")
    async def api_sync_streams(force: bool = False, limit: int = 0):
        settings = get_settings()
        if not settings.athlete_id:
            return JSONResponse(
                {"error": "Not authenticated. Run fitops auth login first."},
                status_code=401,
            )

        result = await _fetch_streams(limit=limit, force=force)
        return JSONResponse(
            {
                **result,
                "synced_at": datetime.now(UTC).isoformat(),
            }
        )

    @router.post("/api/sync/streams/{strava_id}")
    async def api_sync_activity_streams(strava_id: int):
        settings = get_settings()
        if not settings.athlete_id:
            return JSONResponse(
                {"error": "Not authenticated. Run fitops auth login first."},
                status_code=401,
            )

        async with get_async_session() as session:
            row = (
                await session.execute(
                    select(Activity).where(Activity.strava_id == strava_id)
                )
            ).scalar_one_or_none()

        if row is None:
            return JSONResponse({"error": "Activity not found."}, status_code=404)

        client = StravaClient()
        try:
            stream_data = await client.get_activity_streams(strava_id)
            async with get_async_session() as session:
                activity = (
                    await session.execute(
                        select(Activity).where(Activity.strava_id == strava_id)
                    )
                ).scalar_one_or_none()
                if activity:
                    for stream_type, stream_obj in stream_data.items():
                        data_list = (
                            stream_obj.get("data", [])
                            if isinstance(stream_obj, dict)
                            else stream_obj
                        )
                        existing = await session.execute(
                            select(ActivityStream).where(
                                ActivityStream.activity_id == activity.id,
                                ActivityStream.stream_type == stream_type,
                            )
                        )
                        if existing.scalar_one_or_none() is None:
                            session.add(
                                ActivityStream.from_strava_stream(
                                    activity.id, stream_type, data_list
                                )
                            )
                    activity.streams_fetched = True
            # Also fetch weather while we're here
            weather_ok = False
            try:
                wr = await _fetch_weather_for_new_activities([strava_id])
                weather_ok = wr.get("weather_fetched", 0) > 0
            except Exception:
                pass
            return JSONResponse(
                {
                    "ok": True,
                    "streams_fetched": len(stream_data),
                    "weather_fetched": weather_ok,
                }
            )
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    _ALLOWED_METRIC_KEYS = {
        "max_hr",
        "lthr",
        "lt1_hr",
        "vo2max_override",
        "threshold_pace_per_km_s",
        "lt1_pace_s",
    }

    @router.post("/api/settings/metric")
    async def update_athlete_metric(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        key = payload.get("key")
        value = payload.get("value")
        if key not in _ALLOWED_METRIC_KEYS or value is None:
            return JSONResponse({"error": "invalid key or value"}, status_code=400)
        try:
            value = float(value)
        except (TypeError, ValueError):
            return JSONResponse({"error": "value must be numeric"}, status_code=400)
        get_athlete_settings().set(**{key: value})
        return JSONResponse({"ok": True, "key": key, "value": value})

    @router.post("/api/activities/{strava_id}/assign-workout")
    async def assign_workout(strava_id: int, request: Request):
        settings = get_settings()
        if not settings.athlete_id:
            return JSONResponse({"error": "Not authenticated."}, status_code=401)
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        workout_id = payload.get("workout_id")
        if not workout_id:
            return JSONResponse({"error": "workout_id required"}, status_code=400)

        async with get_async_session() as session:
            # Resolve activity
            act = (
                await session.execute(
                    select(Activity).where(
                        Activity.strava_id == strava_id,
                        Activity.athlete_id == settings.athlete_id,
                    )
                )
            ).scalar_one_or_none()
            if act is None:
                return JSONResponse({"error": "Activity not found."}, status_code=404)

            # Resolve workout (must belong to this athlete)
            wkt = (
                await session.execute(
                    select(Workout).where(
                        Workout.id == workout_id,
                        Workout.athlete_id == settings.athlete_id,
                    )
                )
            ).scalar_one_or_none()
            if wkt is None:
                return JSONResponse({"error": "Workout not found."}, status_code=404)

            # Unlink any other workout already assigned to this activity
            prev = (
                await session.execute(
                    select(Workout).where(Workout.activity_id == act.id)
                )
            ).scalar_one_or_none()
            if prev and prev.id != wkt.id:
                prev.activity_id = None
                prev.linked_at = None
                prev.status = "planned"

            # Assign
            wkt.activity_id = act.id
            wkt.linked_at = datetime.now(UTC)
            wkt.status = "completed"

        return JSONResponse(
            {"ok": True, "workout_id": wkt.id, "workout_name": wkt.name}
        )

    @router.post("/api/activities/{strava_id}/unassign-workout")
    async def unassign_workout(strava_id: int):
        settings = get_settings()
        if not settings.athlete_id:
            return JSONResponse({"error": "Not authenticated."}, status_code=401)

        async with get_async_session() as session:
            act = (
                await session.execute(
                    select(Activity).where(
                        Activity.strava_id == strava_id,
                        Activity.athlete_id == settings.athlete_id,
                    )
                )
            ).scalar_one_or_none()
            if act is None:
                return JSONResponse({"error": "Activity not found."}, status_code=404)

            wkt = (
                await session.execute(
                    select(Workout).where(Workout.activity_id == act.id)
                )
            ).scalar_one_or_none()
            if wkt is None:
                return JSONResponse({"error": "No workout linked."}, status_code=404)

            wkt.activity_id = None
            wkt.linked_at = None
            wkt.status = "planned"

        return JSONResponse({"ok": True})

    return router
