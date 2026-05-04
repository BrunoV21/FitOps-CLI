from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from fitops.analytics.activity_splits import compute_km_splits
from fitops.db.models.activity_calibration import ActivityCalibration

RUN_RACE_SPORT_TYPES = {"Run", "TrailRun", "VirtualRun"}


def format_race_time(total_s: float | int | None) -> str | None:
    if total_s is None:
        return None
    total = max(0, int(round(float(total_s))))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_race_time_to_seconds(value: str) -> int:
    raw = value.strip()
    parts = raw.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = (int(parts[0]), int(parts[1]), int(parts[2]))
        return hours * 3600 + minutes * 60 + seconds
    if len(parts) == 2:
        minutes, seconds = (int(parts[0]), int(parts[1]))
        return minutes * 60 + seconds
    raise ValueError(
        f"Invalid chip time {value!r}. Use H:MM:SS for races over an hour or MM:SS for shorter races."
    )


def is_supported_race_activity(activity: Any) -> bool:
    return (
        getattr(activity, "workout_type", None) == 1
        and getattr(activity, "sport_type", None) in RUN_RACE_SPORT_TYPES
    )


def get_recorded_race_distance_m(
    activity: Any, streams: dict | None = None
) -> float | None:
    dist = (streams or {}).get("distance", [])
    if dist:
        try:
            last = float(dist[-1])
        except (TypeError, ValueError):
            last = 0.0
        if last > 0:
            return last
    return getattr(activity, "distance_m", None)


def get_recorded_race_time_s(activity: Any, streams: dict | None = None) -> int | None:
    time_stream = (streams or {}).get("time", [])
    if time_stream:
        try:
            last = int(round(float(time_stream[-1])))
        except (TypeError, ValueError):
            last = 0
        if last > 0:
            return last
    elapsed = getattr(activity, "elapsed_time_s", None)
    if elapsed and elapsed > 0:
        return int(elapsed)
    moving = getattr(activity, "moving_time_s", None)
    if moving and moving > 0:
        return int(moving)
    return None


def summarize_race_result(activity: Any, streams: dict | None = None) -> dict | None:
    if not is_supported_race_activity(activity):
        return None

    recorded_distance_m = get_recorded_race_distance_m(activity, streams)
    recorded_time_s = get_recorded_race_time_s(activity, streams)
    race_distance_m = getattr(activity, "race_distance_m", None)
    chip_time_s = getattr(activity, "chip_time_s", None)

    distance_scale = (
        race_distance_m / recorded_distance_m
        if race_distance_m and recorded_distance_m and recorded_distance_m > 0
        else 1.0
    )
    time_scale = (
        chip_time_s / recorded_time_s
        if chip_time_s and recorded_time_s and recorded_time_s > 0
        else 1.0
    )

    corrected_distance_m = race_distance_m or recorded_distance_m
    corrected_time_s = chip_time_s or recorded_time_s
    corrected_avg_pace_s = None
    if corrected_distance_m and corrected_distance_m > 0 and corrected_time_s:
        corrected_avg_pace_s = corrected_time_s / (corrected_distance_m / 1000.0)

    return {
        "override_active": bool(race_distance_m or chip_time_s),
        "recorded_distance_m": recorded_distance_m,
        "recorded_distance_km": round(recorded_distance_m / 1000.0, 3)
        if recorded_distance_m
        else None,
        "recorded_time_seconds": recorded_time_s,
        "recorded_time_formatted": format_race_time(recorded_time_s),
        "recorded_time_source": "stream"
        if (streams or {}).get("time")
        else "elapsed_time"
        if getattr(activity, "elapsed_time_s", None)
        else "moving_time",
        "race_distance_m": race_distance_m,
        "race_distance_km": round(race_distance_m / 1000.0, 3)
        if race_distance_m
        else None,
        "chip_time_seconds": chip_time_s,
        "chip_time_formatted": format_race_time(chip_time_s),
        "corrected_distance_m": corrected_distance_m,
        "corrected_distance_km": round(corrected_distance_m / 1000.0, 3)
        if corrected_distance_m
        else None,
        "corrected_time_seconds": corrected_time_s,
        "corrected_time_formatted": format_race_time(corrected_time_s),
        "corrected_avg_pace_s_per_km": round(corrected_avg_pace_s, 1)
        if corrected_avg_pace_s
        else None,
        "corrected_avg_pace_formatted": _format_pace(corrected_avg_pace_s),
        "distance_correction_factor": round(distance_scale, 6)
        if race_distance_m and recorded_distance_m
        else None,
        "time_correction_factor": round(time_scale, 6)
        if chip_time_s and recorded_time_s
        else None,
        "pace_correction_factor": round(time_scale / distance_scale, 6)
        if distance_scale > 0
        else None,
    }


