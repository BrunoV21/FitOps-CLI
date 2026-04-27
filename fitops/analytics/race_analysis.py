"""Race Analysis & Replay — Phase 9.

Alignment, gap series, event detection, segment metrics.
All computation is synchronous; callers (CLI/dashboard) run in async context
but call these pure functions directly.
"""
from __future__ import annotations

import math
import statistics
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class NormalizedStream:
    """Athlete streams interpolated to a shared distance grid."""

    label: str
    is_primary: bool
    activity_id: int | None

    # Aligned arrays — index i corresponds to distance_grid[i]
    distance_grid: list[float]  # metres from start
    elapsed_s: list[float]  # seconds from athlete's own start
    latlng: list[tuple[float, float]] | None = None  # [(lat, lon), ...]
    altitude: list[float] | None = None
    heartrate: list[float] | None = None
    cadence: list[float] | None = None
    velocity: list[float] | None = None  # m/s
    # Wall-clock start as UTC epoch seconds — lets the replay align athletes
    # that started at different times onto a shared race clock.
    start_date_utc_s: float | None = None


@dataclass
class DetectedSegment:
    label: str
    start_km: float
    end_km: float
    gradient_type: str  # "climb" | "descent" | "flat"
    avg_grade_pct: float


@dataclass
class RaceEvent:
    event_type: str  # surge|drop|bridge|fade|final_sprint|separation
    athlete_label: str
    distance_km: float
    elapsed_s: float
    impact_s: float  # positive = gained, negative = lost
    description: str


# ---------------------------------------------------------------------------
# Stream normalisation — interpolate to 10 m distance grid
# ---------------------------------------------------------------------------


def _interp(x_raw: list[float], y_raw: list[float], x_new: float) -> float | None:
    """Linear interpolation of y at x_new given parallel arrays."""
    if len(x_raw) < 2:
        return None
    # Clamp to range
    if x_new <= x_raw[0]:
        return y_raw[0]
    if x_new >= x_raw[-1]:
        return y_raw[-1]
    # Binary search
    lo, hi = 0, len(x_raw) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if x_raw[mid] <= x_new:
            lo = mid
        else:
            hi = mid
    t = (x_new - x_raw[lo]) / (x_raw[hi] - x_raw[lo])
    return y_raw[lo] + t * (y_raw[hi] - y_raw[lo])


def _interp_monotonic_y_at_x(
    x_raw: list[float],
    y_raw: list[float],
    x_new: float,
) -> float | None:
    """Interpolate y(x_new) for a monotonic x series."""
    if len(x_raw) < 2 or len(x_raw) != len(y_raw):
        return None
    if x_new <= x_raw[0]:
        return y_raw[0]
    if x_new >= x_raw[-1]:
        return y_raw[-1]
    lo, hi = 0, len(x_raw) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if x_raw[mid] <= x_new:
            lo = mid
        else:
            hi = mid
    span = x_raw[hi] - x_raw[lo]
    frac = (x_new - x_raw[lo]) / span if span > 0 else 0.0
    return y_raw[lo] + frac * (y_raw[hi] - y_raw[lo])


def _interp_array(
    dist_raw: list[float], values: list[float | None], grid: list[float]
) -> list[float | None]:
    """Interpolate values array onto grid using dist_raw as x axis."""
    # Filter out None values
    pairs = [(d, v) for d, v in zip(dist_raw, values) if v is not None]
    if not pairs:
        return [None] * len(grid)
    xs, ys = zip(*pairs)
    xs, ys = list(xs), list(ys)
    return [_interp(xs, ys, g) for g in grid]


def _smooth_latlng(
    latlng_raw: list[tuple[float, float] | list[float]], window: int = 3
) -> list[tuple[float, float]]:
    """Apply rolling median smoothing to GPS coordinates."""
    if not latlng_raw:
        return []
    n = len(latlng_raw)
    smoothed: list[tuple[float, float]] = []
    hw = window // 2
    for i in range(n):
        lo = max(0, i - hw)
        hi = min(n, i + hw + 1)
        lats = [latlng_raw[j][0] for j in range(lo, hi)]
        lons = [latlng_raw[j][1] for j in range(lo, hi)]
        smoothed.append((statistics.median(lats), statistics.median(lons)))
    return smoothed


def _interp_latlng(
    dist_raw: list[float],
    latlng_raw: list[tuple[float, float]],
    grid: list[float],
) -> list[tuple[float, float] | None]:
    """Interpolate lat/lon arrays onto grid."""
    if not latlng_raw or not dist_raw:
        return [None] * len(grid)
    lats = [p[0] for p in latlng_raw]
    lons = [p[1] for p in latlng_raw]
    interp_lats = _interp_array(dist_raw, lats, grid)
    interp_lons = _interp_array(dist_raw, lons, grid)
    return [
        (lat, lon) if lat is not None and lon is not None else None
        for lat, lon in zip(interp_lats, interp_lons)
    ]


def _clean_elapsed_spikes(elapsed: list[float | None]) -> list[float]:
    """Remove GPS timing spikes from a cumulative elapsed_s array.

    A spike is a step > 5× the median inter-point step.  Because elapsed_s is
    cumulative, the excess propagates to every subsequent value — subtract it
    from all following points to restore true pace.
    """
    vals = [float(v) if v is not None else 0.0 for v in elapsed]
    if len(vals) < 3:
        return vals
    steps = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
    median_step = statistics.median(steps)
    threshold = max(median_step * 5, 5.0)
    for i, step in enumerate(steps):
        if step > threshold:
            excess = step - median_step
            for j in range(i + 1, len(vals)):
                vals[j] -= excess
            for j in range(i, len(steps)):
                steps[j] = vals[j + 1] - vals[j]
    return vals


def normalize_stream(
    raw_streams: dict[str, list],
    athlete_label: str,
    is_primary: bool,
    activity_id: int | None = None,
    grid_spacing_m: float = 10.0,
) -> NormalizedStream:
    """Interpolate raw Strava streams onto a uniform distance grid.

    raw_streams keys (Strava names):
        "distance" — metres from start
        "time"     — seconds from start
        "latlng"   — [[lat, lon], ...]
        "altitude"
        "heartrate"
        "cadence"
        "velocity_smooth"
    """
    dist_raw: list[float] = raw_streams.get("distance", [])
    time_raw: list[float] = raw_streams.get("time", [])

    if not dist_raw or not time_raw:
        # Return empty stream — caller should handle this
        return NormalizedStream(
            label=athlete_label,
            is_primary=is_primary,
            activity_id=activity_id,
            distance_grid=[],
            elapsed_s=[],
        )

    total_dist = dist_raw[-1]
    grid = [
        i * grid_spacing_m
        for i in range(int(total_dist / grid_spacing_m) + 1)
        if i * grid_spacing_m <= total_dist
    ]

    elapsed_interp = _clean_elapsed_spikes(_interp_array(dist_raw, time_raw, grid))

    latlng_raw = raw_streams.get("latlng")
    if latlng_raw:
        smoothed_latlng = _smooth_latlng(latlng_raw)
        latlng_interp = _interp_latlng(dist_raw, smoothed_latlng, grid)
    else:
        latlng_interp = None

    altitude_raw = raw_streams.get("altitude")
    altitude_interp = (
        _interp_array(dist_raw, altitude_raw, grid) if altitude_raw else None
    )

    hr_raw = raw_streams.get("heartrate")
    hr_interp = _interp_array(dist_raw, hr_raw, grid) if hr_raw else None

    cad_raw = raw_streams.get("cadence")
    cad_interp = _interp_array(dist_raw, cad_raw, grid) if cad_raw else None

    vel_raw = raw_streams.get("velocity_smooth")
    vel_interp = _interp_array(dist_raw, vel_raw, grid) if vel_raw else None

    return NormalizedStream(
        label=athlete_label,
        is_primary=is_primary,
        activity_id=activity_id,
        distance_grid=[float(g) for g in grid],
        elapsed_s=elapsed_interp,
        latlng=latlng_interp,
        altitude=altitude_interp,
        heartrate=hr_interp,
        cadence=cad_interp,
        velocity=vel_interp,
    )


