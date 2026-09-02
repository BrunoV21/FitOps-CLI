from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
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


def test_default_sync_mode_env_sets_webhook_when_no_saved_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path))
    monkeypatch.setenv("FITOPS_DEFAULT_SYNC_MODE", "webhook")

    from fitops.strava.webhook_config import get_sync_mode

    assert get_sync_mode() == "webhook"


def test_dashboard_webhook_endpoint_queues_event(monkeypatch):
    from starlette.testclient import TestClient

    with patch("fitops.db.migrations.create_all_tables", new_callable=AsyncMock):
        with patch(
            "fitops.dashboard.routes.backup.run_scheduler", new_callable=AsyncMock
        ):
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
async def test_default_webhook_bootstrap_creates_hf_subscription(tmp_path, monkeypatch):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path))
    monkeypatch.setenv(
        "FITOPS_WEBHOOK_CALLBACK_URL",
        "https://user-fitops-dashboard.hf.space/api/strava/webhook",
    )
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "strava": {
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                }
            }
        )
    )
    _reset_settings_and_db()

    monkeypatch.setattr(
        "fitops.strava.webhook_bootstrap.subs.list_subscriptions", lambda: []
    )
    monkeypatch.setattr(
        "fitops.strava.webhook_bootstrap.subs.create_subscription",
        lambda callback_url, verify_token: 99,
    )

    from fitops.strava.webhook_bootstrap import ensure_default_webhook

    result = await ensure_default_webhook()

    config = json.loads((tmp_path / "config.json").read_text())
    assert result["status"] == "configured"
    assert result["subscription_id"] == 99
    assert config["sync"]["mode"] == "webhook"
    assert config["strava"]["webhook"]["enabled"] is True
    assert (
        config["strava"]["webhook"]["callback_url"]
        == "https://user-fitops-dashboard.hf.space/api/strava/webhook"
    )


@pytest.mark.asyncio
async def test_default_webhook_bootstrap_noops_without_hf_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "strava": {
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                }
            }
        )
    )
    _reset_settings_and_db()

    from fitops.strava.webhook_bootstrap import ensure_default_webhook

    result = await ensure_default_webhook()

    config = json.loads((tmp_path / "config.json").read_text())
    assert result == {"status": "skipped", "reason": "no_default_callback_url"}
    assert "sync" not in config
    assert "webhook" not in config["strava"]


@pytest.mark.asyncio
async def test_default_webhook_bootstrap_respects_saved_polling_mode(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path))
    monkeypatch.setenv(
        "FITOPS_WEBHOOK_CALLBACK_URL",
        "https://user-fitops-dashboard.hf.space/api/strava/webhook",
    )
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "strava": {
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                },
                "sync": {"mode": "polling"},
            }
        )
    )
    _reset_settings_and_db()

    from fitops.strava.webhook_bootstrap import ensure_default_webhook

    result = await ensure_default_webhook()

    config = json.loads((tmp_path / "config.json").read_text())
    assert result["reason"] == "saved_sync_mode_not_webhook"
    assert config["sync"]["mode"] == "polling"
    assert "webhook" not in config["strava"]


@pytest.mark.asyncio
async def test_delete_activity_by_strava_id_removes_dependent_rows(
    tmp_path, monkeypatch
):
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
        assert (
            await session.execute(select(ActivityCalibration))
        ).scalars().all() == []
        assert (
            await session.execute(select(WorkoutActivityLink))
        ).scalars().all() == []
        plan = (await session.execute(select(RacePlan))).scalar_one()
        note = (await session.execute(select(Note))).scalar_one()
        assert plan.activity_id is None
        assert note.activity_id is None

    assert result["action"] == "delete"
    assert result["deleted"]["activities"] == 1


