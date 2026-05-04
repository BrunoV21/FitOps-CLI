from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from typer.testing import CliRunner

from fitops.analytics.race_results import (
    parse_race_time_to_seconds,
    summarize_race_result,
)


def _race_activity(**overrides):
    base = {
        "id": 1,
        "workout_type": 1,
        "sport_type": "Run",
        "distance_m": 9820.0,
        "elapsed_time_s": 2460,
        "moving_time_s": 2460,
        "race_distance_m": 10000.0,
        "chip_time_s": 2430,
        "streams_fetched": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_parse_race_time_to_seconds():
    assert parse_race_time_to_seconds("45:00") == 2700
    assert parse_race_time_to_seconds("1:29:30") == 5370


def test_summarize_race_result_uses_official_distance_and_chip_time():
    activity = _race_activity()
    summary = summarize_race_result(
        activity,
        streams={"distance": [0.0, 9820.0], "time": [0.0, 2460.0]},
    )
    assert summary is not None
    assert summary["override_active"] is True
    assert summary["corrected_distance_km"] == 10.0
    assert summary["chip_time_formatted"] == "40:30"
    assert summary["distance_correction_factor"] > 1.0
    assert summary["time_correction_factor"] < 1.0


def test_set_race_result_cli_updates_race_activity(monkeypatch):
    from fitops.cli.activities import app

    runner = CliRunner()
    activity = _race_activity(strava_id=12345)
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=activity))
    )

    @asynccontextmanager
    async def _session_ctx():
        yield session

    monkeypatch.setattr("fitops.cli.activities.init_db", lambda: None)
    monkeypatch.setattr("fitops.cli.activities.get_async_session", _session_ctx)
    monkeypatch.setattr(
        "fitops.cli.activities.persist_calibrated_snapshot",
        AsyncMock(return_value=None),
    )

    result = runner.invoke(
        app,
        [
            "set-race-result",
            "12345",
            "--chip-time",
            "40:00",
            "--race-distance-km",
            "10",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert activity.chip_time_s == 2400
    assert activity.race_distance_m == 10000.0
    assert '"chip_time_formatted": "40:00"' in result.stdout


@pytest.fixture
def client():
    from starlette.testclient import TestClient

    from fitops.dashboard.server import create_app
    from fitops.db import migrations

    migrations.create_all_tables = AsyncMock(return_value=None)
    with TestClient(create_app()) as c:
        yield c


def test_dashboard_race_result_post_updates_activity(client, monkeypatch):
    activity = _race_activity(strava_id=99001)
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=activity))
    )

    @asynccontextmanager
    async def _session_ctx():
        yield session

    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.get_async_session", _session_ctx
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.persist_calibrated_snapshot",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.activities.delete_calibrated_snapshot",
        AsyncMock(return_value=None),
    )

    resp = client.post(
        "/activities/99001/race-result",
        data={"chip_time": "39:59", "race_distance_km": "10"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert activity.chip_time_s == 2399
    assert activity.race_distance_m == 10000.0
