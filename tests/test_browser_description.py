from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from fitops.browser.config import BrowserProfile
from fitops.browser.description import (
    _DESCRIPTION_SELECTOR,
    DescriptionAppendResult,
    _append_on_page,
    _browser_javascript,
    _is_authenticated_strava_target,
    _run_brave_live_session,
    build_appended_description,
    choose_description_backend,
    login_headless_profile,
)
from fitops.utils.exceptions import BrowserPublicationError


class _FakeField:
    def __init__(self, page):
        self.page = page

    @property
    def first(self):
        return self

    def wait_for(self, **_kwargs):
        return None

    def input_value(self):
        return self.page.description

    def get_attribute(self, name):
        return "1000" if name == "maxlength" else None

    def fill(self, value):
        self.page.pending_description = value

    def click(self):
        return None

    def press(self, key):
        if key == "Backspace":
            self.page.pending_description = ""

    def type(self, value):
        self.page.pending_description += value


class _FakeButton:
    def __init__(self, page):
        self.page = page

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def click(self):
        self.page.saved = True
        self.page.description = self.page.pending_description


class _FakePage:
    def __init__(self, description="Existing notes"):
        self.url = "about:blank"
        self.description = description
        self.pending_description = description
        self.saved = False
        self.visited = []

    def goto(self, url, **_kwargs):
        self.url = url
        self.visited.append(url)

    def locator(self, selector):
        if "textarea" in selector:
            return _FakeField(self)
        return _FakeButton(self)

    def get_by_role(self, *_args, **_kwargs):
        return _FakeButton(self)

    def wait_for_timeout(self, _milliseconds):
        return None


def test_build_appended_description_preserves_existing_text():
    assert build_appended_description("Morning run\n", "Coach note") == (
        "Morning run\n\nCoach note"
    )
    assert build_appended_description(None, "First note") == "First note"


def test_description_selector_matches_current_strava_editor():
    assert 'textarea[placeholder*="How\'d it go?" i]' in _DESCRIPTION_SELECTOR


@pytest.mark.parametrize(
    "url",
    [
        "https://www.strava.com/dashboard",
        "https://www.strava.com/settings/profile",
        "https://www.strava.com/activities/19645980884/edit",
    ],
)
def test_authenticated_strava_target_accepts_post_login_pages(url):
    assert _is_authenticated_strava_target(url) is True


def test_authenticated_strava_target_rejects_login_and_public_activity_pages():
    assert _is_authenticated_strava_target("https://www.strava.com/login") is False
    assert (
        _is_authenticated_strava_target("https://www.strava.com/activities/19645980884")
        is False
    )


def test_auto_backend_uses_live_session_for_default_brave_profile(monkeypatch):
    default_dir = Path("/browser/default-data")
    profile = BrowserProfile(
        "brave",
        Path("/Applications/Brave Browser"),
        default_dir,
        "Default",
    )
    monkeypatch.setattr(
        "fitops.browser.config._browser_defaults",
        lambda _browser_type: (Path("/Applications/Brave Browser"), default_dir),
    )
    monkeypatch.setattr("fitops.browser.description.platform.system", lambda: "Darwin")

    assert choose_description_backend(profile, "auto") == "brave-live"


def test_auto_backend_uses_native_headless_brave_for_custom_profile(monkeypatch):
    profile = BrowserProfile(
        "brave",
        Path("/Applications/Brave Browser"),
        Path("/fitops/brave-automation"),
        "Default",
    )
    monkeypatch.setattr(
        "fitops.browser.config._browser_defaults",
        lambda _browser_type: (
            Path("/Applications/Brave Browser"),
            Path("/browser/default-data"),
        ),
    )
    monkeypatch.setattr("fitops.browser.description.platform.system", lambda: "Darwin")

    assert choose_description_backend(profile, "auto") == "brave-headless"


def test_explicit_playwright_backend_launches_persistent_context_headlessly(
    monkeypatch, tmp_path
):
    from fitops.browser.description import append_activity_description

    executable = tmp_path / "Brave Browser"
    executable.touch()
    automation_dir = tmp_path / "brave-automation"
    automation_dir.mkdir()
    profile = BrowserProfile("brave", executable, automation_dir, "Default")
    monkeypatch.setattr(
        "fitops.browser.description.resolve_browser_profile", lambda: profile
    )
    monkeypatch.setattr(
        "fitops.browser.config._browser_defaults",
        lambda _browser_type: (executable, tmp_path / "normal-brave-data"),
    )
    page = _FakePage()
    context = SimpleNamespace(
        pages=[page],
        new_page=MagicMock(return_value=page),
        close=MagicMock(),
    )
    launch = MagicMock(return_value=context)
    playwright = SimpleNamespace(
        chromium=SimpleNamespace(launch_persistent_context=launch)
    )
    manager = MagicMock()
    manager.__enter__.return_value = playwright
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: manager)

    result = append_activity_description(
        19645980884,
        "Headless check",
        dry_run=True,
        headless=True,
        backend="playwright",
    )

    assert result.backend == "playwright"
    assert result.saved is False
    launch.assert_called_once_with(
        str(automation_dir),
        executable_path=str(executable),
        headless=True,
        args=["--profile-directory=Default", "--no-first-run"],
    )
    context.close.assert_called_once()


