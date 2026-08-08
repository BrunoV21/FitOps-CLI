from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from fitops.browser.config import ensure_profile_available, resolve_browser_profile
from fitops.browser.description import (
    _assert_logged_in,
    _launch_native_brave,
    _replace_react_mentions_field,
    _stop_native_brave,
    choose_description_backend,
)
from fitops.importers.activity_files import MAX_ACTIVITY_FILE_BYTES
from fitops.utils.exceptions import BrowserPublicationError

_ACTIVITY_URL_RE = re.compile(r"/activities/(\d+)(?:/|$)")
_DISTANCE_SUFFIX_RE = re.compile(
    r"\s+\([\d.,]+\s*(?:km|mi|miles?|kilomet(?:er|re)s?)\)\s*$", re.IGNORECASE
)
_SUPPORTED_SUFFIXES = {".gpx", ".tcx"}


@dataclass(frozen=True)
class UploadOption:
    value: str
    label: str
    index: int = 0


@dataclass(frozen=True)
class ActivityUploadResult:
    strava_activity_id: int
    activity_url: str
    file_name: str
    file_format: str
    title: str
    sport_type: str
    gear_value: str | None
    gear_label: str | None
    backend: str

    def to_dict(self) -> dict:
        return asdict(self)


def _normalise_option_text(value: str) -> str:
    return " ".join(value.casefold().split())


def match_upload_option(
    options: list[UploadOption], requested: str
) -> UploadOption | None:
    """Match an option value or label, ignoring a gear distance suffix."""
    needle = _normalise_option_text(requested)
    for option in options:
        if _normalise_option_text(option.value) == needle:
            return option
    for option in options:
        if _normalise_option_text(option.label) == needle:
            return option
    for option in options:
        label_without_distance = _DISTANCE_SUFFIX_RE.sub("", option.label)
        if _normalise_option_text(label_without_distance) == needle:
            return option
    return None


def duplicate_upload_message(body_text: str) -> str | None:
    """Return Strava's duplicate line when the staged file already exists."""
    for raw_line in body_text.splitlines():
        line = " ".join(raw_line.split())
        if re.search(r"\bduplicate of\b", line, re.IGNORECASE):
            return line
    return None


def _validate_upload_inputs(file_path: str | Path, title: str, sport_type: str) -> Path:
    source = Path(file_path).expanduser().resolve()
    if not source.is_file():
        raise BrowserPublicationError(
            f"Activity file was not found: {source}",
            code="upload_file_not_found",
            status_code=404,
        )
    if source.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise BrowserPublicationError(
            "Activity upload requires a .gpx or .tcx file.",
            code="upload_file_type_unsupported",
        )
    if source.stat().st_size > MAX_ACTIVITY_FILE_BYTES:
        raise BrowserPublicationError(
            f"Activity files must be no larger than "
            f"{MAX_ACTIVITY_FILE_BYTES // (1024 * 1024)} MiB.",
            code="upload_file_too_large",
            status_code=413,
        )
    if not title.strip():
        raise BrowserPublicationError(
            "Activity title must not be empty.", code="upload_title_empty"
        )
    if not sport_type.strip():
        raise BrowserPublicationError(
            "Sport type must not be empty.", code="upload_sport_empty"
        )
    return source


def _read_options(container) -> list[UploadOption]:
    rows = container.locator("li[data-value]")
    return [
        UploadOption(
            value=rows.nth(index).get_attribute("data-value") or "",
            label=rows.nth(index).inner_text().strip(),
            index=index,
        )
        for index in range(rows.count())
    ]


def _select_dropdown_option(container, requested: str, *, kind: str) -> UploadOption:
    options = _read_options(container)
    selected = match_upload_option(options, requested)
    if selected is None:
        labels = ", ".join(option.label for option in options[:12])
        suffix = "" if len(options) <= 12 else ", …"
        raise BrowserPublicationError(
            f"Strava has no {kind} option matching '{requested}'. "
            f"Available options: {labels}{suffix}",
            code=f"{kind}_not_found",
        )

    current = container.locator(".selection").first.inner_text().strip()
    if _normalise_option_text(current) != _normalise_option_text(selected.label):
        container.locator(".selection").first.click()
        row = container.locator("li[data-value]").nth(selected.index)
        target = row.locator("a").first
        (target if target.count() else row).click()
    return selected


