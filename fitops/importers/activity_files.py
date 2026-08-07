from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from sqlalchemy import select

from fitops.analytics.athlete_settings import AthleteSettings
from fitops.analytics.training_load import _estimate_tss
from fitops.analytics.training_scores import (
    compute_aerobic_score,
    compute_anaerobic_score,
)
from fitops.config.settings import get_settings
from fitops.db.models.activity import Activity
from fitops.db.models.activity_import import ActivityImport
from fitops.db.models.activity_laps import ActivityLap
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.session import get_async_session

MAX_ACTIVITY_FILE_BYTES = 25 * 1024 * 1024
RUN_TYPES = {"Run", "TrailRun", "VirtualRun", "Walk", "Hike"}


class ActivityFileError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_activity_file") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class NormalizedLap:
    index: int
    name: str
    elapsed_time_s: int | None = None
    moving_time_s: int | None = None
    distance_m: float | None = None
    average_speed_ms: float | None = None
    average_heartrate: float | None = None
    max_heartrate: int | None = None
    average_watts: float | None = None


@dataclass
class NormalizedActivity:
    name: str
    sport_type: str
    sport_inference_source: str
    sport_inference_confidence: str
    start_date: datetime
    start_date_local: datetime
    distance_m: float
    moving_time_s: int
    elapsed_time_s: int
    total_elevation_gain_m: float
    average_speed_ms: float | None
    max_speed_ms: float | None
    average_heartrate: float | None
    max_heartrate: int | None
    average_cadence: float | None
    average_watts: float | None
    max_watts: int | None
    calories: int | None
    start_latlng: list[float] | None
    end_latlng: list[float] | None
    device_name: str
    streams: dict[str, list[Any]] = field(default_factory=dict)
    laps: list[NormalizedLap] = field(default_factory=list)


@dataclass
class ActivityImportResult:
    activity: Activity
    import_record: ActivityImport
    created: bool
    match_type: str
    sport_inference_source: str
    sport_inference_confidence: str


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    wanted = name.lower()
    return [item for item in element.iter() if _local_name(item.tag) == wanted]


def _first_text(element: ET.Element, name: str) -> str | None:
    for item in element.iter():
        if _local_name(item.tag) == name.lower() and item.text:
            return item.text.strip()
    return None


def _float_text(element: ET.Element, name: str) -> float | None:
    text = _first_text(element, name)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result


def _haversine_m(a: list[float], b: list[float]) -> float:
    radius = 6_371_000.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return radius * 2 * math.asin(math.sqrt(value))


def _positive(values: list[float | None]) -> list[float]:
    return [float(value) for value in values if value is not None]


def _extension_value(element: ET.Element, names: set[str]) -> float | None:
    for child in element.iter():
        if _local_name(child.tag) in names and child.text:
            try:
                return float(child.text.strip())
            except ValueError:
                continue
    return None


def _infer_sport(
    *,
    requested: str | None,
    embedded: str | None,
    label: str,
    speeds: list[float],
) -> tuple[str, str, str]:
    if requested and requested.lower() != "auto":
        return requested, "override", "high"

    if embedded:
        embedded_lower = embedded.strip().lower()
        mapping = {
            "running": "Run",
            "run": "Run",
            "biking": "Ride",
            "cycling": "Ride",
            "bike": "Ride",
            "walking": "Walk",
            "walk": "Walk",
            "hiking": "Hike",
            "swimming": "Swim",
        }
        value = mapping.get(embedded_lower)
        if value is None:
            if "run" in embedded_lower:
                value = "Run"
            elif any(word in embedded_lower for word in ("bike", "biking", "cycle")):
                value = "Ride"
            elif "walk" in embedded_lower:
                value = "Walk"
            elif "hik" in embedded_lower:
                value = "Hike"
            elif "swim" in embedded_lower:
                value = "Swim"
        if value:
            return value, "file_metadata", "high"

    lowered = label.lower()
    keywords = (
        (("trail",), "TrailRun"),
        (("hike", "hiking"), "Hike"),
        (("walk", "walking"), "Walk"),
        (("ride", "bike", "biking", "cycle", "cycling"), "Ride"),
        (("run", "running", "jog"), "Run"),
    )
    for words, sport in keywords:
        if any(word in lowered for word in words):
            return sport, "name_keyword", "high"

    moving = [speed for speed in speeds if speed > 0.3]
    if moving:
        typical = median(moving)
        if typical < 2.2:
            return "Walk", "median_speed", "medium"
        if typical <= 5.5:
            return "Run", "median_speed", "medium"
        return "Ride", "median_speed", "medium"
    return "Run", "fallback", "low"


