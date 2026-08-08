from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from fitops.analytics.stamp import stamp_activity
from fitops.browser.description import append_activity_description
from fitops.browser.upload import (
    upload_activity_bytes as upload_activity_data,
)
from fitops.browser.upload import (
    upload_activity_file,
)
from fitops.db.models.activity import Activity
from fitops.db.models.activity_publication import ActivityPublication
from fitops.db.session import get_async_session
from fitops.utils.exceptions import BrowserPublicationError

_STAMP_ANCHOR = "📊 FitOps Analytics"


def _stamp_from_description(description: str) -> str:
    """Return only the FitOps footer for browser-based description sync."""
    position = description.find(_STAMP_ANCHOR)
    if position < 0:
        raise BrowserPublicationError(
            "FitOps could not build the activity stamp.",
            code="activity_stamp_missing",
            status_code=500,
        )
    return description[position:].strip()


async def _mark_publication_failed(
    publication_id: int, exc: BrowserPublicationError
) -> None:
    async with get_async_session() as session:
        row = await session.get(ActivityPublication, publication_id)
        if row is not None:
            row.status = "failed"
            row.error_code = exc.code
            row.error_message = str(exc)
            row.updated_at = datetime.now(UTC)


async def publish_activity(
    activity_id: int,
    *,
    strava_id: int | None = None,
    source_path: str | Path | None = None,
    source_bytes: tuple[bytes, str] | None = None,
) -> ActivityPublication:
    """Upload during import or sync a local activity to an existing Strava ID."""
    async with get_async_session() as session:
        activity = await session.get(Activity, activity_id)
        if activity is None:
            raise BrowserPublicationError(
                f"Activity {activity_id} was not found.",
                code="activity_not_found",
                status_code=404,
            )

        target_strava_id = strava_id or activity.strava_id
        if target_strava_id is not None and target_strava_id <= 0:
            raise BrowserPublicationError(
                "Strava activity ID must be a positive integer.",
                code="invalid_strava_id",
            )
        if target_strava_id is not None:
            linked = (
                await session.execute(
                    select(Activity.id).where(
                        Activity.strava_id == target_strava_id,
                        Activity.id != activity.id,
                    )
                )
            ).scalar_one_or_none()
            if linked is not None:
                raise BrowserPublicationError(
                    f"Strava activity {target_strava_id} is already linked to local activity {linked}.",
                    code="strava_activity_already_linked",
                    status_code=409,
                )
        elif source_path is None and source_bytes is None:
            raise BrowserPublicationError(
                "FitOps does not retain imported files. Post during import, or provide an existing Strava activity ID to sync.",
                code="source_file_not_retained",
                status_code=409,
            )

        await stamp_activity(None, session, activity, local_only=True)
        description = activity.description or ""
        stamp = _stamp_from_description(description)
        publication = ActivityPublication(
            activity_id=activity.id,
            action="sync" if target_strava_id else "upload",
            status="running",
            strava_id=target_strava_id,
        )
        session.add(publication)
        await session.flush()
        publication_id = publication.id
        title = activity.name
        sport_type = activity.sport_type

    try:
        if target_strava_id is not None:
            await asyncio.to_thread(
                append_activity_description,
                target_strava_id,
                stamp,
            )
            published_id = target_strava_id
        else:
            if source_bytes is not None:
                data, filename = source_bytes
                upload_result = await asyncio.to_thread(
                    upload_activity_data,
                    data,
                    filename,
                    title=title,
                    description=description,
                    sport_type=sport_type,
                )
            else:
                upload_result = await asyncio.to_thread(
                    upload_activity_file,
                    Path(source_path),
                    title=title,
                    description=description,
                    sport_type=sport_type,
                )
            published_id = upload_result.strava_activity_id
    except Exception as raw_exc:
        exc = (
            raw_exc
            if isinstance(raw_exc, BrowserPublicationError)
            else BrowserPublicationError(
                f"Browser automation failed: {raw_exc}",
                code="browser_automation_failed",
                status_code=502,
            )
        )
        await _mark_publication_failed(publication_id, exc)
        if exc is raw_exc:
            raise
        raise exc from raw_exc

    async with get_async_session() as session:
        row = await session.get(ActivityPublication, publication_id)
        activity = await session.get(Activity, activity_id)
        if row is None or activity is None:
            raise BrowserPublicationError(
                "Publication state was lost.", code="publication_state_missing"
            )
        row.status = "completed"
        row.strava_id = published_id
        row.updated_at = datetime.now(UTC)
        activity.strava_id = published_id
        activity.description = description
        activity.stamped_at = datetime.now(UTC)
        return row


async def publish_activity_bytes(
    activity_id: int,
    data: bytes,
    filename: str,
) -> ActivityPublication:
    """Upload request bytes without writing or retaining another source file."""
    return await publish_activity(
        activity_id,
        source_bytes=(data, filename),
    )
