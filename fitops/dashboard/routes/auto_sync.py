from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fitops.config.settings import get_settings
from fitops.config.state import get_sync_state
from fitops.utils.logging import get_logger

logger = get_logger(__name__)

_AUTO_SYNC_INTERVAL_S = 3 * 3600  # re-sync every 3 hours
_CHECK_INTERVAL_S = 60
_sync_lock = asyncio.Lock()


async def run_auto_sync_scheduler() -> None:
    """Long-running asyncio task started by the FastAPI lifespan.

    Runs an incremental Strava sync immediately if the last sync was more than
    3 hours ago (covers the "haven't synced today" case on first open), then
    re-checks every minute and syncs again whenever 3 hours have elapsed.
    Gracefully exits on cancellation.
    """
    # Immediate check so the first dashboard open auto-syncs without waiting.
    try:
        await _maybe_auto_sync()
    except Exception:
        pass

    while True:
        try:
            await asyncio.sleep(_CHECK_INTERVAL_S)
            await _maybe_auto_sync()
        except asyncio.CancelledError:
            break
        except Exception:
            pass


async def _maybe_auto_sync() -> None:
    settings = get_settings()
    if not settings.is_authenticated:
        return

    state = get_sync_state()
    last = state.last_sync_at
    now = datetime.now(UTC)

    if last is not None and (now - last).total_seconds() < _AUTO_SYNC_INTERVAL_S:
        return

    if _sync_lock.locked():
        return

    async with _sync_lock:
        # Re-check inside the lock in case another task just finished a sync.
        state.reload()
        last = state.last_sync_at
        if last is not None and (now - last).total_seconds() < _AUTO_SYNC_INTERVAL_S:
            return

        logger.info("auto-sync: starting background incremental sync")
        try:
            from sqlalchemy import select

            from fitops.db.models.activity import Activity
            from fitops.db.session import get_async_session
            from fitops.dashboard.routes.api import (
                _fetch_streams,
                _fetch_weather_for_new_activities,
            )
            from fitops.strava.sync_engine import SyncEngine

            result = await SyncEngine().run()
            logger.info(
                "auto-sync: done — %d created, %d updated in %.1fs",
                result.activities_created,
                result.activities_updated,
                result.duration_s,
            )
            if result.activities_created > 0:
                logger.info(
                    "auto-sync: fetching streams + weather for %d new activities",
                    result.activities_created,
                )
                await _fetch_streams(limit=result.activities_created)
                async with get_async_session() as session:
                    newest = await session.execute(
                        select(Activity.strava_id)
                        .where(Activity.athlete_id == settings.athlete_id)
                        .order_by(Activity.start_date.desc())
                        .limit(result.activities_created)
                    )
                    new_strava_ids = [r[0] for r in newest.all()]
                await _fetch_weather_for_new_activities(new_strava_ids)
        except Exception as exc:
            logger.warning("auto-sync: sync failed — %s", exc)
