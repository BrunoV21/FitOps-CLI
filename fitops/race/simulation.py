"""
fitops/race/simulation.py

Race simulation engine: GAP factor formula, split distribution engine for
even/negative/positive strategies, and pacer mode (sit-then-push).

Pure math — no DB access, no I/O.
"""
from __future__ import annotations

from typing import Optional

from fitops.analytics.weather_pace import compute_wap_factor
from fitops.race.course_parser import _fmt_pace, _fmt_duration


def gap_factor(grade_decimal: float) -> float:
    """
    Pace cost multiplier for elevation grade.
    Strava improved model (HR-based, big-data calibrated).
    Source: Strava engineering + Fellrnr.com/wiki/Grade_Adjusted_Pace

    grade_decimal: 0.10 = 10% uphill, -0.05 = 5% downhill.
    Returns: multiplier > 1 for uphill (slower), < 1 for gentle downhill.
    Clamped to [-0.45, 0.45] (validated range).

    Coefficients calibrated to Strava's empirical per-grade data:
      +5%  grade -> factor ~1.12 (12% slower)
      +10% grade -> factor ~1.22 (22% slower)
      -5%  grade -> factor ~0.86 (14% faster)
    Formula: 1 + (-4.0 * grade^2 + 2.6 * grade)
    """
    grade = max(-0.45, min(0.45, grade_decimal))
    relative_cost = -4.0 * grade ** 2 + 2.6 * grade
    return 1.0 + relative_cost


def _neutral_wap() -> float:
    """WAP factor at neutral conditions (15 deg C, 40% RH, no wind) = 1.0."""
    return compute_wap_factor(15.0, 40.0, 0.0, 0.0, None)


