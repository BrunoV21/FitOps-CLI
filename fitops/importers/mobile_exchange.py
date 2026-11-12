from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy import delete, select

from fitops.analytics.athlete_settings import AthleteSettings
from fitops.analytics.training_load import persist_training_load_snapshot
from fitops.analytics.vo2max import estimate_vo2max_from_stream_dict
from fitops.config.settings import get_settings
from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.models.mobile_activity_origin import MobileActivityOrigin
from fitops.db.session import get_async_session
from fitops.importers.activity_files import ActivityFileError

MAX_MOBILE_FILE_BYTES = 10 * 1024 * 1024
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MobileSample(_StrictModel):
    time_seconds: Annotated[Number, Field(ge=0, le=604800)]
    heartrate_bpm: Annotated[Number, Field(ge=25, le=250)] | None
    distance_m: Annotated[Number, Field(ge=0, le=2_000_000)] | None
    speed_m_per_second: Annotated[Number, Field(ge=0, le=100)] | None


class MobileActivity(_StrictModel):
    id: Annotated[str, Field(min_length=1, max_length=1024)]
    provider: Literal["file", "huawei"]
    provider_account_id: Annotated[str, Field(min_length=1, max_length=200)]
    provider_activity_id: Annotated[str, Field(min_length=1, max_length=512)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    sport: Literal["Run", "Ride", "Walk", "Other"]
    start_date: AwareDatetime
    duration_seconds: Annotated[Number, Field(gt=0, le=604800)]
    distance_m: Annotated[Number, Field(ge=0, le=2_000_000)]
    samples: Annotated[list[MobileSample], Field(max_length=100_000)]

    @field_validator("start_date", mode="before")
    @classmethod
    def iso_timestamp(cls, value):
        if not isinstance(value, str):
            raise ValueError(
                "Activity timestamps must be ISO-8601 strings with a timezone."
            )
        return value

    @model_validator(mode="after")
    def chronological_samples(self):
        previous = -1.0
        for sample in self.samples:
            if (
                sample.time_seconds <= previous
                or sample.time_seconds > self.duration_seconds
            ):
                raise ValueError(
                    "Samples must be chronological, unique, and within the activity duration."
                )
            previous = sample.time_seconds
        if not self.name.strip():
            raise ValueError("Activity name cannot be blank.")
        return self


class MobileExchange(_StrictModel):
    format: Literal["fitops.activities"]
    version: Literal[1]
    exported_at: AwareDatetime
    activities: Annotated[list[MobileActivity], Field(min_length=1, max_length=100)]

    @field_validator("exported_at", mode="before")
    @classmethod
    def iso_timestamp(cls, value):
        if not isinstance(value, str):
            raise ValueError(
                "Export timestamps must be ISO-8601 strings with a timezone."
            )
        return value

    @model_validator(mode="after")
    def unique_identities(self):
        identities = [
            (a.provider, a.provider_account_id, a.provider_activity_id)
            for a in self.activities
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("The export contains repeated source identities.")
        return self


@dataclass
class MobileImportResult:
    activities: list[Activity]
    origins: list[MobileActivityOrigin]
    created_count: int
    updated_count: int


def parse_mobile_exchange(data: bytes) -> MobileExchange:
    if not data:
        raise ActivityFileError("The mobile export is empty.", code="empty_file")
    if len(data) > MAX_MOBILE_FILE_BYTES:
        raise ActivityFileError(
            "Mobile exports must be no larger than 10 MiB.", code="file_too_large"
        )
    try:
        # Reject JSON constants such as NaN and avoid treating true as version 1.
        raw = json.loads(
            data, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))
        )
        if not isinstance(raw, dict) or type(raw.get("version")) is not int:
            raise ValueError("version must be an integer")
        return MobileExchange.model_validate(raw)
    except (ValidationError, ValueError, UnicodeError, RecursionError) as exc:
        raise ActivityFileError(
            "Choose a valid FitOps Mobile version 1 activity export. "
            "Check timestamps, units, sample order, and required fields.",
            code="invalid_mobile_export",
        ) from exc


def _streams(record: MobileActivity) -> dict[str, list]:
    samples = record.samples
    result = {"time": [s.time_seconds for s in samples]}
    normalized_speed: list[float | None] = []
    for index, sample in enumerate(samples):
        speed = sample.speed_m_per_second
        if index + 1 < len(samples):
            next_sample = samples[index + 1]
            seconds = next_sample.time_seconds - sample.time_seconds
            if not 0 < seconds <= 30:
                # The desktop segment estimator consumes forward intervals.
                # Mask gaps here without altering any source sample values.
                normalized_speed.append(None)
                continue
            if (
                speed is None
                and sample.distance_m is not None
                and next_sample.distance_m is not None
            ):
                delta = next_sample.distance_m - sample.distance_m
                if delta >= 0 and delta / seconds <= 100:
                    speed = delta / seconds
        normalized_speed.append(speed)

    if samples:
        # Keep the exact raw speed field separate from the derived/gap-masked
        # canonical stream, including nulls when TCX supplied only distance.
        result["source_velocity_m_per_second"] = [s.speed_m_per_second for s in samples]
    for key, values in (
        ("heartrate", [s.heartrate_bpm for s in samples]),
        ("distance", [s.distance_m for s in samples]),
        ("velocity_smooth", normalized_speed),
    ):
        if any(value is not None for value in values):
            result[key] = values
    return result if samples else {}


