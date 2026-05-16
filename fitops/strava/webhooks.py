"""Shared Strava webhook parsing and processing."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update

from fitops.analytics.athlete_settings import AthleteSettings, get_athlete_settings
from fitops.analytics.training_scores import (
    compute_aerobic_score,
    compute_anaerobic_score,
)
from fitops.analytics.weather_pace import pace_heat_factor, wbgt_approx
from fitops.backup.event_sync import trigger_async
from fitops.config.settings import get_settings
from fitops.config.state import get_sync_state
from fitops.dashboard.queries.weather import upsert_activity_weather
from fitops.db.models.activity import Activity
from fitops.db.models.activity_calibration import ActivityCalibration
from fitops.db.models.activity_laps import ActivityLap
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.models.activity_weather import ActivityWeather
from fitops.db.models.analytics_snapshot import AnalyticsSnapshot
from fitops.db.models.note import Note
from fitops.db.models.race_plan import RacePlan
from fitops.db.models.race_session import (
    RaceSession,
    RaceSessionAthlete,
    RaceSessionEvent,
    RaceSessionGap,
    RaceSessionSegment,
)
from fitops.db.models.strava_webhook_event import StravaWebhookEvent
from fitops.db.models.workout import Workout
from fitops.db.models.workout_activity_link import WorkoutActivityLink
from fitops.db.models.workout_segment import WorkoutSegment
from fitops.db.session import get_async_session
from fitops.strava.client import StravaClient
from fitops.strava.webhook_config import get_webhook_config
from fitops.utils.logging import get_logger
from fitops.weather.client import fetch_activity_weather, fetch_forecast_weather

logger = get_logger(__name__)

_process_lock = asyncio.Lock()


@dataclass(frozen=True)
class WebhookProcessResult:
    status: str
    action: str
    object_type: str
    object_id: int
    aspect_type: str
    details: dict


def verify_challenge(verify_token: str | None, challenge: str | None) -> dict:
    cfg = get_webhook_config()
    expected = (cfg or {}).get("verify_token")
    if not expected:
        raise ValueError("Strava webhook is not configured.")
    if not verify_token or verify_token != expected:
        raise ValueError("Invalid Strava webhook verify token.")
    if not challenge:
        raise ValueError("Missing hub.challenge.")
    return {"hub.challenge": challenge}


def _event_key(payload: dict) -> dict:
    return {
        "subscription_id": payload.get("subscription_id"),
        "object_type": str(payload.get("object_type") or ""),
        "object_id": int(payload.get("object_id") or 0),
        "aspect_type": str(payload.get("aspect_type") or ""),
        "event_time": payload.get("event_time"),
    }


async def record_event(payload: dict) -> tuple[int, bool]:
    key = _event_key(payload)
    if not key["object_type"] or not key["object_id"] or not key["aspect_type"]:
        raise ValueError(
            "Webhook payload missing object_type, object_id or aspect_type."
        )

    async with get_async_session() as session:
        stmt = select(StravaWebhookEvent).where(
            StravaWebhookEvent.subscription_id == key["subscription_id"],
            StravaWebhookEvent.object_type == key["object_type"],
            StravaWebhookEvent.object_id == key["object_id"],
            StravaWebhookEvent.aspect_type == key["aspect_type"],
            StravaWebhookEvent.event_time == key["event_time"],
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing.id, False

        event = StravaWebhookEvent(
            subscription_id=key["subscription_id"],
            object_type=key["object_type"],
            object_id=key["object_id"],
            aspect_type=key["aspect_type"],
            owner_id=payload.get("owner_id"),
            event_time=key["event_time"],
            updates_json=json.dumps(payload.get("updates") or {}),
            status="pending",
        )
        session.add(event)
        await session.flush()
        return event.id, True


async def process_webhook_payload(payload: dict) -> WebhookProcessResult:
    event_id, created = await record_event(payload)
    if not created:
        async with get_async_session() as session:
            row = (
                await session.execute(
                    select(StravaWebhookEvent).where(StravaWebhookEvent.id == event_id)
                )
            ).scalar_one()
        return WebhookProcessResult(
            status="duplicate",
            action="ignored",
            object_type=row.object_type,
            object_id=row.object_id,
            aspect_type=row.aspect_type,
            details={"event_id": event_id},
        )
    return await process_event(event_id)


async def process_event(event_id: int) -> WebhookProcessResult:
    async with _process_lock:
        async with get_async_session() as session:
            event = (
                await session.execute(
                    select(StravaWebhookEvent).where(StravaWebhookEvent.id == event_id)
                )
            ).scalar_one()
            event.status = "processing"
            event.error = None

        try:
            details = await _dispatch_event(event_id)
        except Exception as exc:
            async with get_async_session() as session:
                event = (
                    await session.execute(
                        select(StravaWebhookEvent).where(
                            StravaWebhookEvent.id == event_id
                        )
                    )
                ).scalar_one()
                event.status = "failed"
                event.error = str(exc)
                event.processed_at = datetime.now(UTC)
            raise

        async with get_async_session() as session:
            event = (
                await session.execute(
                    select(StravaWebhookEvent).where(StravaWebhookEvent.id == event_id)
                )
            ).scalar_one()
            event.status = details.get("status", "processed")
            event.processed_at = datetime.now(UTC)
            row = event.to_dict()

        return WebhookProcessResult(
            status=row["status"],
            action=details.get("action", row["aspect_type"]),
            object_type=row["object_type"],
            object_id=row["object_id"],
            aspect_type=row["aspect_type"],
            details=details,
        )


async def _dispatch_event(event_id: int) -> dict:
    async with get_async_session() as session:
        event = (
            await session.execute(
                select(StravaWebhookEvent).where(StravaWebhookEvent.id == event_id)
            )
        ).scalar_one()
        payload = event.to_dict()

    if payload["object_type"] == "activity":
        if payload["aspect_type"] in {"create", "update"}:
            return await sync_activity_from_strava(
                payload["object_id"], sync_type=f"webhook_{payload['aspect_type']}"
            )
        if payload["aspect_type"] == "delete":
            return await delete_activity_by_strava_id(payload["object_id"])

    if (
        payload["object_type"] == "athlete"
        and payload["updates"].get("authorized") == "false"
    ):
        return {"status": "ignored", "action": "athlete_deauthorized"}

    return {"status": "ignored", "action": "unsupported_event"}


async def sync_activity_from_strava(strava_id: int, sync_type: str = "webhook") -> dict:
    settings = get_settings()
    settings.require_auth()
    client = StravaClient()
    data = await client.get_activity(strava_id)

    athlete_id = settings.athlete_id
    if athlete_id is None:
        athlete = await client.get_authenticated_athlete()
        athlete_id = int(athlete["id"])

    athlete_settings = AthleteSettings()
    created = updated = 0
    internal_id: int | None = None

    async with get_async_session() as session:
        existing = (
            await session.execute(
                select(Activity).where(Activity.strava_id == strava_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            activity = Activity.from_strava_data(data, athlete_id)
            activity.aerobic_score = compute_aerobic_score(activity, athlete_settings)
            activity.anaerobic_score = compute_anaerobic_score(
                activity, athlete_settings
            )
            session.add(activity)
            await session.flush()
            internal_id = activity.id
            created = 1
        else:
            existing.update_from_strava_data(data)
            existing.aerobic_score = compute_aerobic_score(existing, athlete_settings)
            existing.anaerobic_score = compute_anaerobic_score(
                existing, athlete_settings
            )
            internal_id = existing.id
            updated = 1

    streams = (
        await fetch_streams_for_activities([internal_id], [strava_id])
        if internal_id
        else {}
    )
    weather = await fetch_weather_for_strava_ids([strava_id])

    try:
        from fitops.analytics.stamp import auto_stamp_new_activities

        await auto_stamp_new_activities([strava_id])
    except Exception:
        logger.warning("webhook: auto-stamp failed for activity %s", strava_id)

    plans_linked = 0
    try:
        from fitops.analytics.race_plan import sweep_unlinked_plans

        plans_linked = await sweep_unlinked_plans()
    except Exception:
        pass

    state = get_sync_state()
    state.update_after_sync(
        sync_type=sync_type,
        activities_created=created,
        activities_updated=updated,
        duration_s=0.0,
    )

    try:
        from fitops.analytics.training_load import persist_training_load_snapshot

        await persist_training_load_snapshot(athlete_id)
    except Exception:
        pass

    await trigger_async()
    return {
        "status": "processed",
        "action": sync_type,
        "activities_created": created,
        "activities_updated": updated,
        "streams": streams,
        "weather": weather,
        "plans_linked": plans_linked,
    }


async def fetch_streams_for_activities(
    activity_ids: list[int], strava_ids: list[int], force: bool = False
) -> dict:
    client = StravaClient()
    fetched = 0
    errors = 0
    athlete_settings = get_athlete_settings()

    for internal_id, strava_id in zip(activity_ids, strava_ids, strict=False):
        try:
            if force:
                async with get_async_session() as session:
                    await session.execute(
                        sa_delete(ActivityStream).where(
                            ActivityStream.activity_id == internal_id
                        )
                    )
            stream_data = await client.get_activity_streams(strava_id)
            flat_streams = {
                st: (so.get("data", []) if isinstance(so, dict) else so)
                for st, so in stream_data.items()
            }
            if (
                "gap_pace" not in flat_streams
                and "grade_adjusted_speed" in flat_streams
            ):
                flat_streams["gap_pace"] = [
                    round(1000.0 / v, 2) if v and v > 0.1 else None
                    for v in flat_streams["grade_adjusted_speed"]
                ]

            async with get_async_session() as session:
                for stream_type, stream_obj in stream_data.items():
                    data_list = (
                        stream_obj.get("data", [])
                        if isinstance(stream_obj, dict)
                        else stream_obj
                    )
                    if not force:
                        existing = await session.execute(
                            select(ActivityStream).where(
                                ActivityStream.activity_id == internal_id,
                                ActivityStream.stream_type == stream_type,
                            )
                        )
                        if existing.scalar_one_or_none() is not None:
                            continue
                    session.add(
                        ActivityStream.from_strava_stream(
                            internal_id, stream_type, data_list
                        )
                    )
                activity = (
                    await session.execute(
                        select(Activity).where(Activity.id == internal_id)
                    )
                ).scalar_one_or_none()
                if activity:
                    activity.streams_fetched = True
                    from fitops.analytics.vo2max import estimate_vo2max_from_stream_dict

                    vo2max = estimate_vo2max_from_stream_dict(
                        activity,
                        stream_data,
                        athlete_settings.lthr,
                        athlete_settings.max_hr,
                    )
                    if vo2max is not None:
                        activity.vo2max_estimate = vo2max.estimate
                    if athlete_settings.weight_kg:
                        from fitops.analytics.running_power import (
                            RUN_SPORT_TYPES,
                            persist_power_for_activity,
                        )

                        if activity.sport_type in RUN_SPORT_TYPES:
                            await persist_power_for_activity(
                                session,
                                internal_id,
                                activity,
                                flat_streams,
                                athlete_settings.weight_kg,
                            )
            try:
                from fitops.analytics.race_plan import match_activity_to_plans

                await match_activity_to_plans(internal_id)
            except Exception:
                pass
            fetched += 1
        except Exception as exc:
            logger.warning("webhook: stream fetch failed for %s: %s", strava_id, exc)
            errors += 1
    return {"streams_fetched": fetched, "errors": errors, "strava_ids": strava_ids}


async def fetch_weather_for_strava_ids(strava_ids: list[int]) -> dict:
    fetched = errors = 0
    async with get_async_session() as session:
        result = await session.execute(
            select(Activity).where(Activity.strava_id.in_(strava_ids))
        )
        activities = result.scalars().all()

    for activity in activities:
        if not activity.start_latlng or not activity.start_date:
            continue
        try:
            coords = json.loads(activity.start_latlng)
            if not (isinstance(coords, list) and len(coords) == 2):
                continue
            lat, lng = float(coords[0]), float(coords[1])
            weather = await fetch_activity_weather(lat, lng, activity.start_date)
            if weather is None:
                weather = await fetch_forecast_weather(
                    lat,
                    lng,
                    activity.start_date.strftime("%Y-%m-%d"),
                    activity.start_date.hour,
                )
            if weather:
                tc = weather.get("temperature_c")
                hum = weather.get("humidity_pct")
                if tc is not None and hum is not None:
                    weather["wbgt_c"] = round(wbgt_approx(tc, hum), 2)
                    weather["pace_heat_factor"] = round(pace_heat_factor(tc, hum), 4)
                await upsert_activity_weather(
                    activity.strava_id, weather, source="open-meteo"
                )
                fetched += 1
        except Exception as exc:
            logger.warning(
                "webhook: weather fetch failed for %s: %s", activity.strava_id, exc
            )
            errors += 1
    return {"weather_fetched": fetched, "weather_errors": errors}


async def delete_activity_by_strava_id(strava_id: int) -> dict:
    deleted: dict[str, int] = {}
    async with get_async_session() as session:
        activity = (
            await session.execute(
                select(Activity).where(Activity.strava_id == strava_id)
            )
        ).scalar_one_or_none()
        if activity is None:
            await session.execute(
                sa_delete(ActivityWeather).where(
                    ActivityWeather.activity_id == strava_id
                )
            )
            return {"status": "processed", "action": "delete", "already_deleted": True}

        internal_id = activity.id
        statements = [
            (
                "activity_streams",
                sa_delete(ActivityStream).where(
                    ActivityStream.activity_id == internal_id
                ),
            ),
            (
                "activity_laps",
                sa_delete(ActivityLap).where(ActivityLap.activity_id == internal_id),
            ),
            (
                "activity_weather",
                sa_delete(ActivityWeather).where(
                    ActivityWeather.activity_id == strava_id
                ),
            ),
            (
                "activity_calibrations",
                sa_delete(ActivityCalibration).where(
                    ActivityCalibration.activity_id == internal_id
                ),
            ),
            (
                "workout_activity_links",
                sa_delete(WorkoutActivityLink).where(
                    WorkoutActivityLink.activity_id == internal_id
                ),
            ),
            (
                "workout_segments",
                sa_delete(WorkoutSegment).where(
                    WorkoutSegment.activity_id == internal_id
                ),
            ),
        ]
        for name, stmt in statements:
            result = await session.execute(stmt)
            deleted[name] = result.rowcount or 0

        await session.execute(
            update(Workout)
            .where(Workout.activity_id == internal_id)
            .values(activity_id=None, linked_at=None)
        )
        await session.execute(
            update(RacePlan)
            .where(RacePlan.activity_id == internal_id)
            .values(activity_id=None)
        )
        await session.execute(
            update(Note).where(Note.activity_id == strava_id).values(activity_id=None)
        )

        primary_sessions = (
            (
                await session.execute(
                    select(RaceSession.id).where(
                        RaceSession.primary_activity_id == strava_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if primary_sessions:
            for model in (
                RaceSessionAthlete,
                RaceSessionGap,
                RaceSessionEvent,
                RaceSessionSegment,
            ):
                await session.execute(
                    sa_delete(model).where(model.session_id.in_(primary_sessions))
                )
            await session.execute(
                sa_delete(RaceSession).where(RaceSession.id.in_(primary_sessions))
            )
            deleted["race_sessions"] = len(primary_sessions)

        await session.execute(
            update(RaceSessionAthlete)
            .where(RaceSessionAthlete.activity_id == strava_id)
            .values(activity_id=None)
        )

        await session.execute(sa_delete(Activity).where(Activity.id == internal_id))
        deleted["activities"] = 1

        if get_settings().athlete_id:
            await session.execute(
                sa_delete(AnalyticsSnapshot).where(
                    AnalyticsSnapshot.athlete_id == get_settings().athlete_id
                )
            )

    get_sync_state().update_after_sync(
        sync_type="webhook_delete",
        activities_created=0,
        activities_updated=0,
        duration_s=0.0,
    )
    await trigger_async()
    return {"status": "processed", "action": "delete", "deleted": deleted}


async def recent_events(limit: int = 20) -> list[dict]:
    async with get_async_session() as session:
        result = await session.execute(
            select(StravaWebhookEvent)
            .order_by(StravaWebhookEvent.received_at.desc())
            .limit(limit)
        )
        return [row.to_dict() for row in result.scalars().all()]
