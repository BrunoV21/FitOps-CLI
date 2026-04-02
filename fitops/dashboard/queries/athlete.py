from __future__ import annotations

from sqlalchemy import select

from fitops.db.models.athlete import Athlete
from fitops.db.session import get_async_session


async def get_athlete(athlete_id: int) -> Athlete | None:
    async with get_async_session() as session:
        result = await session.execute(
            select(Athlete).where(Athlete.strava_id == athlete_id)
        )
        return result.scalar_one_or_none()
