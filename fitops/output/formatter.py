from __future__ import annotations

from datetime import UTC, datetime

RUN_SPORT_TYPES = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
RIDE_SPORT_TYPES = {
    "Ride",
    "VirtualRide",
    "EBikeRide",
    "MountainBikeRide",
    "GravelRide",
}

METERS_PER_MILE = 1609.344  # used by _fmt_pace_per_mile


def _fmt_seconds(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_pace_per_km(speed_ms: float | None) -> str | None:
    if not speed_ms or speed_ms <= 0:
        return None
    seconds_per_km = 1000 / speed_ms
    m = int(seconds_per_km // 60)
    s = int(seconds_per_km % 60)
    return f"{m}:{s:02d}"


def _fmt_pace_per_mile(speed_ms: float | None) -> str | None:
    if not speed_ms or speed_ms <= 0:
        return None
    seconds_per_mile = METERS_PER_MILE / speed_ms
    m = int(seconds_per_mile // 60)
    s = int(seconds_per_mile % 60)
    return f"{m}:{s:02d}"


def _round2(val: float | None) -> float | None:
    return round(val, 2) if val is not None else None


def _flags_block(row: dict) -> dict:
    flags = {
        k: True
        for k, v in {
            "trainer": row.get("trainer", False),
            "commute": row.get("commute", False),
            "manual": row.get("manual", False),
            "private": row.get("private", False),
            "is_race": row.get("workout_type") == 1,
        }.items()
        if v
    }
    return {"flags": flags} if flags else {}


def _social_block(row: dict) -> dict:
    kudos = row.get("kudos_count", 0) or 0
    comments = row.get("comment_count", 0) or 0
    if kudos == 0 and comments == 0:
        return {}
    return {"social": {"kudos": kudos, "comments": comments}}


def _data_availability_block(row: dict, avg_hr, avg_w) -> dict:
    available = {
        k: True
        for k, v in {
            "has_gps": bool(row.get("start_latlng")),
            "has_heart_rate": bool(avg_hr),
            "has_power": bool(avg_w),
            "streams_fetched": bool(row.get("streams_fetched", False)),
            "laps_fetched": bool(row.get("laps_fetched", False)),
            "detail_fetched": bool(row.get("detail_fetched", False)),
        }.items()
        if v
    }
    return {"data_availability": available} if available else {}


def format_activity_row(row: dict, gear_lookup: dict | None = None) -> dict:
    """Convert a raw DB activity row dict to LLM-friendly output dict."""
    sport_type = row.get("sport_type", "")
    speed_ms = row.get("average_speed_ms")
    max_speed_ms = row.get("max_speed_ms")
    gear_id = row.get("gear_id")

    gear_name = None
    gear_type = None
    if gear_id and gear_lookup:
        gear_info = gear_lookup.get(gear_id, {})
        gear_name = gear_info.get("name")
        gear_type = gear_info.get("type")

    dist_m = row.get("distance_m")
    dist_km = _round2(dist_m / 1000) if dist_m else None

    pace = None
    if sport_type in RUN_SPORT_TYPES and speed_ms:
        pace = {
            "average_per_km": _fmt_pace_per_km(speed_ms),
            "average_per_mile": _fmt_pace_per_mile(speed_ms),
        }

    power = None
    avg_w = row.get("average_watts")
    if sport_type in RIDE_SPORT_TYPES and avg_w:
        power = {
            "average_watts": _round2(avg_w),
            "max_watts": row.get("max_watts"),
            "weighted_average_watts": _round2(row.get("weighted_average_watts")),
        }

    avg_hr = row.get("average_heartrate")
    heart_rate = None
    if avg_hr:
        heart_rate = {
            "average_bpm": _round2(avg_hr),
            "max_bpm": row.get("max_heartrate"),
        }

    avg_cad = row.get("average_cadence")
    cadence = {"average_spm": _round2(avg_cad)} if avg_cad else None

    return {
        "strava_activity_id": row.get("strava_id"),
        "name": row.get("name", ""),
        "sport_type": sport_type,
        "start_date_local": str(row["start_date_local"])
        if row.get("start_date_local")
        else None,
        "start_date_utc": str(row["start_date"]) if row.get("start_date") else None,
        "timezone": row.get("timezone"),
        "duration": {
            "moving_time_seconds": row.get("moving_time_s"),
            "moving_time_formatted": _fmt_seconds(row.get("moving_time_s")),
            "elapsed_time_seconds": row.get("elapsed_time_s"),
            "elapsed_time_formatted": _fmt_seconds(row.get("elapsed_time_s")),
            "efficiency_pct": round(row["moving_time_s"] / row["elapsed_time_s"] * 100)
            if row.get("moving_time_s")
            and row.get("elapsed_time_s")
            and row["elapsed_time_s"] > 0
            else None,
        },
        "distance": {
            "km": dist_km,
        },
        "pace": pace,
        "speed": {
            "average_kmh": _round2(speed_ms * 3.6) if speed_ms else None,
            "max_kmh": _round2(max_speed_ms * 3.6) if max_speed_ms else None,
        },
        "elevation": {
            "total_gain_m": _round2(row.get("total_elevation_gain_m")),
        },
        "heart_rate": heart_rate,
        "cadence": cadence,
        "power": power,
        "training_metrics": {
            "suffer_score": row.get("suffer_score"),
            "calories": row.get("calories"),
            "training_stress_score": row.get("training_stress_score"),
        },
        "equipment": {
            "gear_id": gear_id,
            "gear_name": gear_name,
            "gear_type": gear_type,
        },
        "description": (row.get("description") or "").strip() or None,
        "device_name": row.get("device_name"),
        **_flags_block(row),
        **_social_block(row),
        **_data_availability_block(row, avg_hr, avg_w),
    }


def make_meta(
    total_count: int | None = None,
    filters_applied: dict | None = None,
    returned_count: int | None = None,
    offset: int | None = None,
    has_more: bool | None = None,
) -> dict:
    meta: dict = {
        "tool": "fitops",
        "version": "0.1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "total_count": total_count,
        "filters_applied": filters_applied or {},
    }
    if returned_count is not None:
        meta["returned_count"] = returned_count
    if offset is not None:
        meta["offset"] = offset
    if has_more is not None:
        meta["has_more"] = has_more
    return meta