def _build_common(
    *,
    filename: str,
    file_name: str | None,
    requested_name: str | None,
    requested_sport: str | None,
    embedded_sport: str | None,
    times: list[datetime],
    latlng: list[list[float] | None],
    altitude: list[float | None],
    native_distance: list[float | None],
    heartrate: list[float | None],
    cadence: list[float | None],
    watts: list[float | None],
    temperature: list[float | None],
    calories: int | None,
    device_name: str,
    laps: list[NormalizedLap] | None = None,
) -> NormalizedActivity:
    if len(times) < 2:
        raise ActivityFileError(
            "An activity needs at least two timed trackpoints.",
            code="insufficient_trackpoints",
        )
    if any(times[index] <= times[index - 1] for index in range(1, len(times))):
        raise ActivityFileError(
            "Trackpoint timestamps must be strictly increasing.",
            code="non_monotonic_time",
        )

    use_native = (
        len(native_distance) == len(times)
        and all(value is not None for value in native_distance)
        and all(
            float(native_distance[index] or 0) >= float(native_distance[index - 1] or 0)
            for index in range(1, len(native_distance))
        )
    )
    distance: list[float] = []
    cumulative = 0.0
    previous_point: list[float] | None = None
    for index, point in enumerate(latlng):
        if use_native:
            value = float(native_distance[index] or 0)
        else:
            if point is not None and previous_point is not None:
                cumulative += _haversine_m(previous_point, point)
            value = cumulative
        distance.append(value)
        if point is not None:
            previous_point = point

    elapsed = [(value - times[0]).total_seconds() for value in times]
    speeds: list[float] = [0.0]
    moving: list[bool] = [False]
    moving_time = 0.0
    for index in range(1, len(times)):
        delta_t = elapsed[index] - elapsed[index - 1]
        delta_d = max(0.0, distance[index] - distance[index - 1])
        speed = delta_d / delta_t if delta_t > 0 else 0.0
        is_moving = speed > 0.3
        speeds.append(speed)
        moving.append(is_moving)
        if is_moving:
            moving_time += delta_t

    label = " ".join(part for part in (filename, file_name or "") if part)
    sport, inference_source, inference_confidence = _infer_sport(
        requested=requested_sport,
        embedded=embedded_sport,
        label=label,
        speeds=speeds,
    )
    name = requested_name or file_name or f"{sport} on {times[0].date().isoformat()}"

    elevation_gain = 0.0
    previous_altitude: float | None = None
    for value in altitude:
        if value is None:
            continue
        if previous_altitude is not None and value > previous_altitude:
            elevation_gain += value - previous_altitude
        previous_altitude = value

    elapsed_total = int(round(elapsed[-1]))
    distance_total = float(distance[-1]) if distance else 0.0
    average_speed = distance_total / moving_time if moving_time > 0 else None
    valid_hr = _positive(heartrate)
    valid_cadence = _positive(cadence)
    valid_watts = _positive(watts)
    cadence_average = sum(valid_cadence) / len(valid_cadence) if valid_cadence else None
    if sport in RUN_TYPES and cadence_average and cadence_average < 130:
        cadence_average *= 2

    streams: dict[str, list[Any]] = {
        "time": [round(value, 3) for value in elapsed],
        "distance": [round(value, 3) for value in distance],
        "velocity_smooth": [round(value, 4) for value in speeds],
        "moving": moving,
    }
    if any(point is not None for point in latlng):
        streams["latlng"] = latlng
    for key, values in (
        ("altitude", altitude),
        ("heartrate", heartrate),
        ("cadence", cadence),
        ("watts", watts),
        ("temp", temperature),
    ):
        if any(value is not None for value in values):
            streams[key] = values

    points = [point for point in latlng if point is not None]
    return NormalizedActivity(
        name=name,
        sport_type=sport,
        sport_inference_source=inference_source,
        sport_inference_confidence=inference_confidence,
        start_date=times[0].astimezone(UTC),
        start_date_local=times[0],
        distance_m=distance_total,
        moving_time_s=int(round(moving_time)),
        elapsed_time_s=elapsed_total,
        total_elevation_gain_m=elevation_gain,
        average_speed_ms=average_speed,
        max_speed_ms=max(speeds) if speeds else None,
        average_heartrate=sum(valid_hr) / len(valid_hr) if valid_hr else None,
        max_heartrate=int(round(max(valid_hr))) if valid_hr else None,
        average_cadence=cadence_average,
        average_watts=sum(valid_watts) / len(valid_watts) if valid_watts else None,
        max_watts=int(round(max(valid_watts))) if valid_watts else None,
        calories=calories,
        start_latlng=points[0] if points else None,
        end_latlng=points[-1] if points else None,
        device_name=device_name,
        streams=streams,
        laps=laps or [],
    )


