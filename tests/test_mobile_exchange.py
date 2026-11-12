from __future__ import annotations

import json
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

from fitops.db.base import Base
from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.models.mobile_activity_origin import MobileActivityOrigin
from fitops.importers import mobile_exchange as mobile
from fitops.importers.activity_files import ActivityFileError


def export_payload() -> dict:
    return {
        "format": "fitops.activities",
        "version": 1,
        "exported_at": "2026-11-01T10:00:00Z",
        "activities": [
            {
                "id": "client-id-is-not-trusted",
                "provider": "file",
                "provider_account_id": "local",
                "provider_activity_id": "tcx:Run:2026-11-01T08:00:00Z",
                "name": "Mobile morning run",
                "sport": "Run",
                "start_date": "2026-11-01T09:00:00+01:00",
                "duration_seconds": 20,
                "distance_m": 80,
                "samples": [
                    {
                        "time_seconds": 0,
                        "heartrate_bpm": 150,
                        "distance_m": 0,
                        "speed_m_per_second": 4,
                    },
                    {
                        "time_seconds": 10,
                        "heartrate_bpm": None,
                        "distance_m": 40,
                        "speed_m_per_second": 4,
                    },
                    {
                        "time_seconds": 20,
                        "heartrate_bpm": 155,
                        "distance_m": 80,
                        "speed_m_per_second": None,
                    },
                ],
            }
        ],
    }


def encoded(payload: dict | None = None) -> bytes:
    return json.dumps(payload or export_payload()).encode()


@pytest.fixture
async def memory_store(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def session():
        async with factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    monkeypatch.setattr(mobile, "get_async_session", session)
    monkeypatch.setattr(
        mobile, "get_settings", lambda: SimpleNamespace(active_athlete_id=1)
    )
    monkeypatch.setattr(
        mobile, "AthleteSettings", lambda: SimpleNamespace(lthr=None, max_hr=None)
    )
    snapshot = AsyncMock()
    monkeypatch.setattr(mobile, "persist_training_load_snapshot", snapshot)
    yield session, snapshot
    await engine.dispose()


def test_mobile_parser_preserves_explicit_units_and_timezone():
    parsed = mobile.parse_mobile_exchange(encoded())
    assert parsed.activities[0].duration_seconds == 20
    assert parsed.activities[0].start_date.isoformat() == "2026-11-01T09:00:00+01:00"
    assert parsed.activities[0].samples[1].heartrate_bpm is None
    assert parsed.activities[0].provider_activity_id.startswith("tcx:")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(version=2),
        lambda p: p.update(version=True),
        lambda p: p.update(access_token="never-accepted"),
        lambda p: p["activities"][0].update(duration_seconds=-1),
        lambda p: p["activities"][0].update(start_date="2026-11-01T08:00:00"),
        lambda p: p["activities"][0].update(start_date=1793520000),
        lambda p: p["activities"][0]["samples"].reverse(),
        lambda p: p["activities"].append(deepcopy(p["activities"][0])),
        lambda p: p["activities"][0]["samples"][0].update(heartrate_bpm=True),
    ],
)
def test_mobile_parser_rejects_unsupported_or_unsafe_exports(mutation):
    payload = export_payload()
    mutation(payload)
    with pytest.raises(ActivityFileError) as exc:
        mobile.parse_mobile_exchange(encoded(payload))
    assert exc.value.code == "invalid_mobile_export"