def _upload_error_text(body_text: str) -> str | None:
    patterns = (
        r"[^\n]*(?:could not|can't|cannot) be processed[^\n]*",
        r"[^\n]*(?:invalid|corrupt|unsupported) (?:activity )?file[^\n]*",
        r"[^\n]*upload (?:failed|error)[^\n]*",
    )
    for pattern in patterns:
        match = re.search(pattern, body_text, re.IGNORECASE)
        if match:
            return " ".join(match.group(0).split())
    return None


def _wait_for_upload_editor(page, source: Path, *, timeout_ms: int = 120_000) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000)
    title_field = page.locator("input[name=name]").first
    sport_menu = page.locator(".drop-down-menu.sport-type").first
    while time.monotonic() < deadline:
        body_text = page.locator("body").inner_text()
        duplicate = duplicate_upload_message(body_text)
        if duplicate:
            raise BrowserPublicationError(
                f"Strava reports that '{source.name}' already exists: {duplicate}",
                code="activity_already_exists",
                status_code=409,
            )
        upload_error = _upload_error_text(body_text)
        if upload_error:
            raise BrowserPublicationError(
                f"Strava rejected '{source.name}': {upload_error}",
                code="strava_upload_rejected",
            )
        if (
            title_field.is_visible()
            and sport_menu.is_visible()
            and _find_enabled_save_button(page) is not None
        ):
            return
        page.wait_for_timeout(500)
    raise BrowserPublicationError(
        f"Strava did not finish processing '{source.name}' within "
        f"{timeout_ms // 1000} seconds.",
        code="upload_processing_timeout",
        status_code=504,
    )


def _find_enabled_save_button(page):
    buttons = page.locator("button.save-and-view:visible")
    for index in range(buttons.count()):
        button = buttons.nth(index)
        classes = button.get_attribute("class") or ""
        if "disabled" not in classes.split() and not button.is_disabled():
            return button
    return None


def _enabled_save_button(page):
    button = _find_enabled_save_button(page)
    if button is not None:
        return button
    raise BrowserPublicationError(
        "Strava's Save & View button is not enabled.",
        code="strava_upload_save_unavailable",
    )


def _wait_for_activity_id(page, *, timeout_ms: int = 60_000) -> int:
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        match = _ACTIVITY_URL_RE.search(page.url)
        if match:
            return int(match.group(1))
        body_text = page.locator("body").inner_text()
        duplicate = duplicate_upload_message(body_text)
        if duplicate:
            raise BrowserPublicationError(
                f"Strava rejected the upload as a duplicate: {duplicate}",
                code="activity_already_exists",
                status_code=409,
            )
        upload_error = _upload_error_text(body_text)
        if upload_error:
            raise BrowserPublicationError(
                f"Strava did not save the activity: {upload_error}",
                code="strava_upload_rejected",
            )
        page.wait_for_timeout(500)
    raise BrowserPublicationError(
        "Strava did not return the uploaded activity ID.",
        code="upload_not_confirmed",
        status_code=502,
    )