def compute_corrected_race_splits(
    activity: Any,
    streams: dict,
    true_pace: list[float] | None = None,
) -> list[dict] | None:
    summary = summarize_race_result(activity, streams)
    if summary is None:
        return None

    distance_scale = summary["distance_correction_factor"] or 1.0
    time_scale = summary["time_correction_factor"] or 1.0
    return compute_km_splits(
        streams,
        getattr(activity, "sport_type", ""),
        true_pace=true_pace,
        distance_scale=distance_scale,
        time_scale=time_scale,
    )


def build_calibrated_summary(activity: Any, streams: dict | None = None) -> dict | None:
    summary = summarize_race_result(activity, streams)
    if summary is None or not summary.get("override_active"):
        return None

    if hasattr(activity, "__table__"):
        data = {c.name: getattr(activity, c.name) for c in activity.__table__.columns}
    else:
        data = dict(getattr(activity, "__dict__", {}))

    corrected_distance_m = summary.get("corrected_distance_m")
    corrected_time_s = summary.get("corrected_time_seconds")
    data["distance_m"] = corrected_distance_m
    if corrected_time_s:
        data["elapsed_time_s"] = corrected_time_s
        data["moving_time_s"] = corrected_time_s
    if corrected_distance_m and corrected_time_s and corrected_time_s > 0:
        data["average_speed_ms"] = corrected_distance_m / corrected_time_s
    return data


def build_calibrated_streams(activity: Any, streams: dict) -> dict | None:
    summary = summarize_race_result(activity, streams)
    if summary is None or not summary.get("override_active"):
        return None

    distance_scale = summary["distance_correction_factor"] or 1.0
    time_scale = summary["time_correction_factor"] or 1.0
    speed_scale = distance_scale / time_scale if time_scale > 0 else distance_scale
    pace_scale = time_scale / distance_scale if distance_scale > 0 else time_scale

    calibrated: dict[str, list] = {}
    for key, values in streams.items():
        if not isinstance(values, list):
            calibrated[key] = values
            continue
        if key == "distance":
            calibrated[key] = [v * distance_scale if _num(v) else v for v in values]
        elif key == "time":
            calibrated[key] = [v * time_scale if _num(v) else v for v in values]
        elif key in {"velocity_smooth", "grade_adjusted_speed", "true_velocity"}:
            calibrated[key] = [v * speed_scale if _num(v) else v for v in values]
        elif key in {"true_pace", "wap_pace"}:
            calibrated[key] = [v * pace_scale if _num(v) else v for v in values]
        else:
            calibrated[key] = list(values)
    return calibrated


async def persist_calibrated_snapshot(
    session,
    activity: Any,
    streams: dict,
) -> ActivityCalibration | None:
    summary = summarize_race_result(activity, streams)
    if summary is None or not summary.get("override_active"):
        return None

    calibrated_summary = build_calibrated_summary(activity, streams)
    calibrated_streams = build_calibrated_streams(activity, streams)
    if calibrated_summary is None or calibrated_streams is None:
        return None

    result = await session.execute(
        select(ActivityCalibration).where(
            ActivityCalibration.activity_id == activity.id
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        existing = ActivityCalibration(
            activity_id=activity.id,
            summary_json=json.dumps(calibrated_summary, default=str),
            streams_json=json.dumps(calibrated_streams, default=str),
            race_result_json=json.dumps(summary, default=str),
        )
        session.add(existing)
        return existing

    existing.summary_json = json.dumps(calibrated_summary, default=str)
    existing.streams_json = json.dumps(calibrated_streams, default=str)
    existing.race_result_json = json.dumps(summary, default=str)
    return existing


async def delete_calibrated_snapshot(session, activity_id: int) -> None:
    result = await session.execute(
        select(ActivityCalibration).where(
            ActivityCalibration.activity_id == activity_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        await session.delete(existing)


def _format_pace(pace_s: float | None) -> str | None:
    if not pace_s or pace_s <= 0:
        return None
    m, s = divmod(int(round(pace_s)), 60)
    return f"{m}:{s:02d}/km"


def _num(value: object) -> bool:
    return isinstance(value, (int, float))