def _parse_gpx(
    root: ET.Element,
    *,
    filename: str,
    requested_name: str | None,
    requested_sport: str | None,
) -> NormalizedActivity:
    tracks = _children(root, "trk")
    if len(tracks) != 1:
        raise ActivityFileError(
            "GPX activity imports require exactly one track.",
            code="multiple_activities",
        )
    track = tracks[0]
    points = _children(track, "trkpt")
    if not points:
        raise ActivityFileError("The GPX track contains no trackpoints.")

    times: list[datetime] = []
    latlng: list[list[float] | None] = []
    altitude: list[float | None] = []
    heartrate: list[float | None] = []
    cadence: list[float | None] = []
    watts: list[float | None] = []
    temperature: list[float | None] = []
    for point in points:
        timestamp = _parse_time(_first_text(point, "time"))
        if timestamp is None:
            raise ActivityFileError(
                "Every GPX trackpoint must include a valid timestamp.",
                code="missing_timestamps",
            )
        times.append(timestamp)
        try:
            latlng.append([float(point.attrib["lat"]), float(point.attrib["lon"])])
        except (KeyError, ValueError):
            latlng.append(None)
        altitude.append(_float_text(point, "ele"))
        heartrate.append(_extension_value(point, {"hr", "heartrate"}))
        cadence.append(_extension_value(point, {"cad", "cadence", "runcadence"}))
        watts.append(_extension_value(point, {"power", "watts"}))
        temperature.append(_extension_value(point, {"atemp", "temp", "temperature"}))

    return _build_common(
        filename=filename,
        file_name=_first_text(track, "name"),
        requested_name=requested_name,
        requested_sport=requested_sport,
        embedded_sport=_first_text(track, "type"),
        times=times,
        latlng=latlng,
        altitude=altitude,
        native_distance=[None] * len(times),
        heartrate=heartrate,
        cadence=cadence,
        watts=watts,
        temperature=temperature,
        calories=None,
        device_name="GPX import",
    )


