from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select

from fitops.analytics.training_load import ALPHA_ATL, ALPHA_CTL
from fitops.analytics.workout_summary import (
    PERIOD_LABELS,
    normalize_period,
    period_since,
)
from fitops.db.models.activity import Activity
from fitops.db.models.activity_weather import ActivityWeather
from fitops.db.models.workout import Workout
from fitops.db.models.workout_activity_link import WorkoutActivityLink
from fitops.db.models.workout_segment import WorkoutSegment
from fitops.db.session import get_async_session


def _activity_date(activity: Activity) -> date | None:
    dt = activity.start_date_local or activity.start_date
    if dt is None:
        return None
    return dt.date()


def _sqlite_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _fmt_pace(pace_s: float | None) -> str | None:
    if pace_s is None or pace_s <= 0:
        return None
    minutes, seconds = divmod(int(round(pace_s)), 60)
    return f"{minutes}:{seconds:02d}"


def _activity_pace_s(activity: Activity) -> float | None:
    if not activity.average_speed_ms or activity.average_speed_ms <= 0:
        return None
    return 1000.0 / activity.average_speed_ms


def _pct(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 100)


def _decayed_contribution(tss: float, alpha: float, days_since: int) -> float:
    return tss * alpha * ((1 - alpha) ** max(days_since, 0))


