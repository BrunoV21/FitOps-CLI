from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine

from fitops.db.base import Base
from fitops.db.session import get_engine

# Import all models so their tables are registered on Base.metadata
from fitops.db.models.athlete import Athlete  # noqa: F401
from fitops.db.models.activity import Activity  # noqa: F401
from fitops.db.models.activity_stream import ActivityStream  # noqa: F401
from fitops.db.models.activity_laps import ActivityLap  # noqa: F401
from fitops.db.models.workout_course import WorkoutCourse  # noqa: F401
from fitops.db.models.workout import Workout  # noqa: F401
from fitops.db.models.analytics_snapshot import AnalyticsSnapshot  # noqa: F401


async def create_all_tables(engine: AsyncEngine | None = None) -> None:
    if engine is None:
        engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def init_db() -> None:
    asyncio.run(create_all_tables())