def _parse_tcx(
    root: ET.Element,
    *,
    filename: str,
    requested_name: str | None,
    requested_sport: str | None,
) -> NormalizedActivity:
    activities = _children(root, "activity")
    if len(activities) != 1:
        raise ActivityFileError(
            "TCX activity imports require exactly one Activity element.",
            code="multiple_activities",
        )
    activity = activities[0]
    points = _children(activity, "trackpoint")
    if not points:
        raise ActivityFileError("The TCX activity contains no trackpoints.")

    times: list[datetime] = []
    latlng: list[list[float] | None] = []
    altitude: list[float | None] = []
    distance: list[float | None] = []
    heartrate: list[float | None] = []
    cadence: list[float | None] = []
    watts: list[float | None] = []
    temperature: list[float | None] = []
    for point in points:
        timestamp = _parse_time(_first_text(point, "time"))
        if timestamp is None:
            raise ActivityFileError(
                "Every TCX trackpoint must include a valid timestamp.",
                code="missing_timestamps",
            )
        times.append(timestamp)
        lat = _float_text(point, "latitudedegrees")
        lon = _float_text(point, "longitudedegrees")
        latlng.append([lat, lon] if lat is not None and lon is not None else None)
        altitude.append(_float_text(point, "altitudemeters"))
        distance.append(_float_text(point, "distancemeters"))
        heartrate.append(_float_text(point, "value"))
        cadence.append(_extension_value(point, {"cadence", "runcadence"}))
        watts.append(_extension_value(point, {"watts", "power"}))
        temperature.append(None)

    laps: list[NormalizedLap] = []
    total_calories = 0
    for index, lap in enumerate(_children(activity, "lap")):
        lap_distance = _float_text(lap, "distancemeters")
        lap_elapsed = _float_text(lap, "totaltimeseconds")
        lap_calories = _float_text(lap, "calories")
        if lap_calories is not None:
            total_calories += int(round(lap_calories))
        lap_hr_values = [
            value
            for value in (
                _float_text(point, "value") for point in _children(lap, "trackpoint")
            )
            if value is not None
        ]
        laps.append(
            NormalizedLap(
                index=index,
                name=f"Lap {index + 1}",
                elapsed_time_s=int(round(lap_elapsed)) if lap_elapsed else None,
                moving_time_s=int(round(lap_elapsed)) if lap_elapsed else None,
                distance_m=lap_distance,
                average_speed_ms=(lap_distance / lap_elapsed)
                if lap_distance and lap_elapsed
                else None,
                average_heartrate=(sum(lap_hr_values) / len(lap_hr_values))
                if lap_hr_values
                else None,
                max_heartrate=int(round(max(lap_hr_values))) if lap_hr_values else None,
            )
        )

    return _build_common(
        filename=filename,
        # TCX Id is normally an ISO timestamp, not a human-facing activity name.
        file_name=_first_text(activity, "notes"),
        requested_name=requested_name,
        requested_sport=requested_sport,
        embedded_sport=activity.attrib.get("Sport") or activity.attrib.get("sport"),
        times=times,
        latlng=latlng,
        altitude=altitude,
        native_distance=distance,
        heartrate=heartrate,
        cadence=cadence,
        watts=watts,
        temperature=temperature,
        calories=total_calories or None,
        device_name="TCX import",
        laps=laps,
    )


def parse_activity_bytes(
    data: bytes,
    filename: str,
    *,
    name: str | None = None,
    sport_type: str | None = "auto",
) -> NormalizedActivity:
    if not data:
        raise ActivityFileError("The activity file is empty.", code="empty_file")
    if len(data) > MAX_ACTIVITY_FILE_BYTES:
        raise ActivityFileError(
            "Activity files must be 25 MiB or smaller.", code="file_too_large"
        )
    lowered = data[:4096].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ActivityFileError(
            "DTD and entity declarations are not allowed.", code="unsafe_xml"
        )
    extension = Path(filename).suffix.lower()
    if extension not in {".gpx", ".tcx"}:
        raise ActivityFileError(
            "Only .gpx and .tcx activity files are supported.",
            code="unsupported_format",
        )
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ActivityFileError(f"Invalid XML: {exc}", code="malformed_xml") from exc

    root_name = _local_name(root.tag)
    if extension == ".gpx" and root_name == "gpx":
        return _parse_gpx(
            root,
            filename=filename,
            requested_name=name,
            requested_sport=sport_type,
        )
    if extension == ".tcx" and root_name == "trainingcenterdatabase":
        return _parse_tcx(
            root,
            filename=filename,
            requested_name=name,
            requested_sport=sport_type,
        )
    raise ActivityFileError(
        f"The XML root does not match the {extension} format.",
        code="format_mismatch",
    )


def _safe_original_name(filename: str) -> str:
    return Path(filename).name or "activity"


