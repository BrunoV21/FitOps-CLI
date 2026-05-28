from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typer.testing import CliRunner

import fitops.db.migrations  # noqa: F401
from fitops.db.base import Base


async def test_workout_contribution_uses_stored_tss(monkeypatch):
    from fitops.analytics.training_load import ALPHA_CTL
    from fitops.analytics.workout_contribution import get_workout_contribution
    from fitops.db.models.activity import Activity
    from fitops.db.models.activity_weather import ActivityWeather
    from fitops.db.models.workout import Workout
    from fitops.db.models.workout_activity_link import WorkoutActivityLink
    from fitops.db.models.workout_segment import WorkoutSegment

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

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
        "fitops.analytics.workout_contribution.get_async_session", _session_ctx
    )

    async with factory() as session:
        workout = Workout(
            name="Threshold Tuesday",
            sport_type="Run",
            athlete_id=42,
            status="completed",
        )
        session.add(workout)
        await session.flush()

        activities = [
            Activity.from_strava_data(
                {
                    "id": 1001,
                    "name": "Threshold A",
                    "sport_type": "Run",
                    "start_date": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                    "start_date_local": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                    "distance": 10000.0,
                    "moving_time": 3000,
                    "average_speed": 3.333,
                    "average_heartrate": 155,
                },
                athlete_id=42,
            ),
            Activity.from_strava_data(
                {
                    "id": 1002,
                    "name": "Threshold B",
                    "sport_type": "Run",
                    "start_date": datetime(2026, 1, 8, tzinfo=UTC).isoformat(),
                    "start_date_local": datetime(2026, 1, 8, tzinfo=UTC).isoformat(),
                    "distance": 10000.0,
                    "moving_time": 2940,
                    "average_speed": 3.401,
                    "average_heartrate": 152,
                },
                athlete_id=42,
            ),
            Activity.from_strava_data(
                {
                    "id": 1003,
                    "name": "Threshold Missing TSS",
                    "sport_type": "Run",
                    "start_date": datetime(2026, 1, 9, tzinfo=UTC).isoformat(),
                    "start_date_local": datetime(2026, 1, 9, tzinfo=UTC).isoformat(),
                    "distance": 9000.0,
                    "moving_time": 3000,
                },
                athlete_id=42,
            ),
            Activity.from_strava_data(
                {
                    "id": 2001,
                    "name": "Easy Other",
                    "sport_type": "Run",
                    "start_date": datetime(2026, 1, 7, tzinfo=UTC).isoformat(),
                    "start_date_local": datetime(2026, 1, 7, tzinfo=UTC).isoformat(),
                    "distance": 6000.0,
                    "moving_time": 2100,
                },
                athlete_id=42,
            ),
        ]
        activities[0].training_stress_score = 80.0
        activities[1].training_stress_score = 40.0
        activities[3].training_stress_score = 30.0
        session.add_all(activities)
        await session.flush()

        session.add_all(
            [
                ActivityWeather(
                    activity_id=activities[0].id,
                    true_pace_s_per_km=304.0,
                ),
                ActivityWeather(
                    activity_id=activities[1].id,
                    true_pace_s_per_km=292.0,
                ),
                WorkoutActivityLink(
                    workout_id=workout.id,
                    activity_id=activities[0].id,
                    compliance_score=0.8,
                    physiology_snapshot=json.dumps({"tsb": -4.2}),
                ),
                WorkoutActivityLink(
                    workout_id=workout.id,
                    activity_id=activities[1].id,
                    compliance_score=0.9,
                ),
                WorkoutActivityLink(
                    workout_id=workout.id,
                    activity_id=activities[2].id,
                    compliance_score=None,
                ),
                WorkoutSegment(
                    workout_id=workout.id,
                    activity_id=activities[0].id,
                    segment_index=0,
                    segment_name="Warmup",
                    compliance_score=0.8,
                    avg_pace_per_km=300.0,
                    avg_heartrate=150,
                ),
                WorkoutSegment(
                    workout_id=workout.id,
                    activity_id=activities[1].id,
                    segment_index=0,
                    segment_name="Warmup",
                    compliance_score=0.7,
                    avg_pace_per_km=290.0,
                    avg_heartrate=148,
                ),
            ]
        )
        await session.commit()
        workout_id = workout.id

    result = await get_workout_contribution(
        42,
        workout_id,
        period="all",
        as_of=date(2026, 1, 10),
    )
    await engine.dispose()

    summary = result["summary"]
    expected_ctl = 80.0 * ALPHA_CTL * ((1 - ALPHA_CTL) ** 9) + 40.0 * ALPHA_CTL * (
        (1 - ALPHA_CTL) ** 2
    )

    assert result["data_availability"]["recomputed"] is False
    assert summary["total_sessions"] == 3
    assert summary["total_tss"] == 120.0
    assert summary["period_total_training_tss"] == 150.0
    assert summary["period_load_share_pct"] == 80.0
    assert summary["compliance_weighted_tss"] == 100.0
    assert summary["missing_tss_sessions"] == 1
    assert summary["tss_coverage_pct"] == 67
    assert summary["current_ctl_contribution"] == round(expected_ctl, 2)
    assert summary["avg_compliance_pct"] == 85
    assert summary["true_pace_change_pct"] > 0
    assert summary["pace_change_pct"] == summary["true_pace_change_pct"]
    assert summary["first_true_pace_formatted"] == "5:04"
    assert summary["latest_true_pace_formatted"] == "4:52"
    assert summary["missing_true_pace_sessions"] == 1
    assert result["trend"][0]["tsb_at_workout"] == -4.2
    assert result["trend"][0]["true_pace_s_per_km"] == 304.0
    assert result["trend"][1]["true_pace_s_per_km"] == 292.0
    assert result["trend"][2]["true_pace_s_per_km"] is None
    assert result["segment_summary"][0]["avg_compliance_pct"] == 75