def _measured_hr(record: MobileActivity) -> tuple[float | None, int | None]:
    weighted = seconds = 0.0
    for sample, next_sample in zip(record.samples, record.samples[1:], strict=False):
        delta = next_sample.time_seconds - sample.time_seconds
        if sample.heartrate_bpm is not None and 0 < delta <= 30:
            weighted += sample.heartrate_bpm * delta
            seconds += delta
    valid = [s.heartrate_bpm for s in record.samples if s.heartrate_bpm is not None]
    return (
        weighted / seconds if seconds else None,
        round(max(valid)) if valid else None,
    )


async def import_mobile_bytes(
    data: bytes, *, athlete_id: int | None = None
) -> MobileImportResult:
    exchange = parse_mobile_exchange(data)
    local_athlete_id = athlete_id or get_settings().active_athlete_id
    if local_athlete_id is None:
        raise ActivityFileError(
            "Create an offline athlete profile before importing activities.",
            code="offline_profile_required",
        )

    activities: list[Activity] = []
    origins: list[MobileActivityOrigin] = []
    created = updated = 0
    athlete_settings = AthleteSettings()
    # One transaction: validation failures never partially import a batch.
    async with get_async_session() as session:
        for record in exchange.activities:
            origin = (
                await session.execute(
                    select(MobileActivityOrigin).where(
                        MobileActivityOrigin.athlete_id == local_athlete_id,
                        MobileActivityOrigin.provider == record.provider,
                        MobileActivityOrigin.provider_account_id
                        == record.provider_account_id,
                        MobileActivityOrigin.provider_activity_id
                        == record.provider_activity_id,
                    )
                )
            ).scalar_one_or_none()
            activity = (
                await session.get(Activity, origin.activity_id) if origin else None
            )
            if activity is None:
                activity = Activity(
                    athlete_id=local_athlete_id,
                    strava_id=None,
                    origin="fitops-mobile",
                    name=record.name.strip(),
                    sport_type=record.sport,
                )
                session.add(activity)
                await session.flush()
                created += 1
            else:
                updated += 1
            activity.name = record.name.strip()
            activity.sport_type = record.sport
            activity.start_date = record.start_date.astimezone(UTC)
            activity.start_date_local = record.start_date
            activity.timezone = str(record.start_date.tzinfo)
            activity.distance_m = record.distance_m
            activity.elapsed_time_s = round(record.duration_seconds)
            # The exchange has elapsed duration, not an independently measured moving duration.
            activity.moving_time_s = None
            activity.average_speed_ms = record.distance_m / record.duration_seconds
            activity.average_heartrate, activity.max_heartrate = _measured_hr(record)
            streams = _streams(record)
            speeds = [
                speed
                for speed in streams.get("velocity_smooth", [])
                if speed is not None
            ]
            activity.max_speed_ms = max(speeds) if speeds else None
            activity.device_name = "FitOps Mobile"
            activity.detail_fetched = True
            activity.streams_fetched = bool(record.samples)
            await session.execute(
                delete(ActivityStream).where(ActivityStream.activity_id == activity.id)
            )
            for kind, values in streams.items():
                session.add(
                    ActivityStream.from_strava_stream(activity.id, kind, values)
                )
            # This format does not convey moving time or calibration. Do not
            # fabricate moving time or stress scores from desktop defaults.
            activity.aerobic_score = None
            activity.anaerobic_score = None
            activity.training_stress_score = None
            estimate = estimate_vo2max_from_stream_dict(
                activity, streams, athlete_settings.lthr, athlete_settings.max_hr
            )
            activity.vo2max_estimate = estimate.estimate if estimate else None
            if origin is None:
                origin = MobileActivityOrigin(
                    activity_id=activity.id,
                    athlete_id=local_athlete_id,
                    provider=record.provider,
                    provider_account_id=record.provider_account_id,
                    provider_activity_id=record.provider_activity_id,
                    exported_at=exchange.exported_at,
                )
                session.add(origin)
            else:
                origin.activity_id = activity.id
                origin.exported_at = exchange.exported_at
                origin.imported_at = datetime.now(UTC)
            activities.append(activity)
            origins.append(origin)
        await session.flush()
    # Explicit import is a write path; snapshots are persisted once per batch.
    await persist_training_load_snapshot(local_athlete_id)
    return MobileImportResult(activities, origins, created, updated)


async def import_mobile_file(path: str | Path) -> MobileImportResult:
    source = Path(path).expanduser()
    if not source.is_file():
        raise ActivityFileError(
            f"Mobile export not found: {source}", code="file_not_found"
        )
    if source.stat().st_size > MAX_MOBILE_FILE_BYTES:
        raise ActivityFileError(
            "Mobile exports must be no larger than 10 MiB.", code="file_too_large"
        )
    return await import_mobile_bytes(source.read_bytes())


def mobile_import_payload(result: MobileImportResult) -> dict:
    """One shared response shape for CLI agents and dashboard rendering."""
    from fitops.output.formatter import format_activity_row

    records = []
    for activity, origin in zip(result.activities, result.origins, strict=True):
        row = format_activity_row(
            {
                column.name: getattr(activity, column.name)
                for column in activity.__table__.columns
            }
        )
        row["source_identity"] = {
            "provider": origin.provider,
            "provider_account_id": origin.provider_account_id,
            "provider_activity_id": origin.provider_activity_id,
        }
        records.append(row)
    return {
        "activities": records,
        "import": {
            "created_count": result.created_count,
            "updated_count": result.updated_count,
        },
        "publication": {"requested": False, "status": "not_requested"},
        "data_availability": {
            "streams_imported": any(a.streams_fetched for a in result.activities),
            "calibration_transferred": False,
            "moving_time_available": False,
            "metrics": "computed_where_supported_using_desktop_settings",
        },
    }
