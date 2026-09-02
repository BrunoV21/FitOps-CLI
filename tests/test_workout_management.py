from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient
from typer.testing import CliRunner

import fitops.db.migrations  # noqa: F401
from fitops.db.base import Base

SAMPLE_WORKOUT_JSON = {
    "training": {
        "warmup": {"time_minutes": 10},
        "intervals": [
            {
                "sets": 2,
                "run": {
                    "time_seconds": 60,
                    "pace_per_km": {"min": "4:00", "max": "4:20"},
                },
                "rest": {"time_seconds": 60},
            }
        ],
        "cooldown": {"time_minutes": 5},
    }
}


UPDATED_WORKOUT_JSON = {
    "training": {
        "warmup": {"time_minutes": 12},
        "intervals": [
            {
                "sets": 3,
                "run": {
                    "time_seconds": 45,
                    "pace_per_km": {"min": "3:50", "max": "4:10"},
                },
                "rest": {"time_seconds": 75},
            }
        ],
        "cooldown": {"time_minutes": 8},
    }
}


def test_workout_edit_and_delete_cli_clear_cache_and_file(monkeypatch, tmp_path):
    from fitops.cli.workouts import app
    from fitops.db.models.activity import Activity
    from fitops.db.models.workout import Workout
    from fitops.db.models.workout_activity_link import WorkoutActivityLink
    from fitops.db.models.workout_segment import WorkoutSegment

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async def _prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
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

        workout_file = tmp_path / "workouts" / "threshold.md"
        workout_file.parent.mkdir(parents=True)
        workout_file.write_text("old", encoding="utf-8")

        async with factory() as session:
            workout = Workout(
                name="Threshold Tuesday",
                sport_type="run",
                athlete_id=42,
                workout_file_name=workout_file.name,
                workout_meta=json.dumps(SAMPLE_WORKOUT_JSON),
                status="completed",
                compliance_score=0.8,
            )
            activity = Activity.from_strava_data(
                {
                    "id": 1001,
                    "name": "Run",
                    "sport_type": "Run",
                    "distance": 10000,
                    "moving_time": 3000,
                },
                athlete_id=42,
            )
            session.add_all([workout, activity])
            await session.flush()
            link = WorkoutActivityLink(
                workout_id=workout.id,
                activity_id=activity.id,
                compliance_score=0.8,
            )
            segment = WorkoutSegment(
                workout_id=workout.id,
                activity_id=activity.id,
                segment_index=0,
                segment_name="Warmup",
                compliance_score=0.8,
            )
            session.add_all([link, segment])
            await session.commit()
            workout_id = workout.id
        return factory, _session_ctx, workout_id, workout_file

    factory, session_ctx, workout_id, workout_file = asyncio.run(_prepare())

    class _Settings:
        athlete_id = 42
        fitops_dir = tmp_path

        def require_auth(self):
            return None

    source = tmp_path / "updated.json"
    source.write_text(json.dumps(UPDATED_WORKOUT_JSON), encoding="utf-8")

    monkeypatch.setattr("fitops.cli.workouts.init_db", lambda: None)
    monkeypatch.setattr("fitops.cli.workouts.get_settings", lambda: _Settings())
    monkeypatch.setattr("fitops.cli.workouts.get_async_session", session_ctx)
    monkeypatch.setattr("fitops.cli.workouts.trigger_cli", lambda: None)
    monkeypatch.setattr(
        "fitops.workouts.loader.get_settings",
        lambda: SimpleNamespace(fitops_dir=tmp_path),
    )

    edit_result = CliRunner().invoke(
        app,
        [
            "edit",
            str(workout_id),
            str(source),
            "--name",
            "Threshold Updated",
            "--json",
        ],
    )
    assert edit_result.exit_code == 0
    edited = json.loads(edit_result.stdout)["updated"]
    assert edited["segment_rows_deleted"] == 1
    assert edited["linked_sessions_invalidated"] == 1
    assert "Threshold Updated" in workout_file.read_text(encoding="utf-8")

    async def _assert_edited():
        async with factory() as session:
            workout = (
                await session.execute(select(Workout).where(Workout.id == workout_id))
            ).scalar_one()
            link = (
                await session.execute(
                    select(WorkoutActivityLink).where(
                        WorkoutActivityLink.workout_id == workout_id
                    )
                )
            ).scalar_one()
            segments = (
                (
                    await session.execute(
                        select(WorkoutSegment).where(
                            WorkoutSegment.workout_id == workout_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert workout.name == "Threshold Updated"
            assert workout.compliance_score is None
            assert link.compliance_score is None
            assert segments == []

    asyncio.run(_assert_edited())

    delete_result = CliRunner().invoke(
        app,
        ["delete", str(workout_id), "--yes", "--json"],
    )
    assert delete_result.exit_code == 0
    deleted = json.loads(delete_result.stdout)["deleted"]
    assert deleted["links"] == 1
    assert deleted["file_deleted"] is True
    assert not workout_file.exists()

    async def _assert_deleted():
        async with factory() as session:
            assert (
                await session.execute(select(Workout).where(Workout.id == workout_id))
            ).scalar_one_or_none() is None
            assert (
                await session.execute(
                    select(WorkoutActivityLink).where(
                        WorkoutActivityLink.workout_id == workout_id
                    )
                )
            ).scalars().all() == []

    asyncio.run(_assert_deleted())
    asyncio.run(engine.dispose())


def test_workout_dashboard_edit_and_delete_routes(monkeypatch, tmp_path):
    from fitops.db.models.activity import Activity
    from fitops.db.models.activity_weather import ActivityWeather
    from fitops.db.models.workout import Workout
    from fitops.db.models.workout_activity_link import WorkoutActivityLink

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async def _prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
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

        workout_file = tmp_path / "workouts" / "dashboard-workout.md"
        workout_file.parent.mkdir(parents=True)
        workout_file.write_text("old", encoding="utf-8")
        current_year = datetime.now(UTC).year
        naive_start = datetime(current_year, 1, 10, 8, 0)

        async with factory() as session:
            workout = Workout(
                name="Dashboard Workout",
                sport_type="run",
                athlete_id=42,
                workout_file_name=workout_file.name,
                workout_meta=json.dumps(SAMPLE_WORKOUT_JSON),
            )
            activity = Activity.from_strava_data(
                {
                    "id": 9001,
                    "name": "Dashboard Workout Run",
                    "sport_type": "Run",
                    "start_date": naive_start.isoformat(),
                    "start_date_local": naive_start.isoformat(),
                    "distance": 8000,
                    "moving_time": 2400,
                    "average_speed": 3.333,
                },
                athlete_id=42,
            )
            activity.training_stress_score = 50.0
            session.add_all([workout, activity])
            await session.flush()
            session.add(
                WorkoutActivityLink(
                    workout_id=workout.id,
                    activity_id=activity.id,
                    compliance_score=0.9,
                )
            )
            session.add(
                ActivityWeather(
                    activity_id=activity.id,
                    true_pace_s_per_km=296.0,
                )
            )
            await session.commit()
            workout_id = workout.id
        return factory, _session_ctx, workout_id, workout_file

    factory, session_ctx, workout_id, workout_file = asyncio.run(_prepare())

    monkeypatch.setattr(
        "fitops.db.migrations.create_all_tables", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.workouts.get_settings",
        lambda: SimpleNamespace(
            athlete_id=42,
            is_authenticated=True,
            has_write_scope=False,
            fitops_dir=tmp_path,
        ),
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.workouts.get_async_session", session_ctx
    )
    monkeypatch.setattr(
        "fitops.dashboard.queries.workouts.get_async_session", session_ctx
    )
    monkeypatch.setattr(
        "fitops.analytics.workout_contribution.get_async_session", session_ctx
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.workouts.trigger_async", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "fitops.workouts.loader.get_settings",
        lambda: SimpleNamespace(fitops_dir=tmp_path),
    )

    from fitops.dashboard.server import create_app

    with TestClient(create_app()) as client:
        detail_response = client.get(f"/workouts/{workout_id}")
        assert detail_response.status_code == 200
        assert "/edit" in detail_response.text
        assert "Delete" in detail_response.text
        assert "Workout Analytics" in detail_response.text
        assert "True Pace Change" in detail_response.text
        assert "True pace min/km" in detail_response.text
        assert "True pace:" in detail_response.text
        assert "true_pace_s_per_km" in detail_response.text
        assert '<th class="r">True Pace</th>' in detail_response.text
        assert "4:56/km" in detail_response.text

        edit_response = client.get(f"/workouts/{workout_id}/edit")
        assert edit_response.status_code == 200
        assert "Edit Workout" in edit_response.text
        assert "Dashboard Workout" in edit_response.text
        assert "Structured Workout JSON" not in edit_response.text
        assert "<textarea" not in edit_response.text
        assert 'id="warmup-time"' in edit_response.text
        assert 'id="intervals-container"' in edit_response.text
        assert 'id="cooldown-time"' in edit_response.text
        assert "workout-builder-basic" in edit_response.text
        assert "workout-builder-nav" in edit_response.text
        assert "workout-builder-section" in edit_response.text
        assert "@media (max-width: 767px)" in edit_response.text
        assert "initialWorkoutJSONString" in edit_response.text

        edit_post_response = client.post(
            f"/workouts/{workout_id}/edit",
            data={
                "name": "Dashboard Workout Updated",
                "sport": "run",
                "workout_json_str": json.dumps(UPDATED_WORKOUT_JSON),
            },
            follow_redirects=False,
        )
        assert edit_post_response.status_code == 303
        assert edit_post_response.headers["location"] == f"/workouts/{workout_id}"
        assert "Dashboard Workout Updated" in workout_file.read_text(encoding="utf-8")

        delete_response = client.post(
            f"/workouts/{workout_id}/delete",
            follow_redirects=False,
        )
        assert delete_response.status_code == 303

    assert not workout_file.exists()

    async def _assert_deleted():
        async with factory() as session:
            assert (
                await session.execute(select(Workout).where(Workout.id == workout_id))
            ).scalar_one_or_none() is None

    asyncio.run(_assert_deleted())
    asyncio.run(engine.dispose())
