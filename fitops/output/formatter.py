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

METERS_PER_MILE = 1609.344


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
    dist_mi = _round2(dist_m / METERS_PER_MILE) if dist_m else None

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
        },
        "distance": {
            "meters": _round2(dist_m),
            "km": dist_km,
            "miles": dist_mi,
        },
        "pace": pace,
        "speed": {
            "average_ms": _round2(speed_ms),
            "average_kmh": _round2(speed_ms * 3.6) if speed_ms else None,
            "max_ms": _round2(max_speed_ms),
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
        "flags": {
            "trainer": bool(row.get("trainer", False)),
            "commute": bool(row.get("commute", False)),
            "manual": bool(row.get("manual", False)),
            "private": bool(row.get("private", False)),
            "is_race": bool(row.get("workout_type") == 1),
        },
        "social": {
            "kudos": row.get("kudos_count", 0) or 0,
            "comments": row.get("comment_count", 0) or 0,
        },
        "data_availability": {
            "has_gps": bool(row.get("start_latlng")),
            "has_heart_rate": bool(avg_hr),
            "has_power": bool(avg_w),
            "streams_fetched": bool(row.get("streams_fetched", False)),
            "laps_fetched": bool(row.get("laps_fetched", False)),
            "detail_fetched": bool(row.get("detail_fetched", False)),
        },
    }


def make_meta(
    total_count: int | None = None,
    filters_applied: dict | None = None,
) -> dict:
    return {
        "tool": "fitops-cli",
        "version": "0.1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "total_count": total_count,
        "filters_applied": filters_applied or {},
    }
