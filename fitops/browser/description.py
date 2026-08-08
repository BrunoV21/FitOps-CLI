from __future__ import annotations

import base64
import json
import platform
import re
import socket
import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from fitops.browser.config import ensure_profile_available, resolve_browser_profile
from fitops.utils.exceptions import BrowserPublicationError

_DESCRIPTION_SELECTOR = (
    "textarea[name=description], "
    "textarea[aria-label*=Description i], "
    "textarea[data-testid*=description i], "
    'textarea[placeholder*="How\'d it go?" i]'
)
_SAVE_BUTTON_NAMES = re.compile(r"^(save|update)( activity)?$", re.IGNORECASE)


@dataclass(frozen=True)
class DescriptionAppendResult:
    activity_id: int
    activity_url: str
    before_length: int
    after_length: int
    saved: bool
    dry_run: bool
    backend: str = "playwright"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HeadlessLoginResult:
    user_data_dir: str
    profile: str
    verified_url: str
    persisted_session_cookies: int

    def to_dict(self) -> dict:
        return asdict(self)


def build_appended_description(existing: str | None, text: str) -> str:
    """Append text while preserving the existing description content."""
    if not text.strip():
        raise BrowserPublicationError(
            "The text to append must not be empty.",
            code="description_text_empty",
        )
    if not existing:
        return text
    existing_without_trailing_lines = existing.rstrip("\r\n")
    return f"{existing_without_trailing_lines}\n\n{text}"


def _assert_logged_in(page) -> None:
    if re.search(r"strava\.com/(?:login|session)(?:/|\?|$)", page.url):
        raise BrowserPublicationError(
            "The selected Brave profile is not logged in to Strava.",
            code="strava_login_required",
            status_code=401,
        )


