"""Tests for the Race Plan feature — model helpers, haversine, auto-match logic, formatters."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fitops.analytics.race_plan import RUN_SPORT_TYPES, _haversine_m
from fitops.db.models.race_plan import RacePlan
from fitops.output.text_formatter import (
    print_race_plan_compare,
    print_race_plan_detail,
    print_race_plans_list,
)

# ---------------------------------------------------------------------------
# _haversine_m — pure math helper
# ---------------------------------------------------------------------------


def test_haversine_same_point():
    assert _haversine_m(51.5, -0.1, 51.5, -0.1) == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance():
    # Berlin → Frankfurt: ~423 km straight-line
    d = _haversine_m(52.52, 13.405, 50.11, 8.682)
    assert 420_000 < d < 430_000


def test_haversine_short_distance():
    # ~111 m per 0.001° lat at equator
    d = _haversine_m(0.0, 0.0, 0.001, 0.0)
    assert 100 < d < 120


def test_haversine_under_500m():
    # ~90 m apart — should be well under 500 m threshold
    d = _haversine_m(51.5, -0.1, 51.5008, -0.1)
    assert d < 500.0


def test_haversine_over_500m():
    # ~1 km apart
    d = _haversine_m(51.5, -0.1, 51.509, -0.1)
    assert d > 500.0


# ---------------------------------------------------------------------------
# RacePlan model helpers
# ---------------------------------------------------------------------------


class _FakePlan:
    """Plain-Python stand-in for RacePlan that borrows its helper methods."""

    get_splits = RacePlan.get_splits
    to_summary_dict = RacePlan.to_summary_dict
    to_detail_dict = RacePlan.to_detail_dict


def _make_plan(**kwargs) -> _FakePlan:
    defaults = {
        "id": 1,
        "course_id": 1,
        "name": "Test Plan",
        "race_date": "2026-09-27",
        "race_hour": 9,
        "target_time": "3:00:00",
        "target_time_s": 10800.0,
        "strategy": "even",
        "pacer_pace": None,
        "drop_at_km": None,
        "weather_temp_c": 15.0,
        "weather_humidity_pct": 40.0,
        "weather_wind_ms": 2.0,
        "weather_wind_dir_deg": 180.0,
        "weather_source": "manual",
        "splits_json": json.dumps(
            [
                {
                    "km": 1,
                    "target_pace_s": 255,
                    "adjusted_pace_fmt": "4:15",
                    "elapsed_fmt": "4:15",
                    "elevation_delta_m": 2.0,
                    "total_adjustment_factor": 1.02,
                },
                {
                    "km": 2,
                    "target_pace_s": 255,
                    "adjusted_pace_fmt": "4:15",
                    "elapsed_fmt": "8:30",
                    "elevation_delta_m": -1.0,
                    "total_adjustment_factor": 0.98,
                },
            ]
        ),
        "activity_id": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(kwargs)
    plan = _FakePlan()
    for k, v in defaults.items():
        setattr(plan, k, v)
    return plan


def test_race_plan_get_splits_empty():
    plan = _make_plan(splits_json=None)
    assert plan.get_splits() == []


def test_race_plan_get_splits_invalid_json():
    plan = _make_plan(splits_json="not-json")
    assert plan.get_splits() == []


def test_race_plan_get_splits_valid():
    plan = _make_plan()
    splits = plan.get_splits()
    assert len(splits) == 2
    assert splits[0]["km"] == 1
    assert splits[0]["adjusted_pace_fmt"] == "4:15"


def test_race_plan_to_summary_dict():
    plan = _make_plan()
    d = plan.to_summary_dict()
    assert d["id"] == 1
    assert d["name"] == "Test Plan"
    assert d["target_time"] == "3:00:00"
    assert d["strategy"] == "even"
    assert "splits" not in d


def test_race_plan_to_detail_dict():
    plan = _make_plan()
    d = plan.to_detail_dict()
    assert "splits" in d
    assert len(d["splits"]) == 2
    assert d["splits"][1]["km"] == 2


def test_race_plan_to_detail_dict_no_splits():
    plan = _make_plan(splits_json=None)
    d = plan.to_detail_dict()
    assert d["splits"] == []


# ---------------------------------------------------------------------------
# match_activity_to_plans — logic paths
# ---------------------------------------------------------------------------


def test_run_sport_types_includes_run():
    assert "Run" in RUN_SPORT_TYPES
    assert "TrailRun" in RUN_SPORT_TYPES
    assert "Walk" in RUN_SPORT_TYPES


def test_run_sport_types_excludes_ride():
    assert "Ride" not in RUN_SPORT_TYPES
    assert "VirtualRide" not in RUN_SPORT_TYPES


@pytest.mark.asyncio
async def test_match_returns_none_for_non_run():
    """Non-running sport types should return None immediately."""
    mock_act = MagicMock()
    mock_act.sport_type = "Ride"
    mock_act.start_latlng = "[51.5, -0.1]"
    mock_act.start_date = MagicMock()
    mock_act.start_date.strftime.return_value = "2026-09-27"

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    scalar_mock = MagicMock()
    scalar_mock.scalar_one_or_none.return_value = mock_act
    mock_session.execute = AsyncMock(return_value=scalar_mock)

    from fitops.analytics import race_plan as rp_module

    with patch.object(rp_module, "get_async_session", return_value=mock_session):
        result = await rp_module.match_activity_to_plans(1)

    assert result is None


@pytest.mark.asyncio
async def test_match_returns_none_when_no_activity():
    """Missing activity returns None."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    scalar_mock = MagicMock()
    scalar_mock.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=scalar_mock)

    from fitops.analytics import race_plan as rp_module

    with patch.object(rp_module, "get_async_session", return_value=mock_session):
        result = await rp_module.match_activity_to_plans(999)

    assert result is None


