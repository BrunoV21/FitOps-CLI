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


@app.command("list")
def list_activities(
    sport: str | None = typer.Option(
        None, "--sport", help="Filter by sport type (e.g. Run, Ride)."
    ),
    limit: int = typer.Option(
        20, "--limit", help="Max number of activities to return."
    ),
    after: str | None = typer.Option(
        None, "--after", help="Filter activities after date (YYYY-MM-DD)."
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

    init_db()

    async def _fetch():
        gear_lookup = await _get_gear_lookup()
        async with get_async_session() as session:
            stmt = select(Activity).order_by(desc(Activity.start_date))
            if sport:
                stmt = stmt.where(Activity.sport_type == sport)
            if after:
                try:
                    after_dt = datetime.fromisoformat(after).replace(tzinfo=UTC)
                    stmt = stmt.where(Activity.start_date >= after_dt)
                except ValueError:
                    pass
            stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        formatted = [
            format_activity_row(
                {c.name: getattr(r, c.name) for c in r.__table__.columns},
                gear_lookup,
            )
            for r in rows
        ]
        filters: dict = {"limit": limit}
        if sport:
            filters["sport_type"] = sport
        if after:
            filters["after"] = after
        return {
            "_meta": make_meta(total_count=len(formatted), filters_applied=filters),
            "activities": formatted,
        }

    output = asyncio.run(_fetch())
    if json_output:
        typer.echo(json.dumps(output, indent=2, default=str))
    else:
        print_activities_table(output["activities"])


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

        # Compute aerobic / anaerobic training scores
        from fitops.analytics.athlete_settings import get_athlete_settings
        from fitops.analytics.training_scores import (
            compute_aerobic_score,
            compute_anaerobic_score,
        )

        _settings = get_athlete_settings()
        formatted.setdefault("insights", {})
        formatted["insights"]["aerobic_training_score"] = compute_aerobic_score(
            row, _settings
        )
        formatted["insights"]["anaerobic_training_score"] = compute_anaerobic_score(
            row, _settings
        )

        # Enrich with HR drift if streams are available
        if row.streams_fetched:
            from fitops.analytics.activity_insights import compute_hr_drift

            async with get_async_session() as session:
                hr_res = await session.execute(
                    select(ActivityStream).where(
                        ActivityStream.activity_id == row.id,
                        ActivityStream.stream_type == "heartrate",
                    )
                )
                vel_res = await session.execute(
                    select(ActivityStream).where(
                        ActivityStream.activity_id == row.id,
                        ActivityStream.stream_type == "velocity_smooth",
                    )
                )
                hr_row = hr_res.scalar_one_or_none()
                vel_row = vel_res.scalar_one_or_none()
            if hr_row and vel_row:
                drift = compute_hr_drift(hr_row.data or [], vel_row.data or [])
                if drift:
                    formatted["insights"]["hr_drift"] = drift

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
