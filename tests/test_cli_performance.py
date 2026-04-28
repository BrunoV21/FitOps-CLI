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
        "current_load": {"ctl": 52.1, "atl": 61.3, "tsb": -9.2, "form_label": "Fatigued"},
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

    result = runner.invoke(app, ["performance", "--sport", "Ride", "--days", "180", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["_meta"]["filters_applied"]["sport"] == "Ride"
    assert payload["_meta"]["filters_applied"]["days"] == 180
    assert payload["performance"]["sport"] == "Ride"
    assert payload["performance"]["days"] == 180
    assert payload["performance"]["current_load"]["ctl"] == 52.1
    assert payload["performance"]["trends"]["summary_label"] == "volume building, pace improving"