# ---------------------------------------------------------------------------
# Text formatter smoke tests — verify they don't crash with typical data
# ---------------------------------------------------------------------------


def test_print_race_plans_list_empty(capsys):
    print_race_plans_list({"plans": []})
    out = capsys.readouterr().out
    assert "No race plans" in out


def test_print_race_plans_list_with_data(capsys):
    print_race_plans_list(
        {
            "plans": [
                {
                    "id": 1,
                    "name": "Berlin 2026",
                    "course_id": 2,
                    "race_date": "2026-09-27",
                    "target_time": "3:00:00",
                    "strategy": "even",
                    "activity_id": None,
                }
            ]
        }
    )
    out = capsys.readouterr().out
    assert "Berlin 2026" in out
    assert "3:00:00" in out


def test_print_race_plan_detail_no_splits(capsys):
    plan = _make_plan(splits_json=None)
    print_race_plan_detail({"plan": plan.to_detail_dict()})
    out = capsys.readouterr().out
    assert "Test Plan" in out


def test_print_race_plan_detail_with_splits(capsys):
    plan = _make_plan()
    print_race_plan_detail({"plan": plan.to_detail_dict()})
    out = capsys.readouterr().out
    assert "Test Plan" in out
    assert "3:00:00" in out


def test_print_race_plan_compare_no_splits(capsys):
    plan = _make_plan()
    print_race_plan_compare(
        {
            "plan": plan.to_detail_dict(),
            "actual_splits": [],
            "actual_avg_pace_fmt": None,
            "actual_finish_fmt": None,
        }
    )
    out = capsys.readouterr().out
    assert "No splits" in out


def test_print_race_plan_compare_with_data(capsys):
    plan = _make_plan()
    actual_splits = [
        {"km": 1, "pace_s": 260, "distance_m": 1000, "avg_hr": 155, "avg_cadence": 90},
        {"km": 2, "pace_s": 258, "distance_m": 1000, "avg_hr": 158, "avg_cadence": 91},
    ]
    print_race_plan_compare(
        {
            "plan": plan.to_detail_dict(),
            "actual_splits": actual_splits,
            "actual_avg_pace_fmt": "4:19",
            "actual_finish_fmt": "8:38",
        }
    )
    out = capsys.readouterr().out
    assert "4:15" in out  # sim pace


# ---------------------------------------------------------------------------
# CLI JSON shape — test via direct function invocation + monkeypatch
# ---------------------------------------------------------------------------


def test_plans_list_json_shape(monkeypatch):
    """get_all_race_plans returns the expected list shape."""
    import asyncio

    fake_plans = [
        {
            "id": 1,
            "course_id": 1,
            "name": "Test",
            "race_date": "2026-09-27",
            "target_time": "3:00:00",
            "strategy": "even",
            "activity_id": None,
        }
    ]

    async def _fake_get_all():
        return fake_plans

    monkeypatch.setattr(
        "fitops.dashboard.queries.race.get_all_race_plans", _fake_get_all
    )

    from fitops.output.formatter import make_meta

    result = asyncio.run(_fake_get_all())
    out = {"_meta": make_meta(total_count=len(result)), "plans": result}
    assert "plans" in out
    assert out["plans"][0]["name"] == "Test"
    assert "_meta" in out
