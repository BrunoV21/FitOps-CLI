"""CLI tests for `fitops analytics performance`."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from typer.testing import CliRunner

from fitops.cli.analytics import app

runner = CliRunner()


def test_cli_performance_json_includes_context(monkeypatch):
    monkeypatch.setattr("fitops.cli.analytics.init_db", lambda: None)
    monkeypatch.setattr(
        "fitops.cli.analytics.get_settings",
        lambda: SimpleNamespace(athlete_id=42, require_auth=lambda: None),
    )

    fake_context = {
        "performance": SimpleNamespace(
            sport="Ride",
            days=180,
            activity_count=12,
            overall_reliability=0.82,
            running=None,
            cycling={
                "ftp_estimate_watts": 190.0,
                "power_to_weight_w_kg": 2.71,
                "normalized_power_ratio": 1.08,
                "power_consistency": 82.0,
                "variability_index": 0.18,
            },
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
    monkeypatch.setattr(
        "fitops.cli.analytics.get_performance_context",
        AsyncMock(return_value=fake_context),
    )

    result = runner.invoke(
        app, ["performance", "--sport", "Ride", "--days", "180", "--json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["_meta"]["filters_applied"]["sport"] == "Ride"
    assert payload["_meta"]["filters_applied"]["days"] == 180
    assert payload["performance"]["sport"] == "Ride"
    assert payload["performance"]["days"] == 180
    assert payload["performance"]["current_load"]["ctl"] == 52.1
    assert (
        payload["performance"]["trends"]["summary_label"]
        == "volume building, pace improving"
    )


def test_cli_performance_json_includes_aerobic_efficiency_trend(monkeypatch):
    monkeypatch.setattr("fitops.cli.analytics.init_db", lambda: None)
    monkeypatch.setattr(
        "fitops.cli.analytics.get_settings",
        lambda: SimpleNamespace(athlete_id=42, require_auth=lambda: None),
    )

    fake_context = {
        "performance": SimpleNamespace(
            sport="Run",
            days=180,
            activity_count=12,
            overall_reliability=0.86,
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
        "current_load": None,
        "trends": None,
    }
    monkeypatch.setattr(
        "fitops.cli.analytics.get_performance_context",
        AsyncMock(return_value=fake_context),
    )

    result = runner.invoke(
        app, ["performance", "--sport", "Run", "--days", "180", "--json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    trend = payload["performance"]["running"]["aerobic_efficiency_trend"]
    assert trend["benchmark_pace_per_km"] == "5:00/km"
    assert trend["hr_change_bpm"] == -6.0
    assert trend["efficiency_change_pct"] == 4.1


def test_cli_performance_text_includes_aerobic_efficiency_trend(monkeypatch):
    monkeypatch.setattr("fitops.cli.analytics.init_db", lambda: None)
    monkeypatch.setattr(
        "fitops.cli.analytics.get_settings",
        lambda: SimpleNamespace(athlete_id=42, require_auth=lambda: None),
    )

    fake_context = {
        "performance": SimpleNamespace(
            sport="Run",
            days=180,
            activity_count=12,
            overall_reliability=0.86,
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
        "current_load": None,
        "trends": None,
    }
    monkeypatch.setattr(
        "fitops.cli.analytics.get_performance_context",
        AsyncMock(return_value=fake_context),
    )

    result = runner.invoke(app, ["performance", "--sport", "Run", "--days", "180"])

    assert result.exit_code == 0
    assert "Aerobic efficiency +4.1%" in result.stdout
    assert "HR at 5:00/km" in result.stdout
    assert "146.0 bpm" in result.stdout
    assert "6.0 bpm lower" in result.stdout
