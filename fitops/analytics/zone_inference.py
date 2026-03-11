from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.session import get_async_session

LTHR_PERCENTILE = 90
MAX_HR_PERCENTILE = 98
MAX_HR_CAP = 220
ROLLING_WINDOW_S = 20 * 60  # 20 minutes


def _percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    sv = sorted(values)
    idx = (pct / 100) * (len(sv) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sv) - 1)
    frac = idx - lo
    return sv[lo] + frac * (sv[hi] - sv[lo])


def _rolling_averages_20min(hr_values: list[float], time_values: list[float]) -> list[float]:
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


def _confidence_score(activity_count: int, quality_score: float, consistency_score: float) -> int:
    if activity_count >= 10:
        count_pts = 40
    elif activity_count >= 5:
        count_pts = 25
    elif activity_count >= 2:
        count_pts = 15
    else:
        count_pts = 5
    return min(100, count_pts + round(quality_score * 30) + round(consistency_score * 30))


@dataclass
class ZoneInferenceResult:
    lthr: Optional[int]
    max_hr: Optional[int]
    resting_hr: Optional[int]
    confidence: int
    activity_count: int
    inference_method: str


async def infer_zones(athlete_id: int) -> ZoneInferenceResult:
    async with get_async_session() as session:
        stmt = (
            select(Activity)
            .where(Activity.athlete_id == athlete_id, Activity.streams_fetched == True)
            .order_by(Activity.start_date.desc())
        )
        result = await session.execute(stmt)
        activities = result.scalars().all()

        all_hr: list[float] = []
        all_rolling: list[float] = []
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
                    all_rolling.extend(_rolling_averages_20min(hr_data, td))

    if not all_hr:
        return ZoneInferenceResult(
            lthr=None, max_hr=None, resting_hr=None,
            confidence=0, activity_count=0, inference_method="none",
        )

    max_hr_raw = _percentile(all_hr, MAX_HR_PERCENTILE)
    max_hr = min(MAX_HR_CAP, round(max_hr_raw)) if max_hr_raw else None

    if all_rolling:
        inference_method = "rolling_window"
        lthr_raw = _percentile(all_rolling, LTHR_PERCENTILE)
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
        resting_hr=None,  # cannot be inferred from activities — must be set manually
        confidence=_confidence_score(acts_with_hr, avg_quality, consistency_score),
        activity_count=acts_with_hr,
        inference_method=inference_method,
    )


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
