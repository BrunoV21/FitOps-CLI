"""Tests for performance metric calculations and day filtering."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import fitops.db.migrations  # noqa: F401 - registers all models on Base.metadata
from fitops.db.base import Base


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def patched_session(engine, monkeypatch):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import fitops.db.session as session_module

    monkeypatch.setattr(session_module, "_session_factory", factory)
    monkeypatch.setattr(session_module, "get_session_factory", lambda: factory)
    return factory


async def _seed_athlete(factory):
    from fitops.db.models.athlete import Athlete

    async with factory() as session:
        session.add(
            Athlete.from_strava_data(
                {
                    "id": 42,
                    "firstname": "Test",
                    "lastname": "Athlete",
                    "weight": 70.0,
                }
            )
        )
        await session.commit()


async def _seed_activity(factory, *, sport_type: str, **activity_kwargs):
    from fitops.db.models.activity import Activity

    async with factory() as session:
        activity = Activity.from_strava_data(
            {
                "id": activity_kwargs.get("id", 1001),
                "name": activity_kwargs.get("name", "Test Activity"),
                "sport_type": sport_type,
                "start_date": activity_kwargs.get(
                    "start_date", "2026-01-01T07:00:00Z"
                ),
                "start_date_local": activity_kwargs.get(
                    "start_date_local", "2026-01-01T08:00:00Z"
                ),
                "distance": activity_kwargs.get("distance", 10_000.0),
                "moving_time": activity_kwargs.get("moving_time", 3_600),
                "elapsed_time": activity_kwargs.get("elapsed_time", 3_650),
                "average_speed": activity_kwargs.get("average_speed", 2.78),
                "average_heartrate": activity_kwargs.get("average_heartrate", 155.0),
                "max_heartrate": activity_kwargs.get("max_heartrate", 170),
                "average_watts": activity_kwargs.get("average_watts"),
                "weighted_average_watts": activity_kwargs.get(
                    "weighted_average_watts"
                ),
            },
            athlete_id=42,
        )
        session.add(activity)
        await session.commit()


async def test_compute_performance_metrics_run_filters_by_days(patched_session):
    from fitops.analytics.performance_metrics import compute_performance_metrics

    await _seed_athlete(patched_session)
    await _seed_activity(
        patched_session,
        sport_type="Run",
        id=1001,
        start_date="2026-04-01T07:00:00Z",
        start_date_local="2026-04-01T08:00:00Z",
        distance=12_000.0,
        moving_time=3_600,
        elapsed_time=3_650,
        average_speed=3.33,
        average_heartrate=158.0,
        max_heartrate=174,
    )
    await _seed_activity(
        patched_session,
        sport_type="Run",
        id=1002,
        start_date="2024-04-01T07:00:00Z",
        start_date_local="2024-04-01T08:00:00Z",
        distance=8_000.0,
        moving_time=2_600,
        elapsed_time=2_700,
        average_speed=3.08,
        average_heartrate=148.0,
        max_heartrate=165,
    )

    result = await compute_performance_metrics(athlete_id=42, sport="Run", days=365)

    assert result is not None
    assert result.sport == "Run"
    assert result.days == 365
    assert result.activity_count == 1
    assert result.running is not None
    assert result.cycling is None
    assert result.running["running_economy_ml_kg_km"] is not None
    assert result.running["max_hr_estimate"] == 174
    assert result.overall_reliability is not None


async def test_compute_performance_metrics_ride(patched_session):
    from fitops.analytics.performance_metrics import compute_performance_metrics

    await _seed_athlete(patched_session)
    await _seed_activity(
        patched_session,
        sport_type="Ride",
        id=2001,
        start_date="2026-04-01T07:00:00Z",
        start_date_local="2026-04-01T08:00:00Z",
        distance=42_000.0,
        moving_time=4_800,
        elapsed_time=4_900,
        average_speed=8.75,
        average_watts=200.0,
        weighted_average_watts=220.0,
    )

    result = await compute_performance_metrics(athlete_id=42, sport="Ride", days=365)

    assert result is not None
    assert result.sport == "Ride"
    assert result.running is None
    assert result.cycling is not None
    assert result.cycling["ftp_estimate_watts"] == 190.0
    assert result.cycling["power_to_weight_w_kg"] == 2.71
    assert result.cycling["power_consistency"] is not None
