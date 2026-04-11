from __future__ import annotations

import asyncio
import json
import shutil
from datetime import UTC, datetime

import typer
from sqlalchemy import desc, select

from fitops.config.settings import get_settings
from fitops.db.migrations import init_db
from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.models.athlete import Athlete
from fitops.db.session import get_async_session
from fitops.output.formatter import format_activity_row, make_meta
from fitops.output.text_formatter import (
    print_activities_table,
    print_activity_detail,
    print_stream_chart,
    print_streams_summary,
)
from fitops.strava.client import StravaClient
from fitops.utils.exceptions import NotAuthenticatedError

app = typer.Typer(no_args_is_help=True)


async def _get_gear_lookup() -> dict:
    settings = get_settings()
    athlete_id = settings.athlete_id
    if not athlete_id:
        return {}
    async with get_async_session() as session:
        result = await session.execute(
            select(Athlete).where(Athlete.strava_id == athlete_id)
        )
        athlete = result.scalar_one_or_none()
        if not athlete:
            return {}
        lookup: dict = {}
        for b in athlete.bikes:
            lookup[b["id"]] = {"name": b["name"], "type": "bike"}
        for s in athlete.shoes:
            lookup[s["id"]] = {"name": s["name"], "type": "shoes"}
        return lookup


_TAG_FILTERS: dict[str, object] = {
    "race": (Activity.workout_type, 1),
    "trainer": (Activity.trainer, True),
    "commute": (Activity.commute, True),
    "manual": (Activity.manual, True),
    "private": (Activity.private, True),
}


