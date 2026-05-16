from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


def test_webhook_verify_challenge_uses_configured_token(tmp_path, monkeypatch):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path))
    from fitops.strava.webhook_config import save_webhook_config
    from fitops.strava.webhooks import verify_challenge

    save_webhook_config(
        callback_url="https://example.test/api/strava/webhook",
        verify_token="secret-token",
    )

    assert verify_challenge("secret-token", "abc123") == {"hub.challenge": "abc123"}


def test_dashboard_webhook_endpoint_queues_event(monkeypatch):
    from starlette.testclient import TestClient

    with patch("fitops.db.migrations.create_all_tables", new_callable=AsyncMock):
        with patch("fitops.dashboard.routes.backup.run_scheduler", new_callable=AsyncMock):
            with patch(
                "fitops.dashboard.routes.auto_sync.run_auto_sync_scheduler",
                new_callable=AsyncMock,
            ):
                from fitops.dashboard.server import create_app
                from fitops.strava import webhooks

                process = AsyncMock()
                monkeypatch.setattr(webhooks, "process_webhook_payload", process)

                with TestClient(create_app()) as client:
                    resp = client.post(
                        "/api/strava/webhook",
                        json={
                            "object_type": "activity",
                            "object_id": 123,
                            "aspect_type": "create",
                            "owner_id": 99,
                            "subscription_id": 1,
                            "event_time": 1714000000,
                        },
                    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    process.assert_called_once()


@pytest.mark.asyncio
async def test_process_webhook_payload_deduplicates_events(tmp_path, monkeypatch):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path))
    _write_tmp_config(tmp_path)
    _reset_settings_and_db()
    await _init_db()

    calls = []

    async def fake_sync(strava_id: int, sync_type: str = "webhook"):
        calls.append((strava_id, sync_type))
        return {"status": "processed", "action": sync_type}

    monkeypatch.setattr("fitops.strava.webhooks.sync_activity_from_strava", fake_sync)

    from fitops.strava.webhooks import process_webhook_payload

    payload = {
        "object_type": "activity",
        "object_id": 123,
        "aspect_type": "create",
        "owner_id": 99,
        "subscription_id": 1,
        "event_time": 1714000000,
    }

    first = await process_webhook_payload(payload)
    second = await process_webhook_payload(payload)

    assert first.status == "processed"
    assert second.status == "duplicate"
    assert calls == [(123, "webhook_create")]


@pytest.mark.asyncio
async def test_delete_activity_by_strava_id_removes_dependent_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path))
    _write_tmp_config(tmp_path)
    _reset_settings_and_db()
    await _init_db()

    monkeypatch.setattr("fitops.strava.webhooks.trigger_async", AsyncMock())

    from fitops.db.models.activity import Activity
    from fitops.db.models.activity_calibration import ActivityCalibration
    from fitops.db.models.activity_stream import ActivityStream
    from fitops.db.models.activity_weather import ActivityWeather
    from fitops.db.models.analytics_snapshot import AnalyticsSnapshot
    from fitops.db.models.note import Note
    from fitops.db.models.race_plan import RacePlan
    from fitops.db.models.workout_activity_link import WorkoutActivityLink
    from fitops.db.session import get_async_session
    from fitops.strava.webhooks import delete_activity_by_strava_id

    async with get_async_session() as session:
        activity = Activity(
            strava_id=123,
            athlete_id=99,
            name="Deleted Run",
            sport_type="Run",
        )
        session.add(activity)
        await session.flush()
        session.add(ActivityStream.from_strava_stream(activity.id, "time", [1, 2]))
        session.add(ActivityWeather(activity_id=123, temperature_c=12.0))
        session.add(
            ActivityCalibration(
                activity_id=activity.id,
                summary_json="{}",
                streams_json="{}",
                race_result_json="{}",
            )
        )
        session.add(WorkoutActivityLink(workout_id=1, activity_id=activity.id))
        session.add(RacePlan(course_id=1, name="Plan", activity_id=activity.id))
        session.add(Note(slug="n", title="Note", activity_id=123))
        session.add(
            AnalyticsSnapshot(
                athlete_id=99,
                snapshot_date=date(2026, 5, 16),
                sport_type=None,
            )
        )

    result = await delete_activity_by_strava_id(123)

    async with get_async_session() as session:
        from sqlalchemy import select

        assert (
            await session.execute(select(Activity).where(Activity.strava_id == 123))
        ).scalar_one_or_none() is None
        assert (await session.execute(select(ActivityStream))).scalars().all() == []
        assert (await session.execute(select(ActivityWeather))).scalars().all() == []
        assert (await session.execute(select(ActivityCalibration))).scalars().all() == []
        assert (await session.execute(select(WorkoutActivityLink))).scalars().all() == []
        plan = (await session.execute(select(RacePlan))).scalar_one()
        note = (await session.execute(select(Note))).scalar_one()
        assert plan.activity_id is None
        assert note.activity_id is None

    assert result["action"] == "delete"
    assert result["deleted"]["activities"] == 1


@pytest.mark.asyncio
async def test_auto_sync_skips_when_not_polling(monkeypatch):
    monkeypatch.setattr("fitops.strava.webhook_config.get_sync_mode", lambda: "webhook")
    monkeypatch.setattr(
        "fitops.dashboard.routes.auto_sync.get_settings",
        lambda: (_ for _ in ()).throw(AssertionError("settings should not be read")),
    )

    from fitops.dashboard.routes.auto_sync import _maybe_auto_sync

    await _maybe_auto_sync()


def test_cli_webhooks_status_json(monkeypatch):
    from typer.testing import CliRunner

    from fitops.cli.webhooks import app

    monkeypatch.setattr("fitops.cli.webhooks.init_db", lambda: None)
    monkeypatch.setattr(
        "fitops.cli.webhooks.wcfg.get_webhook_config",
        lambda: {
            "callback_url": "https://example.test/api/strava/webhook",
            "subscription_id": 42,
            "enabled": True,
        },
    )
    monkeypatch.setattr("fitops.cli.webhooks.wcfg.get_sync_mode", lambda: "webhook")
    monkeypatch.setattr("fitops.cli.webhooks.subs.list_subscriptions", lambda: [])
    monkeypatch.setattr("fitops.cli.webhooks.recent_events", AsyncMock(return_value=[]))

    result = CliRunner().invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["_meta"]["tool"] == "fitops"
    assert payload["webhook"]["sync_mode"] == "webhook"


def _reset_settings_and_db() -> None:
    import fitops.config.settings as settings_module
    import fitops.db.session as session_module

    settings_module._settings = None
    session_module._engine = None
    session_module._session_factory = None


def _write_tmp_config(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"preferences": {"db_path": str(tmp_path / "fitops.db")}})
    )


async def _init_db() -> None:
    from fitops.db.migrations import create_all_tables

    await create_all_tables()
