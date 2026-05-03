from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from typer.testing import CliRunner

from fitops.cli.admin import app

runner = CliRunner()


def _make_candidate(name="Morning Run", avg_w=None):
    return SimpleNamespace(
        id=1,
        strava_id=1001,
        name=name,
        sport_type="Run",
        streams_fetched=True,
        est_power_avg_w=avg_w,
        start_date="2024-01-01T07:00:00",
        start_date_local="2024-01-01T08:00:00",
    )


def _patch_prereqs(
    monkeypatch,
    *,
    athlete_id="123",
    weight_kg=70.0,
    candidates=None,
    streams=None,
    persist_ok=True,
):
    monkeypatch.setattr("fitops.cli.admin.init_db", lambda: None)

    settings = SimpleNamespace(athlete_id=athlete_id)
    monkeypatch.setattr("fitops.cli.admin.get_settings", lambda: settings)

    athlete_settings = SimpleNamespace(weight_kg=weight_kg)
    monkeypatch.setattr(
        "fitops.cli.admin.get_athlete_settings", lambda: athlete_settings
    )

    if candidates is None:
        candidates = [_make_candidate()]

    # Async session context manager that returns candidates on first execute
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = candidates

    # For the write path, second execute returns a single activity row
    candidate = candidates[0] if candidates else None
    mock_write_result = MagicMock()
    mock_write_result.scalar_one_or_none.return_value = candidate

    execute_call_count = 0

    async def _execute(q):
        nonlocal execute_call_count
        execute_call_count += 1
        if execute_call_count == 1:
            return mock_result
        return mock_write_result

    mock_session.execute.side_effect = _execute

    class _FakeAsyncCtx:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr("fitops.db.session.get_async_session", lambda: _FakeAsyncCtx())

    mock_streams = streams if streams is not None else {"velocity_smooth": [3.0] * 100}
    monkeypatch.setattr(
        "fitops.dashboard.queries.activities.get_activity_streams",
        AsyncMock(return_value=mock_streams),
    )

    async def _persist(session, activity_db_id, activity_row, streams_data, weight):
        activity_row.est_power_avg_w = 280.0
        return persist_ok

    monkeypatch.setattr(
        "fitops.analytics.running_power.persist_power_for_activity", _persist
    )


def test_recompute_power_no_athlete(monkeypatch):
    _patch_prereqs(monkeypatch, athlete_id=None)
    result = runner.invoke(app, [])
    assert result.exit_code != 0 or "auth login" in result.output


def test_recompute_power_no_weight(monkeypatch):
    _patch_prereqs(monkeypatch, weight_kg=None)
    result = runner.invoke(app, [])
    assert result.exit_code != 0 or "weight_kg" in result.output


def test_recompute_power_no_candidates(monkeypatch):
    _patch_prereqs(monkeypatch, candidates=[])
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "No activities to process" in result.output


def test_recompute_power_dry_run(monkeypatch):
    _patch_prereqs(monkeypatch)
    result = runner.invoke(app, ["--dry-run"])
    assert result.exit_code == 0
    assert "dry-run" in result.output
    assert "Would process" in result.output


def test_recompute_power_writes(monkeypatch):
    _patch_prereqs(monkeypatch)
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Processed" in result.output


def test_recompute_power_force_includes_existing_estimates(monkeypatch):
    _patch_prereqs(monkeypatch, candidates=[_make_candidate(avg_w=280.0)])
    result = runner.invoke(app, ["--force"])
    assert result.exit_code == 0
    assert "Processed" in result.output


def test_recompute_power_no_streams_skips(monkeypatch):
    _patch_prereqs(monkeypatch, streams={})
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Skipped 1" in result.output
