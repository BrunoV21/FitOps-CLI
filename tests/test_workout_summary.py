from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typer.testing import CliRunner

import fitops.db.migrations  # noqa: F401
from fitops.db.base import Base


@pytest.fixture
async def workout_summary_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def workout_summary_session(workout_summary_engine, monkeypatch):
    factory = async_sessionmaker(
        workout_summary_engine, class_=AsyncSession, expire_on_commit=False
    )

    @asynccontextmanager
    async def _session_ctx():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(
        "fitops.analytics.workout_summary.get_async_session", _session_ctx
    )
    return factory


@pytest.fixture
def client(monkeypatch):
    from starlette.testclient import TestClient

    monkeypatch.setattr(
        "fitops.db.migrations.create_all_tables", AsyncMock(return_value=None)
    )
    from fitops.dashboard.server import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


async def test_workout_summary_uses_stored_scores(workout_summary_session):
    from fitops.analytics.workout_summary import get_workout_summary
    from fitops.db.models.activity import Activity
    from fitops.db.models.workout import Workout
    from fitops.db.models.workout_activity_link import WorkoutActivityLink
    from fitops.db.models.workout_segment import WorkoutSegment

    now = datetime.now(UTC)
    async with workout_summary_session() as session:
        threshold = Workout(
            name="Threshold Tuesday",
            sport_type="Run",
            athlete_id=42,
            status="completed",
        )
        easy = Workout(
            name="Easy Aerobic",
            sport_type="Run",
            athlete_id=42,
            status="planned",
        )
        ride = Workout(
            name="Endurance Ride",
            sport_type="Ride",
            athlete_id=42,
            status="planned",
        )
        session.add_all([threshold, easy, ride])
        await session.flush()

        run_a = Activity.from_strava_data(
            {
                "id": 1001,
                "name": "Run A",
                "sport_type": "Run",
                "start_date": now.isoformat(),
                "start_date_local": now.isoformat(),
                "distance": 10000.0,
                "moving_time": 3600,
            },
            athlete_id=42,
        )
        run_b = Activity.from_strava_data(
            {
                "id": 1002,
                "name": "Run B",
                "sport_type": "Run",
                "start_date": (now - timedelta(days=2)).isoformat(),
                "start_date_local": (now - timedelta(days=2)).isoformat(),
                "distance": 8000.0,
                "moving_time": 3000,
            },
            athlete_id=42,
        )
        ride_a = Activity.from_strava_data(
            {
                "id": 1003,
                "name": "Ride A",
                "sport_type": "Ride",
                "start_date": now.isoformat(),
                "start_date_local": now.isoformat(),
                "distance": 20000.0,
                "moving_time": 3600,
            },
            athlete_id=42,
        )
        session.add_all([run_a, run_b, ride_a])
        await session.flush()

        session.add_all(
            [
                WorkoutActivityLink(
                    workout_id=threshold.id,
                    activity_id=run_a.id,
                    linked_at=now,
                    compliance_score=0.9,
                ),
                WorkoutActivityLink(
                    workout_id=threshold.id,
                    activity_id=run_b.id,
                    linked_at=now - timedelta(days=2),
                    compliance_score=0.7,
                ),
                WorkoutActivityLink(
                    workout_id=ride.id,
                    activity_id=ride_a.id,
                    linked_at=now,
                    compliance_score=None,
                ),
            ]
        )
        session.add_all(
            [
                WorkoutSegment(
                    workout_id=threshold.id,
                    activity_id=run_a.id,
                    segment_index=0,
                    target_achieved=1,
                    time_in_target_pct=80,
                    compliance_score=0.8,
                ),
                WorkoutSegment(
                    workout_id=threshold.id,
                    activity_id=run_a.id,
                    segment_index=1,
                    target_achieved=0,
                    time_in_target_pct=40,
                    compliance_score=0.4,
                ),
                WorkoutSegment(
                    workout_id=threshold.id,
                    activity_id=run_b.id,
                    segment_index=0,
                    target_achieved=1,
                    time_in_target_pct=90,
                    compliance_score=0.9,
                ),
                WorkoutSegment(
                    workout_id=threshold.id,
                    activity_id=run_b.id,
                    segment_index=1,
                    target_achieved=1,
                    time_in_target_pct=70,
                    compliance_score=0.7,
                ),
            ]
        )
        await session.commit()

    result = await get_workout_summary(42, period="month", sport="run")
    summary = result["summary"]

    assert summary["completed_sessions"] == 2
    assert summary["unique_completed_workouts"] == 1
    assert summary["total_definitions"] == 2
    assert summary["unlinked_definitions"] == 1
    assert summary["total_duration_seconds"] == 6600
    assert summary["total_duration_formatted"] == "1:50:00"
    assert summary["total_distance_km"] == 18.0
    assert summary["avg_compliance_pct"] == 80
    assert summary["scored_sessions"] == 2
    assert summary["compliance_coverage_pct"] == 100
    assert summary["segment_count"] == 4
    assert summary["segments_in_target_pct"] == 75
    assert summary["avg_time_in_target_pct"] == 70
    assert summary["most_repeated_workout"]["name"] == "Threshold Tuesday"
    assert summary["most_repeated_workout"]["sessions"] == 2
    assert summary["best_compliance_workout"]["avg_compliance_pct"] == 80