@app.command("list")
def list_activities(
    sport: str | None = typer.Option(
        None, "--sport", help="Filter by sport type (e.g. Run, Ride)."
    ),
    limit: int = typer.Option(
        20, "--limit", help="Max number of activities to return."
    ),
    offset: int = typer.Option(
        0, "--offset", help="Number of activities to skip (for pagination)."
    ),
    after: str | None = typer.Option(
        None, "--after", help="Filter activities after date (YYYY-MM-DD)."
    ),
    before: str | None = typer.Option(
        None, "--before", help="Filter activities before date (YYYY-MM-DD)."
    ),
    search: str | None = typer.Option(
        None, "--search", help="Case-insensitive substring search on activity name."
    ),
    tag: str | None = typer.Option(
        None,
        "--tag",
        help="Filter by tag: race, trainer, commute, manual, private.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """List synced activities."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    if tag and tag not in _TAG_FILTERS:
        typer.echo(
            f"Unknown tag '{tag}'. Valid tags: {', '.join(_TAG_FILTERS)}.", err=True
        )
        raise typer.Exit(1)

    init_db()

    async def _fetch():
        from sqlalchemy import func as sqla_func

        gear_lookup = await _get_gear_lookup()
        async with get_async_session() as session:
            base_stmt = select(Activity)
            if sport:
                base_stmt = base_stmt.where(Activity.sport_type == sport)
            if after:
                try:
                    after_dt = datetime.fromisoformat(after).replace(tzinfo=UTC)
                    base_stmt = base_stmt.where(Activity.start_date >= after_dt)
                except ValueError:
                    pass
            if before:
                try:
                    before_dt = datetime.fromisoformat(before).replace(tzinfo=UTC)
                    base_stmt = base_stmt.where(Activity.start_date <= before_dt)
                except ValueError:
                    pass
            if search:
                base_stmt = base_stmt.where(Activity.name.ilike(f"%{search}%"))
            if tag:
                col, val = _TAG_FILTERS[tag]
                base_stmt = base_stmt.where(col == val)

            # Real total count (not just returned rows)
            count_stmt = select(sqla_func.count()).select_from(base_stmt.subquery())
            total_count = (await session.execute(count_stmt)).scalar_one()

            stmt = (
                base_stmt.order_by(desc(Activity.start_date))
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        formatted = [
            format_activity_row(
                {c.name: getattr(r, c.name) for c in r.__table__.columns},
                gear_lookup,
            )
            for r in rows
        ]
        filters: dict = {"limit": limit, "offset": offset}
        if sport:
            filters["sport_type"] = sport
        if after:
            filters["after"] = after
        if before:
            filters["before"] = before
        if search:
            filters["search"] = search
        if tag:
            filters["tag"] = tag

        returned = len(formatted)
        has_more = (offset + returned) < total_count
        return {
            "_meta": make_meta(
                total_count=total_count,
                filters_applied=filters,
                returned_count=returned,
                offset=offset,
                has_more=has_more,
            ),
            "activities": formatted,
        }

    output = asyncio.run(_fetch())
    if json_output:
        typer.echo(json.dumps(output, indent=2, default=str))
    else:
        print_activities_table(output["activities"])
        typer.echo(
            "\nTip: run `fitops activities list --help` to see all available filters."
        )


@app.command("get")
def get_activity(
    activity_id: int = typer.Argument(..., help="Strava activity ID."),
    fetch_fresh: bool = typer.Option(
        False, "--fresh", help="Re-fetch detail from Strava API."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Get detailed info for a single activity."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    async def _fetch():
        gear_lookup = await _get_gear_lookup()
        async with get_async_session() as session:
            result = await session.execute(
                select(Activity).where(Activity.strava_id == activity_id)
            )
            row = result.scalar_one_or_none()

        if row is None:
            typer.echo(
                f"Activity {activity_id} not found locally. Run `fitops sync run` first.",
                err=True,
            )
            raise typer.Exit(1)

        client = StravaClient()

        if fetch_fresh or not row.detail_fetched:
            data = await client.get_activity(activity_id)
            async with get_async_session() as session:
                result2 = await session.execute(
                    select(Activity).where(Activity.strava_id == activity_id)
                )
                row2 = result2.scalar_one_or_none()
                if row2:
                    row2.update_from_strava_data(data)
                    row2.detail_fetched = True
                    row = row2

        if fetch_fresh or not row.streams_fetched:
            try:
                stream_data = await client.get_activity_streams(activity_id)
                async with get_async_session() as session:
                    result3 = await session.execute(
                        select(Activity).where(Activity.strava_id == activity_id)
                    )
                    row3 = result3.scalar_one_or_none()
                    if row3:
                        for stream_type, stream_obj in stream_data.items():
                            data_list = (
                                stream_obj.get("data", [])
                                if isinstance(stream_obj, dict)
                                else stream_obj
                            )
                            existing = await session.execute(
                                select(ActivityStream).where(
                                    ActivityStream.activity_id == row3.id,
                                    ActivityStream.stream_type == stream_type,
                                )
                            )
                            if existing.scalar_one_or_none() is None:
                                session.add(
                                    ActivityStream.from_strava_stream(
                                        row3.id, stream_type, data_list
                                    )
                                )
                        row3.streams_fetched = True
                        row = row3
            except Exception:
                pass  # streams are best-effort; don't block the activity output

        row_dict = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        formatted = format_activity_row(row_dict, gear_lookup)

        from fitops.analytics.activity_insights import compute_hr_drift
        from fitops.analytics.activity_performance_insights import (
            compute_activity_performance_insights,
        )
        from fitops.analytics.activity_splits import compute_avg_gap, compute_km_splits
        from fitops.analytics.activity_zones import compute_activity_analytics
        from fitops.analytics.athlete_settings import get_athlete_settings
        from fitops.analytics.training_scores import (
            aerobic_label,
            anaerobic_label,
            compute_aerobic_score,
            compute_anaerobic_score,
        )
        from fitops.analytics.weather_pace import (
            compute_bearing,
            compute_wap_factor,
            vo2max_heat_factor,
            weather_row_to_dict,
        )
        from fitops.dashboard.queries.activities import (
            get_activity_laps,
            get_activity_streams,
        )
        from fitops.dashboard.queries.weather import get_weather_for_activities
        from fitops.dashboard.queries.workouts import get_workout_for_activity

        _settings = get_athlete_settings()
        aerobic_score = compute_aerobic_score(row, _settings)
        anaerobic_score = compute_anaerobic_score(row, _settings)

        formatted.setdefault("insights", {})
        formatted["insights"]["aerobic_training_score"] = aerobic_score
        formatted["insights"]["aerobic_label"] = aerobic_label(aerobic_score)
        formatted["insights"]["anaerobic_training_score"] = anaerobic_score
        formatted["insights"]["anaerobic_label"] = anaerobic_label(anaerobic_score)

        # Load streams
        streams: dict = {}
        if row.streams_fetched:
            streams = await get_activity_streams(row.id)

        # Load weather early — needed for true_pace stream injection
        _weather_map = await get_weather_for_activities([activity_id])
        _weather_obj = _weather_map.get(activity_id)

        # Inject true_pace stream (weather + GAP adjusted) before analytics
        if streams and _weather_obj:
            from fitops.dashboard.routes.activities import (
                _compute_true_pace_stream,
                _compute_wap_stream,
            )

            wap_s = _compute_wap_stream(streams, _weather_obj)
            if wap_s:
                streams["wap_pace"] = wap_s
            tp_s = _compute_true_pace_stream(streams, _weather_obj)
            if tp_s:
                streams["true_pace"] = tp_s
                streams["true_velocity"] = [
                    1000.0 / p if p and p > 0 else 0.0 for p in tp_s
                ]

        if streams and "true_pace" not in streams:
            vel_raw = streams.get("velocity_smooth", [])
            if vel_raw:
                streams["true_pace"] = [
                    round(1000.0 / v, 1) if v and v > 0.1 else None for v in vel_raw
                ]

        # HR drift
        hr_data = streams.get("heartrate", [])
        vel_data = streams.get("velocity_smooth", [])
        if hr_data and vel_data:
            drift = compute_hr_drift(hr_data, vel_data)
            if drift:
                formatted["insights"]["hr_drift"] = drift

        # Zone analytics (HR zones + pace zones)
        if streams:
            analytics = compute_activity_analytics(row, streams)
            if analytics:
                formatted["analytics"] = {
                    "hr_zones": [
                        {
                            "zone": z["zone"],
                            "name": z["name"],
                            "min_bpm": z["min_bpm"],
                            "max_bpm": z["max_bpm"],
                            "time_s": z["time_s"],
                            "time_fmt": z["time_fmt"],
                            "pct": z["pct"],
                        }
                        for z in (analytics.hr_zones or [])
                    ],
                    "pace_zones": [
                        {
                            "zone": z["zone"],
                            "name": z["name"],
                            "min_pace": z["min_pace"],
                            "max_pace": z["max_pace"],
                            "time_s": z["time_s"],
                            "time_fmt": z["time_fmt"],
                            "pct": z["pct"],
                        }
                        for z in (analytics.pace_zones or [])
                    ],
                    "lt2_bpm": analytics.lt2,
                    "vo2max": analytics.vo2max,
                }

        # Per-km splits and average GAP (runs only)
        km_splits = compute_km_splits(streams, row.sport_type or "")
        if km_splits is not None:
            formatted["km_splits"] = km_splits
        avg_gap = compute_avg_gap(streams, row.sport_type or "")
        if avg_gap is not None:
            formatted["avg_gap"] = avg_gap

        # Laps
        if row.laps_fetched:
            laps = await get_activity_laps(row.id)
            is_run = (row.sport_type or "") in {
                "Run", "TrailRun", "Walk", "Hike", "VirtualRun"
            }
            lap_rows = []
            for lap in laps:
                spd = lap.average_speed_ms
                pace_s = (
                    round(1000.0 / spd, 1) if spd and spd > 0 and is_run else None
                )
                m, s_rem = divmod(int(pace_s), 60) if pace_s else (None, None)
                lap_rows.append(
                    {
                        "index": (lap.lap_index or 0) + 1,
                        "name": lap.name or f"Lap {(lap.lap_index or 0) + 1}",
                        "moving_time_s": lap.moving_time_s,
                        "distance_km": round(lap.distance_m / 1000, 2)
                        if lap.distance_m
                        else None,
                        "pace": f"{m}:{s_rem:02d}/km"
                        if pace_s and m is not None
                        else None,
                        "pace_s": pace_s,
                        "avg_hr": round(lap.average_heartrate)
                        if lap.average_heartrate
                        else None,
                        "max_hr": lap.max_heartrate,
                        "avg_watts": round(lap.average_watts)
                        if lap.average_watts
                        else None,
                    }
                )
            formatted["laps"] = lap_rows

        # Weather panel
        if _weather_obj:
            import json as _json

            ws = weather_row_to_dict(_weather_obj)

            course_bearing: float | None = None
            if row.start_latlng and row.end_latlng:
                try:
                    s_pt = _json.loads(row.start_latlng)
                    e_pt = _json.loads(row.end_latlng)
                    if len(s_pt) == 2 and len(e_pt) == 2:
                        course_bearing = compute_bearing(
                            s_pt[0], s_pt[1], e_pt[0], e_pt[1]
                        )
                except (ValueError, TypeError, IndexError):
                    pass

            w = _weather_obj
            wap_factor = 1.0
            if w.temperature_c is not None and w.humidity_pct is not None:
                wap_factor = compute_wap_factor(
                    temp_c=w.temperature_c,
                    rh_pct=w.humidity_pct,
                    wind_speed_ms_val=w.wind_speed_ms or 0.0,
                    wind_dir_deg=w.wind_direction_deg or 0.0,
                    course_bearing=course_bearing,
                )

            is_run = (row.sport_type or "") in {
                "Run", "TrailRun", "Walk", "Hike", "VirtualRun"
            }
            wap_fmt = None
            if row.average_speed_ms and row.average_speed_ms > 0:
                if is_run:
                    actual_pace_s = 1000.0 / row.average_speed_ms
                    wap_s_val = actual_pace_s / wap_factor
                    m_w, s_w = divmod(int(wap_s_val), 60)
                    wap_fmt = f"{m_w}:{s_w:02d}/km"
                else:
                    wap_speed_kmh = row.average_speed_ms * 3.6 * wap_factor
                    wap_fmt = f"{wap_speed_kmh:.1f} km/h"

            hr_heat_pct: float | None = None
            hr_heat_bpm: int | None = None
            if w.temperature_c is not None and w.humidity_pct is not None:
                vo2_factor = vo2max_heat_factor(w.temperature_c, w.humidity_pct)
                if vo2_factor < 0.99:
                    hr_heat_pct = round((1.0 / vo2_factor - 1.0) * 100, 1)
                    if row.average_heartrate and row.average_heartrate > 0:
                        hr_heat_bpm = round(
                            row.average_heartrate * (1.0 / vo2_factor - 1.0)
                        )

            true_pace_fmt = None
            tp_stream = streams.get("true_pace", [])
            vel_stream = streams.get("velocity_smooth", [])
            tp_pairs = [
                (p, v)
                for p, v in zip(tp_stream, vel_stream, strict=False)
                if p and p > 0 and v and v > 0.1
            ]
            if tp_pairs:
                paces, vels = zip(*tp_pairs, strict=False)
                total_wt = sum(vels)
                mean_tp = sum(p * v for p, v in zip(paces, vels, strict=False)) / total_wt
                m_tp, s_tp = divmod(int(round(mean_tp)), 60)
                true_pace_fmt = f"{m_tp}:{s_tp:02d}/km"

            formatted["weather"] = {
                **ws,
                "wap_factor": round(wap_factor, 4),
                "wap_factor_pct": round((wap_factor - 1.0) * 100, 1),
                "wap_fmt": wap_fmt,
                "true_pace_fmt": true_pace_fmt,
                "course_bearing": round(course_bearing, 0)
                if course_bearing is not None
                else None,
                "hr_heat_pct": hr_heat_pct,
                "hr_heat_bpm": hr_heat_bpm,
            }

        # Performance insights (new PRs / metric changes)
        if streams:
            perf_insights = compute_activity_performance_insights(
                row, streams, _settings
            )
            if perf_insights:
                formatted["performance_insights"] = [
                    {
                        "metric": pi.metric,
                        "label": pi.label,
                        "setting_key": pi.setting_key,
                        "current_value": pi.current_value,
                        "detected_value": pi.detected_value,
                        "delta_pct": pi.delta_pct,
                        "action": pi.action,
                        "detected_fmt": pi.detected_fmt,
                        "current_fmt": pi.current_fmt,
                        "unit": pi.unit,
                        "explanation": pi.explanation,
                    }
                    for pi in perf_insights
                ]

        # Linked workout + compliance
        linked = await get_workout_for_activity(row.id)
        if linked:
            wo, segs = linked
            formatted["workout"] = {
                "id": wo.id,
                "name": wo.name,
                "compliance_score": wo.compliance_score,
                "compliance_pct": round(wo.compliance_score * 100)
                if wo.compliance_score is not None
                else None,
                "segments": [
                    {
                        **seg.to_dict(),
                        "compliance_pct": round(seg.compliance_score * 100)
                        if seg.compliance_score is not None
                        else None,
                    }
                    for seg in segs
                ],
            }

        return {"_meta": make_meta(total_count=1), "activity": formatted}

    output = asyncio.run(_fetch())
    if json_output:
        typer.echo(json.dumps(output, indent=2, default=str))
    else:
        print_activity_detail(output["activity"])


@app.command("streams")
def get_streams(
    activity_id: int = typer.Argument(..., help="Strava activity ID."),
    fetch_fresh: bool = typer.Option(
        False, "--fresh", help="Re-fetch streams from Strava API."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Get activity stream data (heartrate, pace, power, etc.)."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    async def _fetch():
        async with get_async_session() as session:
            result = await session.execute(
                select(Activity).where(Activity.strava_id == activity_id)
            )
            activity = result.scalar_one_or_none()
            if not activity:
                typer.echo(f"Activity {activity_id} not found locally.", err=True)
                raise typer.Exit(1)

            if fetch_fresh or not activity.streams_fetched:
                client = StravaClient()
                stream_data = await client.get_activity_streams(activity_id)
                for stream_type, stream_obj in stream_data.items():
                    data_list = (
                        stream_obj.get("data", [])
                        if isinstance(stream_obj, dict)
                        else stream_obj
                    )
                    existing = await session.execute(
                        select(ActivityStream).where(
                            ActivityStream.activity_id == activity.id,
                            ActivityStream.stream_type == stream_type,
                        )
                    )
                    existing_row = existing.scalar_one_or_none()
                    if existing_row is None:
                        session.add(
                            ActivityStream.from_strava_stream(
                                activity.id, stream_type, data_list
                            )
                        )
                activity.streams_fetched = True

            streams_result = await session.execute(
                select(ActivityStream).where(ActivityStream.activity_id == activity.id)
            )
            streams = streams_result.scalars().all()
            activity_id_val = activity_id

        return {
            "_meta": make_meta(),
            "activity_strava_id": activity_id_val,
            "streams": {
                s.stream_type: {"data_length": s.data_length, "data": s.data}
                for s in streams
            },
        }

    out = asyncio.run(_fetch())
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_streams_summary(out["streams"], activity_id)


_VALID_STREAMS = frozenset(
    {
        "heartrate",
        "pace",
        "velocity_smooth",
        "speed",
        "gap",
        "wap",
        "altitude",
        "distance",
        "cadence",
        "watts",
    }
)

_CYCLING_SPORTS = frozenset(
    {
        "Ride",
        "VirtualRide",
        "EBikeRide",
        "GravelRide",
        "MountainBikeRide",
        "Handcycle",
        "Velomobile",
    }
)


def _minetti_gap_factor(grade_pct: float) -> float:
    """Energy cost ratio relative to flat running (Minetti et al.)."""
    g = max(-0.45, min(0.45, grade_pct / 100.0))
    cost = 155.4 * g**5 - 30.4 * g**4 - 43.3 * g**3 + 46.3 * g**2 + 19.5 * g + 3.6
    return cost / 3.6  # 3.6 = cost at g=0


def _compute_gap(velocity: list[float], grade: list[float]) -> list[float]:
    """Grade-adjusted velocity (m/s) using Minetti formula."""
    result = []
    for v, gr in zip(velocity, grade, strict=False):
        if v is None or v <= 0:
            result.append(0.0)
        else:
            factor = _minetti_gap_factor(gr if gr is not None else 0.0)
            result.append(v / max(0.1, factor))
    return result


def _compute_wap(velocity: list[float], window: int = 30) -> list[float]:
    """Rolling mean velocity (m/s) over `window` samples — smoothed pace."""
    n = len(velocity)
    result = []
    half = window // 2
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        vals = [v for v in velocity[lo:hi] if v is not None and v > 0]
        result.append(sum(vals) / len(vals) if vals else 0.0)
    return result


@app.command("chart")
def chart_activity(
    activity_id: int = typer.Argument(..., help="Strava activity ID."),
    stream: str | None = typer.Option(
        None,
        "--stream",
        help=(
            "Stream to chart: heartrate, pace, velocity_smooth, speed, "
            "gap (grade-adjusted pace), wap (smoothed pace), "
            "altitude, distance, cadence, watts. "
            "pace/velocity_smooth auto-display as speed (km/h) for cycling activities."
        ),
    ),
    x_axis: str = typer.Option(
        "time",
        "--x-axis",
        help="X-axis source: 'time' (seconds) or 'distance' (meters).",
    ),
    from_val: float | None = typer.Option(
        None,
        "--from",
        help="Start of x-axis zoom range (seconds for time, meters for distance).",
    ),
    to_val: float | None = typer.Option(
        None,
        "--to",
        help="End of x-axis zoom range (seconds for time, meters for distance).",
    ),
    width: int | None = typer.Option(
        None,
        "--width",
        min=3,
        help="Chart width in characters. Defaults to terminal width minus margins.",
    ),
    height: int = typer.Option(20, "--height", min=3, help="Chart height in rows."),
    resolution: int | None = typer.Option(
        None,
        "--resolution",
        min=1,
        help=(
            "Number of data buckets. Lower = smoother (interpolated) curve; "
            "higher = more detail. Max useful value equals --width. "
            "Defaults to width (full detail)."
        ),
    ),
) -> None:
    """Render an activity stream as an ASCII chart in the terminal."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    # Auto-detect terminal width, leaving room for the Y_MARGIN (8 chars) + 1 safety col.
    _Y_MARGIN = 9
    effective_width: int
    if width is not None:
        effective_width = width
    else:
        term_cols = shutil.get_terminal_size(fallback=(80, 24)).columns
        effective_width = max(20, term_cols - _Y_MARGIN)

    # Warn if resolution is capped by width (user might not realise)
    if resolution is not None and resolution > effective_width:
        typer.echo(
            f"[dim]Note: --resolution {resolution} capped at --width {effective_width} "
            f"(can't have more buckets than columns).[/dim]"
        )

    # Normalise pace alias → velocity_smooth
    requested_stream = stream
    if requested_stream == "pace":
        requested_stream = "velocity_smooth"

    if requested_stream is not None and requested_stream not in _VALID_STREAMS:
        typer.echo(
            f"Unknown stream '{requested_stream}'. Valid options: {', '.join(sorted(_VALID_STREAMS))}",
            err=True,
        )
        raise typer.Exit(1)

    if x_axis not in ("time", "distance"):
        typer.echo("--x-axis must be 'time' or 'distance'.", err=True)
        raise typer.Exit(1)

    async def _fetch() -> None:
        async with get_async_session() as session:
            act_result = await session.execute(
                select(Activity).where(Activity.strava_id == activity_id)
            )
            activity = act_result.scalar_one_or_none()

        if activity is None:
            typer.echo(
                f"Activity {activity_id} not found locally. Run `fitops sync run` first.",
                err=True,
            )
            raise typer.Exit(1)

        if not activity.streams_fetched:
            typer.echo(
                f"Streams not synced for activity {activity_id}. "
                f"Run: fitops activities streams {activity_id}",
                err=True,
            )
            raise typer.Exit(1)

        async with get_async_session() as session:
            streams_result = await session.execute(
                select(ActivityStream).where(ActivityStream.activity_id == activity.id)
            )
            streams_by_type = {
                s.stream_type: s.data for s in streams_result.scalars().all()
            }

        is_cycling = activity.sport_type in _CYCLING_SPORTS

        # Default stream selection
        chosen_stream = requested_stream
        if chosen_stream is None:
            chosen_stream = (
                "heartrate" if "heartrate" in streams_by_type else "velocity_smooth"
            )

        # For velocity_smooth on cycling → auto-upgrade to speed (km/h) display
        display_stream = chosen_stream
        if chosen_stream == "velocity_smooth" and is_cycling:
            display_stream = "speed"

        # Derived streams: gap and wap are computed, not stored
        derived_streams = {"gap", "wap"}

        if chosen_stream in derived_streams:
            if "velocity_smooth" not in streams_by_type:
                typer.echo(
                    f"Stream 'velocity_smooth' required for '{chosen_stream}' but not available.",
                    err=True,
                )
                raise typer.Exit(1)
            vel = streams_by_type["velocity_smooth"]

            if chosen_stream == "gap":
                if "grade_smooth" not in streams_by_type:
                    typer.echo(
                        "Stream 'grade_smooth' required for GAP but not available for this activity.",
                        err=True,
                    )
                    raise typer.Exit(1)
                grade = streams_by_type["grade_smooth"]
                n_align = min(len(vel), len(grade))
                y_data: list[float] = _compute_gap(vel[:n_align], grade[:n_align])
            else:  # wap
                y_data = _compute_wap(vel)

        elif chosen_stream == "speed":
            # Explicit speed request: use velocity_smooth data, display as km/h
            if "velocity_smooth" not in streams_by_type:
                typer.echo(
                    "Stream 'velocity_smooth' not available for this activity.",
                    err=True,
                )
                raise typer.Exit(1)
            y_data = streams_by_type["velocity_smooth"]
            display_stream = "speed"

        else:
            if chosen_stream not in streams_by_type:
                available = ", ".join(sorted(streams_by_type.keys()))
                typer.echo(
                    f"Stream '{chosen_stream}' not available for this activity. "
                    f"Available: {available}",
                    err=True,
                )
                raise typer.Exit(1)
            y_data = streams_by_type[chosen_stream]

        # Resolve x-values
        if x_axis == "time":
            if "time" in streams_by_type:
                x_values: list[float] = [float(v) for v in streams_by_type["time"]]
                x_label = "time (s)"
            else:
                typer.echo(
                    "[dim]No time stream found; using sample index as x-axis.[/dim]"
                )
                x_values = list(range(len(y_data)))
                x_label = "time (s)"
        else:  # distance
            if "distance" not in streams_by_type:
                typer.echo("Distance stream not available for this activity.", err=True)
                raise typer.Exit(1)
            x_values = [float(v) for v in streams_by_type["distance"]]
            x_label = "distance (m)"

        # Align lengths
        n = min(len(y_data), len(x_values))
        y_data = y_data[:n]
        x_values = x_values[:n]

        # Apply zoom
        if from_val is not None or to_val is not None:
            indices = [
                i
                for i, xv in enumerate(x_values)
                if (from_val is None or xv >= from_val)
                and (to_val is None or xv <= to_val)
            ]
            if not indices:
                typer.echo("Zoom range produces no data points.", err=True)
                raise typer.Exit(1)
            y_data = [y_data[i] for i in indices]
            x_values = [x_values[i] for i in indices]

        print_stream_chart(
            activity_id,
            display_stream,
            y_data,
            x_values,
            x_label,
            effective_width,
            height,
            resolution,
        )

    asyncio.run(_fetch())
