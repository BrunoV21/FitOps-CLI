"""Estimated running power from pace streams (true_pace > gap_pace > velocity_smooth).

Displayed running power is calibrated to Garmin/Stryd-like user-facing watt ranges
rather than raw metabolic power. Calories remain based on the higher metabolic cost.
"""
from __future__ import annotations

DISPLAY_POWER_COST = 1.0  # J / (kg · m) — calibrated displayed running power proxy
METABOLIC_COST = 3.6  # J / (kg · m) — flat-ground metabolic energy cost
JOULES_PER_KCAL = 4184.0
NP_WINDOW = 30  # seconds — rolling window for normalized power
RUN_SPORT_TYPES = frozenset({"Run", "TrailRun", "VirtualRun", "Walk", "Hike"})


def pick_pace_stream(streams: dict) -> tuple[str, list]:
    """Return (source_name, pace_list_s_per_km) with priority true_pace > gap_pace > velocity_smooth.

    true_pace and gap_pace are already in s/km.
    velocity_smooth is in m/s and is converted here.
    Returns ("none", []) when no usable stream exists.
    """
    for key in ("true_pace", "gap_pace"):
        data = streams.get(key)
        if data:
            return key, data

    vel = streams.get("velocity_smooth", [])
    if vel:
        pace = [round(1000.0 / v, 2) if v and v > 0.1 else None for v in vel]
        return "velocity_smooth", pace

    return "none", []


def estimate_power_stream(
    pace_s_per_km: list[float | None],
    weight_kg: float,
) -> list[float | None]:
    """Per-sample displayed running power in watts.

    The constant is calibrated to match common consumer running power ranges,
    rather than raw metabolic power.
    """
    result: list[float | None] = []
    for p in pace_s_per_km:
        if p and p > 0:
            v_ms = 1000.0 / p  # m/s
            result.append(round(DISPLAY_POWER_COST * weight_kg * v_ms, 1))
        else:
            result.append(None)
    return result


def summarize_power(
    power_stream: list[float | None],
    time_stream: list[int | float] | None = None,
) -> dict:
    """Compute avg_w, max_w, np_w from a per-sample power stream.

    time_stream is optional (seconds since start). When absent, 1 s per sample is assumed.
    All three values are None when the stream has no valid samples.
    """
    valid = [p for p in power_stream if p is not None]
    if not valid:
        return {"avg_w": None, "max_w": None, "np_w": None}

    avg_w = round(sum(valid) / len(valid), 1)
    max_w = round(max(valid), 1)
    np_w = _normalized_power(power_stream, time_stream)

    return {"avg_w": avg_w, "max_w": max_w, "np_w": np_w}


def estimate_kcal(
    power_stream: list[float | None],
    time_stream: list[int | float] | None = None,
) -> int | None:
    """Total estimated kilocalories from the power stream.

    The power stream stores calibrated displayed watts, so kcal converts that back
    to an approximate metabolic equivalent before integrating over time.
    """
    valid_pairs = _valid_power_time_pairs(power_stream, time_stream)
    if not valid_pairs:
        return None

    metabolic_scale = METABOLIC_COST / DISPLAY_POWER_COST
    total_joules = sum(p * metabolic_scale * dt for p, dt in valid_pairs)
    return max(1, round(total_joules / JOULES_PER_KCAL))


def _normalized_power(
    power_stream: list[float | None],
    time_stream: list[int | float] | None,
) -> float | None:
    """30-second rolling average NP: (mean(PA_30^4))^(1/4)."""
    n = len(power_stream)
    if n < NP_WINDOW:
        return None

    # Build rolling 30-sample mean
    rolling: list[float] = []
    for i in range(NP_WINDOW - 1, n):
        window = [p for p in power_stream[i - NP_WINDOW + 1 : i + 1] if p is not None]
        if window:
            rolling.append(sum(window) / len(window))

    if not rolling:
        return None

    np_w = (sum(r**4 for r in rolling) / len(rolling)) ** 0.25
    return round(np_w, 1)


def _valid_power_time_pairs(
    power_stream: list[float | None],
    time_stream: list[int | float] | None,
) -> list[tuple[float, float]]:
    """Return (power, dt_seconds) pairs for valid (non-None) samples only."""
    if not power_stream:
        return []

    if time_stream and len(time_stream) >= 2:
        pairs: list[tuple[float, float]] = []
        for i, p in enumerate(power_stream):
            if p is None:
                continue
            if i + 1 < len(time_stream):
                dt = float(time_stream[i + 1] - time_stream[i])
            else:
                dt = float(time_stream[i] - time_stream[i - 1]) if i > 0 else 1.0
            if dt > 0:
                pairs.append((p, dt))
        return pairs

    # 1 s per sample
    return [(p, 1.0) for p in power_stream if p is not None]


async def persist_power_for_activity(
    session,
    activity_db_id: int,
    activity_row,
    streams: dict,
    weight_kg: float,
) -> bool:
    """Compute running power and persist stream + Activity aggregates.

    Returns True if power was computed and saved, False if skipped
    (wrong sport, missing streams, or already computed).

    Designed to be idempotent: calling twice upserts the stream row and refreshes
    the Activity columns.
    """
    from sqlalchemy import select

    from fitops.db.models.activity_stream import ActivityStream

    sport = getattr(activity_row, "sport_type", None) or ""
    if sport not in RUN_SPORT_TYPES:
        return False

    source, pace_stream = pick_pace_stream(streams)
    if source == "none" or not pace_stream:
        return False

    power_stream = estimate_power_stream(pace_stream, weight_kg)
    time_stream = streams.get("time")
    stats = summarize_power(power_stream, time_stream)
    kcal = estimate_kcal(power_stream, time_stream)

    # Upsert power stream row
    existing = await session.execute(
        select(ActivityStream).where(
            ActivityStream.activity_id == activity_db_id,
            ActivityStream.stream_type == "power",
        )
    )
    stream_row = existing.scalar_one_or_none()
    if stream_row is None:
        session.add(
            ActivityStream.from_strava_stream(activity_db_id, "power", power_stream)
        )
    else:
        import json

        stream_row.data_json = json.dumps(power_stream)
        stream_row.data_length = len(power_stream)

    # Update Activity aggregates
    activity_row.est_power_avg_w = stats["avg_w"]
    activity_row.est_power_max_w = stats["max_w"]
    activity_row.est_power_np_w = stats["np_w"]
    activity_row.est_kcal_model = kcal
    activity_row.est_power_source = source

    return True
