from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
from fitops.db.session import dispose_engine, get_async_session
from fitops.importers.activity_files import (
    ActivityFileError,
    import_activity_bytes,
    import_activity_file,
    parse_activity_bytes,
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
    assert parsed.laps[0].index == 0


def test_tcx_parser_recognizes_health_outdoor_sport_metadata():
    data = (FIXTURES / "sample.tcx").read_bytes().replace(
        b'Sport="Running"', b'Sport="Outdoor run"'
    )

    parsed = parse_activity_bytes(data, "activity.tcx")

    assert parsed.sport_type == "Run"
    assert parsed.sport_inference_source == "file_metadata"
    assert parsed.name == "Run on 2026-01-01"


def test_parser_rejects_mismatched_and_unsafe_xml():
    with pytest.raises(ActivityFileError, match="root"):
        parse_activity_bytes(b"<gpx></gpx>", "activity.tcx")
    with pytest.raises(ActivityFileError, match="DTD"):
        parse_activity_bytes(
            b'<!DOCTYPE gpx [<!ENTITY x "bad">]><gpx>&x;</gpx>', "activity.gpx"
        )


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
    assert (isolated_fitops / first.import_record.relative_path).read_bytes() == (
        FIXTURES / "sample.tcx"
    ).read_bytes()

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
    assert stream_count >= 4
    assert import_count == 1


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
    assert (isolated_fitops / result.import_record.relative_path).is_file()

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
            await connection.execute(sql_text("SELECT activity_id FROM activity_weather"))
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
        ["activities", "import", str(FIXTURES / "sample.tcx"), "--json"],
    )
    assert imported.exit_code == 0, imported.output
    payload = json.loads(imported.output)
    assert payload["_meta"]["tool"] == "fitops"
    assert payload["activity"]["activity_id"] == 1
    assert payload["activity"]["strava_activity_id"] is None
    assert payload["import"]["created"] is True

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
        with (FIXTURES / "sample.tcx").open("rb") as source:
            response = client.post(
                "/api/activities/import",
                files={"file": ("sample.tcx", source, "application/xml")},
                data={"sport": "auto"},
            )
        assert response.status_code == 201
        activity_id = response.json()["activity"]["activity_id"]
        detail = client.get(f"/activities/{activity_id}")
        assert detail.status_code == 200
        assert "Publish to Strava" in detail.text


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


async def test_browser_publish_links_strava_id_and_stamp(isolated_fitops, monkeypatch):
    from fitops.athlete_service import create_local_athlete
    from fitops.browser.publisher import publish_activity

    await create_local_athlete("Publisher")
    imported = await import_activity_file(FIXTURES / "sample.tcx")
    monkeypatch.setattr(
        "fitops.browser.publisher._run_browser", lambda **kwargs: 987654321
    )

    result = await publish_activity(imported.activity.id)
    assert result.status == "completed"
    assert result.strava_id == 987654321
    async with get_async_session() as session:
        activity = await session.get(Activity, imported.activity.id)
    assert activity.strava_id == 987654321
    assert "FitOps Analytics" in activity.description