def _round_or_none(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    return round(value, digits)


async def get_workout_contribution(
    athlete_id: int,
    workout_id: int,
    *,
    period: str = "year",
    as_of: date | None = None,
) -> dict[str, Any] | None:
    """Return stored-data contribution analytics for one workout definition.

    The read path intentionally uses only persisted activity, link, and segment
    rows. Missing activity TSS is reported as unavailable rather than estimated
    here, so dashboard and CLI reads do not repeatedly recompute load.
    """
    period = normalize_period(period)
    since = period_since(period)
    since_compare = _sqlite_datetime(since)
    as_of_date = as_of or datetime.now(UTC).date()

    async with get_async_session() as session:
        workout = (
            await session.execute(
                select(Workout).where(
                    Workout.id == workout_id,
                    Workout.athlete_id == athlete_id,
                )
            )
        ).scalar_one_or_none()
        if workout is None:
            return None

        link_rows = (
            await session.execute(
                select(WorkoutActivityLink, Activity)
                .join(Activity, Activity.id == WorkoutActivityLink.activity_id)
                .where(
                    WorkoutActivityLink.workout_id == workout_id,
                    Activity.athlete_id == athlete_id,
                )
                .order_by(Activity.start_date_local.asc(), Activity.start_date.asc())
            )
        ).all()
        weather_keys = {
            key
            for _, activity in link_rows
            for key in (activity.strava_id, activity.id)
            if key is not None
        }
        if weather_keys:
            weather_rows = (
                (
                    await session.execute(
                        select(ActivityWeather).where(
                            ActivityWeather.activity_id.in_(weather_keys)
                        )
                    )
                )
                .scalars()
                .all()
            )
            weather_by_activity_id = {w.activity_id: w for w in weather_rows}
        else:
            weather_by_activity_id = {}

        period_activity_stmt = select(Activity.training_stress_score).where(
            Activity.athlete_id == athlete_id,
            Activity.training_stress_score.isnot(None),
        )
        if since_compare is not None:
            period_activity_stmt = period_activity_stmt.where(
                Activity.start_date >= since_compare
            )
        period_tss_rows = (await session.execute(period_activity_stmt)).all()

        segment_rows = (
            (
                await session.execute(
                    select(WorkoutSegment)
                    .where(WorkoutSegment.workout_id == workout_id)
                    .order_by(WorkoutSegment.segment_index.asc())
                )
            )
            .scalars()
            .all()
        )

    total_period_tss = sum(float(row[0] or 0.0) for row in period_tss_rows)
    trend: list[dict[str, Any]] = []
    period_points: list[dict[str, Any]] = []
    total_tss = 0.0
    period_tss = 0.0
    compliance_weighted_tss = 0.0
    period_compliance_weighted_tss = 0.0
    ctl_contribution = 0.0
    atl_contribution = 0.0
    period_ctl_contribution = 0.0
    period_atl_contribution = 0.0
    scored_scores: list[float] = []
    period_scores: list[float] = []
    missing_tss_count = 0
    period_missing_tss_count = 0
    missing_true_pace_count = 0
    period_missing_true_pace_count = 0
    cumulative_tss = 0.0

    for link, activity in link_rows:
        weather = weather_by_activity_id.get(
            activity.strava_id
        ) or weather_by_activity_id.get(activity.id)
        act_date = _activity_date(activity)
        activity_start = _sqlite_datetime(
            activity.start_date or activity.start_date_local
        )
        in_period = since_compare is None or (
            activity_start is not None and activity_start >= since_compare
        )
        tss = activity.training_stress_score
        if tss is None:
            missing_tss_count += 1
            if in_period:
                period_missing_tss_count += 1
        else:
            tss_f = float(tss)
            total_tss += tss_f
            cumulative_tss += tss_f
            if link.compliance_score is not None:
                compliance_weighted_tss += tss_f * float(link.compliance_score)
            if act_date is not None:
                days_since = (as_of_date - act_date).days
                ctl_piece = _decayed_contribution(tss_f, ALPHA_CTL, days_since)
                atl_piece = _decayed_contribution(tss_f, ALPHA_ATL, days_since)
                ctl_contribution += ctl_piece
                atl_contribution += atl_piece
                if in_period:
                    period_ctl_contribution += ctl_piece
                    period_atl_contribution += atl_piece
            if in_period:
                period_tss += tss_f
                if link.compliance_score is not None:
                    period_compliance_weighted_tss += tss_f * float(
                        link.compliance_score
                    )

        if link.compliance_score is not None:
            scored_scores.append(float(link.compliance_score))
            if in_period:
                period_scores.append(float(link.compliance_score))

        snapshot = link.get_physiology_snapshot()
        pace_s = _activity_pace_s(activity)
        true_pace_s = (
            float(weather.true_pace_s_per_km)
            if weather is not None and weather.true_pace_s_per_km is not None
            else None
        )
        if true_pace_s is None:
            missing_true_pace_count += 1
            if in_period:
                period_missing_true_pace_count += 1
        point = {
            "date": act_date.isoformat() if act_date else None,
            "activity_id": activity.id,
            "activity_strava_id": activity.strava_id,
            "activity_name": activity.name,
            "sport_type": activity.sport_type,
            "tss": _round_or_none(float(tss), 1) if tss is not None else None,
            "cumulative_tss": round(cumulative_tss, 1),
            "compliance_score": link.compliance_score,
            "compliance_pct": _pct(link.compliance_score),
            "pace_s_per_km": _round_or_none(pace_s, 1),
            "pace_formatted": _fmt_pace(pace_s),
            "true_pace_s_per_km": _round_or_none(true_pace_s, 1),
            "true_pace_formatted": _fmt_pace(true_pace_s),
            "avg_hr_bpm": round(activity.average_heartrate)
            if activity.average_heartrate
            else None,
            "distance_km": round(activity.distance_m / 1000, 2)
            if activity.distance_m
            else None,
            "duration_seconds": activity.moving_time_s,
            "ctl_at_workout": _round_or_none(snapshot.get("ctl")),
            "atl_at_workout": _round_or_none(snapshot.get("atl")),
            "tsb_at_workout": _round_or_none(snapshot.get("tsb")),
        }
        trend.append(point)
        if in_period:
            period_points.append(point)

    first_true_pace = next(
        (p["true_pace_s_per_km"] for p in trend if p["true_pace_s_per_km"]), None
    )
    latest_true_pace = next(
        (p["true_pace_s_per_km"] for p in reversed(trend) if p["true_pace_s_per_km"]),
        None,
    )
    true_pace_change_pct = None
    if first_true_pace and latest_true_pace:
        true_pace_change_pct = (
            (first_true_pace - latest_true_pace) / first_true_pace
        ) * 100

    segments_by_index: dict[int, list[WorkoutSegment]] = defaultdict(list)
    for seg in segment_rows:
        segments_by_index[seg.segment_index].append(seg)

    segment_summary = []
    for segment_index, rows in sorted(segments_by_index.items()):
        compliance_values = [
            float(r.compliance_score) for r in rows if r.compliance_score is not None
        ]
        pace_values = [
            float(r.avg_pace_per_km) for r in rows if r.avg_pace_per_km is not None
        ]
        hr_values = [
            float(r.avg_heartrate) for r in rows if r.avg_heartrate is not None
        ]
        segment_summary.append(
            {
                "segment_index": segment_index,
                "segment_name": rows[0].segment_name,
                "step_type": rows[0].step_type,
                "sessions": len(rows),
                "avg_compliance_pct": _pct(
                    sum(compliance_values) / len(compliance_values)
                    if compliance_values
                    else None
                ),
                "avg_pace_s_per_km": _round_or_none(
                    sum(pace_values) / len(pace_values) if pace_values else None,
                    1,
                ),
                "avg_pace_formatted": _fmt_pace(
                    sum(pace_values) / len(pace_values) if pace_values else None
                ),
                "avg_hr_bpm": round(sum(hr_values) / len(hr_values))
                if hr_values
                else None,
            }
        )

    total_sessions = len(link_rows)
    period_sessions = len(period_points)
    tss_coverage_pct = (
        round(((total_sessions - missing_tss_count) / total_sessions) * 100)
        if total_sessions
        else 0
    )
    period_tss_coverage_pct = (
        round(((period_sessions - period_missing_tss_count) / period_sessions) * 100)
        if period_sessions
        else 0
    )

    return {
        "workout": {
            "id": workout.id,
            "name": workout.name,
            "sport_type": workout.sport_type,
        },
        "period": period,
        "period_label": PERIOD_LABELS[period],
        "summary": {
            "total_sessions": total_sessions,
            "period_sessions": period_sessions,
            "scored_sessions": len(scored_scores),
            "period_scored_sessions": len(period_scores),
            "total_tss": round(total_tss, 1),
            "period_tss": round(period_tss, 1),
            "period_total_training_tss": round(total_period_tss, 1),
            "period_load_share_pct": round((period_tss / total_period_tss) * 100, 1)
            if total_period_tss
            else None,
            "compliance_weighted_tss": round(compliance_weighted_tss, 1),
            "period_compliance_weighted_tss": round(period_compliance_weighted_tss, 1),
            "avg_compliance_pct": _pct(
                sum(scored_scores) / len(scored_scores) if scored_scores else None
            ),
            "period_avg_compliance_pct": _pct(
                sum(period_scores) / len(period_scores) if period_scores else None
            ),
            "current_ctl_contribution": round(ctl_contribution, 2),
            "current_atl_contribution": round(atl_contribution, 2),
            "period_ctl_contribution": round(period_ctl_contribution, 2),
            "period_atl_contribution": round(period_atl_contribution, 2),
            "fatigue_to_fitness_ratio": round(atl_contribution / ctl_contribution, 2)
            if ctl_contribution
            else None,
            "first_true_pace_formatted": _fmt_pace(first_true_pace),
            "latest_true_pace_formatted": _fmt_pace(latest_true_pace),
            "true_pace_change_pct": _round_or_none(true_pace_change_pct, 1),
            "first_pace_formatted": _fmt_pace(first_true_pace),
            "latest_pace_formatted": _fmt_pace(latest_true_pace),
            "pace_change_pct": _round_or_none(true_pace_change_pct, 1),
            "tss_coverage_pct": tss_coverage_pct,
            "period_tss_coverage_pct": period_tss_coverage_pct,
            "missing_tss_sessions": missing_tss_count,
            "period_missing_tss_sessions": period_missing_tss_count,
            "missing_true_pace_sessions": missing_true_pace_count,
            "period_missing_true_pace_sessions": period_missing_true_pace_count,
        },
        "trend": trend,
        "period_trend": period_points,
        "segment_summary": segment_summary,
        "data_availability": {
            "source": "stored activities.training_stress_score, activity_weather.true_pace_s_per_km, workout_activity_links, and workout_segments",
            "recomputed": False,
            "missing_tss_sessions": missing_tss_count,
            "missing_true_pace_sessions": missing_true_pace_count,
            "note": "Rows without stored TSS are excluded from load contribution metrics; rows without stored true pace are omitted from the true pace trend.",
        },
    }
