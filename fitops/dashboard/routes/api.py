from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import select

from fitops.config.settings import get_settings
from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.session import get_async_session
from fitops.strava.client import StravaClient
from fitops.strava.sync_engine import SyncEngine

router = APIRouter()

_STREAMS_BATCH = 50


async def _fetch_streams_for_new(limit: int) -> dict:
    """Fetch and cache streams for activities that don't have them yet."""
    async with get_async_session() as session:
        result = await session.execute(
            select(Activity.id, Activity.strava_id)
            .where(Activity.streams_fetched == False)  # noqa: E712
            .where(Activity.average_heartrate.isnot(None))
            .order_by(Activity.start_date.desc())
            .limit(limit)
        )
        rows = result.fetchall()
    if not rows:
        return {"streams_fetched": 0, "errors": 0}

    client = StravaClient()
    fetched = errors = 0
    for internal_id, strava_id in rows:
        try:
            stream_data = await client.get_activity_streams(strava_id)
            async with get_async_session() as session:
                for stream_type, stream_obj in stream_data.items():
                    data_list = stream_obj.get("data", []) if isinstance(stream_obj, dict) else stream_obj
                    existing = await session.execute(
                        select(ActivityStream).where(
                            ActivityStream.activity_id == internal_id,
                            ActivityStream.stream_type == stream_type,
                        )
                    )
                    if existing.scalar_one_or_none() is None:
                        session.add(ActivityStream.from_strava_stream(internal_id, stream_type, data_list))
                row = (await session.execute(
                    select(Activity).where(Activity.id == internal_id)
                )).scalar_one_or_none()
                if row:
                    row.streams_fetched = True
            fetched += 1
        except Exception:
            errors += 1
    return {"streams_fetched": fetched, "errors": errors}


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
        if result.activities_created > 0:
            streams_result = await _fetch_streams_for_new(_STREAMS_BATCH)

        return JSONResponse({
            "activities_created": result.activities_created,
            "activities_updated": result.activities_updated,
            "pages_fetched": result.pages_fetched,
            "duration_s": round(result.duration_s, 2),
            "streams": streams_result,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        })

    return router
