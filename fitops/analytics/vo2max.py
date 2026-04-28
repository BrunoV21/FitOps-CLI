from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.session import get_async_session

RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
VO2_AGE_DECLINE_RATE = 0.008
VO2_AGE_FACTOR_FLOOR = 0.5

# ---------------------------------------------------------------------------
# Effort qualification thresholds
# ---------------------------------------------------------------------------
# A VO2max estimate from pace alone is only meaningful when the athlete was
# working near or above lactate threshold — otherwise the pace-HR relationship
# is too noisy (cardiac drift, heat, fatigue) to extrapolate an aerobic ceiling.
#
# Primary threshold (LTHR known): avg HR must be >= 90% of LTHR.
#   At LTHR≈165 this means avg HR >= 149 — solidly in the threshold zone.
#   A Z2 run (avg HR ~75–80% of LTHR) correctly fails this test.
#
# Fallback (max HR only): avg HR >= 80% HRmax.
#   Equivalent to the Garmin/Firstbeat minimum qualifying floor.
_EFFORT_LTHR_RATIO = 0.90
_EFFORT_MAXHR_RATIO = 0.80


def _effort_qualifies(
    avg_hr: float | None,
    lthr: int | None,
    max_hr: int | None,
) -> tuple[bool, str]:
    """Return (qualifies, reason_string) for an activity's effort level."""
    if avg_hr is None:
        return False, "no_hr_data"
    if lthr is not None:
        floor = lthr * _EFFORT_LTHR_RATIO
        if avg_hr >= floor:
            return True, f"avg_hr {avg_hr:.0f} ≥ {floor:.0f} (90% LTHR)"
        return False, f"avg_hr {avg_hr:.0f} < {floor:.0f} (90% LTHR={lthr})"
    if max_hr is not None:
        floor = max_hr * _EFFORT_MAXHR_RATIO
        if avg_hr >= floor:
            return True, f"avg_hr {avg_hr:.0f} ≥ {floor:.0f} (80% HRmax)"
        return False, f"avg_hr {avg_hr:.0f} < {floor:.0f} (80% HRmax={max_hr})"
    return False, "no_hr_reference (set LTHR or HRmax in athlete settings)"


def apply_age_adjustment(estimate: float, age: int) -> tuple[float, float]:
    """Returns (age_adjusted_estimate, age_factor)."""
    age_factor = max(VO2_AGE_FACTOR_FLOOR, 1.0 - (age - 25) * VO2_AGE_DECLINE_RATE)
    return round(estimate * age_factor, 1), round(age_factor, 3)


def _daniels_vdot(distance_m: float, time_s: float) -> float | None:
    """
    Jack Daniels' VDOT — velocity-based VO2max estimate.
    Uses fractional utilization based on event duration.
    """
    if time_s <= 0 or distance_m < 1500:
        return None

    v = (distance_m / time_s) * 60  # m/min

    duration_min = time_s / 60
    if duration_min <= 3:
        frac = 1.0
    elif duration_min <= 10:
        frac = 0.98
    elif duration_min <= 20:
        frac = 0.96
    elif duration_min <= 40:
        frac = 0.94
    elif duration_min <= 60:
        frac = 0.92
    elif duration_min <= 120:
        frac = 0.88
    else:
        frac = 0.84

    vo2_demand = -4.6 + 0.182258 * v + 0.000104 * (v**2)
    vo2max = vo2_demand / frac
    return max(28.0, min(90.0, vo2max))


def _cooper_vo2max(distance_m: float, time_s: float) -> float | None:
    """Cooper 12-min test extrapolation (for efforts > 6 min)."""
    if time_s <= 0 or distance_m < 1500:
        return None
    dist_12min = distance_m * (720 / time_s)
    vo2max = (dist_12min - 504.9) / 44.73
    return max(28.0, min(90.0, vo2max))


# Keep old names as aliases so existing test imports don't break
def _vdot(distance_m: float, time_s: float) -> float | None:
    """Alias for _daniels_vdot for backward compatibility."""
    return _daniels_vdot(distance_m, time_s)


def _mcardle(distance_m: float, time_s: float) -> float | None:
    """Kept for backward compatibility; delegates to _cooper_vo2max."""
    return _cooper_vo2max(distance_m, time_s)


def _costill(distance_m: float, time_s: float) -> float | None:
    """Kept for backward compatibility; returns None (method removed)."""
    return None


