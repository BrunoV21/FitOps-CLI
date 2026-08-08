from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from fitops.browser.config import BrowserProfile
from fitops.browser.upload import (
    ActivityUploadResult,
    UploadOption,
    _validate_upload_inputs,
    _wait_for_activity_id,
    _wait_for_upload_editor,
    duplicate_upload_message,
    match_upload_option,
    upload_activity_file,
)
from fitops.utils.exceptions import BrowserPublicationError


def _upload_result(**overrides) -> ActivityUploadResult:
    values = {
        "strava_activity_id": 19650000001,
        "activity_url": "https://www.strava.com/activities/19650000001",
        "file_name": "run.tcx",
        "file_format": "tcx",
        "title": "Outdoor run",
        "sport_type": "Run",
        "gear_value": "27644260",
        "gear_label": "Adidas Adistar 4 (852.7 km)",
        "backend": "brave_headless_cdp",
    }
    values.update(overrides)
    return ActivityUploadResult(**values)


def test_match_upload_option_supports_value_exact_label_and_gear_name():
    options = [
        UploadOption("27644260", "Adidas Adistar 4 (852.7 km)"),
        UploadOption("32905968", "HOKA Rocket X3 (0 km)"),
    ]

    assert match_upload_option(options, "27644260") == options[0]
    assert match_upload_option(options, "adidas adistar 4 (852.7 KM)") == options[0]
    assert match_upload_option(options, "Adidas Adistar 4") == options[0]
    assert match_upload_option(options, "Missing shoe") is None


def test_duplicate_upload_message_extracts_strava_duplicate_line():
    body = "Upload and Sync\n20260806Outdoor cycle.gpx duplicate of Outdoor cycle\nSave"
    assert duplicate_upload_message(body) == (
        "20260806Outdoor cycle.gpx duplicate of Outdoor cycle"
    )
    assert duplicate_upload_message("Upload and Sync\nReady") is None


def test_upload_editor_wait_returns_structured_duplicate_error(tmp_path):
    class Body:
        def inner_text(self):
            return "run.tcx duplicate of Morning Run"

    class Field:
        @property
        def first(self):
            return self

        def is_visible(self):
            return False

    class Page:
        def locator(self, selector):
            return Body() if selector == "body" else Field()

    with pytest.raises(BrowserPublicationError) as raised:
        _wait_for_upload_editor(Page(), tmp_path / "run.tcx")
    assert raised.value.code == "activity_already_exists"
    assert raised.value.status_code == 409


def test_wait_for_activity_id_reads_strava_url():
    page = MagicMock(url="https://www.strava.com/activities/19659146386")
    assert _wait_for_activity_id(page) == 19659146386


def test_upload_input_validation_requires_supported_existing_file(tmp_path):
    unsupported = tmp_path / "activity.fit"
    unsupported.write_text("data")

    with pytest.raises(BrowserPublicationError) as raised:
        _validate_upload_inputs(unsupported, "Morning run", "Run")
    assert raised.value.code == "upload_file_type_unsupported"

    with pytest.raises(BrowserPublicationError) as raised:
        _validate_upload_inputs(tmp_path / "missing.gpx", "Morning run", "Run")
    assert raised.value.code == "upload_file_not_found"


def test_custom_brave_profile_routes_upload_to_native_headless(monkeypatch, tmp_path):
    source = tmp_path / "run.tcx"
    source.write_text("<TrainingCenterDatabase />")
    executable = tmp_path / "Brave Browser"
    executable.touch()
    user_data = tmp_path / "automation"
    user_data.mkdir()
    profile = BrowserProfile("brave", executable, user_data, "Default")
    expected = _upload_result(file_name="run.tcx")
    native = MagicMock(return_value=expected)
    monkeypatch.setattr(
        "fitops.browser.upload.resolve_browser_profile", lambda: profile
    )
    monkeypatch.setattr(
        "fitops.browser.config._browser_defaults",
        lambda _browser_type: (executable, tmp_path / "normal-data"),
    )
    monkeypatch.setattr("fitops.browser.upload._run_native_headless_upload", native)

    result = upload_activity_file(
        source,
        title="Outdoor run",
        description="Uploaded from FitOps",
        sport_type="Run",
        gear="27644260",
    )

    assert result.strava_activity_id == 19650000001
    native.assert_called_once_with(
        profile,
        source=source.resolve(),
        title="Outdoor run",
        description="Uploaded from FitOps",
        sport_type="Run",
        gear="27644260",
    )