def test_custom_profile_auto_backend_runs_native_headless_brave(monkeypatch, tmp_path):
    from fitops.browser.description import append_activity_description

    executable = tmp_path / "Brave Browser"
    executable.touch()
    automation_dir = tmp_path / "brave-automation"
    automation_dir.mkdir()
    profile = BrowserProfile("brave", executable, automation_dir, "Default")
    monkeypatch.setattr(
        "fitops.browser.description.resolve_browser_profile", lambda: profile
    )
    monkeypatch.setattr(
        "fitops.browser.config._browser_defaults",
        lambda _browser_type: (executable, tmp_path / "normal-brave-data"),
    )
    expected = DescriptionAppendResult(
        activity_id=19645980884,
        activity_url="https://www.strava.com/activities/19645980884",
        before_length=10,
        after_length=24,
        saved=False,
        dry_run=True,
        backend="brave_headless_cdp",
    )
    native = MagicMock(return_value=expected)
    monkeypatch.setattr("fitops.browser.description._run_native_brave_headless", native)

    result = append_activity_description(
        19645980884,
        "Headless check",
        dry_run=True,
        backend="auto",
    )

    assert result.backend == "brave_headless_cdp"
    native.assert_called_once_with(
        profile,
        activity_id=19645980884,
        text="Headless check",
        dry_run=True,
    )


def test_login_headless_profile_verifies_and_persists_session_cookie(
    monkeypatch, tmp_path
):
    executable = tmp_path / "Brave Browser"
    executable.touch()
    automation_dir = tmp_path / "brave-automation"
    automation_dir.mkdir()
    profile = BrowserProfile("brave", executable, automation_dir, "Default")
    monkeypatch.setattr(
        "fitops.browser.description.resolve_browser_profile", lambda: profile
    )
    monkeypatch.setattr(
        "fitops.browser.config._browser_defaults",
        lambda _browser_type: (executable, tmp_path / "normal-brave-data"),
    )
    monkeypatch.setattr("fitops.browser.description.platform.system", lambda: "Linux")

    class LoginPage:
        url = "about:blank"

        def goto(self, url, **_kwargs):
            self.url = url

        def wait_for_timeout(self, _milliseconds):
            self.url = "https://www.strava.com/dashboard"

    page = LoginPage()
    cookies = [
        {
            "name": "_strava4_session",
            "value": "encrypted-by-browser",
            "domain": ".strava.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }
    ]
    context = SimpleNamespace(
        pages=[page],
        new_page=MagicMock(return_value=page),
        cookies=MagicMock(return_value=cookies),
        add_cookies=MagicMock(),
        close=MagicMock(),
    )
    launch = MagicMock(return_value=context)
    playwright = SimpleNamespace(
        chromium=SimpleNamespace(launch_persistent_context=launch)
    )
    manager = MagicMock()
    manager.__enter__.return_value = playwright
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: manager)

    result = login_headless_profile(timeout_seconds=30)

    assert result.verified_url == "https://www.strava.com/settings/profile"
    assert result.persisted_session_cookies == 1
    persisted = context.add_cookies.call_args.args[0][0]
    assert persisted["name"] == "_strava4_session"
    assert persisted["expires"] > time.time()
    context.close.assert_called_once()


def test_append_page_visits_activity_and_confirms_saved_description():
    page = _FakePage()

    result = _append_on_page(
        page,
        activity_id=19645980884,
        text="Automated note",
        dry_run=False,
    )

    assert page.visited == [
        "https://www.strava.com/activities/19645980884",
        "https://www.strava.com/activities/19645980884/edit",
        "https://www.strava.com/activities/19645980884/edit",
    ]
    assert page.description == "Existing notes\n\nAutomated note"
    assert page.saved is True
    assert result.saved is True
    assert result.before_length == len("Existing notes")
    assert result.after_length == len(page.description)


def test_append_page_dry_run_never_saves():
    page = _FakePage()

    result = _append_on_page(
        page,
        activity_id=19645980884,
        text="Do not save this",
        dry_run=True,
    )

    assert page.saved is False
    assert page.description == "Existing notes"
    assert result.saved is False
    assert result.dry_run is True


def test_empty_append_text_is_rejected():
    with pytest.raises(BrowserPublicationError) as raised:
        build_appended_description("Existing", "  \n")
    assert raised.value.code == "description_text_empty"