def _confidence(distance_m: float, estimates: list[float]) -> float:
    c = 0.5
    if distance_m >= 5000:
        c += 0.2
    elif distance_m >= 3000:
        c += 0.1
    if len(estimates) >= 2:
        mean = sum(estimates) / len(estimates)
        if mean > 0:
            std = (sum((e - mean) ** 2 for e in estimates) / len(estimates)) ** 0.5
            cv = std / mean
            if cv < 0.1:
                c += 0.2
            elif cv < 0.2:
                c += 0.1
    return min(1.0, c)


@dataclass
class StreamSegment:
    duration_s: float
    distance_m: float  # grade-adjusted distance equivalent
    avg_speed_ms: float  # duration-weighted average grade-adjusted speed (m/s)


_MIN_SEGMENT_S = 600.0  # 10 minutes minimum continuous qualifying effort
_MIN_SPEED_MS = 0.5  # ignore near-stationary data points
_LT2_MIN_SPEED_MS = (
    2.0  # minimum speed for LT2 HR-zone sampling (filters recovery jogging)
)


@dataclass
class VO2MaxResult:
    estimate: float
    confidence: float
    vdot: float | None  # daniels_vdot estimate
    cooper: float | None  # cooper estimate
    activity_strava_id: int
    activity_name: str
    activity_date: str
    distance_km: float
    pace_per_km: str
    best_time_s: float = 0.0
    estimation_method: str = "summary"  # "summary" | "streams"
    measured_lt2_pace_s: float | None = (
        None  # sec/km, directly measured from stream HR/speed
    )

    @property
    def confidence_label(self) -> str:
        if self.confidence >= 0.8:
            return "High"
        elif self.confidence >= 0.6:
            return "Moderate"
        return "Low"


def _fmt_pace(speed_ms: float) -> str:
    if speed_ms <= 0:
        return "N/A"
    spk = 1000 / speed_ms
    return f"{int(spk // 60)}:{int(spk % 60):02d}"


def _estimate_from_activity(activity: Activity) -> VO2MaxResult | None:
    dist = activity.distance_m
    time_s = activity.moving_time_s
    if not dist or not time_s or dist < 1500:
        return None

    d_est = _daniels_vdot(dist, time_s)
    c_est = _cooper_vo2max(dist, time_s)

    # For distances >= 5km use Daniels 60% + Cooper 40%; for <5km use Daniels 100%
    if dist >= 5000:
        estimates = [e for e in [d_est, c_est] if e is not None]
        pairs = [(d_est, 0.60), (c_est, 0.40)]
    else:
        estimates = [e for e in [d_est] if e is not None]
        pairs = [(d_est, 1.0)]

    if not estimates:
        return None

    weighted = total_w = 0.0
    for est, w in pairs:
        if est is not None:
            weighted += est * w
            total_w += w
    if total_w == 0:
        return None

    return VO2MaxResult(
        estimate=round(weighted / total_w, 1),
        confidence=round(_confidence(dist, estimates), 2),
        vdot=round(d_est, 1) if d_est is not None else None,
        cooper=round(c_est, 1) if c_est is not None else None,
        activity_strava_id=activity.strava_id,
        activity_name=activity.name,
        activity_date=activity.start_date.date().isoformat()
        if activity.start_date
        else "unknown",
        distance_km=round(dist / 1000, 2),
        pace_per_km=_fmt_pace(activity.average_speed_ms)
        if activity.average_speed_ms
        else "N/A",
        best_time_s=float(time_s),
    )


