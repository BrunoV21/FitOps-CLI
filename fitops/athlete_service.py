from __future__ import annotations

from sqlalchemy import select

from fitops.config.settings import get_settings
from fitops.db.models.athlete import Athlete
from fitops.db.session import get_async_session


async def create_local_athlete(
    name: str,
    *,
    weight_kg: float | None = None,
    birthday: str | None = None,
) -> tuple[Athlete, bool]:
    """Create and activate an offline athlete, or return the active one."""
    settings = get_settings()
    if settings.active_athlete_id is not None:
        async with get_async_session() as session:
            existing = (
                await session.execute(
                    select(Athlete).where(Athlete.id == settings.active_athlete_id)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing, False

    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValueError("Athlete name is required.")
    first, _, last = cleaned.partition(" ")
    async with get_async_session() as session:
        athlete = Athlete(
            strava_id=None,
            source="local",
            firstname=first,
            lastname=last or None,
            weight_kg=weight_kg,
            birthday=birthday,
        )
        session.add(athlete)
        await session.flush()
        athlete_id = athlete.id
    settings.save_active_athlete_id(athlete_id)
    return athlete, True