@pytest.mark.asyncio
async def test_webhook_activity_upsert_marks_ui_stamp_before_slow_followups(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path))
    _write_tmp_config(
        tmp_path,
        strava={
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "athlete_id": 99,
        },
    )
    _reset_settings_and_db()
    await _init_db()

    class FakeStravaClient:
        async def get_activity(self, strava_id: int) -> dict:
            return {
                "id": strava_id,
                "name": "Webhook Run",
                "sport_type": "Run",
                "start_date": "2026-05-30T08:00:00Z",
                "start_date_local": "2026-05-30T09:00:00Z",
                "distance": 5000.0,
                "moving_time": 1500,
                "elapsed_time": 1500,
                "average_speed": 3.33,
            }

    seen_data_stamp_before_streams = []

    async def fake_fetch_streams(*_args, **_kwargs):
        from fitops.config.state import get_sync_state

        seen_data_stamp_before_streams.append(
            get_sync_state().last_data_update_at is not None
        )
        return {"streams_fetched": 0, "errors": 0, "strava_ids": []}

    monkeypatch.setattr("fitops.strava.webhooks.StravaClient", FakeStravaClient)
    monkeypatch.setattr(
        "fitops.strava.webhooks.fetch_streams_for_activities", fake_fetch_streams
    )
    monkeypatch.setattr(
        "fitops.strava.webhooks.fetch_weather_for_strava_ids",
        AsyncMock(return_value={"weather_fetched": 0, "weather_errors": 0}),
    )
    monkeypatch.setattr("fitops.analytics.stamp.auto_stamp_new_activities", AsyncMock())
    monkeypatch.setattr(
        "fitops.analytics.race_plan.sweep_unlinked_plans",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        "fitops.analytics.training_load.persist_training_load_snapshot", AsyncMock()
    )
    monkeypatch.setattr("fitops.strava.webhooks.trigger_async", AsyncMock())

    from sqlalchemy import select

    from fitops.config.state import get_sync_state
    from fitops.db.models.activity import Activity
    from fitops.db.session import get_async_session
    from fitops.strava.webhooks import sync_activity_from_strava

    result = await sync_activity_from_strava(123, sync_type="webhook_create")
    state = get_sync_state()

    assert result["activities_created"] == 1
    assert seen_data_stamp_before_streams == [True]
    assert state.last_data_update_at is not None
    assert state.last_sync_at is not None
    assert state.last_data_update_at < state.last_sync_at

    async with get_async_session() as session:
        activity = (
            await session.execute(select(Activity).where(Activity.strava_id == 123))
        ).scalar_one_or_none()
    assert activity is not None
    assert activity.name == "Webhook Run"


@pytest.mark.asyncio
async def test_auto_sync_skips_when_not_polling(monkeypatch):
    monkeypatch.setattr("fitops.strava.webhook_config.get_sync_mode", lambda: "webhook")
    monkeypatch.setattr(
        "fitops.dashboard.routes.auto_sync.get_settings",
        lambda: (_ for _ in ()).throw(AssertionError("settings should not be read")),
    )

    from fitops.dashboard.routes.auto_sync import _maybe_auto_sync

    await _maybe_auto_sync()


def test_dashboard_does_not_start_auto_sync_scheduler_in_webhook_mode(
    tmp_path, monkeypatch
):
    from starlette.testclient import TestClient

    monkeypatch.setenv("FITOPS_DIR", str(tmp_path))
    monkeypatch.setenv("FITOPS_DEFAULT_SYNC_MODE", "webhook")

    with patch("fitops.db.migrations.create_all_tables", new_callable=AsyncMock):
        with patch(
            "fitops.dashboard.routes.backup.run_scheduler", new_callable=AsyncMock
        ):
            with patch(
                "fitops.dashboard.routes.auto_sync.run_auto_sync_scheduler",
                new_callable=AsyncMock,
            ) as auto_sync:
                from fitops.dashboard.server import create_app

                with TestClient(create_app()) as client:
                    assert client.get("/health").status_code == 200

    auto_sync.assert_not_called()


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


def _write_tmp_config(tmp_path, strava: dict | None = None) -> None:
    config_path = tmp_path / "config.json"
    data = {"preferences": {"db_path": str(tmp_path / "fitops.db")}}
    if strava is not None:
        data["strava"] = strava
    config_path.write_text(json.dumps(data))


async def _init_db() -> None:
    from fitops.db.migrations import create_all_tables

    await create_all_tables()
