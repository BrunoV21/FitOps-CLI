"""Profile-related dashboard queries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from fitops.db.models.activity import Activity
from fitops.db.models.athlete import Athlete
from fitops.db.session import get_async_session


async def get_athlete(athlete_id: int) -> Athlete | None:
    async with get_async_session() as session:
        result = await session.execute(
            select(Athlete).where(Athlete.strava_id == athlete_id)
        )
        return result.scalar_one_or_none()


async def get_equipment_with_stats(athlete_id: int) -> list[dict]:
    """Return shoes and bikes with local activity distance/count stats."""
    async with get_async_session() as session:
        ath_result = await session.execute(
            select(Athlete).where(Athlete.strava_id == athlete_id)
        )
        athlete = ath_result.scalar_one_or_none()
        if athlete is None:
            return []

        gear_result = await session.execute(
            select(
                Activity.gear_id,
                func.count(Activity.id).label("count"),
                func.sum(Activity.distance_m).label("total_m"),
            )
            .where(
                Activity.athlete_id == athlete_id,
                Activity.gear_id.isnot(None),
            )
            .group_by(Activity.gear_id)
        )
        gear_stats = {
            row.gear_id: {
                "activity_count": row.count,
                "distance_m": row.total_m or 0,
            }
            for row in gear_result.fetchall()
        }

    items = []
    for shoe in athlete.shoes:
        gid = shoe.get("id")
        stats = gear_stats.get(gid, {})
        items.append(
            {
                "gear_id": gid,
                "name": shoe.get("name") or "Unnamed shoe",
                "type": "shoes",
                "strava_distance_km": round(shoe.get("distance_m", 0) / 1000, 1),
                "local_distance_km": round(stats.get("distance_m", 0) / 1000, 1),
                "activity_count": stats.get("activity_count", 0),
                "primary": shoe.get("primary", False),
            }
        )
    for bike in athlete.bikes:
        gid = bike.get("id")
        stats = gear_stats.get(gid, {})
        items.append(
            {
                "gear_id": gid,
                "name": bike.get("name") or "Unnamed bike",
                "type": "bike",
                "strava_distance_km": round(bike.get("distance_m", 0) / 1000, 1),
                "local_distance_km": round(stats.get("distance_m", 0) / 1000, 1),
                "activity_count": stats.get("activity_count", 0),
                "primary": bike.get("primary", False),
            }
        )
    return items


async def get_activity_heatmap_data(
    athlete_id: int, since: datetime | None = None, weeks: int = 53
) -> list[dict]:
    """Return per-day duration totals and per-activity detail for the period since `since`."""
    cutoff = since if since is not None else datetime.now(UTC) - timedelta(weeks=weeks)
    async with get_async_session() as session:
        result = await session.execute(
            select(
                Activity.strava_id,
                Activity.start_date_local,
                Activity.name,
                Activity.sport_type,
                Activity.distance_m,
                Activity.moving_time_s,
            )
            .where(
                Activity.athlete_id == athlete_id,
                Activity.start_date >= cutoff,
            )
            .order_by(Activity.start_date_local)
        )
        rows = result.all()

    day_map: dict[str, dict] = {}
    for row in rows:
        dt = row.start_date_local
        if dt is None:
            continue
        key = dt.strftime("%Y-%m-%d")
        if key not in day_map:
            day_map[key] = {
                "date": key,
                "count": 0,
                "duration_s": 0,
                "distance_km": 0.0,
                "activities": [],
            }
        day_map[key]["count"] += 1
        day_map[key]["duration_s"] += row.moving_time_s or 0
        day_map[key]["distance_km"] += (row.distance_m or 0) / 1000
        day_map[key]["activities"].append(
            {
                "strava_id": row.strava_id,
                "name": row.name or row.sport_type or "Activity",
                "sport_type": row.sport_type or "",
                "distance_km": round((row.distance_m or 0) / 1000, 2),
                "duration_s": row.moving_time_s or 0,
            }
        )

    for v in day_map.values():
        v["distance_km"] = round(v["distance_km"], 1)

    return list(day_map.values())