def test_upload_activity_cli_returns_json_with_strava_id(monkeypatch, tmp_path):
    from fitops.cli.main import app

    source = tmp_path / "run.tcx"
    source.write_text("<TrainingCenterDatabase />")
    automation = MagicMock(return_value=_upload_result(file_name="run.tcx"))
    monkeypatch.setattr("fitops.browser.upload.upload_activity_file", automation)

    result = CliRunner().invoke(
        app,
        [
            "browser",
            "upload-activity",
            str(source),
            "--title",
            "Outdoor run",
            "--description",
            "Uploaded from FitOps",
            "--sport",
            "Run",
            "--gear",
            "27644260",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["_meta"]["tool"] == "fitops"
    assert payload["_meta"]["filters_applied"]["file_name"] == "run.tcx"
    assert "description" not in payload["_meta"]["filters_applied"]
    assert payload["activity_upload"]["strava_activity_id"] == 19650000001
    automation.assert_called_once_with(
        source,
        title="Outdoor run",
        description="Uploaded from FitOps",
        sport_type="Run",
        gear="27644260",
        headless=True,
        backend="auto",
    )


def test_upload_activity_cli_returns_structured_duplicate_error(monkeypatch, tmp_path):
    from fitops.cli.main import app

    source = tmp_path / "ride.gpx"
    source.write_text("<gpx />")
    monkeypatch.setattr(
        "fitops.browser.upload.upload_activity_file",
        MagicMock(
            side_effect=BrowserPublicationError(
                "Strava reports that ride.gpx already exists.",
                code="activity_already_exists",
                status_code=409,
            )
        ),
    )

    result = CliRunner().invoke(
        app,
        [
            "browser",
            "upload-activity",
            str(source),
            "--title",
            "Outdoor ride",
            "--sport",
            "Ride",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["_meta"]["total_count"] == 0
    assert payload["error"]["code"] == "activity_already_exists"


def test_dashboard_upload_route_returns_strava_activity_id(monkeypatch):
    from fitops.dashboard.routes import browser

    automation = MagicMock(return_value=_upload_result())
    monkeypatch.setattr("fitops.browser.upload.upload_activity_file", automation)
    app = FastAPI()
    app.include_router(browser.register())

    with TestClient(app) as client:
        response = client.post(
            "/api/browser/upload-activity",
            files={"file": ("run.tcx", b"<TrainingCenterDatabase />", "text/xml")},
            data={
                "title": "Outdoor run",
                "description": "Uploaded from FitOps",
                "sport_type": "Run",
                "gear": "27644260",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["_meta"]["tool"] == "fitops"
    assert payload["activity_upload"]["strava_activity_id"] == 19650000001
    call = automation.call_args
    assert call.kwargs["title"] == "Outdoor run"
    assert call.kwargs["sport_type"] == "Run"
    assert call.kwargs["gear"] == "27644260"
    assert Path(call.args[0]).name == "run.tcx"


def test_dashboard_upload_route_returns_browser_error(monkeypatch):
    from fitops.dashboard.routes import browser

    monkeypatch.setattr(
        "fitops.browser.upload.upload_activity_file",
        MagicMock(
            side_effect=BrowserPublicationError(
                "The activity already exists on Strava.",
                code="activity_already_exists",
                status_code=409,
            )
        ),
    )
    app = FastAPI()
    app.include_router(browser.register())

    with TestClient(app) as client:
        response = client.post(
            "/api/browser/upload-activity",
            files={"file": ("ride.gpx", b"<gpx />", "text/xml")},
            data={"title": "Outdoor ride", "sport_type": "Ride"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "activity_already_exists"


def test_profile_template_exposes_browser_upload_form():
    template = (
        Path(__file__).parents[1] / "fitops/dashboard/templates/profile.html"
    ).read_text()
    assert 'id="upload-activity-form"' in template
    assert "/api/browser/upload-activity" in template