async def test_mobile_import_uses_source_identity_and_updates_streams(memory_store):
    session, snapshot = memory_store
    first = await mobile.import_mobile_bytes(encoded())
    assert first.created_count == 1
    assert first.activities[0].strava_id is None
    assert first.activities[0].origin == "fitops-mobile"
    assert first.activities[0].start_date.hour == 8
    assert first.activities[0].elapsed_time_s == 20
    assert first.activities[0].moving_time_s is None
    assert first.activities[0].training_stress_score is None
    assert first.activities[0].average_heartrate == 150
    payload = export_payload()
    payload["activities"][0].update(id="another-untrusted-id", name="Changed name")
    payload["activities"][0]["samples"][0]["heartrate_bpm"] = 160
    second = await mobile.import_mobile_bytes(encoded(payload))
    assert second.updated_count == 1
    assert second.activities[0].id == first.activities[0].id
    assert second.activities[0].name == "Changed name"
    async with session() as db:
        assert (
            await db.execute(select(func.count()).select_from(Activity))
        ).scalar_one() == 1
        assert (
            await db.execute(select(func.count()).select_from(MobileActivityOrigin))
        ).scalar_one() == 1
        streams = (
            (
                await db.execute(
                    select(ActivityStream).where(
                        ActivityStream.activity_id == first.activities[0].id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {s.stream_type for s in streams} == {
            "time",
            "distance",
            "heartrate",
            "velocity_smooth",
            "source_velocity_m_per_second",
        }
        assert next(s for s in streams if s.stream_type == "heartrate").data == [
            160,
            None,
            155,
        ]
    assert snapshot.await_count == 2


def test_mobile_speed_derivation_preserves_source_values_and_prefers_direct_speed():
    payload = export_payload()
    record = payload["activities"][0]
    record["samples"][0]["speed_m_per_second"] = None
    record["samples"][1]["speed_m_per_second"] = 2.5
    parsed = mobile.parse_mobile_exchange(encoded(payload)).activities[0]
    streams = mobile._streams(parsed)
    assert streams["distance"] == [0, 40, 80]
    assert streams["heartrate"] == [150, None, 155]
    assert streams["source_velocity_m_per_second"] == [None, 2.5, None]
    assert streams["velocity_smooth"] == [4, 2.5, None]


def test_mobile_speed_derivation_does_not_fill_missing_distance_or_backward_steps():
    payload = export_payload()
    samples = payload["activities"][0]["samples"]
    for sample in samples:
        sample["speed_m_per_second"] = None
    samples[1]["distance_m"] = None
    parsed = mobile.parse_mobile_exchange(encoded(payload)).activities[0]
    streams = mobile._streams(parsed)
    assert streams["distance"] == [0, None, 80]
    assert "velocity_smooth" not in streams
    samples[1]["distance_m"] = 100
    streams = mobile._streams(
        mobile.parse_mobile_exchange(encoded(payload)).activities[0]
    )
    assert streams["velocity_smooth"] == [10, None, None]
    assert streams["distance"] == [0, 100, 80]


async def test_mobile_import_derives_speed_for_cached_vo2max(memory_store, monkeypatch):
    session, _ = memory_store
    monkeypatch.setattr(
        mobile, "AthleteSettings", lambda: SimpleNamespace(lthr=170, max_hr=190)
    )
    fixture = Path("mobile/contracts/fixtures/synthetic-run.fitops.json")
    payload = json.loads(fixture.read_text())
    assert all(
        s["speed_m_per_second"] is None for s in payload["activities"][0]["samples"]
    )
    result = await mobile.import_mobile_bytes(encoded(payload))
    # Desktop intentionally uses its existing Daniels/Cooper weighted model,
    # whereas the phone uses the Daniels-only proxy. Both use the same data.
    assert result.activities[0].vo2max_estimate == pytest.approx(39.9)
    assert result.activities[0].max_speed_ms == pytest.approx(6000 / 1800)
    async with session() as db:
        saved = await db.get(Activity, result.activities[0].id)
        assert saved.vo2max_estimate == pytest.approx(39.9)
        source = (
            await db.execute(
                select(ActivityStream).where(
                    ActivityStream.activity_id == saved.id,
                    ActivityStream.stream_type == "source_velocity_m_per_second",
                )
            )
        ).scalar_one()
        assert source.data == [None] * 181
    monkeypatch.setattr(
        mobile, "AthleteSettings", lambda: SimpleNamespace(lthr=None, max_hr=None)
    )
    without_calibration = await mobile.import_mobile_bytes(encoded(payload))
    assert without_calibration.updated_count == 1
    assert without_calibration.activities[0].vo2max_estimate is None


async def test_mobile_import_excludes_large_gaps_from_vo2max_even_with_direct_speed(
    memory_store, monkeypatch
):
    session, _ = memory_store
    monkeypatch.setattr(
        mobile, "AthleteSettings", lambda: SimpleNamespace(lthr=170, max_hr=190)
    )
    payload = json.loads(
        Path("mobile/contracts/fixtures/synthetic-run.fitops.json").read_text()
    )
    record = payload["activities"][0]
    record["samples"] = [
        s
        for s in record["samples"]
        if s["time_seconds"] <= 200 or s["time_seconds"] >= 1600
    ]
    for sample in record["samples"]:
        sample["speed_m_per_second"] = 4
    result = await mobile.import_mobile_bytes(encoded(payload))
    assert result.activities[0].vo2max_estimate is None
    async with session() as db:
        streams = (
            (
                await db.execute(
                    select(ActivityStream).where(
                        ActivityStream.activity_id == result.activities[0].id
                    )
                )
            )
            .scalars()
            .all()
        )
        raw = next(
            s for s in streams if s.stream_type == "source_velocity_m_per_second"
        ).data
        normalized = next(s for s in streams if s.stream_type == "velocity_smooth").data
        assert raw == [4] * len(record["samples"])
        assert normalized[20] is None
        assert normalized[19] == 4
        assert next(s for s in streams if s.stream_type == "distance").data == [
            s["distance_m"] for s in record["samples"]
        ]


async def test_mobile_identity_is_separate_by_provider_account_and_athlete(
    memory_store,
):
    payload = export_payload()
    first = await mobile.import_mobile_bytes(encoded(payload))
    payload["activities"][0]["provider_account_id"] = "another-user"
    account = await mobile.import_mobile_bytes(encoded(payload))
    payload["activities"][0]["provider"] = "huawei"
    provider = await mobile.import_mobile_bytes(encoded(payload))
    athlete = await mobile.import_mobile_bytes(encoded(payload), athlete_id=2)
    assert len({r.activities[0].id for r in (first, account, provider, athlete)}) == 4


async def test_invalid_mobile_batch_does_not_write_partial_records(memory_store):
    session, _ = memory_store
    payload = export_payload()
    invalid = deepcopy(payload["activities"][0])
    invalid.update(provider_activity_id="second", duration_seconds=0)
    payload["activities"].append(invalid)
    with pytest.raises(ActivityFileError):
        await mobile.import_mobile_bytes(encoded(payload))
    async with session() as db:
        assert (
            await db.execute(select(func.count()).select_from(Activity))
        ).scalar_one() == 0


def test_mobile_cli_import_json_envelope(memory_store, tmp_path, monkeypatch):
    from fitops.cli import activities as commands
    from fitops.cli.main import app

    bootstraps = []
    monkeypatch.setattr(commands, "init_db", lambda: bootstraps.append(True))
    source = tmp_path / "fitops-export.json"
    source.write_bytes(encoded())
    result = CliRunner().invoke(
        app, ["activities", "import-mobile", str(source), "--json"]
    )
    assert result.exit_code == 0, result.output
    response = json.loads(result.output)
    assert response["_meta"]["tool"] == "fitops"
    assert response["_meta"]["total_count"] == 1
    assert response["_meta"]["generated_at"]
    assert response["_meta"]["version"]
    assert response["_meta"]["filters_applied"]["post_to_strava"] is False
    assert response["activities"][0]["source_identity"]["provider"] == "file"
    assert response["publication"]["status"] == "not_requested"
    assert response["data_availability"]["calibration_transferred"] is False
    assert len(bootstraps) == 1


def test_mobile_dashboard_route_handles_empty_valid_and_invalid(
    memory_store, monkeypatch
):
    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates
    from fastapi.testclient import TestClient

    from fitops.dashboard.routes import activity_imports

    monkeypatch.setattr(
        activity_imports,
        "get_settings",
        lambda: SimpleNamespace(active_athlete_id=1, athlete_id=None),
    )
    app = FastAPI()
    templates = Jinja2Templates(directory="fitops/dashboard/templates")
    templates.env.globals["legal_docs"] = {
        "privacy": "/privacy",
        "user_agreement": "/terms",
    }
    app.include_router(activity_imports.register(templates))
    with TestClient(app) as client:
        empty = client.get("/activities/import")
        assert empty.status_code == 200
        assert "Create an offline profile" in empty.text
        valid = client.post(
            "/api/activities/import-mobile",
            files={"file": ("export.json", encoded(), "application/json")},
        )
        assert valid.status_code == 201
        assert valid.json()["import"] == {"created_count": 1, "updated_count": 0}
        assert valid.json()["activities"][0]["duration"]["elapsed_time_seconds"] == 20
        monkeypatch.setattr(
            activity_imports,
            "get_settings",
            lambda: SimpleNamespace(active_athlete_id=1, athlete_id=1),
        )
        monkeypatch.setattr(
            "fitops.dashboard.queries.profile.get_equipment_with_stats",
            AsyncMock(return_value=[]),
        )
        populated_page = client.get("/activities/import")
        assert populated_page.status_code == 200
        assert "Import from FitOps Mobile" in populated_page.text
        repeated = client.post(
            "/api/activities/import-mobile",
            files={"file": ("export.json", encoded(), "application/json")},
        )
        assert repeated.status_code == 200
        invalid = client.post(
            "/api/activities/import-mobile",
            files={"file": ("export.json", b"{}", "application/json")},
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "invalid_mobile_export"
        monkeypatch.setattr(
            activity_imports,
            "get_settings",
            lambda: SimpleNamespace(active_athlete_id=None),
        )
        missing_profile = client.post(
            "/api/activities/import-mobile",
            files={"file": ("export.json", encoded(), "application/json")},
        )
        assert missing_profile.status_code == 409
