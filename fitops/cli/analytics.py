from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer

from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.analytics.training_load import compute_training_load, _compute_overtraining_indicators
from fitops.analytics.vo2max import estimate_vo2max
from fitops.analytics.zones import compute_zones
from fitops.analytics.zone_inference import infer_zones, save_inferred_zones
from fitops.analytics.trends import compute_trends
from fitops.analytics.performance_metrics import compute_performance_metrics
from fitops.analytics.power_curves import compute_power_curve
from fitops.config.settings import get_settings
from fitops.db.migrations import init_db
from fitops.output.formatter import make_meta
from fitops.output.text_formatter import (
    print_training_load,
    print_vo2max,
    print_analytics_zones,
    print_trends,
    print_performance,
    print_power_curve,
    print_pace_zones,
    print_snapshot,
)
from fitops.utils.exceptions import NotAuthenticatedError

app = typer.Typer(no_args_is_help=True)


@app.command("training-load")
def training_load(
    days: int = typer.Option(90, "--days", help="Number of days of history to show."),
    sport: Optional[str] = typer.Option(None, "--sport", help="Filter by sport type (e.g. Run, Ride)."),
    today: bool = typer.Option(False, "--today", help="Show only today's current values."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Show CTL (fitness), ATL (fatigue), and TSB (form) training load."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()
    result = asyncio.run(compute_training_load(athlete_id=settings.athlete_id, days=days, sport_filter=sport))

    if not result.history:
        typer.echo("No activity data found. Run `fitops sync run` first.", err=True)
        return

    current = result.current
    ramp = result.ramp_rate_pct

    overtraining = _compute_overtraining_indicators(result.history)

    if today:
        output = {
            "_meta": make_meta(filters_applied={"sport": sport, "today_only": True}),
            "training_load": {
                "current": {
                    "date": str(current.date), "ctl": current.ctl, "atl": current.atl,
                    "tsb": current.tsb, "form_label": result.form_label(current.tsb),
                },
                "trend_7_days": {
                    "ctl_change": round(current.ctl - result.history[-8].ctl, 2) if len(result.history) >= 8 else None,
                    "ramp_rate_pct": round(ramp, 2) if ramp is not None else None,
                    "ramp_label": result.ramp_label(ramp) if ramp is not None else None,
                },
                "overtraining_indicators": overtraining,
            },
        }
    else:
        output = {
            "_meta": make_meta(total_count=len(result.history), filters_applied={"sport": sport, "days": days}),
            "training_load": {
                "current": {
                    "date": str(current.date), "ctl": current.ctl, "atl": current.atl,
                    "tsb": current.tsb, "form_label": result.form_label(current.tsb),
                },
                "trend_7_days": {
                    "ramp_rate_pct": round(ramp, 2) if ramp is not None else None,
                    "ramp_label": result.ramp_label(ramp) if ramp is not None else None,
                },
                "overtraining_indicators": overtraining,
                "history": [
                    {"date": str(d.date), "ctl": d.ctl, "atl": d.atl, "tsb": d.tsb, "daily_tss": d.daily_tss}
                    for d in result.history
                ],
            },
        }
    if json_output:
        typer.echo(json.dumps(output, indent=2, default=str))
    else:
        print_training_load(output, today)


@app.command("vo2max")
def vo2max(
    activities: int = typer.Option(10, "--activities", help="Number of recent qualifying activities to consider."),
    age_adjusted: bool = typer.Option(False, "--age-adjusted", help="Apply age-based adjustment to VO2max estimate."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Estimate VO2max from recent run activities."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()
    result = asyncio.run(estimate_vo2max(athlete_id=settings.athlete_id, max_activities=activities))

    if result is None:
        typer.echo("No qualifying run activities found. Need at least 1500m run.", err=True)
        return

    vo2max_block: dict = {
        "estimate": result.estimate, "unit": "ml/kg/min",
        "confidence": result.confidence, "confidence_label": result.confidence_label,
        "method_estimates": {"daniels_vdot": result.vdot, "cooper": result.cooper},
        "based_on_activity": {
            "strava_id": result.activity_strava_id, "name": result.activity_name,
            "distance_km": result.distance_km, "pace_per_km": result.pace_per_km, "date": result.activity_date,
        },
    }

    if age_adjusted:
        from fitops.analytics.vo2max import apply_age_adjustment
        from fitops.db.models.athlete import Athlete
        from fitops.db.session import get_async_session
        from sqlalchemy import select

        async def _get_age():
            async with get_async_session() as session:
                ath = (await session.execute(
                    select(Athlete).where(Athlete.strava_id == settings.athlete_id)
                )).scalar_one_or_none()
                return ath.age if ath else None

        age = asyncio.run(_get_age())
        if age is not None:
            adj_estimate, age_factor = apply_age_adjustment(result.estimate, age)
            vo2max_block["age_adjusted"] = {
                "age": age,
                "age_factor": age_factor,
                "adjusted_estimate": adj_estimate,
                "unit": "ml/kg/min",
            }
        else:
            vo2max_block["age_adjusted"] = {"error": "No birthday stored for athlete."}

    out = {"_meta": make_meta(), "vo2max": vo2max_block}
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        print_vo2max(out)


@app.command("zones")
def zones(
    method: Optional[str] = typer.Option(None, "--method", help="Zone method: lthr, max-hr, hrr."),
    set_lthr: Optional[int] = typer.Option(None, "--set-lthr", help="Set lactate threshold HR (BPM)."),
    set_max_hr: Optional[int] = typer.Option(None, "--set-max-hr", help="Set maximum HR (BPM)."),
    set_resting_hr: Optional[int] = typer.Option(None, "--set-resting-hr", help="Set resting HR (BPM)."),
    infer: bool = typer.Option(False, "--infer", help="Infer zones from cached activity streams."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Calculate heart rate training zones."""
    athlete_settings = get_athlete_settings()

    updates = {}
    if set_lthr is not None:
        updates["lthr"] = set_lthr
    if set_max_hr is not None:
        updates["max_hr"] = set_max_hr
    if set_resting_hr is not None:
        updates["resting_hr"] = set_resting_hr
    if updates:
        athlete_settings.set(**updates)
        typer.echo(f"Settings saved: {updates}")

    if infer:
        settings = get_settings()
        try:
            settings.require_auth()
        except NotAuthenticatedError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(1)
        init_db()
        inference_result = asyncio.run(infer_zones(athlete_id=settings.athlete_id))
        save_inferred_zones(inference_result)
        athlete_settings.reload()
        infer_out = {
            "_meta": make_meta(),
            "zone_inference": {
                "lthr_inferred": inference_result.lthr,
                "max_hr_inferred": inference_result.max_hr,
                "resting_hr_inferred": inference_result.resting_hr,
                "confidence": inference_result.confidence,
                "activity_count": inference_result.activity_count,
                "method": inference_result.inference_method,
            },
        }
        if json_output:
            typer.echo(json.dumps(infer_out, indent=2))
        else:
            print_analytics_zones(infer_out)

    if method is None:
        method = athlete_settings.best_zone_method()

    if method == "none":
        typer.echo("No zone parameters configured. Set LTHR: fitops analytics zones --set-lthr 165", err=True)
        return

    zone_result = compute_zones(method=method, lthr=athlete_settings.lthr, max_hr=athlete_settings.max_hr, resting_hr=athlete_settings.resting_hr)
    if zone_result is None:
        typer.echo(f"Missing parameters for method '{method}'.", err=True)
        return

    zones_out = {"_meta": make_meta(), "zones": zone_result.to_dict()}
    if json_output:
        typer.echo(json.dumps(zones_out, indent=2, default=str))
    else:
        print_analytics_zones(zones_out)


@app.command("trends")
def trends(
    sport: Optional[str] = typer.Option(None, "--sport", help="Filter by sport type (e.g. Run, Ride)."),
    days: int = typer.Option(180, "--days", help="Number of days of history to analyse."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Analyse training trends: volume, consistency, seasonal patterns, and performance."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()
    result = asyncio.run(compute_trends(athlete_id=settings.athlete_id, days=days, sport_filter=sport))

    if result is None:
        typer.echo("No activity data found for the specified period.", err=True)
        return

    # Compute overtraining indicators from training load history
    tl_result = asyncio.run(compute_training_load(athlete_id=settings.athlete_id, days=days, sport_filter=sport))
    overtraining = _compute_overtraining_indicators(tl_result.history)

    trends_out = {
        "_meta": make_meta(filters_applied={"sport": sport, "days": days}),
        "trends": {
            "activity_count": result.activity_count,
            "summary_label": result.summary_label,
            "volume_trend": result.volume_trend,
            "consistency": result.consistency,
            "seasonal": result.seasonal,
            "performance_trend": result.performance_trend,
            "overtraining_indicators": overtraining,
        },
    }
    if json_output:
        typer.echo(json.dumps(trends_out, indent=2, default=str))
    else:
        print_trends(trends_out)


@app.command("performance")
def performance(
    sport: Optional[str] = typer.Option(None, "--sport", help="Sport type: Run or Ride."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Show performance metrics (running economy, FTP estimate, efficiency scores)."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()
    result = asyncio.run(compute_performance_metrics(athlete_id=settings.athlete_id, sport=sport))

    if result is None:
        typer.echo("No qualifying activities found.", err=True)
        return

    perf_out = {
        "_meta": make_meta(filters_applied={"sport": sport}),
        "performance": {
            "sport": result.sport,
            "activity_count": result.activity_count,
            "overall_reliability": result.overall_reliability,
            "running": result.running,
            "cycling": result.cycling,
        },
    }
    if json_output:
        typer.echo(json.dumps(perf_out, indent=2, default=str))
    else:
        print_performance(perf_out)


@app.command("power-curve")
def power_curve(
    sport: str = typer.Option("Ride", "--sport", help="Sport type: Ride or Run."),
    activities: int = typer.Option(20, "--activities", help="Max number of recent activities to use."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Compute mean maximal power curve and critical power model."""
    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()
    result = asyncio.run(compute_power_curve(athlete_id=settings.athlete_id, sport=sport, max_activities=activities))

    if result is None:
        typer.echo("No activities with stream data found.", err=True)
        return

    pc_out = {
        "_meta": make_meta(filters_applied={"sport": sport, "max_activities": activities}),
        "power_curve": {
            "sport": result.sport,
            "activity_count": result.activity_count,
            "mean_maximal_power": result.mean_maximal_power,
            "critical_power_watts": result.critical_power,
            "w_prime_joules": result.w_prime,
            "model_r_squared": result.r_squared,
            "zones_from_cp": result.zones,
            "power_to_weight": result.power_to_weight,
        },
    }
    if json_output:
        typer.echo(json.dumps(pc_out, indent=2, default=str))
    else:
        print_power_curve(pc_out)


@app.command("pace-zones")
def pace_zones_cmd(
    set_threshold_pace: Optional[str] = typer.Option(None, "--set-threshold-pace", help="Set threshold pace as MM:SS (e.g. 5:45)."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Show or configure running pace zones."""
    from fitops.analytics.pace_zones import get_pace_zones, set_threshold_pace as save_threshold

    if set_threshold_pace:
        try:
            result = save_threshold(set_threshold_pace)
            typer.echo(f"Threshold pace set: {result.threshold_pace_fmt}/km")
        except ValueError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(1)
    else:
        result = get_pace_zones()
        if result is None:
            typer.echo(
                "No threshold pace configured. Set with: fitops analytics pace-zones --set-threshold-pace 5:00",
                err=True,
            )
            return

    pz_out = {
        "_meta": make_meta(),
        "pace_zones": {
            "threshold_pace": result.threshold_pace_fmt + "/km",
            "threshold_pace_s": result.threshold_pace_s,
            "source": result.source,
            "zones": result.zones,
        },
    }
    if json_output:
        typer.echo(json.dumps(pz_out, indent=2, default=str))
    else:
        print_pace_zones(pz_out)


@app.command("snapshot")
def snapshot(
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Compute and save today's analytics snapshot (CTL, ATL, TSB, VO2max)."""
    from datetime import date, datetime, timezone

    settings = get_settings()
    try:
        settings.require_auth()
    except NotAuthenticatedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    init_db()

    async def _save():
        from fitops.db.models.analytics_snapshot import AnalyticsSnapshot
        from fitops.db.session import get_async_session
        from sqlalchemy import select

        tl = await compute_training_load(athlete_id=settings.athlete_id, days=1)
        vo2 = await estimate_vo2max(athlete_id=settings.athlete_id)
        athlete_settings = get_athlete_settings()
        current = tl.current
        today = date.today()

        async with get_async_session() as session:
            res = await session.execute(
                select(AnalyticsSnapshot).where(
                    AnalyticsSnapshot.athlete_id == settings.athlete_id,
                    AnalyticsSnapshot.snapshot_date == today,
                    AnalyticsSnapshot.sport_type == None,
                )
            )
            existing = res.scalar_one_or_none()
            vals = dict(
                ctl=current.ctl if current else None,
                atl=current.atl if current else None,
                tsb=current.tsb if current else None,
                vo2max_estimate=vo2.estimate if vo2 else None,
                lt1_hr=int(athlete_settings.lthr * 0.92) if athlete_settings.lthr else None,
                lt2_hr=athlete_settings.lthr,
                computed_at=datetime.now(timezone.utc),
            )
            if existing:
                for k, v in vals.items():
                    setattr(existing, k, v)
            else:
                session.add(AnalyticsSnapshot(athlete_id=settings.athlete_id, snapshot_date=today, sport_type=None, **vals))

        return {"date": str(today), **{k: v for k, v in vals.items() if k != "computed_at"}}

    result_data = asyncio.run(_save())
    snap_out = {"_meta": make_meta(), "snapshot": result_data}
    if json_output:
        typer.echo(json.dumps(snap_out, indent=2, default=str))
    else:
        print_snapshot(snap_out)
