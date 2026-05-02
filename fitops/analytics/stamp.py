"""Strava activity description stamping — embed FitOps analytics as a footprint."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from fitops.db.models.activity import Activity
    from fitops.strava.client import StravaClient

STAMP_SENTINEL = "\n\n📊 FitOps Analytics\n"
REPO_LINK = "github.com/BrunoV21/FitOps-CLI"

RUN_SPORT_TYPES = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}

_WBGT_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴", "black": "⚫"}

_SEG_EMOJI = {
    "warmup": "🌅",
    "cooldown": "🧊",
    "rest": "⏸️",
    "interval": "⚡",
    "recovery": "💚",
    "active": "🏃",
}


def _fmt_pace(speed_ms: float | None, sport_type: str) -> str | None:
    if not speed_ms or speed_ms <= 0:
        return None
    if sport_type in RUN_SPORT_TYPES:
        s_per_km = 1000.0 / speed_ms
        m, s = divmod(int(s_per_km), 60)
        return f"{m}:{s:02d}/km"
    return f"{speed_ms * 3.6:.1f} km/h"


def _fmt_pace_s(pace_s: float | None) -> str | None:
    if not pace_s or pace_s <= 0:
        return None
    m, s = divmod(int(pace_s), 60)
    return f"{m}:{s:02d}/km"


def _fmt_dist(meters: float | None) -> str | None:
    if meters is None or meters <= 0:
        return None
    if meters >= 1000:
        return f"{meters / 1000:.2f} km"
    return f"{meters:.0f} m"


def _sep(label: str = "") -> str:
    if label:
        dashes = "─" * max(0, 44 - len(label) - 2)
        return f"── {label} {dashes}"
    return "─" * 47


def compose_stamp(
    activity: "Activity",
    workout_data: dict | None = None,
    performance_insights: list[dict] | None = None,
    weather: dict | None = None,
) -> str:
    from fitops.analytics.training_scores import aerobic_short_label, anaerobic_short_label

    lines: list[str] = []

    # ── Scores (compact single line) ─────────────────────
    score_parts: list[str] = []
    if activity.aerobic_score is not None:
        score_parts.append(f"Aer {activity.aerobic_score:.1f} ({aerobic_short_label(activity.aerobic_score)})")
    if activity.anaerobic_score is not None:
        score_parts.append(f"Ana {activity.anaerobic_score:.1f} ({anaerobic_short_label(activity.anaerobic_score)})")
    if activity.vo2max_estimate is not None:
        score_parts.append(f"VO2 {activity.vo2max_estimate:.1f}")
    if score_parts:
        lines.append(" · ".join(score_parts))

    # ── Power ────────────────────────────────────────────
    if activity.average_watts and activity.average_watts > 0:
        parts = [f"Avg {activity.average_watts:.0f}W"]
        if activity.weighted_average_watts:
            parts.append(f"NP {activity.weighted_average_watts:.0f}W")
        if activity.max_watts:
            parts.append(f"Max {activity.max_watts}W")
        lines.append("")
        lines.append("Power")
        lines.append(" · ".join(parts))
    elif activity.est_power_avg_w and activity.est_power_avg_w > 0:
        src = activity.est_power_source or "est"
        parts = [f"Avg {activity.est_power_avg_w:.0f}W"]
        if activity.est_power_np_w:
            parts.append(f"NP {activity.est_power_np_w:.0f}W")
        if activity.est_power_max_w:
            parts.append(f"Max {activity.est_power_max_w:.0f}W")
        lines.append("")
        lines.append(f"Power ({src})")
        lines.append(" · ".join(parts))

    # ── Weather conditions ───────────────────────────────
    if weather:
        lines.append("")
        lines.append("🌤 Conditions")

        # Line 1: Pace · Temp · Hum
        row1: list[str] = []
        true_pace_fmt = weather.get("true_pace_fmt")
        true_pace_pct = weather.get("true_pace_pct")
        if true_pace_fmt:
            pct_str = f" (+{true_pace_pct:.1f}%)" if true_pace_pct and true_pace_pct > 0 else ""
            row1.append(f"Pace {true_pace_fmt}{pct_str}")
        temp = weather.get("temperature_c")
        feels = weather.get("apparent_temp_c")
        if temp is not None:
            if feels is not None and abs(feels - temp) >= 1:
                row1.append(f"Temp {temp:.0f}°C ({feels:.0f}°C)")
            else:
                row1.append(f"Temp {temp:.0f}°C")
        hum = weather.get("humidity_pct")
        if hum is not None:
            row1.append(f"Hum {hum:.0f}%")
        if row1:
            lines.append(" · ".join(row1))

        # Line 2: Wind · WBGT · HeatHR
        row2: list[str] = []
        wind_kmh = weather.get("wind_speed_kmh")
        wind_dir = weather.get("wind_dir_compass")
        if wind_kmh is not None:
            dir_str = f" {wind_dir}" if wind_dir else ""
            row2.append(f"Wind {wind_kmh:.1f} km/h{dir_str}")
        wbgt = weather.get("wbgt_c")
        wbgt_flag_val = weather.get("wbgt_flag")
        if wbgt is not None:
            flag_emoji = _WBGT_EMOJI.get(wbgt_flag_val or "green", "")
            emoji_str = f" {flag_emoji}" if flag_emoji else ""
            row2.append(f"WBGT {wbgt:.1f}°C{emoji_str}")
        hr_heat_pct = weather.get("hr_heat_pct")
        hr_heat_bpm = weather.get("hr_heat_bpm")
        if hr_heat_pct is not None:
            bpm_str = f" (~+{hr_heat_bpm} bpm)" if hr_heat_bpm else ""
            row2.append(f"HeatHR +{hr_heat_pct:.1f}%{bpm_str}")
        if row2:
            lines.append(" · ".join(row2))

        # Line 3: Condition
        condition = weather.get("condition")
        if condition:
            lines.append(f"Cond {condition}")

    # ── Workout segments ─────────────────────────────────
    if workout_data:
        wo_name = workout_data.get("name", "Workout")
        lines.append("")
        lines.append(f"🏋️ {wo_name}")
        for seg in workout_data.get("segments") or []:
            lines.append("")
            seg_name = seg.get("name") or seg.get("step_type") or "Segment"
            step_type = (seg.get("step_type") or "").lower()
            seg_emoji = _SEG_EMOJI.get(step_type, "🔹")
            lines.append(f"{seg_emoji} {seg_name}")

            # Row 1: Dist · Pace · TP
            row1 = []
            dist = _fmt_dist(seg.get("distance_m"))
            if dist:
                row1.append(f"Dist {dist}")
            pace = _fmt_pace_s(seg.get("avg_pace_s"))
            if pace:
                row1.append(f"Pace {pace}")
            tp = _fmt_pace_s(seg.get("avg_true_pace_s"))
            if tp and tp != pace:
                row1.append(f"TP {tp}")
            if row1:
                lines.append(" · ".join(row1))

            # Row 2: HR · Cad
            row2 = []
            hr = seg.get("avg_hr")
            if hr:
                row2.append(f"HR {hr:.0f} bpm")
            cad = seg.get("avg_cadence")
            if cad:
                row2.append(f"Cad {cad:.0f} spm")
            if row2:
                lines.append(" · ".join(row2))

    # ── Performance records ──────────────────────────────
    highlight_insights = [
        pi for pi in (performance_insights or [])
        if pi.get("action") == "prompt_update" and pi.get("delta_pct", 0) > 0
    ]
    if highlight_insights:
        lines.append("")
        lines.append("🏆 Records")
        for pi in highlight_insights:
            label = pi.get("label", pi.get("metric", ""))
            detected = pi.get("detected_fmt", "")
            current = pi.get("current_fmt")
            delta = pi.get("delta_pct", 0)
            if current:
                lines.append(f"🏆 {label}: {detected}  (was {current}, +{delta:.1f}%)")
            else:
                lines.append(f"🏆 {label}: {detected}")

    # strip any trailing blank lines before footer
    while lines and lines[-1] == "":
        lines.pop()
    lines.append("")
    lines.append(REPO_LINK)

    return "\n".join(lines)


def apply_stamp(current_desc: str | None, new_stamp: str) -> str:
    """Return the description with the FitOps stamp applied (or replaced)."""
    base = (current_desc or "").split(STAMP_SENTINEL)[0].rstrip()
    if base:
        return f"{base}{STAMP_SENTINEL}{new_stamp}"
    return f"📊 FitOps Analytics\n{new_stamp}"


async def stamp_activity(
    strava_client: "StravaClient",
    session: "AsyncSession",
    activity: "Activity",
    *,
    workout_data: dict | None = None,
    performance_insights: list[dict] | None = None,
    fetch_fresh_desc: bool = False,
) -> None:
    """Compose stamp, push to Strava, update stamped_at in DB."""
    from sqlalchemy import select

    from fitops.analytics.weather_pace import vo2max_heat_factor, weather_row_to_dict
    from fitops.db.models.activity import Activity as ActivityModel
    from fitops.db.models.activity_stream import ActivityStream
    from fitops.db.models.activity_weather import ActivityWeather
    from fitops.db.models.workout import Workout
    from fitops.db.models.workout_activity_link import WorkoutActivityLink
    from fitops.db.models.workout_segment import WorkoutSegment

    base_desc = activity.description
    if fetch_fresh_desc:
        try:
            fresh = await strava_client.get_activity(activity.strava_id)
            base_desc = fresh.get("description") or base_desc
        except Exception:
            pass

    # Fetch weather and compute derived fields
    weather: dict | None = None
    try:
        weather_result = await session.execute(
            select(ActivityWeather).where(ActivityWeather.activity_id == activity.strava_id)
        )
        weather_row = weather_result.scalar_one_or_none()
        if weather_row:
            weather = weather_row_to_dict(weather_row)

            # HR heat effect
            if weather_row.temperature_c is not None and weather_row.humidity_pct is not None:
                vo2_factor = vo2max_heat_factor(weather_row.temperature_c, weather_row.humidity_pct)
                if vo2_factor < 0.99:
                    weather["hr_heat_pct"] = round((1.0 / vo2_factor - 1.0) * 100, 1)
                    if activity.average_heartrate and activity.average_heartrate > 0:
                        weather["hr_heat_bpm"] = round(
                            activity.average_heartrate * (1.0 / vo2_factor - 1.0)
                        )

            # True pace: load velocity_smooth + grade_smooth from DB, compute GAP + heat
            is_run = (activity.sport_type or "") in RUN_SPORT_TYPES
            streams_result = await session.execute(
                select(ActivityStream).where(
                    ActivityStream.activity_id == activity.id,
                    ActivityStream.stream_type.in_(["velocity_smooth", "grade_smooth"]),
                )
            )
            streams_dict: dict[str, list] = {}
            for row in streams_result.scalars().all():
                streams_dict[row.stream_type] = row.data

            vel_raw = streams_dict.get("velocity_smooth", [])
            grade_raw = streams_dict.get("grade_smooth", [])
            if vel_raw:
                if grade_raw:
                    wt_pairs = [
                        (v * (1 + 0.033 * g), v)
                        for v, g in zip(vel_raw, grade_raw, strict=False)
                        if v and v > 0.1
                    ]
                else:
                    wt_pairs = [(v, v) for v in vel_raw if v and v > 0.1]
                if wt_pairs:
                    gap_speeds, weights = zip(*wt_pairs, strict=False)
                    total_w = sum(weights)
                    mean_gap_ms = (
                        sum(gs * wt for gs, wt in zip(gap_speeds, weights, strict=False))
                        / total_w
                    )
                    heat_f = weather_row.pace_heat_factor or 1.0
                    if is_run:
                        gap_pace_s = 1000.0 / mean_gap_ms
                        true_pace_s = gap_pace_s / heat_f
                        m_tp, s_tp = divmod(int(round(true_pace_s)), 60)
                        weather["true_pace_fmt"] = f"{m_tp}:{s_tp:02d}/km"
                        if activity.average_speed_ms and activity.average_speed_ms > 0:
                            actual_pace_s = 1000.0 / activity.average_speed_ms
                            pct = (actual_pace_s / true_pace_s - 1.0) * 100
                            if pct > 0.05:
                                weather["true_pace_pct"] = round(pct, 1)
                    else:
                        weather["true_pace_fmt"] = f"{mean_gap_ms / heat_f * 3.6:.1f} km/h"
    except Exception:
        pass

    # Fetch workout link + segments when not provided by caller
    if workout_data is None:
        try:
            link_result = await session.execute(
                select(WorkoutActivityLink).where(WorkoutActivityLink.activity_id == activity.id)
            )
            link = link_result.scalar_one_or_none()
            if link:
                wo_result = await session.execute(
                    select(Workout).where(Workout.id == link.workout_id)
                )
                wo = wo_result.scalar_one_or_none()
                seg_result = await session.execute(
                    select(WorkoutSegment)
                    .where(WorkoutSegment.activity_id == activity.id)
                    .where(WorkoutSegment.workout_id == link.workout_id)
                    .order_by(WorkoutSegment.segment_index)
                )
                segments = seg_result.scalars().all()
                workout_data = {
                    "name": wo.name if wo else "Workout",
                    "segments": [
                        {
                            "name": seg.segment_name,
                            "step_type": seg.step_type,
                            "distance_m": seg.distance_actual_m,
                            "avg_pace_s": seg.avg_pace_per_km,
                            "avg_true_pace_s": seg.avg_true_pace_per_km,
                            "avg_hr": seg.avg_heartrate,
                            "avg_cadence": seg.avg_cadence,
                        }
                        for seg in segments
                    ],
                }
        except Exception:
            pass

    new_stamp = compose_stamp(activity, workout_data, performance_insights, weather)
    new_desc = apply_stamp(base_desc, new_stamp)

    await strava_client.update_activity(activity.strava_id, new_desc)

    result = await session.execute(
        select(ActivityModel).where(ActivityModel.id == activity.id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        row.description = new_desc
        row.stamped_at = datetime.now(UTC)