def estimate_vo2max_from_stream_dict(
    activity: Activity,
    stream_data: dict,
    lthr: int | None,
    max_hr: int | None,
) -> VO2MaxResult | None:
    """Estimate VO2max from in-memory stream data — no DB queries required.

    ``stream_data`` is the raw dict returned by ``StravaClient.get_activity_streams``:
    each key maps to either ``{"data": [...], ...}`` or a plain list.

    Only run-type activities that qualify on effort (avg HR near threshold) are
    estimated; all others return ``None``.
    """
    if activity.sport_type not in RUN_TYPES:
        return None
    qualifies, _ = _effort_qualifies(activity.average_heartrate, lthr, max_hr)
    if not qualifies:
        return None

    def _get(key: str) -> list | None:
        obj = stream_data.get(key)
        if obj is None:
            return None
        return obj.get("data", []) if isinstance(obj, dict) else list(obj)

    hr_data = _get("heartrate")
    if not hr_data:
        return None
    speed_data = _get("grade_adjusted_speed") or _get("velocity_smooth")
    if not speed_data:
        return None
    time_data = _get("time")
    if not time_data:
        return None

    n = min(len(hr_data), len(speed_data), len(time_data))
    hr_data = hr_data[:n]
    speed_data = speed_data[:n]
    time_data = time_data[:n]

    if lthr is not None:
        min_hr = lthr * _EFFORT_LTHR_RATIO
        lt2_hr_floor = lthr * 0.97
    elif max_hr is not None:
        min_hr = max_hr * _EFFORT_MAXHR_RATIO
        lt2_hr_floor = max_hr * 0.85
    else:
        return None

    _LT_MIN_SAMPLES = 20
    lt2_speeds = [
        spd
        for hr, spd in zip(hr_data, speed_data, strict=False)
        if hr is not None
        and spd is not None
        and spd >= _LT2_MIN_SPEED_MS
        and hr >= lt2_hr_floor
    ]

    def _median_pace_s(speeds: list[float]) -> float | None:
        if len(speeds) < _LT_MIN_SAMPLES:
            return None
        sv = sorted(speeds)
        return round(1000.0 / sv[len(sv) // 2], 1)

    measured_lt2 = _median_pace_s(lt2_speeds)

    segments = _extract_high_intensity_segments(hr_data, time_data, speed_data, min_hr)
    if not segments:
        return None

    total_duration = sum(s.duration_s for s in segments)
    total_distance = sum(s.distance_m for s in segments)
    if total_distance < 1500:
        return None

    d_est = _daniels_vdot(total_distance, total_duration)
    c_est = _cooper_vo2max(total_distance, total_duration)

    if total_distance >= 5000:
        estimates = [e for e in [d_est, c_est] if e is not None]
        pairs: list[tuple] = [(d_est, 0.60), (c_est, 0.40)]
    else:
        estimates = [e for e in [d_est] if e is not None]
        pairs = [(d_est, 1.0)]

    if not estimates:
        return None

    weighted = total_w = 0.0
    for est, w in pairs:
        if est is not None:
            weighted += est * w
            total_w += w
    if total_w == 0:
        return None

    avg_v = total_distance / total_duration
    return VO2MaxResult(
        estimate=round(weighted / total_w, 1),
        confidence=round(_confidence(total_distance, estimates), 2),
        vdot=round(d_est, 1) if d_est is not None else None,
        cooper=round(c_est, 1) if c_est is not None else None,
        activity_strava_id=activity.strava_id,
        activity_name=activity.name,
        activity_date=activity.start_date.date().isoformat()
        if activity.start_date
        else "unknown",
        distance_km=round(total_distance / 1000, 2),
        pace_per_km=_fmt_pace(avg_v),
        best_time_s=float(total_duration),
        estimation_method="streams",
        measured_lt2_pace_s=measured_lt2,
    )


def _extract_high_intensity_segments(
    hr_data: list,
    time_data: list,
    speed_data: list,
    min_hr: float,
    min_duration_s: float = _MIN_SEGMENT_S,
    min_speed_ms: float = _MIN_SPEED_MS,
) -> list[StreamSegment]:
    """Extract contiguous high-intensity segments from stream data.

    A sample qualifies when HR >= min_hr, speed >= min_speed_ms, and dt > 0.
    Only segments of at least min_duration_s are returned.
    """
    segments: list[StreamSegment] = []
    n = len(hr_data)
    seg_time_s = 0.0
    seg_speed_x_time = 0.0

    def _flush():
        nonlocal seg_time_s, seg_speed_x_time
        if seg_time_s >= min_duration_s:
            avg_v = seg_speed_x_time / seg_time_s
            segments.append(
                StreamSegment(
                    duration_s=seg_time_s,
                    distance_m=avg_v * seg_time_s,
                    avg_speed_ms=avg_v,
                )
            )
        seg_time_s = 0.0
        seg_speed_x_time = 0.0

    for i in range(n - 1):
        hr = hr_data[i]
        spd = speed_data[i]
        dt = time_data[i + 1] - time_data[i]
        if (
            hr is not None
            and hr >= min_hr
            and spd is not None
            and spd >= min_speed_ms
            and dt > 0
        ):
            seg_time_s += dt
            seg_speed_x_time += spd * dt
        else:
            _flush()

    _flush()
    return segments


async def _estimate_from_streams(
    activity: Activity,
    session: AsyncSession,
    lthr: int | None,
    max_hr: int | None,
) -> VO2MaxResult | None:
    """Estimate VO2max using only high-intensity stream segments.

    Returns None if streams are missing, no qualifying segments found,
    or total qualifying distance < 1500 m.
    """
    # Load HR stream
    hr_res = await session.execute(
        select(ActivityStream).where(
            ActivityStream.activity_id == activity.id,
            ActivityStream.stream_type == "heartrate",
        )
    )
    hr_stream = hr_res.scalar_one_or_none()
    if hr_stream is None:
        return None

    # Load speed stream: prefer grade-adjusted, fallback to velocity_smooth
    gap_res = await session.execute(
        select(ActivityStream).where(
            ActivityStream.activity_id == activity.id,
            ActivityStream.stream_type == "grade_adjusted_speed",
        )
    )
    speed_stream = gap_res.scalar_one_or_none()
    if speed_stream is None:
        vel_res = await session.execute(
            select(ActivityStream).where(
                ActivityStream.activity_id == activity.id,
                ActivityStream.stream_type == "velocity_smooth",
            )
        )
        speed_stream = vel_res.scalar_one_or_none()
    if speed_stream is None:
        return None

    # Load time stream
    time_res = await session.execute(
        select(ActivityStream).where(
            ActivityStream.activity_id == activity.id,
            ActivityStream.stream_type == "time",
        )
    )
    time_stream = time_res.scalar_one_or_none()
    if time_stream is None:
        return None

    hr_data = hr_stream.data
    speed_data = speed_stream.data
    time_data = time_stream.data

    # Truncate to shortest stream to handle partial saves
    n = min(len(hr_data), len(speed_data), len(time_data))
    hr_data = hr_data[:n]
    speed_data = speed_data[:n]
    time_data = time_data[:n]

    # Compute min_hr threshold for segment extraction
    if lthr is not None:
        min_hr = lthr * _EFFORT_LTHR_RATIO
    elif max_hr is not None:
        min_hr = max_hr * _EFFORT_MAXHR_RATIO
    else:
        return None

    # Directly measure LT2 pace from full stream.
    # LT2: samples where HR >= 97% LTHR AND speed >= _LT2_MIN_SPEED_MS (excludes recovery jogging).
    # LT1 is NOT measured from streams — HR lag makes it unreliable (ascending-HR samples during
    # interval build-up are at interval pace, not aerobic pace). LT1 is always VDOT-derived.
    _LT_MIN_SAMPLES = 20
    if lthr is not None:
        lt2_hr_floor = lthr * 0.97
    else:
        lt2_hr_floor = max_hr * 0.85  # type: ignore[operator]

    lt2_speeds: list[float] = []
    for _hr, _spd in zip(hr_data, speed_data, strict=False):
        if _hr is None or _spd is None or _spd < _LT2_MIN_SPEED_MS:
            continue
        if _hr >= lt2_hr_floor:
            lt2_speeds.append(_spd)

    def _median_pace_s(speeds: list[float]) -> float | None:
        if len(speeds) < _LT_MIN_SAMPLES:
            return None
        sv = sorted(speeds)
        return round(1000.0 / sv[len(sv) // 2], 1)

    measured_lt2 = _median_pace_s(lt2_speeds)

    segments = _extract_high_intensity_segments(hr_data, time_data, speed_data, min_hr)
    if not segments:
        return None

    total_duration = sum(s.duration_s for s in segments)
    total_distance = sum(s.distance_m for s in segments)

    if total_distance < 1500:
        return None

    d_est = _daniels_vdot(total_distance, total_duration)
    c_est = _cooper_vo2max(total_distance, total_duration)

    if total_distance >= 5000:
        estimates = [e for e in [d_est, c_est] if e is not None]
        pairs = [(d_est, 0.60), (c_est, 0.40)]
    else:
        estimates = [e for e in [d_est] if e is not None]
        pairs = [(d_est, 1.0)]

    if not estimates:
        return None

    weighted = total_w = 0.0
    for est, w in pairs:
        if est is not None:
            weighted += est * w
            total_w += w
    if total_w == 0:
        return None

    avg_v = total_distance / total_duration

    return VO2MaxResult(
        estimate=round(weighted / total_w, 1),
        confidence=round(_confidence(total_distance, estimates), 2),
        vdot=round(d_est, 1) if d_est is not None else None,
        cooper=round(c_est, 1) if c_est is not None else None,
        activity_strava_id=activity.strava_id,
        activity_name=activity.name,
        activity_date=activity.start_date.date().isoformat()
        if activity.start_date
        else "unknown",
        distance_km=round(total_distance / 1000, 2),
        pace_per_km=_fmt_pace(avg_v),
        best_time_s=float(total_duration),
        estimation_method="streams",
        measured_lt2_pace_s=measured_lt2,
    )


async def estimate_vo2max(
    athlete_id: int, max_activities: int = 200
) -> VO2MaxResult | None:
    from fitops.analytics.athlete_settings import get_athlete_settings

    settings = get_athlete_settings()
    lthr = settings.lthr
    max_hr = settings.max_hr

    lookback = datetime.now(UTC) - timedelta(days=365)
    async with get_async_session() as session:
        stmt = (
            select(Activity)
            .where(
                Activity.manual.is_(False),
                Activity.athlete_id == athlete_id,
                Activity.sport_type.in_(list(RUN_TYPES)),
                Activity.start_date >= lookback,
                Activity.distance_m >= 1500,
                Activity.moving_time_s > 0,
            )
            .order_by(desc(Activity.start_date))
            .limit(max_activities)
        )
        result = await session.execute(stmt)
        activities = result.scalars().all()

        best: VO2MaxResult | None = None
        for activity in activities:
            # Only consider activities where the athlete was working near threshold.
            # Easy/Z2 runs produce unreliable VDOT estimates from pace alone.
            qualifies, _ = _effort_qualifies(activity.average_heartrate, lthr, max_hr)
            if not qualifies:
                continue
            est: VO2MaxResult | None = None
            if activity.streams_fetched:
                est = await _estimate_from_streams(activity, session, lthr, max_hr)
            if est is None:
                est = _estimate_from_activity(activity)
            if est is None:
                continue
            # Pick the activity with the highest VO2max estimate — that's the hardest effort
            # and the best signal for true aerobic ceiling. Confidence acts as a tiebreaker
            # only when estimates are within 1 ml/kg/min of each other.
            if (
                best is None
                or est.estimate > best.estimate + 1.0
                or (
                    abs(est.estimate - best.estimate) <= 1.0
                    and est.confidence > best.confidence
                )
            ):
                best = est
    return best


# ---------------------------------------------------------------------------
# Race Predictions
# ---------------------------------------------------------------------------

RIEGEL_EXP = 1.06
RACE_DISTANCES = {
    "5K": 5000.0,
    "10K": 10000.0,
    "Half": 21097.5,
    "Marathon": 42195.0,
}


def _riegel(d1_m: float, t1_s: float, d2_m: float) -> float:
    return t1_s * (d2_m / d1_m) ** RIEGEL_EXP


def _fmt_hms(total_s: float) -> str:
    h = int(total_s // 3600)
    m = int((total_s % 3600) // 60)
    s = int(total_s % 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_pace_from_s(time_s: float, dist_m: float) -> str:
    pace_s = time_s / (dist_m / 1000)
    return f"{int(pace_s // 60)}:{int(pace_s % 60):02d}"


# ---------------------------------------------------------------------------
# Rolling VO2max — ratchet model
# ---------------------------------------------------------------------------

# Minimum confidence for an activity to *update* the rolling estimate.
# confidence ≥ 0.6 requires distance ≥ 5 km plus consistent VDOT/Cooper agreement.
_QUALIFY_CONFIDENCE = 0.6

# After GRACE_DAYS of no qualifying effort, VO2max starts to decay.
_DECAY_GRACE_DAYS = 14

# Exponential decay rate per week beyond the grace period (~0.5%/week; full
# detraining is ~1-2%/week, regular easy training halves that).
_DECAY_RATE_PER_WEEK = 0.005

# How much of a qualifying activity's downward signal to absorb (0.2 = damped).
# Upward signals are absorbed fully.
_DECREASE_DAMPING = 0.2


def compute_vo2max_rolling(
    history: list[dict], initial: float | None = None
) -> list[dict]:
    """
    Apply a ratchet model to the per-activity VO2max history (oldest first).

    Rules:
    - Only "qualifying" activities (confidence ≥ 0.6, i.e. ≥5 km good-effort runs)
      can move the rolling estimate.
    - A qualifying activity raises the rolling value immediately and fully.
    - A qualifying activity that is lower than the current value only damps it down
      by DECREASE_DAMPING (20%) of the gap — a single easy 5km doesn't wipe fitness.
    - Non-qualifying activities (short, slow, easy) leave the rolling value unchanged.
    - After DECAY_GRACE_DAYS with no qualifying effort, the estimate decays at
      DECAY_RATE_PER_WEEK — modelling real detraining.

    Adds ``rolling_vo2max`` and ``is_qualifying`` to each entry in-place.
    Returns the same list.

    ``initial`` should be the athlete's known best VO2max estimate (e.g. from the
    all-time best qualifying effort).  This anchors the rolling value so it starts
    from peak fitness rather than from whichever easy run happens to be first in the
    selected time window.  When None the first qualifying activity bootstraps the value.
    """
    if not history:
        return history

    from datetime import date as _date

    def _parse(d: str) -> _date:
        try:
            return _date.fromisoformat(d)
        except ValueError:
            return _date.today()

    rolling: float | None = initial
    last_qualifying_date: _date | None = None

    for row in history:
        activity_date = _parse(row["date"])
        estimate = row.get("estimate", 0.0)
        confidence = row.get("confidence", 0.0)
        is_qualifying = confidence >= _QUALIFY_CONFIDENCE

        # Apply decay if we have an established estimate and qualifying activity is overdue
        if rolling is not None and last_qualifying_date is not None:
            days_gap = (activity_date - last_qualifying_date).days
            if days_gap > _DECAY_GRACE_DAYS:
                extra_weeks = (days_gap - _DECAY_GRACE_DAYS) / 7.0
                rolling = rolling * (1 - _DECAY_RATE_PER_WEEK) ** extra_weeks

        if rolling is None:
            # No initial given: bootstrap from first qualifying activity only
            if is_qualifying:
                rolling = estimate
                last_qualifying_date = activity_date
        elif is_qualifying:
            if estimate >= rolling:
                rolling = estimate  # full increase
            else:
                rolling = rolling + _DECREASE_DAMPING * (
                    estimate - rolling
                )  # damped decrease
            last_qualifying_date = activity_date
        # else: non-qualifying — rolling stays as is (possibly already decayed above)

        row["rolling_vo2max"] = round(rolling, 1)
        row["is_qualifying"] = is_qualifying

    return history


# ---------------------------------------------------------------------------
# Race Predictions
# ---------------------------------------------------------------------------
#
# Primary method: Jack Daniels VDOT fractional utilization.
#   Derives race pace by solving the VO2 demand quadratic at the fraction of
#   VO2max that an athlete can sustain at each race distance.  This is the
#   same model used in the Daniels VDOT tables and is the most internally
#   consistent approach — it only requires a single VDOT estimate as input.
#
# Fractional utilization by distance (Daniels VDOT tables, averaged VDOT 40–65):
#   5K  → 97.9% of VO2max
#   10K → 93.9%
#   Half → 87.9%
#   Marathon → 83.8%
#
# LT2-anchored (secondary, when a measured threshold pace is available):
#   Derives race paces from the measured threshold pace via Daniels VDOT
#   table ratios.  Shown as a reference alongside the primary VDOT prediction.
#
# Riegel (T2 = T1 × (D2/D1)^1.06) is computed as tertiary reference but is
# only accurate when the source effort was near-maximal (race or time-trial).

# Daniels VDOT fractional utilization per race distance
VDOT_RACE_FRACS: dict[str, float] = {
    "5K": 0.979,
    "10K": 0.939,
    "Half": 0.879,
    "Marathon": 0.838,
}

_LT2_RACE_PACE_RATIOS: dict[str, float] = {
    "5K": 0.924,
    "10K": 0.962,
    "Half": 1.020,
    "Marathon": 1.070,
}


def _vdot_to_race_entry(vdot: float, frac: float, d2_m: float) -> dict:
    """Predict race time/pace using Daniels VDOT fractional utilization.

    Solves the VO2 demand quadratic for the speed at which the athlete uses
    ``frac * vdot`` of their aerobic capacity over distance ``d2_m``.
    """
    demand = vdot * frac
    a, b, c = 0.000104, 0.182258, -(demand + 4.6)
    v_mpm = (-b + (b**2 - 4 * a * c) ** 0.5) / (2 * a)  # m/min
    v_ms = v_mpm / 60  # m/s
    pred_s = d2_m / v_ms
    return _pred_entry(pred_s, d2_m)


def vo2max_from_lt2_pace(lt2_pace_s: float) -> float:
    """
    Back-calculate VO2max from a measured LT2 pace (sec/km).

    LT2 is assumed to occur at 88% of VO2max (Daniels standard).
    Uses the same VO2-demand quadratic as _daniels_vdot, solved at LT2 speed.
    """
    v_mpm = (1000.0 / lt2_pace_s) * 60.0  # m/min
    vo2_demand = -4.6 + 0.182258 * v_mpm + 0.000104 * v_mpm**2
    return round(max(28.0, min(90.0, vo2_demand / 0.88)), 1)


def _pred_entry(pred_s: float, d2_m: float) -> dict:
    return {
        "distance_km": round(d2_m / 1000, 4),
        "predicted_time_s": round(pred_s),
        "predicted_pace": _fmt_pace_from_s(pred_s, d2_m),
        "hms": _fmt_hms(pred_s),
    }


def compute_race_predictions(
    vo2_result: VO2MaxResult,
    lt2_pace_s: float | None = None,
) -> dict:
    """
    Predict race times using three complementary methods.

    VDOT-anchored (primary, always computed when vdot is available):
        Uses Daniels VDOT fractional utilization — solves the VO2 demand
        quadratic at the fraction of VO2max sustainable at each race distance.
        This is the same model as the Daniels VDOT tables and is the most
        internally consistent method.

    LT2-anchored (secondary when lt2_pace_s is set):
        Derives race paces from the measured threshold pace via Daniels VDOT
        table ratios.  Shown as a reference alongside the VDOT prediction.

    Riegel (tertiary reference):
        T2 = T1 × (D2/D1)^1.06 from the best recorded effort.
        Only accurate when the source effort was near-maximal.
    """
    out: dict = {}

    # --- VDOT-anchored predictions (primary) ---
    if vo2_result.vdot is not None:
        vdot_preds = {}
        for label, d2_m in RACE_DISTANCES.items():
            vdot_preds[label] = _vdot_to_race_entry(
                vo2_result.vdot, VDOT_RACE_FRACS[label], d2_m
            )
        out["vdot_predictions"] = vdot_preds
        out["vdot_source"] = round(vo2_result.vdot, 1)

    # --- LT2-anchored predictions ---
    if lt2_pace_s is not None:
        lt2_preds = {}
        for label, d2_m in RACE_DISTANCES.items():
            pace_s = lt2_pace_s * _LT2_RACE_PACE_RATIOS[label]
            lt2_preds[label] = _pred_entry(pace_s * (d2_m / 1000), d2_m)
        out["lt2_predictions"] = lt2_preds
        out["lt2_source_pace"] = f"{int(lt2_pace_s // 60)}:{int(lt2_pace_s % 60):02d}"
        out["lt2_implied_vo2max"] = vo2max_from_lt2_pace(lt2_pace_s)

    # --- Riegel predictions ---
    d1_m = vo2_result.distance_km * 1000
    t1_s = vo2_result.best_time_s
    if t1_s > 0 and d1_m > 0:
        riegel_preds = {}
        for label, d2_m in RACE_DISTANCES.items():
            riegel_preds[label] = _pred_entry(_riegel(d1_m, t1_s, d2_m), d2_m)
        out["riegel_predictions"] = riegel_preds
        out["riegel_source_distance_km"] = vo2_result.distance_km
        out["riegel_source_pace"] = vo2_result.pace_per_km
        out["riegel_source_confidence"] = vo2_result.confidence_label

    # Expose ``predictions`` pointing at the most reliable method:
    # VDOT > LT2 > Riegel
    if "vdot_predictions" in out:
        out["predictions"] = out["vdot_predictions"]
        out["method"] = "vdot"
    elif "lt2_predictions" in out:
        out["predictions"] = out["lt2_predictions"]
        out["method"] = "lt2"
    elif "riegel_predictions" in out:
        out["predictions"] = out["riegel_predictions"]
        out["method"] = "riegel"

    return out
