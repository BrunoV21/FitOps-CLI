from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from fitops.analytics.stamp import apply_stamp, compose_stamp
from fitops.browser.config import ensure_profile_available, resolve_browser_profile
from fitops.config.settings import get_settings
from fitops.db.models.activity import Activity
from fitops.db.models.activity_import import ActivityImport
from fitops.db.models.activity_publication import ActivityPublication
from fitops.db.session import get_async_session
from fitops.utils.exceptions import BrowserPublicationError

_ACTIVITY_URL_RE = re.compile(r"/activities/(\d+)")


def _fill_first(page, selectors: list[str], value: str) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count():
            locator.fill(value)
            return
    raise BrowserPublicationError(
        "Strava's page no longer exposes an expected form field.",
        code="strava_page_changed",
    )


def _click_first(page, labels: list[str]) -> None:
    for label in labels:
        button = page.get_by_role("button", name=re.compile(label, re.I)).first
        if button.count():
            button.click()
            return
    raise BrowserPublicationError(
        "Strava's page no longer exposes an expected publish button.",
        code="strava_page_changed",
    )


def _run_browser(
    *,
    source_path: Path | None,
    title: str,
    description: str,
    existing_strava_id: int | None,
) -> int:
    profile = resolve_browser_profile()
    ensure_profile_available(profile)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserPublicationError(
            "Browser publishing requires Playwright. Reinstall FitOps dependencies.",
            code="playwright_missing",
            status_code=500,
        ) from exc

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile.user_data_dir),
            executable_path=str(profile.executable),
            headless=False,
            args=[f"--profile-directory={profile.profile}"],
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            if existing_strava_id is not None:
                page.goto(
                    f"https://www.strava.com/activities/{existing_strava_id}/edit",
                    wait_until="domcontentloaded",
                )
            else:
                if source_path is None:
                    raise BrowserPublicationError(
                        "The original GPX/TCX file is missing.",
                        code="source_file_missing",
                    )
                page.goto(
                    "https://www.strava.com/upload/select",
                    wait_until="domcontentloaded",
                )
                upload = page.locator("input[type=file]").first
                if not upload.count():
                    raise BrowserPublicationError(
                        "Strava's upload control was not found. Check that the selected profile is logged in.",
                        code="strava_login_required",
                        status_code=401,
                    )
                upload.set_input_files(str(source_path))

            if "/login" in page.url or "/session" in page.url:
                raise BrowserPublicationError(
                    "The selected browser profile is not logged in to Strava.",
                    code="strava_login_required",
                    status_code=401,
                )
            page.locator(
                "input[name=name], input[name=title], input[aria-label*=Title i]"
            ).first.wait_for(state="visible", timeout=60_000)

            _fill_first(
                page,
                ["input[name=name]", "input[name=title]", "input[aria-label*=Title i]"],
                title,
            )
            _fill_first(
                page,
                [
                    "textarea[name=description]",
                    "textarea[aria-label*=Description i]",
                    "textarea",
                ],
                description,
            )
            _click_first(page, ["save", "publish", "create"])
            page.wait_for_load_state("domcontentloaded")
            match = _ACTIVITY_URL_RE.search(page.url)
            if existing_strava_id is not None:
                return existing_strava_id
            if not match:
                page.wait_for_timeout(2000)
                match = _ACTIVITY_URL_RE.search(page.url)
            if not match:
                raise BrowserPublicationError(
                    "Strava did not confirm the uploaded activity.",
                    code="publication_not_confirmed",
                )
            return int(match.group(1))
        finally:
            context.close()


async def publish_activity(
    activity_id: int, *, strava_id: int | None = None
) -> ActivityPublication:
    """Upload a local file or edit an existing Strava activity using a real profile."""
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
        import_row = (
            await session.execute(
                select(ActivityImport).where(ActivityImport.activity_id == activity.id)
            )
        ).scalar_one_or_none()
        source_path = None
        if target_strava_id is None:
            if import_row is None:
                raise BrowserPublicationError(
                    "Only imported activities retain an original file for upload.",
                    code="source_file_missing",
                )
            source_path = get_settings().fitops_dir / import_row.relative_path
        description = apply_stamp(activity.description, compose_stamp(activity))
        title = activity.name
        publication = ActivityPublication(
            activity_id=activity.id,
            action="edit" if target_strava_id else "upload",
            status="running",
            strava_id=target_strava_id,
        )
        session.add(publication)
        await session.flush()
        publication_id = publication.id

    try:
        published_id = await asyncio.to_thread(
            _run_browser,
            source_path=source_path,
            title=title,
            description=description,
            existing_strava_id=target_strava_id,
        )
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
        async with get_async_session() as session:
            row = await session.get(ActivityPublication, publication_id)
            if row:
                row.status = "failed"
                row.error_code = exc.code
                row.error_message = str(exc)
                row.updated_at = datetime.now(UTC)
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
