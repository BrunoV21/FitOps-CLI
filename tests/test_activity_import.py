from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine
from typer.testing import CliRunner

from fitops.browser.config import BrowserProfile, ensure_profile_available
from fitops.config import settings as settings_module
from fitops.db.migrations import create_all_tables
from fitops.db.models.activity import Activity
from fitops.db.models.activity_import import ActivityImport
from fitops.db.models.activity_laps import ActivityLap
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.models.activity_weather import ActivityWeather
from fitops.db.session import dispose_engine, get_async_session
from fitops.importers.activity_files import (
    ActivityFileError,
    import_activity_bytes,
    import_activity_file,
    parse_activity_bytes,
    suggest_activity_from_filename,
)
from fitops.strava.availability import (
    clear_availability_cache,
    get_strava_availability,
)
from fitops.utils.exceptions import BrowserPublicationError, StravaAPIError

FIXTURES = Path(__file__).parent / "fixtures"

TIMED_GPX = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Sample Run</name><trkseg>
    <trkpt lat="51.5000" lon="-0.1000"><ele>10</ele><time>2026-01-01T09:00:00Z</time></trkpt>
    <trkpt lat="51.5009" lon="-0.1000"><ele>20</ele><time>2026-01-01T09:00:30Z</time></trkpt>
    <trkpt lat="51.5018" lon="-0.1000"><ele>30</ele><time>2026-01-01T09:01:00Z</time></trkpt>
    <trkpt lat="51.5027" lon="-0.1000"><ele>25</ele><time>2026-01-01T09:01:30Z</time></trkpt>
    <trkpt lat="51.5036" lon="-0.1000"><ele>15</ele><time>2026-01-01T09:02:00Z</time></trkpt>
  </trkseg></trk>