def _is_authenticated_strava_target(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.hostname not in {"strava.com", "www.strava.com"}:
        return False
    return bool(
        parsed.path.startswith(("/dashboard", "/settings"))
        or re.fullmatch(r"/activities/\d+/edit/?", parsed.path)
    )


def _description_field(page):
    field = page.locator(_DESCRIPTION_SELECTOR).first
    try:
        field.wait_for(state="visible", timeout=60_000)
    except Exception as exc:
        raise BrowserPublicationError(
            "The Strava description editor was not found. Confirm that this profile "
            "owns the activity and that Strava's edit page is available.",
            code="strava_description_editor_not_found",
        ) from exc
    return field


def _save_button(page):
    button = page.get_by_role("button", name=_SAVE_BUTTON_NAMES).first
    if button.count():
        return button
    fallback = page.locator("button[type=submit], input[type=submit]").first
    if fallback.count():
        return fallback
    raise BrowserPublicationError(
        "Strava's save button was not found.",
        code="strava_page_changed",
    )


def _replace_react_mentions_field(field, value: str) -> None:
    """Replace a react-mentions field without merging its stale markup."""
    select_all = "Meta+A" if platform.system() == "Darwin" else "Control+A"
    field.click()
    field.press(select_all)
    field.press("Backspace")
    if value:
        field.type(value)


def _append_on_page(
    page,
    *,
    activity_id: int,
    text: str,
    dry_run: bool,
    backend_label: str = "playwright",
) -> DescriptionAppendResult:
    activity_url = f"https://www.strava.com/activities/{activity_id}"
    edit_url = f"{activity_url}/edit"

    page.goto(
        activity_url,
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    _assert_logged_in(page)
    page.goto(edit_url, wait_until="domcontentloaded", timeout=60_000)
    _assert_logged_in(page)

    field = _description_field(page)
    existing = field.input_value()
    updated = build_appended_description(existing, text)
    maximum = field.get_attribute("maxlength")
    if maximum and maximum.isdigit() and len(updated) > int(maximum):
        raise BrowserPublicationError(
            f"The resulting description is {len(updated)} characters, exceeding "
            f"Strava's {maximum}-character limit.",
            code="strava_description_too_long",
        )

    if dry_run:
        return DescriptionAppendResult(
            activity_id=activity_id,
            activity_url=activity_url,
            before_length=len(existing),
            after_length=len(updated),
            saved=False,
            dry_run=True,
            backend=backend_label,
        )

    # Strava's editor is react-mentions backed. Playwright's fill() sends one
    # synthetic input event, which react-mentions can merge with stale markup
    # and duplicate the old description. Real keyboard replacement keeps the
    # visible textarea and its submitted hidden input in sync.
    _replace_react_mentions_field(field, updated)
    _save_button(page).click()
    page.wait_for_timeout(2_000)

    # Read the edit form again so a successful click alone cannot be mistaken
    # for a persisted update.
    page.goto(edit_url, wait_until="domcontentloaded", timeout=60_000)
    _assert_logged_in(page)
    persisted = _description_field(page).input_value()
    if persisted != updated:
        raise BrowserPublicationError(
            "Strava did not persist the updated description.",
            code="description_update_not_confirmed",
            status_code=502,
        )

    return DescriptionAppendResult(
        activity_id=activity_id,
        activity_url=activity_url,
        before_length=len(existing),
        after_length=len(updated),
        saved=True,
        dry_run=False,
        backend=backend_label,
    )


def _available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _launch_native_brave(profile, *, headless: bool, initial_url: str | None = None):
    port = _available_local_port()
    args = [
        str(profile.executable),
        f"--user-data-dir={profile.user_data_dir}",
        f"--profile-directory={profile.profile}",
        f"--remote-debugging-port={port}",
        f"--remote-allow-origins=http://127.0.0.1:{port}",
        "--no-first-run",
    ]
    if headless:
        args.append("--headless=new")
    if initial_url:
        args.append(initial_url)
    process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    endpoint = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{endpoint}/json/version", timeout=0.25):
                return process, endpoint
        except Exception:
            if process.poll() is not None:
                break
            time.sleep(0.1)
    process.terminate()
    raise BrowserPublicationError(
        "Native Brave debugging endpoint did not start.",
        code="brave_headless_start_failed",
        status_code=502,
    )


def _stop_native_brave(process) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _run_native_brave_headless(
    profile, *, activity_id: int, text: str, dry_run: bool
) -> DescriptionAppendResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserPublicationError(
            "Native headless automation requires Playwright's CDP client.",
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
            return _append_on_page(
                page,
                activity_id=activity_id,
                text=text,
                dry_run=dry_run,
                backend_label="brave_headless_cdp",
            )
    finally:
        _stop_native_brave(process)


_BRAVE_APPLESCRIPT = r"""
on waitForTab(targetTab)
    tell application "Brave Browser"
        repeat 120 times
            if (loading of targetTab is false) then exit repeat
            delay 0.25
        end repeat
    end tell
end waitForTab

on run argv
    set activityUrl to item 1 of argv
    set editUrl to item 2 of argv
    set inspectScript to item 3 of argv
    set saveScript to item 4 of argv
    set verifyScript to item 5 of argv
    set shouldSave to item 6 of argv
    set automationTab to missing value
    set targetWindow to missing value
    set createdWindow to false

    try
        tell application "Brave Browser"
            if not running then launch
            repeat 80 times
                if (count of windows) > 0 then exit repeat
                delay 0.25
            end repeat
            if (count of windows) is 0 then
                make new window
                set createdWindow to true
            end if

            set targetWindow to front window
            set automationTab to make new tab at end of tabs of targetWindow with properties {URL:activityUrl}
            my waitForTab(automationTab)
            set currentUrl to URL of automationTab
            if currentUrl contains "/login" or currentUrl contains "/session" then error "FITOPS_LOGIN_REQUIRED"

            set URL of automationTab to editUrl
            my waitForTab(automationTab)
            set currentUrl to URL of automationTab
            if currentUrl contains "/login" or currentUrl contains "/session" then error "FITOPS_LOGIN_REQUIRED"

            set inspectResult to execute automationTab javascript inspectScript
            if inspectResult contains "\"error\"" then
                if createdWindow then
                    close targetWindow
                else
                    close automationTab
                end if
                return inspectResult
            end if
            if shouldSave is "true" then
                set saveResult to execute automationTab javascript saveScript
                if saveResult contains "\"error\"" then error "FITOPS_SAVE_FAILED:" & saveResult
                delay 1
                set URL of automationTab to editUrl
                my waitForTab(automationTab)
                set verifyResult to execute automationTab javascript verifyScript
                if verifyResult is not "true" then error "FITOPS_NOT_PERSISTED:" & verifyResult
            end if

            if createdWindow then
                close targetWindow
            else
                close automationTab
            end if
            return inspectResult
        end tell
    on error errorMessage number errorNumber
        try
            tell application "Brave Browser"
                if createdWindow and targetWindow is not missing value then
                    close targetWindow
                else if automationTab is not missing value then
                    close automationTab
                end if
            end tell
        end try
        error errorMessage number errorNumber
    end try
end run
"""


def _browser_javascript(text: str) -> tuple[str, str, str]:
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    setup = f"""
const field = document.querySelector({json.dumps(_DESCRIPTION_SELECTOR)});
if (!field) return JSON.stringify({{error: 'description_editor_not_found'}});
const bytes = Uint8Array.from(atob('{encoded}'), c => c.charCodeAt(0));
const text = new TextDecoder().decode(bytes);
const existing = field.value || '';
const updated = existing ? existing.replace(/[\\r\\n]+$/, '') + '\\n\\n' + text : text;
if (!text.trim()) return JSON.stringify({{error: 'description_text_empty'}});
if (field.maxLength > 0 && updated.length > field.maxLength) {{
  return JSON.stringify({{error: 'description_too_long', maximum: field.maxLength, actual: updated.length}});
}}
"""
    inspect_script = (
        "(() => {"
        + setup
        + "return JSON.stringify({ok: true, before_length: existing.length, after_length: updated.length});})()"
    )
    save_script = (
        "(() => {"
        + setup
        + "sessionStorage.setItem('__fitops_expected_description', updated);"
        + "const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;"
        + "setter.call(field, updated);"
        + "field.dispatchEvent(new Event('input', {bubbles: true}));"
        + "field.dispatchEvent(new Event('change', {bubbles: true}));"
        + "const buttons = [...document.querySelectorAll('button, input[type=submit]')];"
        + "const save = buttons.find(el => /^(save|update)( activity)?$/i.test((el.innerText || el.value || '').trim()))"
        + " || document.querySelector('button[type=submit], input[type=submit]');"
        + "if (!save) return JSON.stringify({error: 'save_button_not_found'});"
        + "save.click(); return JSON.stringify({ok: true});})()"
    )
    verify_script = (
        "(() => {"
        + f"const field = document.querySelector({json.dumps(_DESCRIPTION_SELECTOR)});"
        + "const expected = sessionStorage.getItem('__fitops_expected_description');"
        + "const persisted = Boolean(field && expected !== null && field.value === expected);"
        + "sessionStorage.removeItem('__fitops_expected_description');"
        + "return String(persisted);})()"
    )
    return inspect_script, save_script, verify_script


def _run_brave_live_session(
    *, activity_id: int, text: str, dry_run: bool
) -> DescriptionAppendResult:
    activity_url = f"https://www.strava.com/activities/{activity_id}"
    edit_url = f"{activity_url}/edit"
    scripts = _browser_javascript(text)
    try:
        completed = subprocess.run(
            [
                "osascript",
                "-e",
                _BRAVE_APPLESCRIPT,
                activity_url,
                edit_url,
                *scripts,
                "false" if dry_run else "true",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BrowserPublicationError(
            f"Could not control Brave through Apple Events: {exc}",
            code="brave_automation_failed",
            status_code=502,
        ) from exc

    if completed.returncode:
        message = completed.stderr.strip()
        if "Executing JavaScript through AppleScript is turned off" in message:
            raise BrowserPublicationError(
                "Brave must allow JavaScript from Apple Events. In Brave, enable "
                "View > Developer > Allow JavaScript from Apple Events, then retry.",
                code="brave_javascript_events_disabled",
                status_code=409,
            )
        if "FITOPS_LOGIN_REQUIRED" in message:
            raise BrowserPublicationError(
                "The current Brave session is not logged in to Strava.",
                code="strava_login_required",
                status_code=401,
            )
        if "Not authorized" in message or "not allowed assistive" in message.lower():
            raise BrowserPublicationError(
                "macOS did not allow FitOps to automate Brave. Grant your terminal "
                "Automation access in System Settings > Privacy & Security.",
                code="brave_automation_permission_denied",
                status_code=409,
            )
        if "FITOPS_NOT_PERSISTED" in message:
            raise BrowserPublicationError(
                "Strava did not persist the updated description.",
                code="description_update_not_confirmed",
                status_code=502,
            )
        if "FITOPS_SAVE_FAILED" in message:
            raise BrowserPublicationError(
                "Strava's save button was not found or could not be activated.",
                code="strava_save_failed",
                status_code=502,
            )
        raise BrowserPublicationError(
            f"Brave live-session automation failed: {message}",
            code="brave_automation_failed",
            status_code=502,
        )

    try:
        inspected = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as exc:
        raise BrowserPublicationError(
            "Brave returned an unreadable automation result.",
            code="brave_automation_failed",
            status_code=502,
        ) from exc
    error = inspected.get("error")
    if error:
        messages = {
            "description_editor_not_found": (
                "The Strava description editor was not found. Confirm that the "
                "current Brave session owns this activity."
            ),
            "description_text_empty": "The text to append must not be empty.",
            "description_too_long": (
                "The resulting description exceeds Strava's character limit."
            ),
            "save_button_not_found": "Strava's save button was not found.",
        }
        raise BrowserPublicationError(
            messages.get(error, "Strava's activity editor could not be automated."),
            code=f"strava_{error}",
        )

    return DescriptionAppendResult(
        activity_id=activity_id,
        activity_url=activity_url,
        before_length=int(inspected["before_length"]),
        after_length=int(inspected["after_length"]),
        saved=not dry_run,
        dry_run=dry_run,
        backend="brave_live_session",
    )


def append_activity_description(
    activity_id: int,
    text: str,
    *,
    dry_run: bool = False,
    headless: bool = True,
    backend: str = "auto",
) -> DescriptionAppendResult:
    """Append text on Strava using the configured logged-in Brave profile."""
    if activity_id <= 0:
        raise BrowserPublicationError(
            "Strava activity ID must be a positive integer.",
            code="invalid_strava_id",
        )
    if not text.strip():
        raise BrowserPublicationError(
            "The text to append must not be empty.",
            code="description_text_empty",
        )

    if backend not in {"auto", "brave-live", "brave-headless", "playwright"}:
        raise BrowserPublicationError(
            "Browser backend must be auto, brave-live, brave-headless, or playwright.",
            code="browser_backend_invalid",
        )

    profile = resolve_browser_profile()
    selected_backend = choose_description_backend(profile, backend)
    use_brave_live = selected_backend == "brave-live"
    if use_brave_live:
        if platform.system() != "Darwin" or profile.browser_type != "brave":
            raise BrowserPublicationError(
                "The brave-live backend requires Brave on macOS.",
                code="browser_backend_unavailable",
            )
        return _run_brave_live_session(
            activity_id=activity_id,
            text=text,
            dry_run=dry_run,
        )

    ensure_profile_available(profile)
    if selected_backend == "brave-headless":
        if profile.browser_type != "brave":
            raise BrowserPublicationError(
                "The brave-headless backend requires Brave.",
                code="browser_backend_unavailable",
            )
        return _run_native_brave_headless(
            profile,
            activity_id=activity_id,
            text=text,
            dry_run=dry_run,
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserPublicationError(
            "This command requires Playwright. Reinstall FitOps dependencies.",
            code="playwright_missing",
            status_code=500,
        ) from exc

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile.user_data_dir),
                executable_path=str(profile.executable),
                headless=headless,
                args=[
                    f"--profile-directory={profile.profile}",
                    "--no-first-run",
                ],
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                return _append_on_page(
                    page,
                    activity_id=activity_id,
                    text=text,
                    dry_run=dry_run,
                )
            finally:
                context.close()
    except BrowserPublicationError:
        raise
    except Exception as exc:
        raise BrowserPublicationError(
            f"Brave automation failed: {exc}",
            code="browser_automation_failed",
            status_code=502,
        ) from exc


def choose_description_backend(profile, backend: str) -> str:
    """Resolve auto to live Brave or isolated-profile Playwright automation."""
    if backend != "auto":
        return backend
    if (
        platform.system() == "Darwin"
        and profile.browser_type == "brave"
        and profile.is_default_user_data_dir
    ):
        return "brave-live"
    if profile.browser_type == "brave" and not profile.is_default_user_data_dir:
        return "brave-headless"
    return "playwright"


def _login_native_brave_profile(
    profile, *, timeout_seconds: int
) -> HeadlessLoginResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserPublicationError(
            "Headless login requires Playwright's CDP client.",
            code="playwright_missing",
            status_code=500,
        ) from exc

    process, endpoint = _launch_native_brave(
        profile,
        headless=False,
        initial_url="https://www.strava.com/login",
    )
    try:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"{endpoint}/json/list", timeout=0.5
                ) as response:
                    targets = json.load(response)
                if any(
                    _is_authenticated_strava_target(target.get("url", ""))
                    for target in targets
                ):
                    break
            except Exception:
                if process.poll() is not None:
                    raise BrowserPublicationError(
                        "The dedicated Brave login window was closed before login completed.",
                        code="strava_login_cancelled",
                        status_code=409,
                    )
            time.sleep(0.5)
        else:
            raise BrowserPublicationError(
                "Timed out waiting for Strava login.",
                code="strava_login_timeout",
                status_code=408,
            )

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(endpoint)
            context = next(
                (
                    context
                    for context in browser.contexts
                    if any(
                        _is_authenticated_strava_target(page.url)
                        for page in context.pages
                    )
                ),
                None,
            )
            if context is None:
                raise BrowserPublicationError(
                    "The authenticated Strava browser context was not found.",
                    code="strava_login_not_confirmed",
                    status_code=401,
                )
            verification = context.new_page()
            verification.goto(
                "https://www.strava.com/settings/profile",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            _assert_logged_in(verification)
            if "/settings/profile" not in verification.url:
                raise BrowserPublicationError(
                    "Strava login could not be verified on the profile settings page.",
                    code="strava_login_not_confirmed",
                    status_code=401,
                )
            expires = time.time() + (30 * 24 * 60 * 60)
            cookies = context.cookies("https://www.strava.com")
            persistent_cookies = []
            for cookie in cookies:
                if cookie["name"] not in {"_strava4_session", "_currentH"}:
                    continue
                persistent = {
                    key: cookie[key]
                    for key in (
                        "name",
                        "value",
                        "domain",
                        "path",
                        "httpOnly",
                        "secure",
                        "sameSite",
                    )
                    if key in cookie
                }
                persistent["expires"] = expires
                persistent_cookies.append(persistent)
            context.add_cookies(persistent_cookies)
            verification.wait_for_timeout(1_000)
            result = HeadlessLoginResult(
                user_data_dir=str(profile.user_data_dir),
                profile=profile.profile,
                verified_url=verification.url,
                persisted_session_cookies=len(persistent_cookies),
            )
        return result
    finally:
        _stop_native_brave(process)


def _login_playwright_profile(profile, *, timeout_seconds: int) -> HeadlessLoginResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserPublicationError(
            "Headless login requires Playwright. Reinstall FitOps dependencies.",
            code="playwright_missing",
            status_code=500,
        ) from exc

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile.user_data_dir),
                executable_path=str(profile.executable),
                headless=False,
                args=[f"--profile-directory={profile.profile}", "--no-first-run"],
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(
                    "https://www.strava.com/login",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                deadline = time.monotonic() + timeout_seconds
                while time.monotonic() < deadline:
                    parsed_url = urlparse(page.url)
                    if parsed_url.hostname in {"strava.com", "www.strava.com"} and (
                        parsed_url.path.startswith("/dashboard")
                        or parsed_url.path.startswith("/settings")
                    ):
                        break
                    page.wait_for_timeout(500)
                else:
                    raise BrowserPublicationError(
                        "Timed out waiting for Strava login.",
                        code="strava_login_timeout",
                        status_code=408,
                    )

                cookies = context.cookies("https://www.strava.com")
                session_cookies = [
                    cookie
                    for cookie in cookies
                    if cookie["name"] in {"_strava4_session", "_currentH"}
                    and cookie.get("expires", -1) < 0
                ]
                if not any(
                    cookie["name"] == "_strava4_session" for cookie in session_cookies
                ):
                    raise BrowserPublicationError(
                        "Strava login completed without an authenticated session cookie.",
                        code="strava_login_not_confirmed",
                        status_code=401,
                    )

                expires = time.time() + (30 * 24 * 60 * 60)
                persistent_cookies = []
                for cookie in session_cookies:
                    persistent = {
                        key: cookie[key]
                        for key in (
                            "name",
                            "value",
                            "domain",
                            "path",
                            "httpOnly",
                            "secure",
                            "sameSite",
                        )
                        if key in cookie
                    }
                    persistent["expires"] = expires
                    persistent_cookies.append(persistent)
                page.goto(
                    "https://www.strava.com/settings/profile",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                _assert_logged_in(page)
                if "/settings/profile" not in page.url:
                    raise BrowserPublicationError(
                        "Strava login could not be verified on the profile settings page.",
                        code="strava_login_not_confirmed",
                        status_code=401,
                    )
                # Verify first: Strava may reissue the authenticated cookie as
                # session-only while loading settings. Persist that final value.
                verified_cookies = context.cookies("https://www.strava.com")
                persistent_cookies = []
                for cookie in verified_cookies:
                    if cookie["name"] not in {"_strava4_session", "_currentH"}:
                        continue
                    persistent = {
                        key: cookie[key]
                        for key in (
                            "name",
                            "value",
                            "domain",
                            "path",
                            "httpOnly",
                            "secure",
                            "sameSite",
                        )
                        if key in cookie
                    }
                    persistent["expires"] = expires
                    persistent_cookies.append(persistent)
                context.add_cookies(persistent_cookies)
                return HeadlessLoginResult(
                    user_data_dir=str(profile.user_data_dir),
                    profile=profile.profile,
                    verified_url=page.url,
                    persisted_session_cookies=len(persistent_cookies),
                )
            finally:
                context.close()
    except BrowserPublicationError:
        raise
    except Exception as exc:
        raise BrowserPublicationError(
            f"Headless-profile login failed: {exc}",
            code="browser_login_failed",
            status_code=502,
        ) from exc


def login_headless_profile(*, timeout_seconds: int = 300) -> HeadlessLoginResult:
    """Open the dedicated profile for login and persist its Strava session."""
    if timeout_seconds < 30 or timeout_seconds > 900:
        raise BrowserPublicationError(
            "Login timeout must be between 30 and 900 seconds.",
            code="browser_login_timeout_invalid",
        )
    profile = resolve_browser_profile()
    if profile.is_default_user_data_dir:
        raise BrowserPublicationError(
            "Headless login requires a dedicated, non-default browser data directory.",
            code="headless_profile_required",
            status_code=409,
        )
    ensure_profile_available(profile)
    if platform.system() == "Darwin" and profile.browser_type == "brave":
        try:
            return _login_native_brave_profile(profile, timeout_seconds=timeout_seconds)
        except BrowserPublicationError:
            raise
        except Exception as exc:
            raise BrowserPublicationError(
                f"Native Brave login failed: {exc}",
                code="browser_login_failed",
                status_code=502,
            ) from exc
    return _login_playwright_profile(profile, timeout_seconds=timeout_seconds)