def _within_tolerance(
    left: float | int | None,
    right: float | int | None,
    *,
    absolute: float,
    relative: float,
) -> bool:
    if left is None or right is None:
        return False
    tolerance = max(absolute, max(abs(float(left)), abs(float(right))) * relative)
    return abs(float(left) - float(right)) <= tolerance


def _sport_family(sport_type: str) -> str:
    if sport_type in {"Run", "TrailRun", "VirtualRun"}:
        return "run"
    if sport_type in {
        "Ride",
        "VirtualRide",
        "MountainBikeRide",
        "GravelRide",
        "EBikeRide",
    }:
        return "ride"
    return sport_type.lower()


def _matches_activity_signature(
    activity: Activity, normalized: NormalizedActivity
) -> bool:
    """Match the same recording exported in another format or already on Strava."""
    if activity.start_date is None:
        return False
    stored_start = activity.start_date
    if stored_start.tzinfo is None:
        stored_start = stored_start.replace(tzinfo=UTC)
    if abs((stored_start.astimezone(UTC) - normalized.start_date).total_seconds()) > 2:
        return False
    return (
        _sport_family(activity.sport_type) == _sport_family(normalized.sport_type)
        and _within_tolerance(
            activity.elapsed_time_s,
            normalized.elapsed_time_s,
            absolute=5,
            relative=0.002,
        )
        and _within_tolerance(
            activity.distance_m,
            normalized.distance_m,
            absolute=50,
            relative=0.002,
        )
    )


async def _find_matching_activity(
    session, athlete_id: int, normalized: NormalizedActivity
) -> Activity | None:
    start_min = normalized.start_date - timedelta(seconds=2)
    start_max = normalized.start_date + timedelta(seconds=2)
    candidates = (
        await session.execute(
            select(Activity).where(
                Activity.athlete_id == athlete_id,
                Activity.start_date >= start_min,
                Activity.start_date <= start_max,
            )
        )
    ).scalars()
    return next(
        (
            activity
            for activity in candidates
            if _matches_activity_signature(activity, normalized)
        ),
        None,
    )


async def _enrich_matching_activity(
    session,
    activity: Activity,
    normalized: NormalizedActivity,
    *,
    description: str | None,
) -> None:
    """Add file-only detail without overwriting richer data already in FitOps."""
    summary_values = {
        "distance_m": normalized.distance_m,
        "moving_time_s": normalized.moving_time_s,
        "elapsed_time_s": normalized.elapsed_time_s,
        "total_elevation_gain_m": normalized.total_elevation_gain_m,
        "average_speed_ms": normalized.average_speed_ms,
        "max_speed_ms": normalized.max_speed_ms,
        "average_heartrate": normalized.average_heartrate,
        "max_heartrate": normalized.max_heartrate,
        "average_cadence": normalized.average_cadence,
        "average_watts": normalized.average_watts,
        "max_watts": normalized.max_watts,
        "calories": normalized.calories,
        "start_latlng": json.dumps(normalized.start_latlng)
        if normalized.start_latlng
        else None,
        "end_latlng": json.dumps(normalized.end_latlng)
        if normalized.end_latlng
        else None,
    }
    for field_name, value in summary_values.items():
        if getattr(activity, field_name) is None and value is not None:
            setattr(activity, field_name, value)
    if not activity.description and description and description.strip():
        activity.description = description.strip()

    existing_stream_types = set(
        (
            await session.execute(
                select(ActivityStream.stream_type).where(
                    ActivityStream.activity_id == activity.id
                )
            )
        ).scalars()
    )
    for stream_type_name, values in normalized.streams.items():
        if stream_type_name not in existing_stream_types:
            session.add(
                ActivityStream.from_strava_stream(
                    activity.id, stream_type_name, values
                )
            )
    activity.streams_fetched = bool(existing_stream_types or normalized.streams)

    if normalized.laps and not activity.laps_fetched:
        for lap in normalized.laps:
            session.add(
                ActivityLap(
                    activity_id=activity.id,
                    lap_index=lap.index,
                    name=lap.name,
                    elapsed_time_s=lap.elapsed_time_s,
                    moving_time_s=lap.moving_time_s,
                    distance_m=lap.distance_m,
                    average_speed_ms=lap.average_speed_ms,
                    average_heartrate=lap.average_heartrate,
                    max_heartrate=lap.max_heartrate,
                    average_watts=lap.average_watts,
                )
            )
        activity.laps_fetched = True
    activity.detail_fetched = True