def simulate_splits(
    segments: list[dict],
    target_total_s: float,
    weather: dict,
    strategy: str = "even",
) -> list[dict]:
    """
    Distribute target_total_s across segments proportional to difficulty.

    Each segment dict must have: distance_m, grade, bearing (from build_km_segments).
    Weather dict must have: temperature_c, humidity_pct.
    Optional weather keys: wind_speed_ms (default 0), wind_direction_deg (default 0).

    strategy: "even" | "negative" | "positive"
    Returns: list of per-km split dicts.
    """
    if not segments:
        return []

    temp_c = weather["temperature_c"]
    rh_pct = weather["humidity_pct"]
    wind_ms = weather.get("wind_speed_ms", 0.0)
    wind_dir = weather.get("wind_direction_deg", 0.0)

    # Step 1: compute per-segment factors
    enriched = []
    for seg in segments:
        gf = gap_factor(seg["grade"])
        wf = compute_wap_factor(temp_c, rh_pct, wind_ms, wind_dir, seg.get("bearing"))
        combined = gf * wf
        enriched.append({**seg, "gap_factor": gf, "wap_factor": wf, "combined_factor": combined})

    # Step 2: total difficulty-weighted distance
    total_dist_m = sum(s["distance_m"] for s in enriched)

    # Step 3: base flat-equivalent pace for the target time
    # (what pace we'd need on flat, no weather?)
    base_pace_s = target_total_s / (total_dist_m / 1000.0)  # s/km

    # Step 4: strategy multipliers
    n = len(enriched)
    if strategy == "negative":
        # Research basis: Grivas et al. (2025), PMC12307312 — 2% differential optimal
        strat = [1.02 if i < n // 2 else 0.98 for i in range(n)]
    elif strategy == "positive":
        strat = [0.98 if i < n // 2 else 1.02 for i in range(n)]
    else:  # "even"
        strat = [1.0] * n

    # Step 5: per-segment target pace and time
    # target_pace = base_pace * combined_factor * strat_factor
    # (combined_factor > 1 = hard segment -> numerically larger pace seconds -> slower)
    #
    # Re-normalise so total time sums exactly to target:
    # raw_time_i = base_pace * combined_i * strat_i * (dist_i / 1000)
    # scale = target_total_s / sum(raw_time_i)
    raw_times = []
    for i, seg in enumerate(enriched):
        pace = base_pace_s * seg["combined_factor"] * strat[i]
        raw_times.append(pace * (seg["distance_m"] / 1000.0))

    total_raw = sum(raw_times)
    scale = target_total_s / total_raw if total_raw > 0 else 1.0

    splits = []
    cumulative_s = 0.0
    for i, seg in enumerate(enriched):
        seg_time_s = raw_times[i] * scale
        pace_s = seg_time_s / (seg["distance_m"] / 1000.0)
        cumulative_s += seg_time_s
        splits.append({
            "km": seg["km"],
            "distance_m": round(seg["distance_m"], 1),
            "elevation_gain_m": round(seg.get("elevation_gain_m", 0.0), 1),
            "grade_pct": round(seg["grade"] * 100, 1),
            "bearing_deg": round(seg.get("bearing", 0.0), 1),
            "gap_factor": round(seg["gap_factor"], 4),
            "wap_factor": round(seg["wap_factor"], 4),
            "combined_factor": round(seg["combined_factor"], 4),
            "target_pace_s": round(pace_s, 1),
            "target_pace_fmt": _fmt_pace(pace_s),
            "segment_time_s": round(seg_time_s, 1),
            "cumulative_time_s": round(cumulative_s, 1),
            "cumulative_time_fmt": _fmt_duration(cumulative_s),
        })
    return splits


def simulate_pacer_mode(
    segments: list[dict],
    target_total_s: float,
    pacer_pace_s: float,
    drop_at_km: float,
    weather: dict,
) -> dict:
    """
    Pacer strategy: sit with pacer until drop_at_km, then push to hit target_total_s.

    pacer_pace_s: pacer's constant pace in s/km.
    drop_at_km: km marker at which athlete breaks away from pacer.

    Raises ValueError if pacer is too slow to achieve target (sit time already exceeds budget).
    """
    if not segments:
        raise ValueError("No segments provided.")

    total_dist_km = sum(s["distance_m"] for s in segments) / 1000.0
    required_avg_pace_s = target_total_s / total_dist_km

    # Validate: pacer pace must not exceed 20% slower than required average pace.
    # A pacer significantly slower than your target average leaves the push phase
    # physically infeasible (push pace would need to be faster than human capacity).
    # 20% threshold: e.g. 300s/km target avg allows up to 360s/km pacer.
    _PACER_SLOWNESS_LIMIT = 1.2
    if pacer_pace_s > required_avg_pace_s * _PACER_SLOWNESS_LIMIT:
        raise ValueError(
            f"Pacer is too slow to achieve target. "
            f"Pacer pace {_fmt_pace(pacer_pace_s)} exceeds required average "
            f"{_fmt_pace(required_avg_pace_s)} by more than {int((_PACER_SLOWNESS_LIMIT - 1) * 100)}%."
        )

    sit_segs = [s for s in segments if s["km"] <= drop_at_km]
    push_segs = [s for s in segments if s["km"] > drop_at_km]

    if not push_segs:
        raise ValueError("drop_at_km is at or beyond the finish — no push phase exists.")

    # Sit phase: constant pacer pace (per-segment pace scaled to segment distance)
    sit_dist_km = sum(s["distance_m"] for s in sit_segs) / 1000.0
    sit_time_s = pacer_pace_s * sit_dist_km

    remaining_time_s = target_total_s - sit_time_s
    push_dist_km = sum(s["distance_m"] for s in push_segs) / 1000.0
    required_push_pace_s = remaining_time_s / push_dist_km

    # Distribute push time across push segments with terrain adjustment
    push_splits = simulate_splits(push_segs, remaining_time_s, weather, strategy="even")

    return {
        "sit_phase": {
            "through_km": drop_at_km,
            "pacer_pace_fmt": _fmt_pace(pacer_pace_s),
            "projected_time_at_drop": _fmt_duration(sit_time_s),
            "distance_km": round(sit_dist_km, 2),
            "sit_time_s": round(sit_time_s, 1),
        },
        "push_phase": {
            "from_km": drop_at_km,
            "required_avg_pace_fmt": _fmt_pace(required_push_pace_s),
            "remaining_distance_km": round(push_dist_km, 2),
            "remaining_time_budget": _fmt_duration(remaining_time_s),
            "splits": push_splits,
        },
        "projected_finish": _fmt_duration(target_total_s),
    }