</gpx>"""


@pytest.fixture(autouse=True)
def mock_import_weather(monkeypatch):
    weather = {
        "temperature_c": 22.0,
        "humidity_pct": 55.0,
        "apparent_temp_c": 22.5,
        "dew_point_c": 12.5,
        "wind_speed_ms": 2.0,
        "wind_direction_deg": 180.0,
        "wind_gusts_ms": 3.0,
        "precipitation_mm": 0.0,
        "weather_code": 1,
    }
    monkeypatch.setattr(
        "fitops.weather.service.fetch_activity_weather",
        AsyncMock(return_value=weather),
    )
    monkeypatch.setattr(
        "fitops.weather.service.fetch_forecast_weather",
        AsyncMock(return_value=None),
    )


@pytest.fixture
async def isolated_fitops(tmp_path, monkeypatch):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path / "fitops"))
    settings_module._settings = None
    await dispose_engine()
    await create_all_tables()
    yield tmp_path / "fitops"
    await dispose_engine()
    settings_module._settings = None
    clear_availability_cache()


def test_tcx_parser_normalizes_summary_streams_and_laps():
    parsed = parse_activity_bytes((FIXTURES / "sample.tcx").read_bytes(), "sample.tcx")

    assert parsed.sport_type == "Run"
    assert parsed.sport_inference_source == "file_metadata"
    assert parsed.distance_m == pytest.approx(400.0)
    assert parsed.moving_time_s == 120
    assert parsed.streams["distance"][-1] == pytest.approx(400.0)
    assert len(parsed.streams["grade_smooth"]) == len(parsed.streams["time"])
    assert parsed.laps[0].index == 0


def test_tcx_parser_recognizes_health_outdoor_sport_metadata():
    data = (
        (FIXTURES / "sample.tcx")
        .read_bytes()
        .replace(b'Sport="Running"', b'Sport="Outdoor run"')
    )

    parsed = parse_activity_bytes(data, "activity.tcx")

    assert parsed.sport_type == "Run"
    assert parsed.sport_inference_source == "file_metadata"
    assert parsed.name == "Outdoor run"


def test_import_default_cycle_title_can_be_overridden():
    parsed = parse_activity_bytes(TIMED_GPX, "activity.gpx", sport_type="Ride")
    overridden = parse_activity_bytes(
        TIMED_GPX,
        "activity.gpx",
        sport_type="Ride",
        name="Sunday club ride",
    )

    assert parsed.name == "Outdoor cycle"
    assert overridden.name == "Sunday club ride"


def test_parser_rejects_mismatched_and_unsafe_xml():
    with pytest.raises(ActivityFileError, match="root"):
        parse_activity_bytes(b"<gpx></gpx>", "activity.tcx")
    with pytest.raises(ActivityFileError, match="DTD"):
        parse_activity_bytes(
            b'<!DOCTYPE gpx [<!ENTITY x "bad">]><gpx>&x;</gpx>', "activity.gpx"
        )


@pytest.mark.parametrize(
    ("filename", "expected_name", "expected_sport"),
    [
        ("20260808Outdoor run.tcx", "Outdoor run", "Run"),
        ("20260807Outdoor cycle.tcx", "Outdoor cycle", "Ride"),
        ("2026-08-06_Trail_run.gpx", "Trail run", "TrailRun"),
        ("morning_swim.gpx", "morning swim", "Swim"),
    ],
)
def test_filename_suggestion_extracts_title_and_sport(
    filename, expected_name, expected_sport
):
    suggestion = suggest_activity_from_filename(filename)

    assert suggestion == {"name": expected_name, "sport_type": expected_sport}


async def test_import_persists_processed_activity_and_deduplicates(isolated_fitops):
    from fitops.athlete_service import create_local_athlete

    athlete, created = await create_local_athlete("Offline Athlete")
    assert created is True

    first = await import_activity_file(FIXTURES / "sample.tcx")
    second = await import_activity_file(FIXTURES / "sample.tcx")

    assert first.created is True
    assert second.created is False
    assert second.activity.id == first.activity.id
    assert first.activity.athlete_id == athlete.id
    assert first.activity.strava_id is None
    assert first.activity.origin == "tcx"
    assert first.activity.name == "Outdoor run"
    assert first.weather_status == "fetched"
    assert second.weather_status == "already_available"
    assert first.import_record.relative_path == ""
    assert not (isolated_fitops / "activity-files").exists()

    async with get_async_session() as session:
        stream_count = (
            await session.execute(
                select(func.count())
                .select_from(ActivityStream)
                .where(ActivityStream.activity_id == first.activity.id)
            )
        ).scalar_one()
        import_count = (
            await session.execute(select(func.count()).select_from(ActivityImport))
        ).scalar_one()
        weather = (
            await session.execute(
                select(ActivityWeather).where(
                    ActivityWeather.activity_id == first.activity.id
                )
            )
        ).scalar_one()
        stream_types = set(
            (
                await session.execute(
                    select(ActivityStream.stream_type).where(
                        ActivityStream.activity_id == first.activity.id
                    )
                )
            ).scalars()
        )
    assert stream_count >= 4
    assert import_count == 1
    assert weather.wbgt_c is not None
    assert weather.wap_factor is not None
    assert weather.true_pace_s_per_km is not None
    assert {"grade_smooth", "true_pace"}.issubset(stream_types)


async def test_import_deduplicates_same_recording_across_gpx_and_tcx(
    isolated_fitops,
):
    from fitops.athlete_service import create_local_athlete

    await create_local_athlete("Offline Athlete")

    first = await import_activity_bytes(TIMED_GPX, "same-run.gpx")
    second = await import_activity_file(FIXTURES / "sample.tcx")

    assert first.created is True
    assert second.created is False
    assert second.match_type == "activity_signature"
    assert second.activity.id == first.activity.id
    assert second.import_record.id == first.import_record.id

    async with get_async_session() as session:
        activity_count = (
            await session.execute(select(func.count()).select_from(Activity))
        ).scalar_one()
        import_count = (
            await session.execute(select(func.count()).select_from(ActivityImport))
        ).scalar_one()
        lap_count = (
            await session.execute(
                select(func.count())
                .select_from(ActivityLap)
                .where(ActivityLap.activity_id == first.activity.id)
            )
        ).scalar_one()
    assert activity_count == 1
    assert import_count == 1
    assert lap_count == 1


async def test_import_attaches_source_to_matching_strava_activity(isolated_fitops):
    from fitops.athlete_service import create_local_athlete

    athlete, _ = await create_local_athlete("Connected Athlete")
    async with get_async_session() as session:
        existing = Activity(
            strava_id=123456,
            athlete_id=athlete.id,
            origin="strava",
            name="Already on Strava",
            sport_type="Run",
            start_date=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            start_date_local=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            distance_m=400,
            moving_time_s=120,
            elapsed_time_s=120,
        )
        session.add(existing)
        await session.flush()
        existing_id = existing.id

    result = await import_activity_bytes(TIMED_GPX, "same-run.gpx")

    assert result.created is False
    assert result.match_type == "activity_signature"
    assert result.activity.id == existing_id
    assert result.activity.strava_id == 123456
    assert result.import_record.activity_id == existing_id
    assert result.import_record.relative_path == ""
    assert not (isolated_fitops / "activity-files").exists()

    async with get_async_session() as session:
        activity_count = (
            await session.execute(select(func.count()).select_from(Activity))
        ).scalar_one()
        stream_count = (
            await session.execute(
                select(func.count())
                .select_from(ActivityStream)
                .where(ActivityStream.activity_id == existing_id)
            )
        ).scalar_one()
    assert activity_count == 1
    assert stream_count >= 4


async def test_first_strava_sync_links_active_offline_profile(isolated_fitops):
    from fitops.athlete_service import create_local_athlete
    from fitops.strava.sync_engine import SyncEngine

    local, _ = await create_local_athlete("Offline Athlete")
    engine = SyncEngine()
    engine._client = SimpleNamespace(
        get_authenticated_athlete=AsyncMock(
            return_value={"id": 445566, "firstname": "Connected", "lastname": "Athlete"}
        )
    )

    resolved_id = await engine._upsert_athlete()

    assert resolved_id == local.id
    async with get_async_session() as session:
        athlete = await session.get(type(local), local.id)
    assert athlete.strava_id == 445566
    assert athlete.source == "strava"


async def test_startup_migrates_legacy_provider_ids_to_local_ids(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    async with engine.begin() as connection:
        await connection.execute(
            sql_text(
                "CREATE TABLE athletes (id INTEGER PRIMARY KEY, strava_id INTEGER NOT NULL UNIQUE, firstname TEXT)"
            )
        )
        await connection.execute(
            sql_text(
                "CREATE TABLE activities (id INTEGER PRIMARY KEY, strava_id INTEGER NOT NULL UNIQUE, athlete_id INTEGER NOT NULL, name TEXT NOT NULL, sport_type TEXT NOT NULL)"
            )
        )
        await connection.execute(
            sql_text(
                "CREATE TABLE activity_weather (id INTEGER PRIMARY KEY, activity_id INTEGER NOT NULL UNIQUE)"
            )
        )
        await connection.execute(
            sql_text("INSERT INTO athletes VALUES (7, 999, 'Legacy')")
        )
        await connection.execute(
            sql_text("INSERT INTO activities VALUES (11, 555, 999, 'Run', 'Run')")
        )
        await connection.execute(
            sql_text("INSERT INTO activity_weather VALUES (1, 555)")
        )

    await create_all_tables(engine)

    async with engine.connect() as connection:
        athlete_info = (
            await connection.execute(sql_text("PRAGMA table_info(athletes)"))
        ).fetchall()
        activity_info = (
            await connection.execute(sql_text("PRAGMA table_info(activities)"))
        ).fetchall()
        athlete_id = (
            await connection.execute(sql_text("SELECT athlete_id FROM activities"))
        ).scalar_one()
        weather_id = (
            await connection.execute(
                sql_text("SELECT activity_id FROM activity_weather")
            )
        ).scalar_one()

    assert next(row for row in athlete_info if row[1] == "strava_id")[3] == 0
    assert next(row for row in activity_info if row[1] == "strava_id")[3] == 0
    assert athlete_id == 7
    assert weather_id == 11
    await engine.dispose()


def test_cli_init_import_and_list_json(tmp_path, monkeypatch):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path / "fitops"))
    settings_module._settings = None
    from fitops.cli.main import app

    runner = CliRunner()
    initialized = runner.invoke(
        app, ["athlete", "init", "--name", "CLI Athlete", "--json"]
    )
    assert initialized.exit_code == 0, initialized.output

    imported = runner.invoke(
        app,
        [
            "activities",
            "import",
            str(FIXTURES / "sample.tcx"),
            "--local-only",
            "--json",
        ],
    )
    assert imported.exit_code == 0, imported.output
    payload = json.loads(imported.output)
    assert payload["_meta"]["tool"] == "fitops"
    assert payload["activity"]["activity_id"] == 1
    assert payload["activity"]["strava_activity_id"] is None
    assert payload["import"]["created"] is True
    assert payload["weather"]["status"] == "fetched"
    assert payload["publication"]["status"] == "not_requested"

    stamped = runner.invoke(
        app,
        ["activities", "stamp", "--local-id", "1", "--json"],
    )
    assert stamped.exit_code == 0, stamped.output
    stamp_payload = json.loads(stamped.output)
    assert stamp_payload["_meta"]["tool"] == "fitops"
    assert stamp_payload["activity_id"] == 1
    assert stamp_payload["status"] == "stamped"

    listed = runner.invoke(app, ["activities", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["activities"][0]["origin"] == "tcx"


def test_dashboard_import_route_and_local_detail(isolated_fitops):
    from fastapi.testclient import TestClient

    from fitops.dashboard.server import create_app

    with TestClient(create_app()) as client:
        empty_page = client.get("/activities/import")
        assert empty_page.status_code == 200
        assert "Create an offline profile" in empty_page.text
        offline = client.post("/api/setup/offline", json={"name": "Web Athlete"})
        assert offline.status_code == 201
        ready_page = client.get("/activities/import")
        assert ready_page.status_code == 200
        assert 'id="post-to-strava"' in ready_page.text
        assert 'name="post_to_strava" value="true" checked' in ready_page.text
        assert 'id="activity-import-loading"' in ready_page.text
        assert (
            'id="activity-import-loading" class="activity-import-loading" aria-hidden="true" hidden'
            in ready_page.text
        )
        suggestion = client.get(
            "/api/activities/import/suggestion",
            params={"filename": "20260807Outdoor cycle.tcx"},
        )
        assert suggestion.status_code == 200
        assert suggestion.json() == {"name": "Outdoor cycle", "sport_type": "Ride"}
        with (FIXTURES / "sample.tcx").open("rb") as source:
            response = client.post(
                "/api/activities/import",
                files={"file": ("sample.tcx", source, "application/xml")},
                data={"sport": "auto", "post_to_strava": "false"},
            )
        assert response.status_code == 201
        assert response.json()["publication"]["status"] == "not_requested"
        activity_id = response.json()["activity"]["activity_id"]
        detail = client.get(f"/activities/{activity_id}")
        assert detail.status_code == 200
        assert "Imported TCX" in detail.text
        assert 'id="publish-btn"' not in detail.text
        assert ">Publish</button>" not in detail.text
        assert 'for="existing-strava-id">Strava activity ID</label>' in detail.text
        assert 'id="sync-btn"' in detail.text
        assert ">Sync</button>" in detail.text
        assert 'id="local-stamp-btn"' in detail.text
        assert 'class="btn btn-primary"' in detail.text

        activity_list = client.get("/activities")
        assert activity_list.status_code == 200
        assert ">Imported</span>" not in activity_list.text

        stamped = client.post(
            f"/api/activities/local/{activity_id}/stamp",
            json={"force": False},
        )
        assert stamped.status_code == 200
        assert stamped.json()["status"] == "stamped"

        stamped_detail = client.get(f"/activities/{activity_id}")
        assert stamped_detail.status_code == 200
        assert "Re-stamp" in stamped_detail.text
        assert "FitOps Analytics" in stamped_detail.text
        assert "Double-click to copy the FitOps stamp" in stamped_detail.text


def test_dashboard_import_posts_by_default_and_links_returned_id(
    isolated_fitops, monkeypatch
):
    from fastapi.testclient import TestClient

    from fitops.dashboard.server import create_app

    publish = AsyncMock(
        return_value=SimpleNamespace(
            id=7,
            activity_id=1,
            action="upload",
            status="completed",
            strava_id=987654321,
        )
    )
    monkeypatch.setattr(
        "fitops.browser.publisher.publish_activity_bytes",
        publish,
    )

    with TestClient(create_app()) as client:
        client.post("/api/setup/offline", json={"name": "Posting Athlete"})
        with (FIXTURES / "sample.tcx").open("rb") as source:
            response = client.post(
                "/api/activities/import",
                files={"file": ("sample.tcx", source, "application/xml")},
                data={"sport": "auto"},
            )

    assert response.status_code == 201
    payload = response.json()
    assert payload["publication"] == {
        "requested": True,
        "status": "completed",
        "strava_id": 987654321,
        "id": 7,
        "action": "upload",
    }
    assert payload["activity"]["strava_activity_id"] == 987654321
    assert publish.await_args.args[1] == (FIXTURES / "sample.tcx").read_bytes()
    assert publish.await_args.args[2] == "sample.tcx"


def test_dashboard_import_keeps_local_activity_when_post_fails(
    isolated_fitops, monkeypatch
):
    from fastapi.testclient import TestClient

    from fitops.dashboard.server import create_app

    monkeypatch.setattr(
        "fitops.browser.publisher.publish_activity_bytes",
        AsyncMock(
            side_effect=BrowserPublicationError(
                "Strava reports this upload is a duplicate.",
                code="activity_already_exists",
                status_code=409,
            )
        ),
    )

    with TestClient(create_app()) as client:
        client.post("/api/setup/offline", json={"name": "Fallback Athlete"})
        with (FIXTURES / "sample.tcx").open("rb") as source:
            response = client.post(
                "/api/activities/import",
                files={"file": ("sample.tcx", source, "application/xml")},
                data={"sport": "auto"},
            )

        assert response.status_code == 201
        payload = response.json()
        assert payload["activity"]["activity_id"] == 1
        assert payload["activity"]["strava_activity_id"] is None
        assert payload["publication"]["status"] == "failed"
        assert payload["publication"]["code"] == "activity_already_exists"
        assert "duplicate" in payload["publication"]["error"]
        assert client.get("/activities/1").status_code == 200

    assert not (isolated_fitops / "activity-files").exists()


def test_dashboard_sync_links_existing_strava_activity(isolated_fitops, monkeypatch):
    from fastapi.testclient import TestClient

    from fitops.dashboard.server import create_app

    publication = SimpleNamespace(
        id=9,
        activity_id=1,
        action="sync",
        status="completed",
        strava_id=24681012,
    )
    sync = AsyncMock(return_value=publication)
    monkeypatch.setattr("fitops.browser.publisher.publish_activity", sync)

    with TestClient(create_app()) as client:
        client.post("/api/setup/offline", json={"name": "Sync Athlete"})
        with (FIXTURES / "sample.tcx").open("rb") as source:
            imported = client.post(
                "/api/activities/import",
                files={"file": ("sample.tcx", source, "application/xml")},
                data={"post_to_strava": "false"},
            )
        activity_id = imported.json()["activity"]["activity_id"]

        missing_id = client.post(f"/api/activities/{activity_id}/sync-strava")
        assert missing_id.status_code == 422
        assert missing_id.json()["code"] == "strava_id_required"

        response = client.post(
            f"/api/activities/{activity_id}/sync-strava?strava_id=24681012"
        )

    assert response.status_code == 200
    assert response.json()["publication"] == {
        "id": 9,
        "activity_id": 1,
        "action": "sync",
        "status": "completed",
        "strava_id": 24681012,
    }
    sync.assert_awaited_once_with(activity_id, strava_id=24681012)


def test_sync_endpoint_preserves_strava_403(isolated_fitops, monkeypatch):
    from fastapi.testclient import TestClient

    from fitops.dashboard.server import create_app

    fake_settings = SimpleNamespace(
        is_authenticated=True,
        athlete_id=1,
        has_write_scope=False,
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.api.get_settings", lambda: fake_settings
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.api.SyncEngine.run",
        AsyncMock(
            side_effect=StravaAPIError(
                "Strava API error 403 for /athlete",
                status_code=403,
                endpoint="/athlete",
            )
        ),
    )

    with TestClient(create_app()) as client:
        response = client.post("/api/sync")
    assert response.status_code == 403
    assert response.json()["upstream_status"] == 403


async def test_availability_preserves_upstream_status(monkeypatch):
    clear_availability_cache()
    monkeypatch.setattr(
        "fitops.strava.availability.get_settings",
        lambda: SimpleNamespace(is_authenticated=True),
    )
    client = SimpleNamespace(
        get_authenticated_athlete=AsyncMock(
            side_effect=StravaAPIError("inactive", status_code=403)
        )
    )
    result = await get_strava_availability(force=True, client=client)
    assert result.available is False
    assert result.status_code == 403


def test_open_browser_profile_fails_safely(tmp_path):
    executable = tmp_path / "browser"
    executable.touch()
    user_data = tmp_path / "data"
    user_data.mkdir()
    (user_data / "SingletonLock").touch()
    profile = BrowserProfile("brave", executable, user_data, "Default")

    with pytest.raises(BrowserPublicationError) as raised:
        ensure_profile_available(profile)
    assert raised.value.status_code == 409
    assert raised.value.code == "browser_profile_in_use"


async def test_browser_publish_uploads_selected_file_and_links_returned_id(
    isolated_fitops, monkeypatch
):
    from fitops.athlete_service import create_local_athlete
    from fitops.browser.publisher import publish_activity

    await create_local_athlete("Publisher")
    imported = await import_activity_file(FIXTURES / "sample.tcx")
    upload = MagicMock(return_value=SimpleNamespace(strava_activity_id=987654321))
    monkeypatch.setattr("fitops.browser.publisher.upload_activity_file", upload)

    result = await publish_activity(
        imported.activity.id,
        source_path=FIXTURES / "sample.tcx",
    )
    assert result.status == "completed"
    assert result.action == "upload"
    assert result.strava_id == 987654321
    assert upload.call_args.args[0] == FIXTURES / "sample.tcx"
    assert "FitOps Analytics" in upload.call_args.kwargs["description"]
    async with get_async_session() as session:
        activity = await session.get(Activity, imported.activity.id)
    assert activity.strava_id == 987654321
    assert "FitOps Analytics" in activity.description


async def test_browser_publish_uploads_request_bytes_without_source_copy(
    isolated_fitops, monkeypatch
):
    from fitops.athlete_service import create_local_athlete
    from fitops.browser.publisher import publish_activity_bytes

    await create_local_athlete("Byte Publisher")
    data = (FIXTURES / "sample.tcx").read_bytes()
    imported = await import_activity_bytes(data, "sample.tcx")
    upload = MagicMock(return_value=SimpleNamespace(strava_activity_id=1122334455))
    monkeypatch.setattr("fitops.browser.publisher.upload_activity_data", upload)

    result = await publish_activity_bytes(imported.activity.id, data, "sample.tcx")

    assert result.strava_id == 1122334455
    assert upload.call_args.args[:2] == (data, "sample.tcx")
    assert "FitOps Analytics" in upload.call_args.kwargs["description"]
    assert not (isolated_fitops / "activity-files").exists()


async def test_browser_existing_strava_id_links_without_upload(
    isolated_fitops, monkeypatch
):
    from fitops.athlete_service import create_local_athlete
    from fitops.browser.publisher import publish_activity

    await create_local_athlete("Linker")
    imported = await import_activity_file(FIXTURES / "sample.tcx")
    append_description = MagicMock(return_value=SimpleNamespace(saved=True))
    upload = MagicMock()
    monkeypatch.setattr(
        "fitops.browser.publisher.append_activity_description", append_description
    )
    monkeypatch.setattr("fitops.browser.publisher.upload_activity_file", upload)

    result = await publish_activity(imported.activity.id, strava_id=123456789)

    assert result.action == "sync"
    assert result.strava_id == 123456789
    assert append_description.call_args.args[0] == 123456789
    assert "FitOps Analytics" in append_description.call_args.args[1]
    upload.assert_not_called()


def test_cli_existing_strava_id_reports_sync(monkeypatch):
    from fitops.cli.main import app

    monkeypatch.setattr("fitops.cli.activities.init_db", lambda: None)
    monkeypatch.setattr(
        "fitops.browser.publisher.publish_activity",
        AsyncMock(
            return_value=SimpleNamespace(
                id=1,
                activity_id=42,
                action="sync",
                status="completed",
                strava_id=123456789,
            )
        ),
    )

    result = CliRunner().invoke(
        app,
        ["activities", "sync-strava", "42", "--strava-id", "123456789"],
    )

    assert result.exit_code == 0, result.output
    assert "Synced with Strava activity 123456789." in result.output


def test_cli_import_posts_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path / "fitops"))
    settings_module._settings = None
    from fitops.cli.main import app

    publication = SimpleNamespace(
        id=3,
        activity_id=1,
        action="upload",
        status="completed",
        strava_id=1357911,
    )
    publish = AsyncMock(return_value=publication)
    monkeypatch.setattr("fitops.browser.publisher.publish_activity", publish)

    runner = CliRunner()
    initialized = runner.invoke(
        app, ["athlete", "init", "--name", "CLI Poster", "--json"]
    )
    assert initialized.exit_code == 0, initialized.output

    imported = runner.invoke(
        app,
        ["activities", "import", str(FIXTURES / "sample.tcx"), "--json"],
    )

    assert imported.exit_code == 0, imported.output
    payload = json.loads(imported.output)
    assert payload["_meta"]["filters_applied"]["post_to_strava"] is True
    assert payload["activity"]["strava_activity_id"] == 1357911
    assert payload["publication"]["status"] == "completed"
    assert payload["publication"]["strava_id"] == 1357911
    publish.assert_awaited_once()
    assert publish.await_args.kwargs["source_path"] == FIXTURES / "sample.tcx"


def test_cli_import_reports_post_failure_without_losing_activity(tmp_path, monkeypatch):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path / "fitops"))
    settings_module._settings = None
    from fitops.cli.main import app

    monkeypatch.setattr(
        "fitops.browser.publisher.publish_activity",
        AsyncMock(
            side_effect=BrowserPublicationError(
                "The configured browser profile is not logged in.",
                code="strava_login_required",
                status_code=401,
            )
        ),
    )

    runner = CliRunner()
    initialized = runner.invoke(
        app, ["athlete", "init", "--name", "CLI Fallback", "--json"]
    )
    assert initialized.exit_code == 0, initialized.output

    imported = runner.invoke(
        app,
        ["activities", "import", str(FIXTURES / "sample.tcx"), "--json"],
    )

    assert imported.exit_code == 1
    payload = json.loads(imported.stdout)
    assert payload["activity"]["activity_id"] == 1
    assert payload["activity"]["strava_activity_id"] is None
    assert payload["publication"]["status"] == "failed"
    assert payload["publication"]["error"]["code"] == "strava_login_required"

    listed = runner.invoke(app, ["activities", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["activities"][0]["activity_id"] == 1
