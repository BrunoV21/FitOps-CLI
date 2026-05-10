"""Dashboard HTTP tests for the Overview page."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fitops.dashboard.queries.analytics import RUNNING_SPORTS


@pytest.fixture
def client():
    from starlette.testclient import TestClient

    from fitops.dashboard.server import create_app

    with TestClient(create_app()) as c:
        yield c


def _fake_settings():
    return SimpleNamespace(
        athlete_id=42,
        is_authenticated=True,
        has_write_scope=False,
    )


def test_overview_run_view_filters_heatmap(client, monkeypatch):
    heatmap_mock = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_settings", lambda: _fake_settings()
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_athlete",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_recent_activities",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_activity_stats",
        AsyncMock(
            return_value={
                "total_count": 0,
                "total_distance_km": 0.0,
                "total_elevation_m": 0,
                "total_duration_h": 0.0,
            }
        ),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_current_training_load",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_trends_data",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_activity_heatmap_data",
        heatmap_mock,
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview._get_today_weather",
        AsyncMock(return_value=None),
    )

    resp = client.get("/?view=run&period=week")

    assert resp.status_code == 200
    heatmap_mock.assert_awaited_once_with(42, since=None, sport_types=RUNNING_SPORTS)