def normalized_stream_to_dict(ns: NormalizedStream) -> dict:
    """Serialise NormalizedStream for storage in stream_json column."""
    return {
        "label": ns.label,
        "is_primary": ns.is_primary,
        "activity_id": ns.activity_id,
        "distance_grid": ns.distance_grid,
        "elapsed_s": ns.elapsed_s,
        "latlng": [list(p) if p else None for p in ns.latlng]
        if ns.latlng
        else None,
        "altitude": ns.altitude,
        "heartrate": ns.heartrate,
        "cadence": ns.cadence,
        "velocity": ns.velocity,
    }


def normalized_stream_from_dict(d: dict) -> NormalizedStream:
    """Deserialise NormalizedStream from stored dict."""
    latlng = d.get("latlng")
    if latlng:
        latlng = [tuple(p) if p else None for p in latlng]
    return NormalizedStream(
        label=d["label"],
        is_primary=d["is_primary"],
        activity_id=d.get("activity_id"),
        distance_grid=d["distance_grid"],
        elapsed_s=d["elapsed_s"],
        latlng=latlng,
        altitude=d.get("altitude"),
        heartrate=d.get("heartrate"),
        cadence=d.get("cadence"),
        velocity=d.get("velocity"),
    )


# ---------------------------------------------------------------------------
# Alignment — build a common distance grid across all athletes
# ---------------------------------------------------------------------------


def build_common_grid(
    athletes: list[NormalizedStream], step_m: float = 50.0
) -> list[float]:
    """Return a coarser shared grid for gap computation.

    Uses the minimum total distance so all athletes have coverage.
    """
    if not athletes:
        return []
    min_dist = min(ns.distance_grid[-1] for ns in athletes if ns.distance_grid)
    return [
        i * step_m
        for i in range(int(min_dist / step_m) + 1)
        if i * step_m <= min_dist
    ]


def elapsed_at_distance(ns: NormalizedStream, target_m: float) -> float | None:
    """Return elapsed seconds at target_m for a NormalizedStream."""
    grid = ns.distance_grid
    elapsed = ns.elapsed_s
    if not grid:
        return None
    return _interp(grid, elapsed, target_m)


# ---------------------------------------------------------------------------
# Gap series
# ---------------------------------------------------------------------------


