from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer

from fitops.analytics.athlete_settings import get_athlete_settings
from fitops.analytics.training_load import compute_training_load, _compute_overtraining_indicators
from fitops.analytics.vo2max import estimate_vo2max, compute_race_predictions
from fitops.dashboard.queries.analytics import get_volume_summary
from fitops.analytics.zones import compute_zones
from fitops.analytics.zone_inference import infer_zones, infer_lt1_pace, infer_lt2_pace, save_inferred_zones, vo2max_pace_from_vdot
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
    volume_summary = asyncio.run(get_volume_summary(athlete_id=settings.athlete_id, sport=sport))

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
                "volume_summary": volume_summary,
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
                "volume_summary": volume_summary,
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
    activities: int = typer.Option(50, "--activities", help="Number of recent qualifying activities to consider."),
    age_adjusted: bool = typer.Option(False, "--age-adjusted", help="Apply age-based adjustment to VO2max estimate."),
    method: Optional[str] = typer.Option(None, "--method", help="Method to use as estimate: daniels, cooper, composite."),
    save: bool = typer.Option(False, "--save", help="Save the selected method's result as a manual override."),
    set_override: Optional[float] = typer.Option(None, "--set-override", help="Directly set VO2max override value (ml/kg/min)."),
    clear_override: bool = typer.Option(False, "--clear-override", help="Clear manual VO2max override."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Estimate VO2max from recent run activities."""
    athlete_settings = get_athlete_settings()

    if clear_override:
        athlete_settings.clear("vo2max_override")
        typer.echo("VO2max override cleared.")
        if not set_override and not save:
            return

    if set_override is not None:
        athlete_settings.set(vo2max_override=round(set_override, 1))
        typer.echo(f"VO2max override set: {set_override} ml/kg/min")
        return

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

    # Pick estimate for the selected method
    method_value: Optional[float] = None
    if method == "daniels":
        method_value = result.vdot
    elif method == "cooper":
        method_value = result.cooper
    elif method in (None, "composite"):
        method_value = result.estimate

    if save and method_value is not None:
        athlete_settings.set(vo2max_override=round(float(method_value), 1))
        typer.echo(f"VO2max override saved ({method or 'composite'}): {method_value} ml/kg/min")

    vo2max_block: dict = {
        "estimate": method_value if method else result.estimate,
        "unit": "ml/kg/min",
        "confidence": result.confidence, "confidence_label": result.confidence_label,
        "method_estimates": {"daniels_vdot": result.vdot, "cooper": result.cooper},
        "selected_method": method or "composite",
        "override_saved": save and method_value is not None,
        "based_on_activity": {
            "strava_id": result.activity_strava_id, "name": result.activity_name,
            "distance_km": result.distance_km, "pace_per_km": result.pace_per_km, "date": result.activity_date,
        },
    }

    if athlete_settings.vo2max_override:
        vo2max_block["manual_override"] = athlete_settings.vo2max_override

    race_preds = compute_race_predictions(result, lt2_pace_s=athlete_settings.threshold_pace_per_km_s)
    if race_preds:
        vo2max_block["race_predictions"] = race_preds

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
    set_lt1: Optional[int] = typer.Option(None, "--set-lt1", help="Override LT1 aerobic threshold display (BPM)."),
    set_lt2: Optional[int] = typer.Option(None, "--set-lt2", help="Override LT2 lactate threshold display (BPM)."),
    clear_lt1: bool = typer.Option(False, "--clear-lt1", help="Clear LT1 override."),
    clear_lt2: bool = typer.Option(False, "--clear-lt2", help="Clear LT2 override."),
    infer: bool = typer.Option(False, "--infer", help="Infer zones from cached activity streams."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted text."),
) -> None:
    """Calculate heart rate training zones."""
    athlete_settings = get_athlete_settings()

    # Handle clears first
    clear_keys = []
    if clear_lt1:
        clear_keys.append("lt1_hr")
    if clear_lt2:
        clear_keys.append("lt2_hr")
    if clear_keys:
        athlete_settings.clear(*clear_keys)
        typer.echo(f"Cleared: {', '.join(clear_keys)}")

    updates = {}
    if set_lthr is not None:
        updates["lthr"] = set_lthr
    if set_max_hr is not None:
        updates["max_hr"] = set_max_hr
    if set_resting_hr is not None:
        updates["resting_hr"] = set_resting_hr
    if set_lt1 is not None:
        updates["lt1_hr"] = set_lt1
    if set_lt2 is not None:
        updates["lt2_hr"] = set_lt2
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
        lt2_pace_s_inferred: Optional[float] = None
        lt1_pace_s_inferred: Optional[float] = None
        vo2max_pace_s_computed: Optional[float] = None
        if athlete_settings.lthr:
            lt2_pace_s_inferred = asyncio.run(infer_lt2_pace(athlete_id=settings.athlete_id, lthr=athlete_settings.lthr))
            if lt2_pace_s_inferred is not None:
                athlete_settings.set(threshold_pace_per_km_s=lt2_pace_s_inferred)
            # LT1 pace from GAP at ±6 bpm of LT1
            zone_for_infer = compute_zones(method="lthr", lthr=athlete_settings.lthr)
            if zone_for_infer and zone_for_infer.lt1_bpm:
                lt1_pace_s_inferred = asyncio.run(infer_lt1_pace(athlete_id=settings.athlete_id, lt1_bpm=zone_for_infer.lt1_bpm))
                if lt1_pace_s_inferred is not None:
                    athlete_settings.set(lt1_pace_s=lt1_pace_s_inferred)
        # VO2Max pace derived from VDOT (mathematical — more reliable than sparse HR data)
        vo2max_result_for_infer = asyncio.run(estimate_vo2max(athlete_id=settings.athlete_id))
        if vo2max_result_for_infer and vo2max_result_for_infer.vdot:
            vo2max_pace_s_computed = vo2max_pace_from_vdot(vo2max_result_for_infer.vdot)
            athlete_settings.set(vo2max_pace_s=vo2max_pace_s_computed)
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

        def _fmt(s: float) -> str:
            return f"{int(s // 60)}:{int(s % 60):02d}/km"

        if lt1_pace_s_inferred is not None:
            infer_out["zone_inference"]["lt1_pace_inferred"] = _fmt(lt1_pace_s_inferred)
            infer_out["zone_inference"]["lt1_pace_s"] = lt1_pace_s_inferred
        if lt2_pace_s_inferred is not None:
            infer_out["zone_inference"]["lt2_pace_inferred"] = _fmt(lt2_pace_s_inferred)
            infer_out["zone_inference"]["lt2_pace_s"] = lt2_pace_s_inferred
        if vo2max_pace_s_computed is not None:
            infer_out["zone_inference"]["vo2max_pace_computed"] = _fmt(vo2max_pace_s_computed)
            infer_out["zone_inference"]["vo2max_pace_s"] = vo2max_pace_s_computed
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
    # Inject GAP-based threshold paces if available
    def _inject_pace(key_fmt: str, key_s: str, pace_s: Optional[float]) -> None:
        if pace_s is not None:
            zones_out["zones"]["thresholds"][key_fmt] = f"{int(pace_s // 60)}:{int(pace_s % 60):02d}/km"
            zones_out["zones"]["thresholds"][key_s] = pace_s
    _inject_pace("lt1_pace_fmt", "lt1_pace_s", athlete_settings.lt1_pace_s)
    _inject_pace("lt2_pace_fmt", "lt2_pace_s", athlete_settings.threshold_pace_per_km_s)
    _inject_pace("vo2max_pace_fmt", "vo2max_pace_s", athlete_settings.vo2max_pace_s)
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
                lt1_hr=(
                    athlete_settings.lt1_hr
                    if athlete_settings.lt1_hr is not None
                    else (int(athlete_settings.lthr * 0.92) if athlete_settings.lthr else None)
                ),
                lt2_hr=(
                    athlete_settings.lt2_hr
                    if athlete_settings.lt2_hr is not None
                    else athlete_settings.lthr
                ),
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
