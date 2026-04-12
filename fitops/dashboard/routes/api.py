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
from fitops.db.models.workout_activity_link import WorkoutActivityLink
from fitops.db.models.workout_segment import WorkoutSegment
from fitops.db.session import get_async_session
from fitops.strava.client import StravaClient
from fitops.strava.sync_engine import SyncEngine
from fitops.weather.client import fetch_activity_weather, fetch_forecast_weather

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
        return {"streams_fetched": 0, "errors": 0, "strava_ids": []}

    client = StravaClient()
    fetched = errors = 0
    fetched_strava_ids: list[int] = []
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
            # Silently try to auto-associate to a race plan
            try:
                from fitops.analytics.race_plan import match_activity_to_plans

                await match_activity_to_plans(internal_id)
            except Exception:
                pass
            fetched += 1
            fetched_strava_ids.append(strava_id)
        except Exception:
            errors += 1
        # Rate limit: ~1 req/sec to stay under 100 req/15min
        if idx < total:
            await asyncio.sleep(1.0)
    return {
        "streams_fetched": fetched,
        "errors": errors,
        "strava_ids": fetched_strava_ids,
    }


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
            # Archive API has ~5-day lag — fall back to forecast API for recent activities
            if weather is None:
                date_str = act.start_date.strftime("%Y-%m-%d")
                weather = await fetch_forecast_weather(
                    lat, lng, date_str, act.start_date.hour
                )
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

        # Always sweep for unlinked plans — catches plans created after their
        # matching activity was already synced.
        plans_linked = 0
        try:
            from fitops.analytics.race_plan import sweep_unlinked_plans

            plans_linked = await sweep_unlinked_plans()
        except Exception:
            pass

        return JSONResponse(
            {
                "activities_created": result.activities_created,
                "activities_updated": result.activities_updated,
                "pages_fetched": result.pages_fetched,
                "duration_s": round(result.duration_s, 2),
                "streams": streams_result,
                "weather": weather_result,
                "plans_linked": plans_linked,
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
        weather_result = None
        if result.get("strava_ids"):
            weather_result = await _fetch_weather_for_new_activities(
                result["strava_ids"]
            )
        return JSONResponse(
            {
                "streams_fetched": result["streams_fetched"],
                "errors": result["errors"],
                "weather": weather_result,
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

    @router.post("/api/sync/weather/{strava_id}")
    async def api_sync_activity_weather(strava_id: int):
        import json as _json

        from fitops.dashboard.queries.weather import upsert_activity_weather

        settings = get_settings()
        if not settings.athlete_id:
            return JSONResponse({"error": "Not authenticated."}, status_code=401)

        async with get_async_session() as session:
            row = (
                await session.execute(
                    select(Activity).where(Activity.strava_id == strava_id)
                )
            ).scalar_one_or_none()

        if row is None:
            return JSONResponse({"error": "Activity not found."}, status_code=404)
        if not row.start_latlng or not row.start_date:
            return JSONResponse(
                {"error": "Activity has no GPS coordinates."}, status_code=422
            )

        try:
            coords = _json.loads(row.start_latlng)
            if not (isinstance(coords, list) and len(coords) == 2):
                raise ValueError("bad coords")
            lat, lng = float(coords[0]), float(coords[1])
        except Exception:
            return JSONResponse({"error": "Invalid coordinates."}, status_code=422)

        # Try archive API first; fall back to forecast for recent activities
        weather = await fetch_activity_weather(lat, lng, row.start_date)
        if weather is None:
            date_str = row.start_date.strftime("%Y-%m-%d")
            weather = await fetch_forecast_weather(
                lat, lng, date_str, row.start_date.hour
            )

        if weather is None:
            return JSONResponse(
                {"error": "Weather data unavailable for this date/location."},
                status_code=502,
            )

        tc = weather.get("temperature_c")
        hum = weather.get("humidity_pct")
        if tc is not None and hum is not None:
            weather["wbgt_c"] = round(wbgt_approx(tc, hum), 2)
            weather["pace_heat_factor"] = round(pace_heat_factor(tc, hum), 4)

        await upsert_activity_weather(strava_id, weather, source="open-meteo")
        return JSONResponse({"ok": True})

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

            # If this activity already has a different workout linked, remove that link
            prev_link = (
                await session.execute(
                    select(WorkoutActivityLink).where(
                        WorkoutActivityLink.activity_id == act.id
                    )
                )
            ).scalar_one_or_none()
            if prev_link and prev_link.workout_id != wkt.id:
                await session.delete(prev_link)

            # Upsert the WorkoutActivityLink for this (workout, activity) pair
            link = prev_link if (prev_link and prev_link.workout_id == wkt.id) else None
            if link is None:
                link = WorkoutActivityLink(
                    workout_id=wkt.id,
                    activity_id=act.id,
                    linked_at=datetime.now(UTC),
                    status="completed",
                )
                session.add(link)
            else:
                link.linked_at = datetime.now(UTC)
                link.status = "completed"

            activity_internal_id = act.id
            workout_id_assigned = wkt.id
            workout_name_assigned = wkt.name

        # Run compliance scoring automatically after assignment
        compliance_result = None
        compliance_error = None
        try:
            from fitops.workouts.engine import run_compliance_for_activity

            result, err = await run_compliance_for_activity(
                activity_internal_id, recalculate=True
            )
            if err:
                compliance_error = err
            else:
                compliance_result = result
        except Exception as exc:
            compliance_error = str(exc)

        return JSONResponse(
            {
                "ok": True,
                "workout_id": workout_id_assigned,
                "workout_name": workout_name_assigned,
                "compliance": compliance_result,
                "compliance_error": compliance_error,
            }
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

            link = (
                await session.execute(
                    select(WorkoutActivityLink).where(
                        WorkoutActivityLink.activity_id == act.id
                    )
                )
            ).scalar_one_or_none()
            if link is None:
                return JSONResponse({"error": "No workout linked."}, status_code=404)

            workout_id_to_clean = link.workout_id
            await session.delete(link)
            # Also remove the compliance segments for this (workout, activity) pair
            await session.execute(
                sa_delete(WorkoutSegment).where(
                    WorkoutSegment.workout_id == workout_id_to_clean,
                    WorkoutSegment.activity_id == act.id,
                )
            )

        return JSONResponse({"ok": True})

    return router
