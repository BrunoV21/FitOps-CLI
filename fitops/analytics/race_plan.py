"""Auto-association logic: match a freshly-fetched activity to a saved RacePlan."""

from __future__ import annotations

import json
import math

from sqlalchemy import select

from fitops.db.models.activity import Activity
from fitops.db.models.race_course import RaceCourse
from fitops.db.models.race_plan import RacePlan
from fitops.db.session import get_async_session

RUN_SPORT_TYPES = {
    "Run",
    "TrailRun",
    "VirtualRun",
    "Walk",
    "Hike",
}


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two lat/lon points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def sweep_unlinked_plans() -> int:
    """Scan every unlinked RacePlan against all activities already in the DB.

    Called at the end of every sync so plans created *after* their matching
    activity was already synced still get linked.  Returns the count of
    newly linked plans.
    """
    from datetime import UTC, datetime, timedelta
    from datetime import date as _date

    async with get_async_session() as session:
        plans_res = await session.execute(
            select(RacePlan).where(
                RacePlan.activity_id.is_(None),
                RacePlan.race_date.is_not(None),
            )
        )
        plans = plans_res.scalars().all()

        matched = 0
        for plan in plans:
            try:
                plan_d = _date.fromisoformat(plan.race_date)  # type: ignore[arg-type]
            except (ValueError, TypeError):
                continue

            course_res = await session.execute(
                select(RaceCourse).where(RaceCourse.id == plan.course_id)
            )
            course = course_res.scalar_one_or_none()
            if course is None or course.start_lat is None or course.start_lon is None:
                continue

            # Widen the window by 1 day on each side
            dt_low = datetime(
                (plan_d - timedelta(days=1)).year,
                (plan_d - timedelta(days=1)).month,
                (plan_d - timedelta(days=1)).day,
                tzinfo=UTC,
            )
            dt_high = datetime(
                (plan_d + timedelta(days=1)).year,
                (plan_d + timedelta(days=1)).month,
                (plan_d + timedelta(days=1)).day,
                23,
                59,
                59,
                tzinfo=UTC,
            )

            acts_res = await session.execute(
                select(Activity).where(
                    Activity.start_date >= dt_low,
                    Activity.start_date <= dt_high,
                )
            )
            candidates = acts_res.scalars().all()

            for act in candidates:
                if (act.sport_type or "") not in RUN_SPORT_TYPES:
                    continue
                if not act.start_latlng:
                    continue
                # Distance check: activity must be within ±20% of course length
                if (
                    act.distance_m is not None
                    and course.total_distance_m > 0
                    and abs(act.distance_m - course.total_distance_m)
                    / course.total_distance_m
                    > 0.20
                ):
                    continue
                try:
                    coords = json.loads(act.start_latlng)
                    if not (isinstance(coords, list) and len(coords) == 2):
                        continue
                    act_lat, act_lon = float(coords[0]), float(coords[1])
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

                if (
                    _haversine_m(act_lat, act_lon, course.start_lat, course.start_lon)
                    < 500.0
                ):
                    plan.activity_id = act.id
                    plan.updated_at = datetime.now(UTC)
                    matched += 1
                    break

    return matched


async def match_activity_to_plans(activity_internal_id: int) -> int | None:
    """Try to match *activity_internal_id* to an unlinked RacePlan.

    Matching criteria (all must pass):
    1. Activity sport_type is in RUN_SPORT_TYPES.
    2. Activity start_date is within ±1 calendar day of plan.race_date.
    3. Haversine distance between activity.start_latlng and course start < 500 m.
    4. Plan has no activity_id already set.

    Returns the matched plan_id on success, None otherwise.
    """
    async with get_async_session() as session:
        act_res = await session.execute(
            select(Activity).where(Activity.id == activity_internal_id)
        )
        act = act_res.scalar_one_or_none()
        if act is None:
            return None

        # Must be a running-type sport
        if (act.sport_type or "") not in RUN_SPORT_TYPES:
            return None

        # Parse activity coordinates
        if not act.start_latlng:
            return None
        try:
            coords = json.loads(act.start_latlng)
            if not (isinstance(coords, list) and len(coords) == 2):
                return None
            act_lat, act_lon = float(coords[0]), float(coords[1])
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

        # Activity date string (YYYY-MM-DD)
        if not act.start_date:
            return None
        act_date_str = act.start_date.strftime("%Y-%m-%d")

        # Load all unlinked plans that have a race_date set
        plans_res = await session.execute(
            select(RacePlan).where(
                RacePlan.activity_id.is_(None),
                RacePlan.race_date.is_not(None),
            )
        )
        plans = plans_res.scalars().all()

        for plan in plans:
            # Date check: within ±1 day
            try:
                from datetime import date

                plan_d = date.fromisoformat(plan.race_date)  # type: ignore[arg-type]
                act_d = date.fromisoformat(act_date_str)
                if abs((act_d - plan_d).days) > 1:
                    continue
            except (ValueError, TypeError):
                continue

            # Load course to get start coords
            course_res = await session.execute(
                select(RaceCourse).where(RaceCourse.id == plan.course_id)
            )
            course = course_res.scalar_one_or_none()
            if course is None or course.start_lat is None or course.start_lon is None:
                continue

            # Distance check: activity must be within ±20% of course length
            if (
                act.distance_m is not None
                and course.total_distance_m > 0
                and abs(act.distance_m - course.total_distance_m)
                / course.total_distance_m
                > 0.20
            ):
                continue

            dist_m = _haversine_m(act_lat, act_lon, course.start_lat, course.start_lon)
            if dist_m >= 500.0:
                continue

            # Match found — persist and return
            plan.activity_id = activity_internal_id
            from datetime import UTC, datetime

            plan.updated_at = datetime.now(UTC)
            return plan.id

    return None
