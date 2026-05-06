"""Tests for fitops.backup.event_sync — event-triggered remote sync."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import fitops.backup.event_sync as es


@pytest.fixture(autouse=True)
def reset_cooldowns():
    """Reset module-level cooldown timestamps before each test."""
    es._cli_last_triggered = 0.0
    es._dashboard_last_triggered = 0.0
    yield
    es._cli_last_triggered = 0.0
    es._dashboard_last_triggered = 0.0


# ---------------------------------------------------------------------------
# trigger_cli() tests
# ---------------------------------------------------------------------------


def test_trigger_cli_no_config_skips_popen():
    with (
        patch("fitops.backup.event_sync.subprocess.Popen") as mock_popen,
        patch("fitops.backup.config.get_github_config", return_value=None),
    ):
        es.trigger_cli()
        mock_popen.assert_not_called()


def test_trigger_cli_with_config_spawns_backup():
    cfg = {"token": "tok", "repo": "user/repo"}
    with (
        patch("fitops.backup.event_sync.subprocess.Popen") as mock_popen,
        patch("fitops.backup.config.get_github_config", return_value=cfg),
    ):
        es.trigger_cli()
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert "backup" in args
        assert "create" in args
        assert "--to" in args
        assert "github" in args


def test_trigger_cli_cooldown_suppresses_second_call():
    cfg = {"token": "tok", "repo": "user/repo"}
    with (
        patch("fitops.backup.event_sync.subprocess.Popen") as mock_popen,
        patch("fitops.backup.config.get_github_config", return_value=cfg),
    ):
        es.trigger_cli()
        es.trigger_cli()
        assert mock_popen.call_count == 1


def test_trigger_cli_cooldown_allows_after_expiry():
    cfg = {"token": "tok", "repo": "user/repo"}
    # Start at 100s so first call passes the cooldown (100 - 0 = 100 > 30).
    # Second call at 131s so the gap (131 - 100 = 31 > 30) also passes.
    call_times = [100.0, 131.0]
    call_iter = iter(call_times)

    with (
        patch("fitops.backup.event_sync.subprocess.Popen") as mock_popen,
        patch("fitops.backup.config.get_github_config", return_value=cfg),
        patch(
            "fitops.backup.event_sync.time.monotonic",
            side_effect=lambda: next(call_iter),
        ),
    ):
        es.trigger_cli()
        es.trigger_cli()
        assert mock_popen.call_count == 2


def test_trigger_cli_popen_raises_does_not_propagate():
    cfg = {"token": "tok", "repo": "user/repo"}
    with (
        patch(
            "fitops.backup.event_sync.subprocess.Popen", side_effect=OSError("no exec")
        ),
        patch("fitops.backup.config.get_github_config", return_value=cfg),
    ):
        es.trigger_cli()  # must not raise


# ---------------------------------------------------------------------------
# trigger_async() tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_async_no_config_skips_task():
    with (
        patch("fitops.backup.config.get_github_config", return_value=None),
        patch("asyncio.create_task") as mock_ct,
    ):
        await es.trigger_async()
        mock_ct.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_async_with_config_creates_task():
    cfg = {"token": "tok", "repo": "user/repo"}
    created_tasks = []

    async def fake_run():
        pass

    with (
        patch("fitops.backup.config.get_github_config", return_value=cfg),
        patch(
            "asyncio.create_task",
            side_effect=lambda coro: created_tasks.append(coro) or MagicMock(),
        ),
    ):
        await es.trigger_async()

    assert len(created_tasks) == 1


@pytest.mark.asyncio
async def test_trigger_async_cooldown_suppresses_second_call():
    cfg = {"token": "tok", "repo": "user/repo"}
    with (
        patch("fitops.backup.config.get_github_config", return_value=cfg),
        patch("asyncio.create_task") as mock_ct,
    ):
        await es.trigger_async()
        await es.trigger_async()
        assert mock_ct.call_count == 1


@pytest.mark.asyncio
async def test_run_backup_async_swallows_exceptions():
    cfg = {"token": "tok", "repo": "user/repo"}
    with (
        patch("fitops.backup.config.get_github_config", return_value=cfg),
        patch(
            "fitops.backup.archive.create_archive",
            side_effect=RuntimeError("disk full"),
        ),
        patch("fitops.config.settings.get_settings") as mock_settings,
    ):
        mock_settings.return_value = MagicMock(
            fitops_dir=MagicMock(), db_path=MagicMock()
        )
        await es._run_backup_async()  # must not raise


# ---------------------------------------------------------------------------
# Integration smoke tests via CLI runner
# ---------------------------------------------------------------------------


def _make_sync_result():
    from fitops.strava.sync_engine import SyncResult

    return SyncResult()


def test_cli_sync_triggers_backup_when_configured(monkeypatch):
    """trigger_cli() fires after a successful sync when GitHub config is present."""
    cfg = {"token": "tok", "repo": "user/repo"}
    trigger_calls: list = []

    def fake_trigger():
        trigger_calls.append(True)

    monkeypatch.setattr("fitops.cli.sync.trigger_cli", fake_trigger)

    async def fake_engine_run(**_kwargs):
        return _make_sync_result()

    mock_engine = MagicMock()
    mock_engine.run = fake_engine_run

    with (
        patch("fitops.backup.config.get_github_config", return_value=cfg),
        patch("fitops.cli.sync.SyncEngine", return_value=mock_engine),
        patch("fitops.cli.sync.init_db"),
        patch("fitops.cli.sync.get_settings") as mock_settings,
        patch("fitops.cli.sync.print_sync_result"),
    ):
        mock_settings.return_value = MagicMock(athlete_id=123, require_auth=MagicMock())
        from typer.testing import CliRunner

        from fitops.cli.sync import app as sync_app

        runner = CliRunner()
        runner.invoke(sync_app, ["run"])

    assert trigger_calls, "trigger_cli was not called after sync"


def test_cli_sync_no_backup_when_not_configured(monkeypatch):
    """trigger_cli() is a no-op when no GitHub config is present."""
    popen_calls: list = []

    def fake_popen(args, **kwargs):
        popen_calls.append(args)
        return MagicMock()

    monkeypatch.setattr("fitops.backup.event_sync.subprocess.Popen", fake_popen)

    async def fake_engine_run(**_kwargs):
        return _make_sync_result()

    mock_engine = MagicMock()
    mock_engine.run = fake_engine_run

    with (
        patch("fitops.backup.config.get_github_config", return_value=None),
        patch("fitops.cli.sync.SyncEngine", return_value=mock_engine),
        patch("fitops.cli.sync.init_db"),
        patch("fitops.cli.sync.get_settings") as mock_settings,
        patch("fitops.cli.sync.print_sync_result"),
    ):
        mock_settings.return_value = MagicMock(athlete_id=123, require_auth=MagicMock())
        from typer.testing import CliRunner

        from fitops.cli.sync import app as sync_app

        runner = CliRunner()
        runner.invoke(sync_app, ["run"])

    assert not popen_calls
