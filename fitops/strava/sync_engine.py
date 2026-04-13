from __future__ import annotations

import time
from datetime import datetime, timedelta

from sqlalchemy import select

from fitops.analytics.athlete_settings import AthleteSettings
from fitops.analytics.training_scores import compute_aerobic_score, compute_anaerobic_score
from fitops.config.settings import get_settings
from fitops.config.state import get_sync_state
from fitops.db.models.activity import Activity
from fitops.db.models.athlete import Athlete
from fitops.db.session import get_async_session
from fitops.strava.client import StravaClient
from fitops.utils.logging import get_logger

logger = get_logger(__name__)

MAX_PAGES = 100
PER_PAGE = 30
OVERLAP_DAYS = 3


class SyncResult:
    def __init__(self) -> None:
        self.activities_created = 0
        self.activities_updated = 0
        self.pages_fetched = 0
        self.duration_s = 0.0

    def __repr__(self) -> str:
        return (
            f"SyncResult(created={self.activities_created}, "
            f"updated={self.activities_updated}, "
            f"pages={self.pages_fetched}, "
            f"duration={self.duration_s:.1f}s)"
        )


class SyncEngine:
    """Incremental Strava activity sync engine."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = StravaClient()

    def _determine_sync_parameters(
        self,
        *,
        full: bool = False,
        after_override: datetime | None = None,
        before_override: datetime | None = None,
    ) -> tuple[int | None, int | None, str]:
        """Return (after_epoch, before_epoch, sync_type)."""
        if full:
            return None, None, "full"

        if after_override is not None:
            after_epoch = int(after_override.timestamp())
            return after_epoch, None, "custom"

        state = get_sync_state()
        last_sync = state.last_sync_at
        if last_sync is None:
            return None, None, "initial"

        overlap = last_sync - timedelta(days=OVERLAP_DAYS)
        after_epoch = int(overlap.timestamp())
        return after_epoch, None, "incremental"

    async def _upsert_athlete(self) -> int:
        """Sync athlete profile and return their strava_id."""
        athlete_data = await self._client.get_authenticated_athlete()
        strava_id = athlete_data["id"]

        async with get_async_session() as session:
            result = await session.execute(
                select(Athlete).where(Athlete.strava_id == strava_id)
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                athlete = Athlete.from_strava_data(athlete_data)
                session.add(athlete)
            else:
                existing.update_from_strava_data(athlete_data)

        return strava_id

    async def _sync_activities_paginated(
        self,
        athlete_id: int,
        after: int | None,
        before: int | None,
        result: SyncResult,
        settings: AthleteSettings,
    ) -> None:
        for page in range(1, MAX_PAGES + 1):
            activities = await self._client.list_athlete_activities(
                after=after,
                before=before,
                page=page,
                per_page=PER_PAGE,
            )
            if not activities:
                break

            result.pages_fetched += 1

            async with get_async_session() as session:
                for item in activities:
                    strava_id = item.get("id")
                    if strava_id is None:
                        continue

                    existing = await session.execute(
                        select(Activity).where(Activity.strava_id == strava_id)
                    )
                    existing_row = existing.scalar_one_or_none()

                    if existing_row is None:
                        activity = Activity.from_strava_data(item, athlete_id)
                        activity.aerobic_score = compute_aerobic_score(activity, settings)
                        activity.anaerobic_score = compute_anaerobic_score(activity, settings)
                        session.add(activity)
                        result.activities_created += 1
                    else:
                        existing_row.update_from_strava_data(item)
                        existing_row.aerobic_score = compute_aerobic_score(existing_row, settings)
                        existing_row.anaerobic_score = compute_anaerobic_score(existing_row, settings)
                        result.activities_updated += 1

            if len(activities) < PER_PAGE:
                break

    async def run(
        self,
        *,
        full: bool = False,
        after_override: datetime | None = None,
        before_override: datetime | None = None,
    ) -> SyncResult:
        start_time = time.monotonic()
        result = SyncResult()

        after, before, sync_type = self._determine_sync_parameters(
            full=full,
            after_override=after_override,
            before_override=before_override,
        )

        athlete_id = await self._upsert_athlete()
        athlete_settings = AthleteSettings()
        await self._sync_activities_paginated(athlete_id, after, before, result, athlete_settings)

        result.duration_s = time.monotonic() - start_time

        state = get_sync_state()
        state.update_after_sync(
            sync_type=sync_type,
            activities_created=result.activities_created,
            activities_updated=result.activities_updated,
            duration_s=result.duration_s,
        )

        return result