async def test_workout_contribution_handles_sqlite_naive_dates(monkeypatch):
    from fitops.analytics.workout_contribution import get_workout_contribution
    from fitops.db.models.activity import Activity
    from fitops.db.models.workout import Workout
    from fitops.db.models.workout_activity_link import WorkoutActivityLink

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

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
        "fitops.analytics.workout_contribution.get_async_session", _session_ctx
    )

    current_year = datetime.now(UTC).year
    naive_start = datetime(current_year, 1, 10, 8, 0)

    async with factory() as session:
        workout = Workout(
            name="Tempo Friday",
            sport_type="Run",
            athlete_id=42,
            status="completed",
        )
        session.add(workout)
        await session.flush()

        activity = Activity.from_strava_data(
            {
                "id": 3001,
                "name": "Tempo A",
                "sport_type": "Run",
                "start_date": naive_start.isoformat(),
                "start_date_local": naive_start.isoformat(),
                "distance": 8000.0,
                "moving_time": 2400,
                "average_speed": 3.333,
            },
            athlete_id=42,
        )
        activity.training_stress_score = 55.0
        session.add(activity)
        await session.flush()

        session.add(
            WorkoutActivityLink(
                workout_id=workout.id,
                activity_id=activity.id,
                compliance_score=0.95,
            )
        )
        await session.commit()
        workout_id = workout.id

    result = await get_workout_contribution(
        42,
        workout_id,
        period="year",
        as_of=date(current_year, 1, 11),
    )
    await engine.dispose()

    assert result["summary"]["period_sessions"] == 1
    assert result["summary"]["period_tss"] == 55.0
    assert result["period_trend"][0]["activity_strava_id"] == 3001


def test_workout_analytics_cli_json(monkeypatch):
    from fitops.cli.workouts import app
    from fitops.db.models.workout import Workout

    class _Result:
        def scalar_one_or_none(self):
            return Workout(id=7, athlete_id=42, name="Threshold Tuesday")

    class _Session:
        async def execute(self, *_args, **_kwargs):
            return _Result()

    @asynccontextmanager
    async def _session_ctx():
        yield _Session()

    class _Settings:
        athlete_id = 42

        def require_auth(self):
            return None

    monkeypatch.setattr("fitops.cli.workouts.init_db", lambda: None)
    monkeypatch.setattr("fitops.cli.workouts.get_settings", lambda: _Settings())
    monkeypatch.setattr("fitops.cli.workouts.get_async_session", _session_ctx)
    monkeypatch.setattr(
        "fitops.cli.workouts.get_workout_contribution",
        AsyncMock(
            return_value={
                "workout": {"id": 7, "name": "Threshold Tuesday", "sport_type": "Run"},
                "period": "year",
                "period_label": "This Year",
                "summary": {"period_sessions": 1},
                "trend": [{"date": "2026-01-01", "tss": 80.0}],
                "period_trend": [{"date": "2026-01-01", "tss": 80.0}],
                "segment_summary": [],
                "data_availability": {"recomputed": False},
            }
        ),
    )

    result = CliRunner().invoke(
        app,
        ["analytics", "Threshold Tuesday", "--period", "year", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["_meta"]["filters_applied"] == {
        "workout": "Threshold Tuesday",
        "period": "year",
    }
    assert payload["workout_analytics"]["data_availability"]["recomputed"] is False
