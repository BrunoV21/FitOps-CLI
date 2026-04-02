from __future__ import annotations

import statistics
from dataclasses import dataclass

from sqlalchemy import select

from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.session import get_async_session

LTHR_PERCENTILE = 90
MAX_HR_PERCENTILE = 98
MAX_HR_CAP = 220
ROLLING_WINDOW_S = 20 * 60  # 20 minutes


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    sv = sorted(values)
    idx = (pct / 100) * (len(sv) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sv) - 1)
    frac = idx - lo
    return sv[lo] + frac * (sv[hi] - sv[lo])


def _rolling_averages_20min(
    hr_values: list[float], time_values: list[float]
) -> list[float]:
    """20-min rolling window averages over one activity HR stream."""
    if len(hr_values) < 2 or len(time_values) < 2:
        return []
    avgs = []
    left = 0
    for right in range(len(hr_values)):
        while time_values[right] - time_values[left] > ROLLING_WINDOW_S:
            left += 1
        window = hr_values[left : right + 1]
        if len(window) >= 10:
            avgs.append(sum(window) / len(window))
    return avgs


def _confidence_score(
    activity_count: int, quality_score: float, consistency_score: float
) -> int:
    if activity_count >= 10:
        count_pts = 40
    elif activity_count >= 5:
        count_pts = 25
    elif activity_count >= 2:
        count_pts = 15
    else:
        count_pts = 5
    return min(
        100, count_pts + round(quality_score * 30) + round(consistency_score * 30)
    )


@dataclass
class ZoneInferenceResult:
    lthr: int | None
    max_hr: int | None
    resting_hr: int | None
    confidence: int
    activity_count: int
    inference_method: str


async def infer_zones(athlete_id: int) -> ZoneInferenceResult:
    async with get_async_session() as session:
        stmt = (
            select(Activity)
            .where(Activity.athlete_id == athlete_id, Activity.streams_fetched.is_(True))
            .order_by(Activity.start_date.desc())
        )
        result = await session.execute(stmt)
        activities = result.scalars().all()

        all_hr: list[float] = []
        pending_rolling: list[
            list[float]
        ] = []  # per-activity rolling windows, filtered later
        acts_with_hr = 0
        quality_scores: list[float] = []

        for act in activities:
            hr_res = await session.execute(
                select(ActivityStream).where(
                    ActivityStream.activity_id == act.id,
                    ActivityStream.stream_type == "heartrate",
                )
            )
            hr_stream = hr_res.scalar_one_or_none()
            if hr_stream is None:
                continue

            time_res = await session.execute(
                select(ActivityStream).where(
                    ActivityStream.activity_id == act.id,
                    ActivityStream.stream_type == "time",
                )
            )
            time_stream = time_res.scalar_one_or_none()

            hr_data = hr_stream.data
            valid = [h for h in hr_data if h and 30 <= h <= MAX_HR_CAP]
            if len(valid) < 10:
                continue

            acts_with_hr += 1
            all_hr.extend(valid)
            quality_scores.append(len(valid) / len(hr_data))

            if time_stream is not None:
                td = time_stream.data
                if len(td) == len(hr_data):
                    pending_rolling.append(_rolling_averages_20min(hr_data, td))

    if not all_hr:
        return ZoneInferenceResult(
            lthr=None,
            max_hr=None,
            resting_hr=None,
            confidence=0,
            activity_count=0,
            inference_method="none",
        )

    max_hr_raw = _percentile(all_hr, MAX_HR_PERCENTILE)
    max_hr = min(MAX_HR_CAP, round(max_hr_raw)) if max_hr_raw else None

    # Only include rolling windows from hard efforts (>=80% of max HR)
    # so easy runs don't dilute the LTHR percentile estimate.
    intensity_floor = (max_hr_raw * 0.80) if max_hr_raw else 155.0
    all_rolling = [
        avg for windows in pending_rolling for avg in windows if avg >= intensity_floor
    ]

    if all_rolling:
        # Clip top 2% before taking 90th percentile — prevents a single interval spike
        # from biasing LTHR high. Winsorize: cap values above 98th percentile.
        ceiling = _percentile(all_rolling, 98)
        all_rolling_clipped = (
            [min(v, ceiling) for v in all_rolling] if ceiling else all_rolling
        )
        inference_method = "rolling_window"
        lthr_raw = _percentile(all_rolling_clipped, LTHR_PERCENTILE)
    else:
        inference_method = "percentile_fallback"
        lthr_raw = _percentile(all_hr, 85)
    lthr = round(lthr_raw) if lthr_raw else None

    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
    if len(all_rolling) >= 2 and (m := sum(all_rolling) / len(all_rolling)) > 0:
        consistency_score = max(0.0, 1.0 - statistics.stdev(all_rolling) / m)
    else:
        consistency_score = 0.5

    return ZoneInferenceResult(
        lthr=lthr,
        max_hr=max_hr,
        resting_hr=None,
        confidence=_confidence_score(acts_with_hr, avg_quality, consistency_score),
        activity_count=acts_with_hr,
        inference_method=inference_method,
    )