def test_append_description_cli_json(monkeypatch):
    from fitops.cli.main import app

    result_value = DescriptionAppendResult(
        activity_id=19645980884,
        activity_url="https://www.strava.com/activities/19645980884",
        before_length=10,
        after_length=25,
        saved=True,
        dry_run=False,
    )
    automation = MagicMock(return_value=result_value)
    monkeypatch.setattr(
        "fitops.browser.description.append_activity_description", automation
    )

    result = CliRunner().invoke(
        app,
        [
            "browser",
            "append-description",
            "19645980884",
            "Automated note",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["_meta"]["tool"] == "fitops"
    assert payload["_meta"]["filters_applied"]["activity_id"] == 19645980884
    assert payload["description_update"]["saved"] is True
    automation.assert_called_once_with(
        19645980884,
        "Automated note",
        dry_run=False,
        headless=True,
        backend="auto",
    )


def test_append_description_cli_forwards_dry_run_and_visible_browser(monkeypatch):
    from fitops.cli.main import app

    result_value = DescriptionAppendResult(
        activity_id=19645980884,
        activity_url="https://www.strava.com/activities/19645980884",
        before_length=10,
        after_length=25,
        saved=False,
        dry_run=True,
    )
    automation = MagicMock(return_value=result_value)
    monkeypatch.setattr(
        "fitops.browser.description.append_activity_description", automation
    )

    result = CliRunner().invoke(
        app,
        [
            "browser",
            "append-description",
            "19645980884",
            "Automated note",
            "--dry-run",
            "--show-browser",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Dry run passed" in result.output
    automation.assert_called_once_with(
        19645980884,
        "Automated note",
        dry_run=True,
        headless=False,
        backend="auto",
    )


def test_browser_status_reports_automatic_native_headless_backend(
    monkeypatch, tmp_path
):
    from fitops.cli.main import app

    executable = tmp_path / "Brave Browser"
    executable.touch()
    automation_dir = tmp_path / "brave-automation"
    automation_dir.mkdir()
    profile = BrowserProfile("brave", executable, automation_dir, "Default")
    monkeypatch.setattr("fitops.cli.browser.resolve_browser_profile", lambda: profile)
    monkeypatch.setattr(
        "fitops.browser.config._browser_defaults",
        lambda _browser_type: (executable, tmp_path / "normal-brave-data"),
    )

    result = CliRunner().invoke(app, ["browser", "status", "--json"])

    assert result.exit_code == 0, result.output
    browser = json.loads(result.output)["browser"]
    assert browser["is_default_user_data_dir"] is False
    assert browser["append_backend"] == "brave-headless"


def test_dashboard_description_append_route(monkeypatch):
    from fitops.dashboard.routes import browser

    result_value = DescriptionAppendResult(
        activity_id=19645980884,
        activity_url="https://www.strava.com/activities/19645980884",
        before_length=10,
        after_length=25,
        saved=False,
        dry_run=True,
    )
    automation = MagicMock(return_value=result_value)
    monkeypatch.setattr(browser, "append_activity_description", automation)
    app = FastAPI()
    app.include_router(browser.register())

    with TestClient(app) as client:
        response = client.post(
            "/api/browser/append-description",
            json={
                "activity_id": 19645980884,
                "text": "Automated note",
                "dry_run": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["_meta"]["tool"] == "fitops"
    assert response.json()["description_update"]["dry_run"] is True
    automation.assert_called_once_with(
        19645980884,
        "Automated note",
        dry_run=True,
        headless=True,
        backend="auto",
    )


def test_dashboard_description_append_returns_browser_error(monkeypatch):
    from fitops.dashboard.routes import browser

    monkeypatch.setattr(
        browser,
        "append_activity_description",
        MagicMock(
            side_effect=BrowserPublicationError(
                "Close Brave first.",
                code="browser_profile_in_use",
                status_code=409,
            )
        ),
    )
    app = FastAPI()
    app.include_router(browser.register())

    with TestClient(app) as client:
        response = client.post(
            "/api/browser/append-description",
            json={"activity_id": 19645980884, "text": "Automated note"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "browser_profile_in_use"


def test_brave_javascript_passes_private_text_as_base64():
    private_text = "Private note with 'quotes' and ünicode"

    scripts = _browser_javascript(private_text)

    assert all(private_text not in script for script in scripts)
    assert all("document.querySelector" in script for script in scripts)


def test_brave_live_session_parses_dry_run_result(monkeypatch):
    completed = SimpleNamespace(
        returncode=0,
        stdout='{"ok":true,"before_length":12,"after_length":27}\n',
        stderr="",
    )
    run = MagicMock(return_value=completed)
    monkeypatch.setattr("fitops.browser.description.subprocess.run", run)

    result = _run_brave_live_session(
        activity_id=19645980884,
        text="Automated note",
        dry_run=True,
    )

    assert result.backend == "brave_live_session"
    assert result.saved is False
    assert result.before_length == 12
    command = run.call_args.args[0]
    assert command[0:2] == ["osascript", "-e"]
    assert "Automated note" not in command[2]


def test_brave_live_session_explains_disabled_javascript(monkeypatch):
    completed = SimpleNamespace(
        returncode=1,
        stdout="",
        stderr="Executing JavaScript through AppleScript is turned off.",
    )
    monkeypatch.setattr(
        "fitops.browser.description.subprocess.run", MagicMock(return_value=completed)
    )

    with pytest.raises(BrowserPublicationError) as raised:
        _run_brave_live_session(
            activity_id=19645980884,
            text="Automated note",
            dry_run=True,
        )

    assert raised.value.code == "brave_javascript_events_disabled"
