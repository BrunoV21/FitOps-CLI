"""Dashboard HTTP tests for the analytics performance page."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


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


def _fake_athlete_settings():
    return SimpleNamespace(
        lthr=165,
        max_hr=190,
        threshold_pace_per_km_s=270,
        lt1_pace_s=300,
        vo2max_pace_s=240,
        vo2max_override=None,
    )


def test_performance_page_renders_with_context(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.dashboard.routes.analytics.get_settings", lambda: _fake_settings()
    )
    monkeypatch.setattr(
        "fitops.analytics.athlete_settings.get_athlete_settings",
        _fake_athlete_settings,
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.analytics.get_performance_context",
        AsyncMock(
            return_value={
                "performance": SimpleNamespace(
                    sport="Run",
                    days=180,
                    activity_count=12,
                    overall_reliability=0.84,
                    running={
                        "running_economy_ml_kg_km": 202.3,
                        "pace_efficiency_score": 88.5,
                        "variability_index": 0.115,
                        "aerobic_efficiency_trend": {
                            "activity_count": 12,
                            "benchmark_pace_s_per_km": 300.0,
                            "benchmark_pace_per_km": "5:00/km",
                            "baseline_hr_at_benchmark_bpm": 152.0,
                            "recent_hr_at_benchmark_bpm": 146.0,
                            "hr_change_bpm": -6.0,
                            "hr_change_pct": -3.9,
                            "efficiency_change_pct": 4.1,
                            "baseline_efficiency_factor": 0.01974,
                            "recent_efficiency_factor": 0.02055,
                            "trend_label": "improving",
                        },
                    },
                    cycling=None,
                ),
                "current_load": {
                    "ctl": 52.1,
                    "atl": 61.3,
                    "tsb": -9.2,
                    "form_label": "Fatigued",
                },
                "trends": SimpleNamespace(
                    summary_label="volume building, pace improving",
                    performance_trend={
                        "pace_direction": "improving",
                        "pace_strength": "moderate",
                        "hr_direction": "stable",
                    },
                ),
            }
        ),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.analytics.estimate_vo2max",
        AsyncMock(
            return_value=SimpleNamespace(
                estimate=52.5,
                vdot=51.8,
                cooper=52.1,
                activity_name="Test Run",
                activity_date="2026-04-01",
                distance_km=12.0,
                pace_per_km="4:00",
                confidence_label="High",
            )
        ),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.analytics.get_vo2max_history",
        AsyncMock(
            return_value=[
                {
                    "date": "2026-04-01",
                    "name": "Test Run",
                    "strava_id": 1001,
                    "distance_km": 12.0,
                    "avg_hr": 158.0,
                    "effort_reason": "threshold",
                    "estimate": 52.5,
                    "confidence": 0.9,
                    "confidence_label": "High",
                    "vdot": 51.8,
                    "cooper": 52.1,
                    "estimation_method": "summary",
                    "measured_lt2_pace_s": None,
                    "rolling_vo2max": 52.5,
                    "is_qualifying": True,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.analytics.compute_race_predictions",
        lambda *_args, **_kwargs: {
            "lt2_predictions": {
                "5K": {"hms": "20:00", "predicted_pace": "4:00"},
                "10K": {"hms": "41:00", "predicted_pace": "4:06"},
                "Half": {"hms": "1:31:00", "predicted_pace": "4:19"},
                "Marathon": {"hms": "3:15:00", "predicted_pace": "4:37"},
            },
            "lt2_source_pace": "4:30",
            "riegel_predictions": {},
        },
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.analytics.compute_vo2max_rolling",
        lambda *args, **kwargs: None,
    )

    resp = client.get("/analytics/performance?sport=Run&days=180")
    assert resp.status_code == 200
    assert "Current Load" in resp.text
    assert "Trend Snapshot" in resp.text
    assert "Profile Link" in resp.text
    assert "Aerobic Efficiency Trend" in resp.text
    assert "HR at 5:00/km" in resp.text
    assert "Max HR estimate" not in resp.text
    assert "Grade-adjusted paces from HR streams" not in resp.text
    assert "VO₂max Over Time" in resp.text


def test_performance_page_empty_state(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.dashboard.routes.analytics.get_settings", lambda: _fake_settings()
    )
    monkeypatch.setattr(
        "fitops.analytics.athlete_settings.get_athlete_settings",
        lambda: SimpleNamespace(
            lthr=None,
            max_hr=None,
            threshold_pace_per_km_s=None,
            lt1_pace_s=None,
            vo2max_pace_s=None,
            vo2max_override=None,
        ),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.analytics.get_performance_context",
        AsyncMock(return_value=None),
    )

    resp = client.get("/analytics/performance?sport=Ride&days=180")
    assert resp.status_code == 200
    assert "Run Profile Context" in resp.text
    assert "HR reference required" in resp.text


def test_profile_page_shows_performance_card(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.dashboard.routes.profile.get_settings", lambda: _fake_settings()
    )
    monkeypatch.setattr(
        "fitops.analytics.athlete_settings.get_athlete_settings",
        _fake_athlete_settings,
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.profile.get_athlete",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.profile.get_equipment_with_stats",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.profile.estimate_vo2max",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.profile.get_current_training_load",
        AsyncMock(
            return_value={
                "ctl": 52.1,
                "atl": 61.3,
                "tsb": -9.2,
                "form_label": "Fatigued",
            }
        ),
    )

    resp = client.get("/profile")
    assert resp.status_code == 200
    assert "Current Training Load" in resp.text
    assert "52.1" in resp.text
    assert "61.3" in resp.text
    assert "-9.2" in resp.text
    assert "Fatigued" in resp.text
    assert "Performance →" in resp.text
    assert ".profile-mobile-stack" in resp.text
    assert 'class="grid-2 profile-mobile-stack"' in resp.text


def test_profile_page_no_load_data(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.dashboard.routes.profile.get_settings", lambda: _fake_settings()
    )
    monkeypatch.setattr(
        "fitops.analytics.athlete_settings.get_athlete_settings",
        lambda: SimpleNamespace(
            lthr=None,
            max_hr=None,
            threshold_pace_per_km_s=None,
            lt1_pace_s=None,
            vo2max_pace_s=None,
            vo2max_override=None,
        ),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.profile.get_athlete",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.profile.get_equipment_with_stats",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.profile.estimate_vo2max",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.profile.get_current_training_load",
        AsyncMock(return_value=None),
    )

    resp = client.get("/profile")
    assert resp.status_code == 200
    assert "Current Training Load" not in resp.text