def _upload_on_page(
    page,
    *,
    source: Path,
    title: str,
    description: str,
    sport_type: str,
    gear: str | None,
    backend_label: str,
) -> ActivityUploadResult:
    page.goto(
        "https://www.strava.com/upload/select",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    _assert_logged_in(page)
    upload = page.locator("input[type=file]").first
    try:
        upload.wait_for(state="attached", timeout=60_000)
    except Exception as exc:
        raise BrowserPublicationError(
            "Strava's file upload control was not found.",
            code="strava_upload_control_not_found",
            status_code=502,
        ) from exc
    upload.set_input_files(str(source))
    _wait_for_upload_editor(page, source)

    page.locator("input[name=name]").first.fill(title.strip())
    description_field = page.locator(
        ".description-container textarea, textarea[class*=mentions__input]"
    ).first
    description_field.wait_for(state="visible", timeout=30_000)
    _replace_react_mentions_field(description_field, description)
    hidden_description = page.locator("input[type=hidden][name=description]").first
    if hidden_description.count() and hidden_description.input_value() != description:
        raise BrowserPublicationError(
            "Strava's description editor did not accept the supplied text.",
            code="strava_description_not_applied",
            status_code=502,
        )

    sport_menu = page.locator(".drop-down-menu.sport-type").first
    selected_sport = _select_dropdown_option(sport_menu, sport_type, kind="sport_type")

    selected_gear = None
    if gear:
        page.wait_for_timeout(250)
        gear_menu = page.locator(
            ".drop-down-menu.shoes, .drop-down-menu.bikes, .drop-down-menu.gear"
        ).first
        if not gear_menu.count() or not gear_menu.is_visible():
            raise BrowserPublicationError(
                f"Strava does not offer gear for sport type '{selected_sport.label}'.",
                code="gear_not_available",
            )
        selected_gear = _select_dropdown_option(gear_menu, gear, kind="gear")

    _enabled_save_button(page).click()
    activity_id = _wait_for_activity_id(page)
    return ActivityUploadResult(
        strava_activity_id=activity_id,
        activity_url=f"https://www.strava.com/activities/{activity_id}",
        file_name=source.name,
        file_format=source.suffix.lower().lstrip("."),
        title=title.strip(),
        sport_type=selected_sport.value,
        gear_value=selected_gear.value if selected_gear else None,
        gear_label=selected_gear.label if selected_gear else None,
        backend=backend_label,
    )


def _run_native_headless_upload(
    profile,
    *,
    source: Path,
    title: str,
    description: str,
    sport_type: str,
    gear: str | None,
) -> ActivityUploadResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserPublicationError(
            "Native headless upload requires Playwright's CDP client.",
            code="playwright_missing",
            status_code=500,
        ) from exc

    process, endpoint = _launch_native_brave(profile, headless=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(endpoint)
            if not browser.contexts:
                raise BrowserPublicationError(
                    "Native Brave did not expose its browser context.",
                    code="brave_headless_context_missing",
                    status_code=502,
                )
            page = browser.contexts[0].new_page()
            return _upload_on_page(
                page,
                source=source,
                title=title,
                description=description,
                sport_type=sport_type,
                gear=gear,
                backend_label="brave_headless_cdp",
            )
    finally:
        _stop_native_brave(process)


def upload_activity_file(
    file_path: str | Path,
    *,
    title: str,
    description: str = "",
    sport_type: str,
    gear: str | None = None,
    headless: bool = True,
    backend: str = "auto",
) -> ActivityUploadResult:
    """Upload a GPX/TCX file through the configured logged-in browser profile."""
    source = _validate_upload_inputs(file_path, title, sport_type)
    if backend not in {"auto", "brave-headless", "playwright"}:
        raise BrowserPublicationError(
            "Upload backend must be auto, brave-headless, or playwright.",
            code="browser_backend_invalid",
        )

    profile = resolve_browser_profile()
    selected_backend = choose_description_backend(profile, backend)
    if selected_backend == "brave-live":
        raise BrowserPublicationError(
            "Background uploads require a dedicated browser data directory. "
            "Configure one and run `fitops browser login-headless` first.",
            code="headless_profile_required",
            status_code=409,
        )
    ensure_profile_available(profile)

    if selected_backend == "brave-headless":
        if profile.browser_type != "brave":
            raise BrowserPublicationError(
                "The brave-headless backend requires Brave.",
                code="browser_backend_unavailable",
            )
        return _run_native_headless_upload(
            profile,
            source=source,
            title=title,
            description=description,
            sport_type=sport_type,
            gear=gear,
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserPublicationError(
            "Browser upload requires Playwright. Reinstall FitOps dependencies.",
            code="playwright_missing",
            status_code=500,
        ) from exc

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile.user_data_dir),
                executable_path=str(profile.executable),
                headless=headless,
                args=[f"--profile-directory={profile.profile}", "--no-first-run"],
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                return _upload_on_page(
                    page,
                    source=source,
                    title=title,
                    description=description,
                    sport_type=sport_type,
                    gear=gear,
                    backend_label="playwright",
                )
            finally:
                context.close()
    except BrowserPublicationError:
        raise
    except Exception as exc:
        raise BrowserPublicationError(
            f"Browser upload failed: {exc}",
            code="browser_upload_failed",
            status_code=502,
        ) from exc
