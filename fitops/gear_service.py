from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import select

from fitops.config.settings import get_settings
from fitops.db.models.athlete import Athlete
from fitops.db.session import get_async_session


class GearError(ValueError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def _normalize_gear_type(gear_type: str) -> str:
    normalized = gear_type.strip().lower()
    if normalized in {"shoe", "shoes"}:
        return "shoes"
    if normalized in {"bike", "bikes"}:
        return "bike"
    raise GearError("Gear type must be 'shoes' or 'bike'.", code="invalid_gear_type")


def _gear_items(athlete: Athlete) -> list[dict]:
    return [
        *({**item, "type": "shoes"} for item in athlete.shoes),
        *({**item, "type": "bike"} for item in athlete.bikes),
    ]


async def add_local_gear(
    athlete_id: int,
    *,
    name: str,
    gear_type: str,
    primary: bool = False,
    strava_connected: bool | None = None,
) -> dict:
    """Add gear to an offline athlete profile.

    Strava-connected profiles remain provider-owned so a later sync cannot create
    conflicting local equipment entries.
    """
    connected = (
        get_settings().is_authenticated
        if strava_connected is None
        else strava_connected
    )
    if connected:
        raise GearError(
            "Gear is managed by Strava while this profile is connected.",
            code="strava_connected",
        )

    cleaned_name = " ".join(name.split())
    if not cleaned_name:
        raise GearError("Gear name is required.", code="gear_name_required")
    normalized_type = _normalize_gear_type(gear_type)

    async with get_async_session() as session:
        athlete = (
            await session.execute(select(Athlete).where(Athlete.id == athlete_id))
        ).scalar_one_or_none()
        if athlete is None:
            raise GearError("Athlete profile was not found.", code="athlete_not_found")

        target = list(athlete.shoes if normalized_type == "shoes" else athlete.bikes)
        if primary:
            target = [{**item, "primary": False} for item in target]
        item = {
            "id": f"local-{uuid4().hex}",
            "name": cleaned_name,
            "distance_m": 0,
            "primary": bool(primary),
            "source": "local",
        }
        target.append(item)
        if normalized_type == "shoes":
            athlete.shoes_json = json.dumps(target)
        else:
            athlete.bikes_json = json.dumps(target)

    return {**item, "type": normalized_type}


async def list_gear(athlete_id: int) -> list[dict]:
    async with get_async_session() as session:
        athlete = (
            await session.execute(select(Athlete).where(Athlete.id == athlete_id))
        ).scalar_one_or_none()
        return _gear_items(athlete) if athlete else []


async def resolve_gear(athlete_id: int, value: str | None) -> dict | None:
    """Resolve gear by stable ID or exact case-insensitive name."""
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    items = await list_gear(athlete_id)
    by_id = next((item for item in items if item.get("id") == cleaned), None)
    if by_id:
        return by_id
    by_name = [
        item
        for item in items
        if str(item.get("name") or "").casefold() == cleaned.casefold()
    ]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        raise GearError(
            f"More than one gear item is named '{cleaned}'; use its gear ID.",
            code="ambiguous_gear",
        )
    raise GearError(
        f"Gear '{cleaned}' was not found on the active profile.",
        code="gear_not_found",
    )


async def get_gear_lookup(athlete_id: int) -> dict[str, dict]:
    return {
        item["id"]: {"name": item.get("name"), "type": item["type"]}
        for item in await list_gear(athlete_id)
        if item.get("id")
    }
