"""Tests for persist_training_load_snapshot and get_current_training_load."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

import fitops.db.migrations  # noqa: F401 — registers all models on Base.metadata
from fitops.db.base import Base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    """In-memory async SQLite engine with all tables created."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def patched_session(engine, monkeypatch):
    """Redirect get_async_session to use the in-memory engine."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import fitops.db.session as session_module

    monkeypatch.setattr(session_module, "_session_factory", factory)
    monkeypatch.setattr(session_module, "get_session_factory", lambda: factory)
    return factory


@pytest.fixture
async def populated_db(engine, patched_session):
    """Insert a run activity using the ORM so all NOT NULL defaults are respected."""
    from fitops.db.models.activity import Activity

    factory = patched_session
    async with factory() as session:
        activity = Activity.from_strava_data(
            {
                "id": 1001,
                "name": "Test Run",
                "sport_type": "Run",
                "start_date": "2026-01-01T07:00:00Z",
                "start_date_local": "2026-01-01T08:00:00Z",
                "distance": 12000.0,
                "moving_time": 3600,
                "elapsed_time": 3650,
                "total_elevation_gain": 50.0,
                "average_speed": 3.33,
                "average_heartrate": 155.0,
            },
            athlete_id=42,
        )
        session.add(activity)
    return 42  # athlete_id


# ---------------------------------------------------------------------------
# persist_training_load_snapshot
# ---------------------------------------------------------------------------


async def test_persist_snapshot_creates_row(populated_db, patched_session, engine):
    """After persist_training_load_snapshot, a row must exist in analytics_snapshots."""
    from fitops.analytics.training_load import persist_training_load_snapshot

    athlete_id = populated_db
    await persist_training_load_snapshot(athlete_id)

    async with engine.connect() as conn:
        row = await conn.execute(
            text(
                "SELECT ctl, atl, tsb FROM analytics_snapshots "
                "WHERE athlete_id = :aid AND sport_type IS NULL"
            ),
            {"aid": athlete_id},
        )
        result = row.fetchone()

    assert result is not None, "Snapshot row was not written"
    ctl, atl, tsb = result
    assert ctl >= 0.0
    assert atl >= 0.0
    assert abs(tsb - (ctl - atl)) < 0.01


async def test_persist_snapshot_upserts(populated_db, patched_session, engine):
    """Calling persist_training_load_snapshot twice must not create duplicate rows."""
    from fitops.analytics.training_load import persist_training_load_snapshot

    athlete_id = populated_db
    await persist_training_load_snapshot(athlete_id)
    await persist_training_load_snapshot(athlete_id)

    async with engine.connect() as conn:
        row = await conn.execute(
            text(
                "SELECT COUNT(*) FROM analytics_snapshots "
                "WHERE athlete_id = :aid AND sport_type IS NULL"
            ),
            {"aid": athlete_id},
        )
        count = row.scalar()

    assert count == 1, f"Expected 1 snapshot row, got {count}"


async def test_persist_snapshot_no_activities(patched_session, engine):
    """persist_training_load_snapshot writes a zero-CTL snapshot even with no activities."""
    from fitops.analytics.training_load import persist_training_load_snapshot

    await persist_training_load_snapshot(99)

    async with engine.connect() as conn:
        row = await conn.execute(
            text(
                "SELECT ctl, atl, tsb FROM analytics_snapshots "
                "WHERE athlete_id = 99 AND sport_type IS NULL"
            )
        )
        result = row.fetchone()

    # A zero-CTL snapshot is valid and useful — it lets the dashboard show 0s
    # instead of triggering a cold-start recompute on the next page load.
    assert result is not None
    ctl, atl, tsb = result
    assert ctl == 0.0
    assert atl == 0.0
    assert tsb == 0.0


# ---------------------------------------------------------------------------
# get_current_training_load
# ---------------------------------------------------------------------------


async def test_get_current_training_load_returns_dict(
    populated_db, patched_session, engine
):
    """get_current_training_load returns a dict with ctl/atl/tsb/form_label."""
    from fitops.analytics.training_load import persist_training_load_snapshot
    from fitops.dashboard.queries.analytics import get_current_training_load

    athlete_id = populated_db
    await persist_training_load_snapshot(athlete_id)

    result = await get_current_training_load(athlete_id)

    assert result is not None
    assert "ctl" in result
    assert "atl" in result
    assert "tsb" in result
    assert "form_label" in result
    assert isinstance(result["form_label"], str)
    assert len(result["form_label"]) > 0


async def test_get_current_training_load_cold_start(populated_db, patched_session):
    """get_current_training_load falls back gracefully when no snapshot row exists."""
    from fitops.dashboard.queries.analytics import get_current_training_load

    # No snapshot written — should compute on-the-fly and return a dict
    result = await get_current_training_load(populated_db)

    assert result is not None
    assert "ctl" in result
    assert "tsb" in result


async def test_get_current_training_load_no_data(patched_session):
    """get_current_training_load returns zero-CTL dict even when athlete has no activities."""
    from fitops.dashboard.queries.analytics import get_current_training_load

    result = await get_current_training_load(999)

    # compute_training_load always produces today's row (even with 0 TSS), so
    # get_current_training_load should return a valid dict rather than None.
    assert result is not None
    assert result["ctl"] == 0.0
    assert result["atl"] == 0.0
    assert result["tsb"] == 0.0
