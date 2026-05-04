from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fitops.db.base import Base
from fitops.db.models.activity import Activity  # noqa: F401
from fitops.db.models.activity_calibration import ActivityCalibration  # noqa: F401
from fitops.db.models.activity_laps import ActivityLap  # noqa: F401
from fitops.db.models.activity_stream import ActivityStream  # noqa: F401
from fitops.db.models.activity_weather import ActivityWeather  # noqa: F401
from fitops.db.models.analytics_snapshot import AnalyticsSnapshot  # noqa: F401

# Import all models so their tables are registered on Base.metadata
from fitops.db.models.athlete import Athlete  # noqa: F401
from fitops.db.models.note import Note  # noqa: F401
from fitops.db.models.race_course import RaceCourse  # noqa: F401
from fitops.db.models.race_plan import RacePlan  # noqa: F401
from fitops.db.models.race_session import (  # noqa: F401
    RaceSession,
    RaceSessionAthlete,
    RaceSessionEvent,
    RaceSessionGap,
    RaceSessionSegment,
)
from fitops.db.models.workout import Workout  # noqa: F401
from fitops.db.models.workout_activity_link import WorkoutActivityLink  # noqa: F401
from fitops.db.models.workout_course import WorkoutCourse  # noqa: F401
from fitops.db.models.workout_segment import WorkoutSegment  # noqa: F401
from fitops.db.session import get_engine

# Columns added to `athletes` after the initial schema.
_ATHLETE_NEW_COLUMNS: list[tuple[str, str]] = [
    ("birthday", "TEXT"),
    ("stamp_on_sync", "INTEGER NOT NULL DEFAULT 0"),
]


async def _migrate_athlete_columns(conn) -> None:
    """Add new columns to the athletes table if they don't exist yet."""
    result = await conn.execute(text("PRAGMA table_info(athletes)"))
    existing = {row[1] for row in result.fetchall()}
    for col_name, col_type in _ATHLETE_NEW_COLUMNS:
        if col_name not in existing:
            await conn.execute(
                text(f"ALTER TABLE athletes ADD COLUMN {col_name} {col_type}")
            )


# Columns added to `activities` after the initial schema.
_ACTIVITY_NEW_COLUMNS: list[tuple[str, str]] = [
    ("workout_type", "INTEGER"),
    ("aerobic_score", "REAL"),
    ("anaerobic_score", "REAL"),
    ("vo2max_estimate", "REAL"),
    ("chip_time_s", "INTEGER"),
    ("race_distance_m", "REAL"),
    ("est_power_avg_w", "REAL"),
    ("est_power_max_w", "REAL"),
    ("est_power_np_w", "REAL"),
    ("est_kcal_model", "INTEGER"),
    ("est_power_source", "TEXT"),
    ("stamped_at", "DATETIME"),
]


async def _migrate_activity_columns(conn) -> None:
    """Add new columns to the activities table if they don't exist yet."""
    result = await conn.execute(text("PRAGMA table_info(activities)"))
    existing = {row[1] for row in result.fetchall()}
    for col_name, col_type in _ACTIVITY_NEW_COLUMNS:
        if col_name not in existing:
            await conn.execute(
                text(f"ALTER TABLE activities ADD COLUMN {col_name} {col_type}")
            )


# Columns added to `workouts` after the initial Phase 1 stub.
# Each tuple: (column_name, SQLite type definition)
_WORKOUT_NEW_COLUMNS: list[tuple[str, str]] = [
    ("athlete_id", "INTEGER"),
    ("workout_file_name", "TEXT"),
    ("workout_markdown", "TEXT"),
    ("workout_meta", "TEXT"),
    ("linked_at", "DATETIME"),
    ("physiology_snapshot", "TEXT"),
]


async def _migrate_workout_columns(conn) -> None:
    """Add new columns to the workouts table if they don't exist yet."""
    result = await conn.execute(text("PRAGMA table_info(workouts)"))
    existing = {row[1] for row in result.fetchall()}
    for col_name, col_type in _WORKOUT_NEW_COLUMNS:
        if col_name not in existing:
            await conn.execute(
                text(f"ALTER TABLE workouts ADD COLUMN {col_name} {col_type}")
            )


# Columns added to `workout_segments` for extended compliance scoring.
_WORKOUT_SEGMENT_NEW_COLUMNS: list[tuple[str, str]] = [
    ("avg_speed_ms", "REAL"),
    ("avg_cadence", "REAL"),
    ("avg_gap_per_km", "REAL"),
    ("avg_true_pace_per_km", "REAL"),
    ("target_hr_min_bpm", "REAL"),
    ("target_hr_max_bpm", "REAL"),
    ("target_pace_min_s_per_km", "REAL"),
    ("target_pace_max_s_per_km", "REAL"),
    ("duration_actual_s", "INTEGER"),
    ("distance_actual_m", "REAL"),
]


async def _migrate_workout_segment_columns(conn) -> None:
    """Add new columns to the workout_segments table if they don't exist yet."""
    result = await conn.execute(text("PRAGMA table_info(workout_segments)"))
    existing = {row[1] for row in result.fetchall()}
    for col_name, col_type in _WORKOUT_SEGMENT_NEW_COLUMNS:
        if col_name not in existing:
            await conn.execute(
                text(f"ALTER TABLE workout_segments ADD COLUMN {col_name} {col_type}")
            )


# Columns added to `race_sessions` after the initial schema.
_RACE_SESSION_NEW_COLUMNS: list[tuple[str, str]] = [
    ("replay_frames_json", "TEXT"),
    ("replay_time_step_s", "REAL"),
]

_RACE_SESSION_EVENT_NEW_COLUMNS: list[tuple[str, str]] = [
    ("context_json", "TEXT"),
]