def _fake_settings():
    return SimpleNamespace(
        athlete_id=42,
        is_authenticated=True,
        has_write_scope=False,
    )


def test_workouts_dashboard_renders_summary(client, monkeypatch):
    monkeypatch.setattr(
        "fitops.dashboard.routes.workouts.get_settings", lambda: _fake_settings()
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.workouts.get_workout_summary",
        AsyncMock(
            return_value={
                "period": "month",
                "period_label": "This Month",
                "sport": "total",
                "summary": {
                    "completed_sessions": 3,
                    "unique_completed_workouts": 2,
                    "total_definitions": 4,
                    "planned_definitions": 1,
                    "unlinked_definitions": 1,
                    "total_duration_seconds": 7200,
                    "total_duration_formatted": "2:00:00",
                    "total_distance_km": 21.1,
                    "avg_compliance_pct": 88,
                    "scored_sessions": 2,
                    "compliance_coverage_pct": 67,
                    "segment_count": 8,
                    "segments_in_target_pct": 75,
                    "avg_time_in_target_pct": 72,
                    "avg_segment_compliance_pct": 81,
                    "most_repeated_workout": {
                        "id": 1,
                        "name": "Threshold Tuesday",
                        "sessions": 2,
                    },
                    "best_compliance_workout": {
                        "id": 2,
                        "name": "Easy Aerobic",
                        "avg_compliance_pct": 94,
                        "sessions": 1,
                    },
                    "latest_completed": {
                        "workout_id": 1,
                        "name": "Threshold Tuesday",
                        "activity_id": 1001,
                        "completed_at": "2026-05-16T08:00:00+00:00",
                    },
                },
                "distributions": {"by_sport": [], "compliance_bands": {}},
            }
        ),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.workouts.get_async_session",
        lambda: _empty_session_ctx(),
    )
    monkeypatch.setattr("fitops.workouts.loader.list_workout_files", lambda: [])

    response = client.get("/workouts?period=month&view=total")

    assert response.status_code == 200
    assert "Completed — This Month" in response.text
    assert "Average Compliance" in response.text
    assert "Threshold Tuesday" in response.text


def test_workouts_summary_cli_json(monkeypatch):
    from fitops.cli.workouts import app

    class _Settings:
        athlete_id = 42

        def require_auth(self):
            return None

    monkeypatch.setattr("fitops.cli.workouts.init_db", lambda: None)
    monkeypatch.setattr("fitops.cli.workouts.get_settings", lambda: _Settings())
    monkeypatch.setattr(
        "fitops.cli.workouts.get_workout_summary",
        AsyncMock(
            return_value={
                "period": "month",
                "period_label": "This Month",
                "sport": "total",
                "summary": {
                    "completed_sessions": 2,
                    "unique_completed_workouts": 1,
                    "total_definitions": 1,
                    "planned_definitions": 0,
                    "unlinked_definitions": 0,
                    "total_duration_seconds": 3600,
                    "total_duration_formatted": "1:00:00",
                    "total_distance_km": 10.0,
                    "avg_compliance_pct": 90,
                    "scored_sessions": 2,
                    "compliance_coverage_pct": 100,
                    "segment_count": 4,
                    "segments_in_target_pct": 75,
                    "avg_time_in_target_pct": 70,
                    "avg_segment_compliance_pct": 80,
                    "most_repeated_workout": None,
                    "best_compliance_workout": None,
                    "latest_completed": None,
                },
                "distributions": {"by_sport": [], "compliance_bands": {}},
            }
        ),
    )

    result = CliRunner().invoke(
        app,
        ["summary", "--period", "month", "--sport", "total", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["_meta"]["tool"] == "fitops"
    assert payload["_meta"]["filters_applied"] == {
        "period": "month",
        "sport": "total",
    }
    assert payload["summary"]["summary"]["completed_sessions"] == 2
    assert payload["data_availability"]["recomputed"] is False


@asynccontextmanager
async def _empty_session_ctx():
    class _Result:
        def fetchall(self):
            return []

        def scalars(self):
            return self

        def all(self):
            return []

    class _Session:
        async def execute(self, *_args, **_kwargs):
            return _Result()

        def add(self, *_args, **_kwargs):
            return None

        async def commit(self):
            return None

    yield _Session()