async def infer_lt2_pace(
    athlete_id: int, lthr: int, max_activities: int = 30
) -> float | None:
    """
    Estimate LT2 pace (sec/km) from grade_adjusted_speed stream at moments
    where HR >= 97% of LTHR. Returns median GAP as sec/km, or None if insufficient data.
    """
    hr_floor = lthr * 0.97
    gap_values: list[float] = []

    async with get_async_session() as session:
        stmt = (
            select(Activity)
            .where(
                Activity.athlete_id == athlete_id,
                Activity.streams_fetched.is_(True),
                Activity.sport_type.in_(["Run", "TrailRun", "VirtualRun"]),
            )
            .order_by(Activity.start_date.desc())
            .limit(max_activities)
        )
        result = await session.execute(stmt)
        activities = result.scalars().all()

        for act in activities:
            hr_res = await session.execute(
                select(ActivityStream).where(
                    ActivityStream.activity_id == act.id,
                    ActivityStream.stream_type == "heartrate",
                )
            )
            hr_stream = hr_res.scalar_one_or_none()
            if hr_stream is None:
                continue

            gap_res = await session.execute(
                select(ActivityStream).where(
                    ActivityStream.activity_id == act.id,
                    ActivityStream.stream_type == "grade_adjusted_speed",
                )
            )
            gap_stream = gap_res.scalar_one_or_none()
            if gap_stream is None:
                continue

            hr_data = hr_stream.data
            gap_data = gap_stream.data
            if len(hr_data) != len(gap_data):
                continue

            for hr, gap_ms in zip(hr_data, gap_data, strict=False):
                if hr is None or gap_ms is None:
                    continue
                if hr >= hr_floor and gap_ms > 0.5:  # >0.5 m/s = moving
                    gap_values.append(1000.0 / gap_ms)  # convert m/s -> sec/km

    if len(gap_values) < 20:
        return None

    gap_values.sort()
    median_idx = len(gap_values) // 2
    return round(gap_values[median_idx], 1)


async def infer_lt1_pace(
    athlete_id: int, lt1_bpm: int, max_activities: int = 30
) -> float | None:
    """
    Estimate LT1 pace (sec/km) from grade_adjusted_speed at moments where HR is
    within ±6 bpm of LT1 (aerobic threshold). Returns median GAP as sec/km, or None.
    """
    hr_lo = lt1_bpm - 6
    hr_hi = lt1_bpm + 6
    gap_values: list[float] = []

    async with get_async_session() as session:
        stmt = (
            select(Activity)
            .where(
                Activity.athlete_id == athlete_id,
                Activity.streams_fetched.is_(True),
                Activity.sport_type.in_(["Run", "TrailRun", "VirtualRun"]),
            )
            .order_by(Activity.start_date.desc())
            .limit(max_activities)
        )
        result = await session.execute(stmt)
        activities = result.scalars().all()

        for act in activities:
            hr_res = await session.execute(
                select(ActivityStream).where(
                    ActivityStream.activity_id == act.id,
                    ActivityStream.stream_type == "heartrate",
                )
            )
            hr_stream = hr_res.scalar_one_or_none()
            if hr_stream is None:
                continue

            gap_res = await session.execute(
                select(ActivityStream).where(
                    ActivityStream.activity_id == act.id,
                    ActivityStream.stream_type == "grade_adjusted_speed",
                )
            )
            gap_stream = gap_res.scalar_one_or_none()
            if gap_stream is None:
                continue

            hr_data = hr_stream.data
            gap_data = gap_stream.data
            if len(hr_data) != len(gap_data):
                continue

            for hr, gap_ms in zip(hr_data, gap_data, strict=False):
                if hr is None or gap_ms is None:
                    continue
                if hr_lo <= hr <= hr_hi and gap_ms > 0.5:
                    gap_values.append(1000.0 / gap_ms)

    if len(gap_values) < 20:
        return None

    gap_values.sort()
    return round(gap_values[len(gap_values) // 2], 1)


def vo2max_pace_from_vdot(vdot: float) -> float:
    """
    Derive vVO2max pace (sec/km) from Daniels VDOT using the VO2 demand formula.
    Solves: vdot = -4.6 + 0.182258*v + 0.000104*v^2 for v in m/min.
    """
    a, b, c = 0.000104, 0.182258, -(vdot + 4.6)
    v_mpm = (-b + (b**2 - 4 * a * c) ** 0.5) / (2 * a)  # m/min
    return round(1000.0 / (v_mpm / 60), 1)  # sec/km


def paces_from_vdot(vdot: float) -> tuple[float, float, float]:
    """
    Derive LT1, LT2, and vVO2max paces (sec/km) from Daniels VDOT.
    LT1 ≈ 75% VO2max, LT2 ≈ 88% VO2max, vVO2max = 100% VO2max.
    Returns (lt1_pace_s, lt2_pace_s, vo2max_pace_s).
    """

    def _solve(vo2: float) -> float:
        a, b, c = 0.000104, 0.182258, -(vo2 + 4.6)
        v_mpm = (-b + (b**2 - 4 * a * c) ** 0.5) / (2 * a)
        return round(1000.0 / (v_mpm / 60), 1)

    return _solve(0.75 * vdot), _solve(0.88 * vdot), _solve(vdot)


def save_inferred_zones(result: ZoneInferenceResult) -> None:
    settings = get_athlete_settings()
    updates: dict = {"inference_confidence": result.confidence}
    if result.lthr is not None:
        updates["lthr"] = result.lthr
        updates["lthr_source"] = "inferred"
    if result.max_hr is not None:
        updates["max_hr"] = result.max_hr
        updates["max_hr_source"] = "inferred"
    # resting_hr is never inferred — user must set it via --set-resting-hr
    settings.set(**updates)