async def _migrate_race_session_columns(conn) -> None:
    """Add new columns to the race_sessions table if they don't exist yet."""
    result = await conn.execute(text("PRAGMA table_info(race_sessions)"))
    existing = {row[1] for row in result.fetchall()}
    for col_name, col_type in _RACE_SESSION_NEW_COLUMNS:
        if col_name not in existing:
            await conn.execute(
                text(f"ALTER TABLE race_sessions ADD COLUMN {col_name} {col_type}")
            )


async def _migrate_race_session_event_columns(conn) -> None:
    """Add new columns to the race_session_events table if they don't exist yet."""
    result = await conn.execute(text("PRAGMA table_info(race_session_events)"))
    existing = {row[1] for row in result.fetchall()}
    for col_name, col_type in _RACE_SESSION_EVENT_NEW_COLUMNS:
        if col_name not in existing:
            await conn.execute(
                text(
                    f"ALTER TABLE race_session_events ADD COLUMN {col_name} {col_type}"
                )
            )


async def _migrate_race_plans(conn) -> None:
    """Create race_plans table if it doesn't exist yet."""
    await conn.execute(
        text("""
        CREATE TABLE IF NOT EXISTS race_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            race_date TEXT,
            race_hour INTEGER DEFAULT 9,
            target_time TEXT,
            target_time_s REAL,
            strategy TEXT DEFAULT 'even',
            pacer_pace TEXT,
            drop_at_km REAL,
            weather_temp_c REAL,
            weather_humidity_pct REAL,
            weather_wind_ms REAL,
            weather_wind_dir_deg REAL,
            weather_source TEXT,
            splits_json TEXT,
            activity_id INTEGER,
            created_at DATETIME,
            updated_at DATETIME
        )
        """)
    )


async def _migrate_activity_calibrations(conn) -> None:
    """Create activity_calibrations table if it doesn't exist yet."""
    await conn.execute(
        text("""
        CREATE TABLE IF NOT EXISTS activity_calibrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER NOT NULL,
            summary_json TEXT NOT NULL,
            streams_json TEXT NOT NULL,
            race_result_json TEXT NOT NULL,
            created_at DATETIME,
            updated_at DATETIME,
            CONSTRAINT uq_activity_calibrations_activity_id UNIQUE (activity_id)
        )
        """)
    )


async def _ensure_schema_version_table(conn) -> None:
    """Create the schema_version key/value table used to gate one-shot migrations."""
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "key TEXT PRIMARY KEY, "
            "value TEXT, "
            "applied_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
    )


async def _has_migration_run(conn, key: str) -> bool:
    result = await conn.execute(
        text("SELECT 1 FROM schema_version WHERE key = :k"), {"k": key}
    )
    return result.scalar_one_or_none() is not None


async def _mark_migration_run(conn, key: str) -> None:
    await conn.execute(
        text("INSERT OR IGNORE INTO schema_version (key, value) VALUES (:k, :v)"),
        {"k": key, "v": "1"},
    )


async def _migrate_workout_activity_links(conn) -> None:
    """Create workout_activity_links table and migrate any existing Workout.activity_id data.

    The data backfill is one-shot: gated on a row in `schema_version` so that
    after the first successful run we skip the SELECT/INSERT loop entirely.
    """
    # Create table (Base.metadata.create_all handles it, but we also need the data migration)
    await conn.execute(
        text("""
        CREATE TABLE IF NOT EXISTS workout_activity_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workout_id INTEGER NOT NULL,
            activity_id INTEGER NOT NULL,
            linked_at DATETIME,
            physiology_snapshot TEXT,
            compliance_score REAL,
            status TEXT DEFAULT 'completed'
        )
        """)
    )

    if await _has_migration_run(conn, "workout_activity_links_backfill"):
        return

    # Migrate existing 1:1 links from workouts.activity_id
    result = await conn.execute(
        text(
            "SELECT id, activity_id, linked_at, physiology_snapshot, compliance_score, status "
            "FROM workouts WHERE activity_id IS NOT NULL"
        )
    )
    rows = result.fetchall()
    for row in rows:
        workout_id, activity_id, linked_at, phys, comp, status = row
        existing = await conn.execute(
            text(
                "SELECT id FROM workout_activity_links "
                "WHERE workout_id = :wid AND activity_id = :aid"
            ),
            {"wid": workout_id, "aid": activity_id},
        )
        if existing.scalar_one_or_none() is None:
            await conn.execute(
                text(
                    "INSERT INTO workout_activity_links "
                    "(workout_id, activity_id, linked_at, physiology_snapshot, compliance_score, status) "
                    "VALUES (:wid, :aid, :lat, :phys, :comp, :status)"
                ),
                {
                    "wid": workout_id,
                    "aid": activity_id,
                    "lat": linked_at,
                    "phys": phys,
                    "comp": comp,
                    "status": status or "completed",
                },
            )

    await _mark_migration_run(conn, "workout_activity_links_backfill")


async def create_all_tables(engine: AsyncEngine | None = None) -> None:
    if engine is None:
        engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # schema_version gates one-shot data migrations; create it before any
        # gated migration tries to read from it.
        await _ensure_schema_version_table(conn)
        # Migrate any missing columns on pre-existing tables
        await _migrate_athlete_columns(conn)
        await _migrate_activity_columns(conn)
        await _migrate_workout_columns(conn)
        await _migrate_workout_segment_columns(conn)
        await _migrate_workout_activity_links(conn)
        await _migrate_activity_calibrations(conn)
        await _migrate_race_plans(conn)
        await _migrate_race_session_columns(conn)
        await _migrate_race_session_event_columns(conn)


def init_db() -> None:
    asyncio.run(create_all_tables())
