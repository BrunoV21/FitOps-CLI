"""Dashboard HTTP tests for the Overview page."""

from __future__ import annotations

import asyncio
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


def test_overview_omits_weather_when_forecast_is_slow(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_settings", lambda: _fake_settings()
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview._TODAY_WEATHER_TIMEOUT_SECONDS", 0.001
    )
    athlete_mock = AsyncMock(return_value=None)
    recent_mock = AsyncMock(return_value=[])
    stats_mock = AsyncMock(
        return_value={
            "total_count": 0,
            "total_distance_km": 0.0,
            "total_elevation_m": 0,
            "total_duration_h": 0.0,
        }
    )
    load_mock = AsyncMock(return_value=None)
    trends_mock = AsyncMock(return_value=None)
    heatmap_mock = AsyncMock(return_value=[])

    async def slow_weather(athlete_id):
        await asyncio.sleep(1)
        return {"temperature_c": 18.0}

    monkeypatch.setattr("fitops.dashboard.routes.overview.get_athlete", athlete_mock)
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_recent_activities", recent_mock
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_activity_stats", stats_mock
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_current_training_load", load_mock
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_trends_data", trends_mock
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview.get_activity_heatmap_data", heatmap_mock
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.overview._get_today_weather", slow_weather
    )

    resp = client.get("/?period=week")

    assert resp.status_code == 200
    athlete_mock.assert_awaited_once_with(42)
    recent_mock.assert_awaited_once()
    stats_mock.assert_awaited_once()
    load_mock.assert_awaited_once_with(42)
    trends_mock.assert_awaited_once_with(42, days=90, sport_types=None)
    heatmap_mock.assert_awaited_once_with(42, since=None, sport_types=None)