def compute_gap_series(
    athletes: list[NormalizedStream],
    step_m: float = 50.0,
) -> dict[str, list[dict]]:
    """Compute gap series for each athlete relative to the leader at each grid point.

    Returns {athlete_label: [{distance_km, time_s, gap_to_leader_s, position}]}.
    `gap_to_leader_s` is the elapsed-time difference between the athlete and the
    leader at the same race distance — the same definition used by event detection.
    """
    primary = next((a for a in athletes if a.is_primary), athletes[0]) if athletes else None
    course = _build_course_polyline(primary.latlng, primary.distance_grid) if primary else None
    progress_series = {ns.label: _map_stream_to_course_progress(ns, course) for ns in athletes}
    max_common_m = min(
        (series[-1] for series in progress_series.values() if series),
        default=0.0,
    )
    if max_common_m <= 0:
        return {ns.label: [] for ns in athletes}
    grid = [i * step_m for i in range(int(max_common_m // step_m) + 1)]
    if not grid:
        return {ns.label: [] for ns in athletes}

    result: dict[str, list[dict]] = {ns.label: [] for ns in athletes}

    for g_m in grid:
        # Elapsed times at this distance for all athletes
        times: dict[str, float] = {}
        for ns in athletes:
            t = _interp_monotonic_y_at_x(progress_series[ns.label], ns.elapsed_s, g_m)
            if t is not None:
                times[ns.label] = t

        if not times:
            continue

        leader_time = min(times.values())
        sorted_labels = sorted(times.keys(), key=lambda lbl: times[lbl])

        for rank_0, label in enumerate(sorted_labels):
            t = times[label]
            gap_s = t - leader_time

            result[label].append(
                {
                    "distance_km": round(g_m / 1000, 3),
                    "time_s": round(t, 1),
                    "gap_to_leader_s": round(gap_s, 1),
                    "position": rank_0 + 1,
                }
            )

    return result


# ---------------------------------------------------------------------------
# Replay frames — authoritative timeline computed server-side
# ---------------------------------------------------------------------------


REPLAY_FRAME_SCHEMA_V = 4


def _interp_by_elapsed(
    elapsed_s: list[float],
    distance_grid: list[float],
    t: float,
) -> tuple[int, int, float, float]:
    """Binary-search elapsed_s for time t; return (lo, hi, frac, dist_m).

    dist_m is interpolated along distance_grid using the same fractional index.
    """
    n = len(elapsed_s)
    if n == 0:
        return (0, 0, 0.0, 0.0)
    if t <= elapsed_s[0]:
        return (0, 0, 0.0, distance_grid[0] if distance_grid else 0.0)
    if t >= elapsed_s[-1]:
        last = n - 1
        return (last, last, 0.0, distance_grid[last] if distance_grid else 0.0)
    lo, hi = 0, n - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if elapsed_s[mid] <= t:
            lo = mid
        else:
            hi = mid
    span = elapsed_s[hi] - elapsed_s[lo]
    frac = (t - elapsed_s[lo]) / span if span > 0 else 0.0
    if distance_grid:
        dist_m = distance_grid[lo] + frac * (distance_grid[hi] - distance_grid[lo])
    else:
        dist_m = 0.0
    return (lo, hi, frac, dist_m)


def _build_course_polyline(
    latlng: list[tuple[float, float] | None] | None,
    distance_grid: list[float] | None,
) -> dict | None:
    """Convert the primary athlete's track into a projection-ready polyline.

    Returns ``{xy, cum_m, lat0, lon0, cos_lat0}`` (local equirectangular metres
    plus the cumulative distance from the primary's distance grid), or
    ``None`` when there are fewer than two valid GPS samples.

    Pairing the polyline samples with the primary's *recorded* cumulative
    distance (rather than re-summing haversine segments) means the projection
    returns values directly comparable to the primary's distance grid.
    """
    if not latlng or not distance_grid:
        return None
    pairs: list[tuple[tuple[float, float], float]] = []
    for i, p in enumerate(latlng):
        if p is None or i >= len(distance_grid):
            continue
        pairs.append((p, distance_grid[i]))
    if len(pairs) < 2:
        return None
    R = 6_371_000.0
    lat0, lon0 = pairs[0][0]
    lat0_rad = math.radians(lat0)
    cos_lat0 = math.cos(lat0_rad)
    xy = [
        (math.radians(lon - lon0) * R * cos_lat0, math.radians(lat - lat0) * R)
        for ((lat, lon), _d) in pairs
    ]
    cum_m = [d for (_p, d) in pairs]
    return {
        "xy": xy,
        "cum_m": cum_m,
        "lat0": lat0,
        "lon0": lon0,
        "cos_lat0": cos_lat0,
        "total_m": cum_m[-1],
    }


def _project_onto_course(
    lat: float,
    lon: float,
    course: dict,
    min_course_m: float | None = None,
    max_course_m: float | None = None,
    hint_course_m: float | None = None,
) -> float:
    """Project (lat, lon) onto the canonical course polyline; return course_m.

    Iterates every segment and keeps the foot with the smallest perpendicular
    distance. ``course_m`` is the cumulative distance along the polyline at
    that foot, so it represents course progress regardless of where each
    athlete pressed Start.

    When a plausible course-progress window or hint is provided, projection is
    continuity-aware: this prevents points on out-and-backs or tightly packed
    switchbacks from snapping to the wrong nearby segment and causing the
    leaderboard to jump around.
    """
    xy = course["xy"]
    cum_m = course["cum_m"]
    if len(xy) < 2:
        return 0.0
    R = 6_371_000.0
    px = math.radians(lon - course["lon0"]) * R * course["cos_lat0"]
    py = math.radians(lat - course["lat0"]) * R
    best_d2 = float("inf")
    best_course_m = 0.0

    def _score_candidate(d2: float, course_m: float) -> float:
        if hint_course_m is None:
            return d2
        deviation_m = course_m - hint_course_m
        return d2 + deviation_m * deviation_m * 0.001

    for i in range(len(xy) - 1):
        seg_start = cum_m[i]
        seg_end = cum_m[i + 1]
        seg_min = min(seg_start, seg_end)
        seg_max = max(seg_start, seg_end)
        if min_course_m is not None and seg_max < min_course_m:
            continue
        if max_course_m is not None and seg_min > max_course_m:
            continue
        ax, ay = xy[i]
        bx, by = xy[i + 1]
        dx = bx - ax
        dy = by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq <= 1e-9:
            t = 0.0
        else:
            t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        d2 = (px - proj_x) ** 2 + (py - proj_y) ** 2
        course_m = cum_m[i] + t * (cum_m[i + 1] - cum_m[i])
        if min_course_m is not None and course_m < min_course_m:
            continue
        if max_course_m is not None and course_m > max_course_m:
            continue
        score = _score_candidate(d2, course_m)
        if score < best_d2:
            best_d2 = score
            best_course_m = course_m
    if best_d2 != float("inf"):
        return best_course_m
    if min_course_m is not None or max_course_m is not None or hint_course_m is not None:
        return _project_onto_course(lat, lon, course)
    return best_course_m


def _interp_value(
    arr: list[float | None] | None,
    lo: int,
    hi: int,
    frac: float,
) -> float | None:
    """Linearly interpolate an aligned sample array."""
    if not arr:
        return None
    v_lo = arr[lo] if lo < len(arr) else None
    v_hi = arr[hi] if hi < len(arr) else None
    if v_lo is None and v_hi is None:
        return None
    if v_hi is None:
        return v_lo
    if v_lo is None:
        return v_hi
    return v_lo + frac * (v_hi - v_lo)


def _bearing_deg(
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> float | None:
    """Initial bearing from ``p1`` to ``p2`` in degrees [0, 360)."""
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    d_lon = lon2 - lon1
    y = math.sin(d_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        return None
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _bearing_diff_deg(a: float | None, b: float | None) -> float:
    """Smallest absolute difference between two bearings in degrees."""
    if a is None or b is None:
        return 0.0
    diff = abs(a - b) % 360.0
    return min(diff, 360.0 - diff)


def _projection_candidates(
    lat: float,
    lon: float,
    course: dict,
    max_candidates: int = 8,
    dedupe_window_m: float = 15.0,
) -> list[tuple[float, float, float | None]]:
    """Return candidate ``(course_m, lateral_m, segment_bearing_deg)``.

    We keep several nearby branches of the course instead of only the single
    nearest point. Loop courses often bring the start, finish, and mid-race
    sections physically close together, so the correct map-match must be chosen
    from the full path context, not from one point in isolation.
    """
    xy = course["xy"]
    cum_m = course["cum_m"]
    if len(xy) < 2:
        return []

    R = 6_371_000.0
    px = math.radians(lon - course["lon0"]) * R * course["cos_lat0"]
    py = math.radians(lat - course["lat0"]) * R
    raw_candidates: list[tuple[float, float, float | None]] = []
    for i in range(len(xy) - 1):
        ax, ay = xy[i]
        bx, by = xy[i + 1]
        dx = bx - ax
        dy = by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq <= 1e-9:
            t = 0.0
        else:
            t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        lateral_m = math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)
        course_m = cum_m[i] + t * (cum_m[i + 1] - cum_m[i])
        seg_bearing = _bearing_deg(
            (course["lat0"] + math.degrees(ay / R), course["lon0"] + math.degrees(ax / (R * course["cos_lat0"]))),
            (course["lat0"] + math.degrees(by / R), course["lon0"] + math.degrees(bx / (R * course["cos_lat0"]))),
        )
        raw_candidates.append((course_m, lateral_m, seg_bearing))

    raw_candidates.sort(key=lambda item: item[1])
    deduped: list[tuple[float, float, float | None]] = []
    for course_m, lateral_m, seg_bearing in raw_candidates:
        if any(abs(course_m - existing_cm) <= dedupe_window_m for existing_cm, _, _ in deduped):
            continue
        deduped.append((course_m, lateral_m, seg_bearing))
        if len(deduped) >= max_candidates:
            break
    return deduped


def _map_stream_to_course_progress(
    ns: NormalizedStream,
    course: dict | None,
) -> list[float]:
    """Map an athlete's whole track onto the primary course once.

    Returns a monotonic ``course_m`` series aligned to ``ns.distance_grid``.
    This avoids frame-by-frame rematching, which is what causes leader flips on
    nearby parallel geometry, out-and-backs, and switchbacks.
    """
    if not ns.distance_grid:
        return []
    if ns.is_primary:
        return list(ns.distance_grid)
    if course is None or not ns.latlng:
        return list(ns.distance_grid)

    candidate_lists: list[list[tuple[float, float, float | None]]] = []
    for latlon in ns.latlng:
        if latlon is None:
            candidate_lists.append([])
        else:
            candidate_lists.append(_projection_candidates(latlon[0], latlon[1], course))

    states: list[list[tuple[float, float, float | None]]] = []
    backptr: list[list[int | None]] = []
    prev_state_idx: int | None = None

    for i, latlon in enumerate(ns.latlng):
        candidates = candidate_lists[i]
        if latlon is None or not candidates:
            if states:
                states.append(states[-1])
                backptr.append([prev_state_idx] * len(states[-1]))
            else:
                states.append([(0.0, 0.0, None)])
                backptr.append([None])
            continue

        cur_costs: list[tuple[float, float, float | None]] = []
        cur_backptr: list[int | None] = []
        if not states or not candidate_lists[i - 1]:
            for course_m, lateral_m, seg_bearing in candidates:
                # Mild prior toward earlier course positions when two branches
                # are similarly close in space, which disambiguates start/finish
                # overlap without preventing legitimate later start points.
                start_cost = lateral_m + (course_m / 1000.0)
                cur_costs.append((course_m, start_cost, seg_bearing))
                cur_backptr.append(None)
        else:
            prev_latlon = ns.latlng[i - 1]
            step_m = _haversine_m(prev_latlon, latlon) if prev_latlon is not None else 0.0
            move_bearing = _bearing_deg(prev_latlon, latlon) if prev_latlon is not None else None
            max_forward_m = max(80.0, step_m * 3.0 + 20.0)
            for course_m, lateral_m, seg_bearing in candidates:
                best_cost = float("inf")
                best_prev_idx: int | None = None
                for prev_idx, (prev_course_m, prev_cost, _prev_seg_bearing) in enumerate(states[-1]):
                    delta_m = course_m - prev_course_m
                    if delta_m < -20.0:
                        continue
                    if delta_m > max_forward_m:
                        continue
                    heading_penalty = _bearing_diff_deg(move_bearing, seg_bearing) * 0.35
                    transition_cost = lateral_m + abs(delta_m - step_m) * 0.25 + heading_penalty
                    total_cost = prev_cost + transition_cost
                    if total_cost < best_cost:
                        best_cost = total_cost
                        best_prev_idx = prev_idx
                if best_prev_idx is None:
                    continue
                cur_costs.append((course_m, best_cost, seg_bearing))
                cur_backptr.append(best_prev_idx)

        if not cur_costs:
            prev_course_m = states[-1][prev_state_idx][0] if states and prev_state_idx is not None else 0.0
            prev_cost = states[-1][prev_state_idx][1] if states and prev_state_idx is not None else 0.0
            prev_seg_bearing = states[-1][prev_state_idx][2] if states and prev_state_idx is not None else None
            states.append([(prev_course_m, prev_cost + 500.0, prev_seg_bearing)])
            backptr.append([prev_state_idx])
            prev_state_idx = 0
            continue

        states.append(cur_costs)
        backptr.append(cur_backptr)
        prev_state_idx = min(range(len(cur_costs)), key=lambda idx: cur_costs[idx][1])

    if not states:
        return list(ns.distance_grid)

    final_idx = min(range(len(states[-1])), key=lambda idx: states[-1][idx][1])
    mapped_rev: list[float] = []
    cur_idx: int | None = final_idx
    for i in range(len(states) - 1, -1, -1):
        if cur_idx is None:
            mapped_rev.append(mapped_rev[-1] if mapped_rev else 0.0)
            continue
        mapped_rev.append(states[i][cur_idx][0])
        next_idx = backptr[i][cur_idx] if i < len(backptr) and cur_idx < len(backptr[i]) else None
        cur_idx = next_idx

    mapped = list(reversed(mapped_rev))
    for i in range(1, len(mapped)):
        if mapped[i] < mapped[i - 1]:
            mapped[i] = mapped[i - 1]
    return mapped


def compute_replay_frames(
    athletes: list[NormalizedStream],
    time_step_s: float = 5.0,
) -> list[dict]:
    """Build a time-indexed replay timeline from normalised streams.

    Each frame carries a time-aligned snapshot for every athlete (preserving
    input order) with server-computed rank and course progress. The frontend
    simply renders what it receives — no interpolation or ranking client-side.

    Frame shape:
        {
          "t_s": float,
          "athletes": [
            {"lat", "lon", "course_m", "vel", "hr", "rank", "gap_m", "gap_geo_m"},
            ...
          ]
        }

    `course_m` is each athlete's *projected progress* along the primary
    athlete's recorded track. The interpolated GPS position at this instant is
    projected perpendicular onto that polyline and the cumulative course
    distance at the foot is taken as their progress. This makes ranking match
    visual position on the map even when athletes started recording at
    different points on the course or with different warmup padding.

    `gap_m` is leader's `course_m` minus this athlete's `course_m` (along-route
    progress gap). `gap_geo_m` is the great-circle (haversine) distance
    between the leader's and the athlete's interpolated GPS coordinates at
    this instant — the value the F1-style leaderboard renders so it matches
    what's visible on the map.
    """
    if not athletes or time_step_s <= 0:
        return []

    max_time = 0.0
    for ns in athletes:
        if ns.elapsed_s:
            max_time = max(max_time, ns.elapsed_s[-1])
    if max_time <= 0:
        return []

    primary = next((a for a in athletes if a.is_primary), athletes[0])
    course = _build_course_polyline(primary.latlng, primary.distance_grid)
    course_progress_series = [
        _map_stream_to_course_progress(ns, course) for ns in athletes
    ]
    prev_ranks: list[int | None] = [None] * len(athletes)

    frames: list[dict] = []
    t = 0.0
    # Guard against runaway loops on absurdly long races
    while t <= max_time + 1e-6:
        per_athlete: list[dict] = []
        ranking_state: list[dict] = []
        for athlete_idx, ns in enumerate(athletes):
            if not ns.elapsed_s or not ns.distance_grid:
                entry = {
                    "lat": None,
                    "lon": None,
                    "course_m": 0.0,
                    "vel": None,
                    "hr": None,
                    "rank": None,
                    "gap_m": 0.0,
                    "gap_geo_m": 0.0,
                }
                per_athlete.append(entry)
                ranking_state.append({"course_m_exact": 0.0, "course_m_rate": 0.0, "prev_rank": prev_ranks[athlete_idx]})
                continue

            lo, hi, frac, dist_m = _interp_by_elapsed(ns.elapsed_s, ns.distance_grid, t)

            lat = lon = None
            if ns.latlng and ns.latlng[lo] is not None:
                if hi != lo and ns.latlng[hi] is not None:
                    a = ns.latlng[lo]
                    b = ns.latlng[hi]
                    lat = a[0] + frac * (b[0] - a[0])
                    lon = a[1] + frac * (b[1] - a[1])
                else:
                    lat, lon = ns.latlng[lo]

            course_m = _interp_value(course_progress_series[athlete_idx], lo, hi, frac)
            if course_m is None:
                course_m = dist_m

            vel = _interp_value(ns.velocity, lo, hi, frac)
            hr = _interp_value(ns.heartrate, lo, hi, frac)
            course_m_lo = (
                course_progress_series[athlete_idx][lo]
                if lo < len(course_progress_series[athlete_idx])
                else course_m
            )
            course_m_hi = (
                course_progress_series[athlete_idx][hi]
                if hi < len(course_progress_series[athlete_idx])
                else course_m
            )
            elapsed_lo = ns.elapsed_s[lo] if lo < len(ns.elapsed_s) else t
            elapsed_hi = ns.elapsed_s[hi] if hi < len(ns.elapsed_s) else t
            dt = elapsed_hi - elapsed_lo
            course_rate = (
                (course_m_hi - course_m_lo) / dt
                if hi != lo and dt > 1e-6
                else (vel if vel is not None else 0.0)
            )

            entry = {
                "lat": round(lat, 6) if lat is not None else None,
                "lon": round(lon, 6) if lon is not None else None,
                "course_m": round(course_m, 1),
                "vel": round(vel, 3) if vel is not None else None,
                "hr": round(hr, 1) if hr is not None else None,
                "rank": None,
                "gap_m": 0.0,
                "gap_geo_m": 0.0,
            }
            per_athlete.append(entry)
            ranking_state.append(
                {
                    "course_m_exact": course_m,
                    "course_m_rate": course_rate or 0.0,
                    "prev_rank": prev_ranks[athlete_idx],
                }
            )

        # Rank by course_m descending; leader = rank 1
        order = sorted(
            range(len(per_athlete)),
            key=lambda i: (
                -ranking_state[i]["course_m_exact"],
                -ranking_state[i]["course_m_rate"],
                ranking_state[i]["prev_rank"] if ranking_state[i]["prev_rank"] is not None else 10_000,
                i,
            ),
        )
        leader_idx = order[0] if order else None
        leader_course_exact = (
            ranking_state[leader_idx]["course_m_exact"] if leader_idx is not None else 0.0
        )
        leader_lat = per_athlete[leader_idx]["lat"] if leader_idx is not None else None
        leader_lon = per_athlete[leader_idx]["lon"] if leader_idx is not None else None
        for pos, idx in enumerate(order):
            per_athlete[idx]["rank"] = pos + 1
            prev_ranks[idx] = pos + 1
            gap = leader_course_exact - ranking_state[idx]["course_m_exact"]
            per_athlete[idx]["gap_m"] = round(max(0.0, gap), 1)
            a_lat = per_athlete[idx]["lat"]
            a_lon = per_athlete[idx]["lon"]
            if (
                leader_lat is not None
                and leader_lon is not None
                and a_lat is not None
                and a_lon is not None
            ):
                geo_m = _haversine_m((leader_lat, leader_lon), (a_lat, a_lon))
                per_athlete[idx]["gap_geo_m"] = round(geo_m, 1)
            else:
                per_athlete[idx]["gap_geo_m"] = 0.0

        frames.append(
            {
                "schema_v": REPLAY_FRAME_SCHEMA_V,
                "t_s": round(t, 2),
                "athletes": per_athlete,
            }
        )
        t += time_step_s

    return frames


def compute_delta_series(
    gap_series: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """Derivative of gap series: positive = gaining on leader, negative = losing.

    Returns {athlete_label: [{distance_km, delta_s_per_km}]}
    """
    result: dict[str, list[dict]] = {}
    for label, series in gap_series.items():
        deltas: list[dict] = []
        for i in range(1, len(series)):
            prev = series[i - 1]
            curr = series[i]
            d_dist = curr["distance_km"] - prev["distance_km"]
            if d_dist == 0:
                continue
            # Negative = gap closing = gaining; flip sign for intuitive display
            d_gap = prev["gap_to_leader_s"] - curr["gap_to_leader_s"]
            deltas.append(
                {
                    "distance_km": curr["distance_km"],
                    "delta_s_per_km": round(d_gap / d_dist, 2),
                }
            )
        result[label] = deltas
    return result


# ---------------------------------------------------------------------------
# Segment detection
# ---------------------------------------------------------------------------


def detect_segments_from_km_segments(
    km_segments: list[dict],
    climb_threshold_pct: float = 3.0,
    descent_threshold_pct: float = -3.0,
    min_length_km: float = 0.2,
) -> list[DetectedSegment]:
    """Build DetectedSegments from a RaceCourse's km_segments list.

    km_segments format: [{km, distance_m, elevation_gain_m, grade, bearing}, ...]
    """
    if not km_segments:
        return []

    segments: list[DetectedSegment] = []
    seg_start_km = km_segments[0].get("km", 0.0)
    seg_grade_sum = 0.0
    seg_count = 0
    seg_type: str | None = None

    def _grade_type(grade: float) -> str:
        if grade >= climb_threshold_pct:
            return "climb"
        if grade <= descent_threshold_pct:
            return "descent"
        return "flat"

    for i, seg in enumerate(km_segments):
        km = seg.get("km", i)
        grade = seg.get("grade", 0.0)
        gtype = _grade_type(grade)

        if seg_type is None:
            seg_type = gtype
            seg_start_km = km - 1.0  # km_segments[0].km == 1.0 for first km

        if gtype != seg_type:
            # Flush current segment
            avg_grade = seg_grade_sum / seg_count if seg_count else 0.0
            seg_end_km = km - 1.0
            if seg_end_km - seg_start_km >= min_length_km:
                label = f"{seg_type.title()} {seg_start_km:.1f}–{seg_end_km:.1f} km"
                segments.append(
                    DetectedSegment(
                        label=label,
                        start_km=round(seg_start_km, 3),
                        end_km=round(seg_end_km, 3),
                        gradient_type=seg_type,
                        avg_grade_pct=round(avg_grade, 2),
                    )
                )
            seg_start_km = km - 1.0
            seg_grade_sum = grade
            seg_count = 1
            seg_type = gtype
        else:
            seg_grade_sum += grade
            seg_count += 1

    # Flush last segment
    if seg_type is not None and seg_count:
        avg_grade = seg_grade_sum / seg_count
        seg_end_km = km_segments[-1].get("km", len(km_segments))
        if seg_end_km - seg_start_km >= min_length_km:
            label = f"{seg_type.title()} {seg_start_km:.1f}–{seg_end_km:.1f} km"
            segments.append(
                DetectedSegment(
                    label=label,
                    start_km=round(seg_start_km, 3),
                    end_km=round(seg_end_km, 3),
                    gradient_type=seg_type,
                    avg_grade_pct=round(avg_grade, 2),
                )
            )

    return segments


def detect_segments_from_altitude(
    primary: NormalizedStream,
    window_m: float = 200.0,
    climb_threshold_pct: float = 3.0,
    descent_threshold_pct: float = -3.0,
    min_length_km: float = 0.2,
) -> list[DetectedSegment]:
    """Fallback segment detection from the primary athlete's altitude stream."""
    if not primary.altitude or not primary.distance_grid:
        return []

    grid = primary.distance_grid
    alt = primary.altitude
    step_m = grid[1] - grid[0] if len(grid) > 1 else 10.0
    window_pts = max(1, int(window_m / step_m))

    # Compute grade per grid point using rolling window
    grades: list[float] = []
    for i in range(len(grid)):
        lo = max(0, i - window_pts // 2)
        hi = min(len(grid) - 1, i + window_pts // 2)
        if hi == lo:
            grades.append(0.0)
            continue
        d_alt = (alt[hi] or 0.0) - (alt[lo] or 0.0)
        d_dist = grid[hi] - grid[lo]
        grade = (d_alt / d_dist) * 100.0 if d_dist > 0 else 0.0
        grades.append(grade)

    def _grade_type(grade: float) -> str:
        if grade >= climb_threshold_pct:
            return "climb"
        if grade <= descent_threshold_pct:
            return "descent"
        return "flat"

    segments: list[DetectedSegment] = []
    seg_start_idx = 0
    seg_type = _grade_type(grades[0])
    seg_grade_sum = grades[0]
    seg_count = 1

    for i in range(1, len(grades)):
        gtype = _grade_type(grades[i])
        if gtype != seg_type:
            avg_grade = seg_grade_sum / seg_count
            start_km = grid[seg_start_idx] / 1000
            end_km = grid[i - 1] / 1000
            if end_km - start_km >= min_length_km:
                label = f"{seg_type.title()} {start_km:.1f}–{end_km:.1f} km"
                segments.append(
                    DetectedSegment(
                        label=label,
                        start_km=round(start_km, 3),
                        end_km=round(end_km, 3),
                        gradient_type=seg_type,
                        avg_grade_pct=round(avg_grade, 2),
                    )
                )
            seg_start_idx = i
            seg_type = gtype
            seg_grade_sum = grades[i]
            seg_count = 1
        else:
            seg_grade_sum += grades[i]
            seg_count += 1

    # Flush last
    avg_grade = seg_grade_sum / seg_count if seg_count else 0.0
    start_km = grid[seg_start_idx] / 1000
    end_km = grid[-1] / 1000
    if end_km - start_km >= min_length_km:
        label = f"{seg_type.title()} {start_km:.1f}–{end_km:.1f} km"
        segments.append(
            DetectedSegment(
                label=label,
                start_km=round(start_km, 3),
                end_km=round(end_km, 3),
                gradient_type=seg_type,
                avg_grade_pct=round(avg_grade, 2),
            )
        )

    return segments


# ---------------------------------------------------------------------------
# Segment athlete metrics
# ---------------------------------------------------------------------------


def compute_segment_athlete_metrics(
    athletes: list[NormalizedStream],
    segments: list[DetectedSegment],
) -> dict[str, dict[str, dict]]:
    """Compute per-segment per-athlete metrics.

    Returns {segment_label: {athlete_label: {time_s, avg_pace_s_per_km, rank,
                                              time_vs_leader_s}}}
    """
    result: dict[str, dict[str, dict]] = {}
    primary = next((a for a in athletes if a.is_primary), athletes[0]) if athletes else None
    course = _build_course_polyline(primary.latlng, primary.distance_grid) if primary else None
    progress_series = {ns.label: _map_stream_to_course_progress(ns, course) for ns in athletes}

    for seg in segments:
        start_m = seg.start_km * 1000
        end_m = seg.end_km * 1000
        seg_dist_km = seg.end_km - seg.start_km

        athlete_times: dict[str, float] = {}
        for ns in athletes:
            t_start = _interp_monotonic_y_at_x(progress_series[ns.label], ns.elapsed_s, start_m)
            t_end = _interp_monotonic_y_at_x(progress_series[ns.label], ns.elapsed_s, end_m)
            if t_start is not None and t_end is not None and t_end > t_start:
                athlete_times[ns.label] = t_end - t_start

        if not athlete_times:
            result[seg.label] = {}
            continue

        best_time = min(athlete_times.values())
        sorted_labels = sorted(athlete_times.keys(), key=lambda l: athlete_times[l])

        seg_metrics: dict[str, dict] = {}
        for rank_0, label in enumerate(sorted_labels):
            t = athlete_times[label]
            pace_s_per_km = (t / seg_dist_km) if seg_dist_km > 0 else None
            time_vs_leader_s = t - best_time
            seg_metrics[label] = {
                "time_s": round(t, 1),
                "avg_pace_s_per_km": round(pace_s_per_km, 1) if pace_s_per_km else None,
                "rank": rank_0 + 1,
                "time_vs_leader_s": round(time_vs_leader_s, 1),
            }
        result[seg.label] = seg_metrics

    return result


# ---------------------------------------------------------------------------
# Overall athlete metrics
# ---------------------------------------------------------------------------


def compute_athlete_metrics(ns: NormalizedStream) -> dict:
    """Compute summary metrics for a single athlete."""
    if not ns.elapsed_s or not ns.distance_grid:
        return {}

    total_time_s = ns.elapsed_s[-1]
    total_dist_km = ns.distance_grid[-1] / 1000
    avg_pace_s_per_km = (total_time_s / total_dist_km) if total_dist_km > 0 else None

    # Average HR
    valid_hr = [h for h in (ns.heartrate or []) if h is not None]
    avg_hr = round(statistics.mean(valid_hr), 1) if valid_hr else None

    # Cadence std dev
    valid_cad = [c for c in (ns.cadence or []) if c is not None]
    cad_std = round(statistics.stdev(valid_cad), 2) if len(valid_cad) > 1 else None

    # HR drift ratio: compare avg HR in second half vs first half
    hr_drift_ratio = None
    if valid_hr and len(valid_hr) > 10:
        mid = len(valid_hr) // 2
        first_half_hr = statistics.mean(valid_hr[:mid])
        second_half_hr = statistics.mean(valid_hr[mid:])
        hr_drift_ratio = round(second_half_hr / first_half_hr, 3) if first_half_hr > 0 else None

    # Pace variability index
    valid_vel = [v for v in (ns.velocity or []) if v is not None and v > 0]
    pace_variability = None
    if len(valid_vel) > 1:
        mean_vel = statistics.mean(valid_vel)
        std_vel = statistics.stdev(valid_vel)
        pace_variability = round(std_vel / mean_vel, 3) if mean_vel > 0 else None

    return {
        "total_time_s": round(total_time_s, 1),
        "total_dist_km": round(total_dist_km, 3),
        "avg_pace_s_per_km": round(avg_pace_s_per_km, 1) if avg_pace_s_per_km else None,
        "avg_hr_bpm": avg_hr,
        "cadence_std": cad_std,
        "hr_drift_ratio": hr_drift_ratio,
        "pace_variability_index": pace_variability,
    }


# ---------------------------------------------------------------------------
# Event detection
# ---------------------------------------------------------------------------


def detect_events(
    athletes: list[NormalizedStream],
    gap_series: dict[str, list[dict]],
) -> list[RaceEvent]:
    """Rules-based event detection across all athletes.

    Events: surge | drop | bridge | fade | final_sprint | separation
    """
    events: list[RaceEvent] = []
    primary = next((a for a in athletes if a.is_primary), athletes[0]) if athletes else None
    course = _build_course_polyline(primary.latlng, primary.distance_grid) if primary else None
    progress_series = {ns.label: _map_stream_to_course_progress(ns, course) for ns in athletes}

    for ns in athletes:
        if not ns.velocity or not ns.distance_grid or len(ns.velocity) < 20:
            continue

        progress = progress_series.get(ns.label, ns.distance_grid)
        total_dist_m = progress[-1] if progress else ns.distance_grid[-1]
        _detect_surges(ns, progress, events)
        _detect_fade(ns, progress, events)
        _detect_final_sprint(ns, progress, events, total_dist_m)

    # Gap-based events (require at least 2 athletes)
    if len(athletes) > 1:
        for ns in athletes:
            series = gap_series.get(ns.label, [])
            if not series:
                continue
            _detect_drops(ns, series, events)
            _detect_bridges(ns, series, events)
            _detect_separation(ns, series, events)

    # Sort by distance
    events.sort(key=lambda e: e.distance_km)
    return events


def _rolling_mean(values: list[float | None], center: int, half_window: int) -> float | None:
    lo = max(0, center - half_window)
    hi = min(len(values), center + half_window + 1)
    valid = [v for v in values[lo:hi] if v is not None]
    return statistics.mean(valid) if valid else None


def _detect_surges(
    ns: NormalizedStream,
    progress_m: list[float],
    events: list[RaceEvent],
) -> None:
    """Surge: pace increases >15% above 60s rolling average, sustained 20s+."""
    grid = progress_m if progress_m else ns.distance_grid
    vel = ns.velocity
    elapsed = ns.elapsed_s
    if not vel or len(vel) < 2:
        return

    # Approximate grid spacing in seconds
    dt_per_pt = (elapsed[-1] / len(elapsed)) if elapsed else 1.0
    window_60s_pts = max(1, int(60 / dt_per_pt))
    sustained_20s_pts = max(1, int(20 / dt_per_pt))

    in_surge = False
    surge_start_idx = 0

    for i in range(len(vel)):
        v = vel[i]
        if v is None:
            continue
        # Use backward-only window so the baseline doesn't include the surge itself
        lo = max(0, i - window_60s_pts)
        baseline_vals = [u for u in vel[lo:i] if u is not None]
        baseline = statistics.mean(baseline_vals) if baseline_vals else None
        if baseline is None or baseline <= 0:
            continue
        is_fast = v > baseline * 1.15

        if is_fast and not in_surge:
            in_surge = True
            surge_start_idx = i
        elif not is_fast and in_surge:
            in_surge = False
            surge_len = i - surge_start_idx
            if surge_len >= sustained_20s_pts:
                mid_idx = (surge_start_idx + i) // 2
                d_km = grid[mid_idx] / 1000
                t_s = elapsed[mid_idx]
                # Estimate time gained vs baseline pace
                baseline_t = (grid[i] - grid[surge_start_idx]) / baseline if baseline > 0 else 0
                actual_t = elapsed[i] - elapsed[surge_start_idx]
                gained = round(baseline_t - actual_t, 1)
                events.append(
                    RaceEvent(
                        event_type="surge",
                        athlete_label=ns.label,
                        distance_km=round(d_km, 2),
                        elapsed_s=round(t_s, 1),
                        impact_s=gained,
                        description=f"{ns.label} surged at km {d_km:.1f}, gaining ~{gained:.0f}s",
                    )
                )


def _detect_fade(
    ns: NormalizedStream,
    progress_m: list[float],
    events: list[RaceEvent],
) -> None:
    """Fade: 30s rolling pace degrades >10% in second half of race."""
    vel = ns.velocity
    elapsed = ns.elapsed_s
    grid = progress_m if progress_m else ns.distance_grid
    if not vel or len(vel) < 20:
        return

    mid = len(vel) // 2
    dt_per_pt = elapsed[-1] / len(elapsed) if elapsed else 1.0
    w = max(1, int(30 / dt_per_pt))

    first_half_speeds = [v for v in vel[:mid] if v is not None]
    if not first_half_speeds:
        return
    first_mean = statistics.mean(first_half_speeds)

    # Look for a sustained window in the second half where speed < 90% of first half
    for i in range(mid, len(vel)):
        win = [v for v in vel[max(mid, i - w) : i + 1] if v is not None]
        if not win:
            continue
        win_mean = statistics.mean(win)
        if win_mean < first_mean * 0.90:
            d_km = grid[i] / 1000
            t_s = elapsed[i]
            degradation_pct = round((1 - win_mean / first_mean) * 100, 1)
            events.append(
                RaceEvent(
                    event_type="fade",
                    athlete_label=ns.label,
                    distance_km=round(d_km, 2),
                    elapsed_s=round(t_s, 1),
                    impact_s=0.0,
                    description=f"{ns.label} faded at km {d_km:.1f} ({degradation_pct}% pace loss vs first half)",
                )
            )
            break  # One fade event per athlete


def _detect_final_sprint(
    ns: NormalizedStream,
    progress_m: list[float],
    events: list[RaceEvent],
    total_dist_m: float,
) -> None:
    """Final sprint: last 400m, pace >10% faster than race average."""
    vel = ns.velocity
    grid = progress_m if progress_m else ns.distance_grid
    elapsed = ns.elapsed_s
    if not vel or not grid:
        return

    sprint_start_m = total_dist_m - 400.0
    if sprint_start_m < 0:
        return

    # Average velocity over whole race
    valid_vel = [v for v in vel if v is not None and v > 0]
    if not valid_vel:
        return
    race_avg = statistics.mean(valid_vel)

    # Average velocity in last 400m
    sprint_vels = [
        v
        for d, v in zip(grid, vel)
        if d >= sprint_start_m and v is not None and v > 0
    ]
    if not sprint_vels:
        return
    sprint_avg = statistics.mean(sprint_vels)

    if sprint_avg > race_avg * 1.10:
        # Find index where sprint starts
        sprint_idx = next(
            (i for i, d in enumerate(grid) if d >= sprint_start_m), len(grid) - 1
        )
        d_km = grid[sprint_idx] / 1000
        t_s = elapsed[sprint_idx]
        events.append(
            RaceEvent(
                event_type="final_sprint",
                athlete_label=ns.label,
                distance_km=round(d_km, 2),
                elapsed_s=round(t_s, 1),
                impact_s=0.0,
                description=f"{ns.label} sprinted in the final 400m ({sprint_avg:.1f} m/s vs {race_avg:.1f} race avg)",
            )
        )


def _detect_drops(
    ns: NormalizedStream,
    series: list[dict],
    events: list[RaceEvent],
) -> None:
    """Drop: gap to leader increases >10s over 500m and continues growing."""
    window_km = 0.5
    threshold_s = 10.0

    for i, point in enumerate(series):
        if point["gap_to_leader_s"] == 0:
            continue  # leader
        # Find point ~500m earlier
        target_km = point["distance_km"] - window_km
        prev = next(
            (p for p in reversed(series[:i]) if p["distance_km"] <= target_km),
            None,
        )
        if prev is None:
            continue
        gap_increase = point["gap_to_leader_s"] - prev["gap_to_leader_s"]
        if gap_increase >= threshold_s:
            # Check it's still growing (look at one more point ahead)
            if i + 1 < len(series) and series[i + 1]["gap_to_leader_s"] > point["gap_to_leader_s"]:
                impact_s = round(-gap_increase, 1)
                events.append(
                    RaceEvent(
                        event_type="drop",
                        athlete_label=ns.label,
                        distance_km=point["distance_km"],
                        elapsed_s=point["time_s"],
                        impact_s=impact_s,
                        description=f"{ns.label} dropped {gap_increase:.0f}s over {window_km:.1f} km at km {point['distance_km']:.1f}",
                    )
                )
                break  # One drop event per detection window — avoid spam


def _detect_bridges(
    ns: NormalizedStream,
    series: list[dict],
    events: list[RaceEvent],
) -> None:
    """Bridge: gap decreases >10s over 500m."""
    window_km = 0.5
    threshold_s = 10.0

    last_bridge_km = -1.0  # prevent duplicate events

    for i, point in enumerate(series):
        if point["gap_to_leader_s"] == 0:
            continue  # leader can't bridge to itself
        target_km = point["distance_km"] - window_km
        prev = next(
            (p for p in reversed(series[:i]) if p["distance_km"] <= target_km),
            None,
        )
        if prev is None:
            continue
        gap_decrease = prev["gap_to_leader_s"] - point["gap_to_leader_s"]
        if gap_decrease >= threshold_s and point["distance_km"] - last_bridge_km > 1.0:
            impact_s = round(gap_decrease, 1)
            events.append(
                RaceEvent(
                    event_type="bridge",
                    athlete_label=ns.label,
                    distance_km=point["distance_km"],
                    elapsed_s=point["time_s"],
                    impact_s=impact_s,
                    description=f"{ns.label} bridged {gap_decrease:.0f}s over {window_km:.1f} km at km {point['distance_km']:.1f}",
                )
            )
            last_bridge_km = point["distance_km"]


def _detect_separation(
    ns: NormalizedStream,
    series: list[dict],
    events: list[RaceEvent],
) -> None:
    """Separation: first time an athlete falls >30s behind the leader."""
    threshold_s = 30.0
    already_detected = False

    for point in series:
        if already_detected:
            break
        if point["gap_to_leader_s"] >= threshold_s:
            events.append(
                RaceEvent(
                    event_type="separation",
                    athlete_label=ns.label,
                    distance_km=point["distance_km"],
                    elapsed_s=point["time_s"],
                    impact_s=round(-point["gap_to_leader_s"], 1),
                    description=f"{ns.label} fell {point['gap_to_leader_s']:.0f}s behind the leader at km {point['distance_km']:.1f}",
                )
            )
            already_detected = True


# ---------------------------------------------------------------------------
# GPX parsing
# ---------------------------------------------------------------------------


def parse_gpx_streams(gpx_content: str) -> dict[str, list]:
    """Parse a GPX file string and extract distance, time, latlng, altitude streams.

    Returns a dict compatible with normalize_stream().
    """
    ns_map = {
        "gpx": "http://www.topografix.com/GPX/1/1",
        "gpx10": "http://www.topografix.com/GPX/1/0",
    }

    root = ET.fromstring(gpx_content)
    ns = "http://www.topografix.com/GPX/1/1"
    if root.tag == "{http://www.topografix.com/GPX/1/0}gpx":
        ns = "http://www.topografix.com/GPX/1/0"

    trkpts = root.findall(f".//{{{ns}}}trkpt")
    if not trkpts:
        return {}

    import datetime as _dt

    latlng: list[list[float]] = []
    altitude: list[float | None] = []
    timestamps: list[_dt.datetime | None] = []

    for pt in trkpts:
        lat = float(pt.get("lat", 0))
        lon = float(pt.get("lon", 0))
        latlng.append([lat, lon])
        ele = pt.find(f"{{{ns}}}ele")
        altitude.append(float(ele.text) if ele is not None and ele.text else None)
        time_el = pt.find(f"{{{ns}}}time")
        if time_el is not None and time_el.text:
            try:
                ts = _dt.datetime.fromisoformat(time_el.text.replace("Z", "+00:00"))
                timestamps.append(ts)
            except ValueError:
                timestamps.append(None)
        else:
            timestamps.append(None)

    # Build distance array using haversine
    dist_m: list[float] = [0.0]
    for i in range(1, len(latlng)):
        d = _haversine_m(latlng[i - 1], latlng[i])
        dist_m.append(dist_m[-1] + d)

    # Build time array
    valid_ts = [t for t in timestamps if t is not None]
    time_s: list[float] = []
    if valid_ts and timestamps[0] is not None:
        t0 = timestamps[0]
        for ts in timestamps:
            if ts is not None:
                time_s.append((ts - t0).total_seconds())
            elif time_s:
                time_s.append(time_s[-1])
            else:
                time_s.append(0.0)
    else:
        # No timestamps — estimate from distance at 10 km/h
        time_s = [d / (10000 / 3600) for d in dist_m]

    return {
        "distance": dist_m,
        "time": time_s,
        "latlng": latlng,
        "altitude": altitude,
    }


def _haversine_m(
    p1: list[float] | tuple[float, float],
    p2: list[float] | tuple[float, float],
) -> float:
    """Haversine distance in metres between two [lat, lon] points."""
    R = 6_371_000.0
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# DB stream loading helpers (async — called by CLI/dashboard)
# ---------------------------------------------------------------------------


async def load_primary_streams(activity_id: int) -> dict[str, list] | None:
    """Load activity streams from local DB for the primary athlete.

    ``activity_id`` is the Strava activity ID.  Streams are stored keyed by the
    local DB ``Activity.id``, so we resolve the Strava ID first.

    Returns dict keyed by stream type (Strava names), or None if not found.
    """
    from sqlalchemy import select

    from fitops.db.models.activity import Activity
    from fitops.db.models.activity_stream import ActivityStream
    from fitops.db.session import get_async_session

    async with get_async_session() as session:
        act_result = await session.execute(
            select(Activity).where(Activity.strava_id == activity_id)
        )
        act = act_result.scalar_one_or_none()
        if act is None:
            return None
        internal_id = act.id

        result = await session.execute(
            select(ActivityStream).where(ActivityStream.activity_id == internal_id)
        )
        stream_rows = result.scalars().all()

    if not stream_rows:
        return None

    return {row.stream_type: row.data for row in stream_rows}


async def fetch_activity_companions(activity_id: int) -> list[dict]:
    """Return athletes who ran together in a Strava group activity.

    Parses the ``with_entries`` field from the full activity detail — only
    present for group runs where the companions follow/are followed by the
    authenticated athlete.  Returns [] on any failure or when the field is
    absent.

    Each entry: ``{"label": str, "activity_id": int}``
    """
    from fitops.strava.client import StravaClient

    try:
        client = StravaClient()
        detail = await client.get_activity(activity_id)
        with_entries = detail.get("with_entries") or []
        companions = []
        for entry in with_entries:
            athlete = entry.get("athlete") or {}
            firstname = athlete.get("firstname", "")
            lastname = athlete.get("lastname", "")
            label = f"{firstname} {lastname}".strip() or f"Athlete {athlete.get('id', '?')}"
            act_id = entry.get("id")
            if act_id:
                companions.append({"label": label, "activity_id": int(act_id)})
        return companions
    except Exception:
        return []


async def fetch_strava_comparison_streams(activity_id: int) -> dict[str, list] | None:
    """Fetch public activity streams via Strava API using primary athlete's token.

    Returns raw stream dict or None on failure.
    """
    from fitops.strava.client import StravaClient

    try:
        client = StravaClient()
        raw = await client.get_activity_streams(
            activity_id,
            keys=["time", "distance", "latlng", "altitude", "heartrate", "cadence", "velocity_smooth"],
        )
        if not raw:
            return None

        # Convert from {stream_type: {data: [...], ...}} to {stream_type: [...]}
        streams: dict[str, list] = {}
        for stream_type, payload in raw.items():
            if isinstance(payload, dict):
                streams[stream_type] = payload.get("data", [])
            elif isinstance(payload, list):
                streams[stream_type] = payload
        return streams
    except Exception:
        return None