async def import_activity_bytes(
    data: bytes,
    filename: str,
    *,
    name: str | None = None,
    description: str | None = None,
    sport_type: str | None = "auto",
    athlete_id: int | None = None,
) -> ActivityImportResult:
    settings = get_settings()
    local_athlete_id = athlete_id or settings.active_athlete_id
    if local_athlete_id is None:
        raise ActivityFileError(
            "Create an offline athlete profile before importing activities.",
            code="offline_profile_required",
        )

    filename = _safe_original_name(filename)
    normalized = parse_activity_bytes(data, filename, name=name, sport_type=sport_type)
    digest = hashlib.sha256(data).hexdigest()
    matched_activity_id: int | None = None

    async with get_async_session() as session:
        duplicate = (
            await session.execute(
                select(ActivityImport).where(
                    ActivityImport.athlete_id == local_athlete_id,
                    ActivityImport.sha256 == digest,
                )
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            activity = (
                await session.execute(
                    select(Activity).where(Activity.id == duplicate.activity_id)
                )
            ).scalar_one()
            return ActivityImportResult(
                activity=activity,
                import_record=duplicate,
                created=False,
                match_type="file_hash",
                sport_inference_source=normalized.sport_inference_source,
                sport_inference_confidence=normalized.sport_inference_confidence,
            )

        matched_activity = await _find_matching_activity(
            session, local_athlete_id, normalized
        )
        if matched_activity is not None:
            existing_import = (
                await session.execute(
                    select(ActivityImport).where(
                        ActivityImport.activity_id == matched_activity.id
                    )
                )
            ).scalar_one_or_none()
            if existing_import is not None:
                await _enrich_matching_activity(
                    session,
                    matched_activity,
                    normalized,
                    description=description,
                )
                return ActivityImportResult(
                    activity=matched_activity,
                    import_record=existing_import,
                    created=False,
                    match_type="activity_signature",
                    sport_inference_source=normalized.sport_inference_source,
                    sport_inference_confidence=normalized.sport_inference_confidence,
                )
            matched_activity_id = matched_activity.id

    extension = Path(filename).suffix.lower()
    relative_path = Path("activity-files") / f"{digest}{extension}"
    destination = settings.fitops_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    created_file = not destination.exists()
    temp_path: Path | None = None
    if created_file:
        handle = tempfile.NamedTemporaryFile(
            prefix=f".{digest[:12]}-",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        )
        temp_path = Path(handle.name)
        try:
            with handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(destination)
            temp_path = None
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    try:
        async with get_async_session() as session:
            athlete_settings = AthleteSettings()
            if matched_activity_id is not None:
                activity = await session.get(Activity, matched_activity_id)
                if activity is None:
                    raise ActivityFileError(
                        "The matching activity disappeared during import.",
                        code="activity_not_found",
                    )
                await _enrich_matching_activity(
                    session,
                    activity,
                    normalized,
                    description=description,
                )
            else:
                activity = Activity(
                    strava_id=None,
                    athlete_id=local_athlete_id,
                    origin=extension.lstrip("."),
                    name=normalized.name,
                    description=(description or "").strip() or None,
                    sport_type=normalized.sport_type,
                    start_date=normalized.start_date,
                    start_date_local=normalized.start_date_local,
                    distance_m=normalized.distance_m,
                    moving_time_s=normalized.moving_time_s,
                    elapsed_time_s=normalized.elapsed_time_s,
                    total_elevation_gain_m=normalized.total_elevation_gain_m,
                    average_speed_ms=normalized.average_speed_ms,
                    max_speed_ms=normalized.max_speed_ms,
                    average_heartrate=normalized.average_heartrate,
                    max_heartrate=normalized.max_heartrate,
                    average_cadence=normalized.average_cadence,
                    average_watts=normalized.average_watts,
                    max_watts=normalized.max_watts,
                    calories=normalized.calories,
                    device_name=normalized.device_name,
                    start_latlng=json.dumps(normalized.start_latlng)
                    if normalized.start_latlng
                    else None,
                    end_latlng=json.dumps(normalized.end_latlng)
                    if normalized.end_latlng
                    else None,
                    detail_fetched=True,
                    streams_fetched=True,
                    laps_fetched=bool(normalized.laps),
                )
                session.add(activity)
                await session.flush()

                for stream_type_name, values in normalized.streams.items():
                    session.add(
                        ActivityStream.from_strava_stream(
                            activity.id, stream_type_name, values
                        )
                    )
                for lap in normalized.laps:
                    session.add(
                        ActivityLap(
                            activity_id=activity.id,
                            lap_index=lap.index,
                            name=lap.name,
                            elapsed_time_s=lap.elapsed_time_s,
                            moving_time_s=lap.moving_time_s,
                            distance_m=lap.distance_m,
                            average_speed_ms=lap.average_speed_ms,
                            average_heartrate=lap.average_heartrate,
                            max_heartrate=lap.max_heartrate,
                            average_watts=lap.average_watts,
                        )
                    )

            activity.aerobic_score = compute_aerobic_score(activity, athlete_settings)
            activity.anaerobic_score = compute_anaerobic_score(
                activity, athlete_settings
            )
            activity.training_stress_score = _estimate_tss(activity)
            import_record = ActivityImport(
                activity_id=activity.id,
                athlete_id=local_athlete_id,
                file_format=extension.lstrip("."),
                original_filename=filename,
                relative_path=relative_path.as_posix(),
                sha256=digest,
                size_bytes=len(data),
            )
            session.add(import_record)
            await session.flush()

            try:
                from fitops.analytics.vo2max import estimate_vo2max_from_stream_dict

                estimate = estimate_vo2max_from_stream_dict(
                    activity,
                    normalized.streams,
                    athlete_settings.lthr,
                    athlete_settings.max_hr,
                )
                if estimate is not None:
                    activity.vo2max_estimate = estimate.estimate
            except Exception:
                pass

            try:
                if athlete_settings.weight_kg and activity.sport_type in RUN_TYPES:
                    from fitops.analytics.running_power import (
                        persist_power_for_activity,
                    )

                    await persist_power_for_activity(
                        session,
                        activity.id,
                        activity,
                        normalized.streams,
                        athlete_settings.weight_kg,
                    )
            except Exception:
                pass
    except Exception:
        if created_file:
            destination.unlink(missing_ok=True)
        raise

    try:
        from fitops.analytics.training_load import persist_training_load_snapshot

        await persist_training_load_snapshot(local_athlete_id)
    except Exception:
        pass
    try:
        from fitops.analytics.race_plan import match_activity_to_plans

        await match_activity_to_plans(activity.id)
    except Exception:
        pass

    return ActivityImportResult(
        activity=activity,
        import_record=import_record,
        created=matched_activity_id is None,
        match_type="new" if matched_activity_id is None else "activity_signature",
        sport_inference_source=normalized.sport_inference_source,
        sport_inference_confidence=normalized.sport_inference_confidence,
    )


async def import_activity_file(
    path: str | Path,
    *,
    name: str | None = None,
    description: str | None = None,
    sport_type: str | None = "auto",
    athlete_id: int | None = None,
) -> ActivityImportResult:
    source = Path(path).expanduser()
    if not source.is_file():
        raise ActivityFileError(
            f"Activity file not found: {source}", code="file_not_found"
        )
    if source.stat().st_size > MAX_ACTIVITY_FILE_BYTES:
        raise ActivityFileError(
            f"Activity files must be no larger than {MAX_ACTIVITY_FILE_BYTES // (1024 * 1024)} MiB.",
            code="file_too_large",
        )
    return await import_activity_bytes(
        source.read_bytes(),
        source.name,
        name=name,
        description=description,
        sport_type=sport_type,
        athlete_id=athlete_id,
    )
