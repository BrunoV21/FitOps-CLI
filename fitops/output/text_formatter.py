from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich import box

console = Console(highlight=False)


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

def print_activities_table(activities: list[dict]) -> None:
    if not activities:
        console.print("[dim]No activities found.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Date", style="dim", no_wrap=True)
    table.add_column("Name")
    table.add_column("Sport", no_wrap=True)
    table.add_column("Dist", justify="right", no_wrap=True)
    table.add_column("Duration", justify="right", no_wrap=True)
    table.add_column("Pace/Speed", justify="right", no_wrap=True)
    table.add_column("HR", justify="right", no_wrap=True)

    for a in activities:
        activity_id = str(a.get("strava_activity_id") or "")
        date_str = (a.get("start_date_local") or "")[:10]
        name = a.get("name") or ""
        sport = a.get("sport_type") or ""
        dist = a.get("distance") or {}
        dist_km = dist.get("km")
        dist_str = f"{dist_km} km" if dist_km else "-"
        dur = (a.get("duration") or {}).get("moving_time_formatted") or "-"
        pace_block = a.get("pace")
        speed_block = a.get("speed") or {}
        if pace_block:
            perf = f"{pace_block.get('average_per_km') or '-'}/km"
        elif speed_block.get("average_kmh"):
            perf = f"{speed_block['average_kmh']} km/h"
        else:
            perf = "-"
        hr_block = a.get("heart_rate")
        hr = str(int(hr_block["average_bpm"])) if hr_block and hr_block.get("average_bpm") else "-"
        table.add_row(activity_id, date_str, name, sport, dist_str, dur, perf, hr)

    console.print(table)


def print_activity_detail(activity: dict) -> None:
    dist = activity.get("distance") or {}
    dur = activity.get("duration") or {}
    pace = activity.get("pace") or {}
    speed = activity.get("speed") or {}
    hr = activity.get("heart_rate") or {}
    elev = activity.get("elevation") or {}
    power = activity.get("power") or {}
    equip = activity.get("equipment") or {}
    training = activity.get("training_metrics") or {}
    flags = activity.get("flags") or {}
    insights = activity.get("insights") or {}

    date_str = (activity.get("start_date_local") or "")[:10]
    console.print(f"\n[bold]{activity.get('name', 'Activity')}[/bold]  "
                  f"[dim]{activity.get('sport_type', '')}  |  {date_str}[/dim]")
    console.print()

    # Overview
    dist_km = dist.get("km")
    dist_str = f"{dist_km} km" if dist_km else "-"
    dist_mi = dist.get("miles")
    if dist_mi:
        dist_str += f"  ({dist_mi} mi)"
    console.print(f"  Distance   {dist_str}")
    console.print(f"  Duration   {dur.get('moving_time_formatted') or '-'}")
    if pace.get("average_per_km"):
        console.print(f"  Pace       {pace['average_per_km']}/km  |  {pace.get('average_per_mile', '-')}/mi")
    elif speed.get("average_kmh"):
        console.print(f"  Speed      {speed['average_kmh']} km/h")
    if elev.get("total_gain_m"):
        console.print(f"  Elevation  +{elev['total_gain_m']} m")
    if hr.get("average_bpm"):
        console.print(f"  Heart Rate {int(hr['average_bpm'])} avg bpm  |  {hr.get('max_bpm') or '-'} max")
    if power.get("average_watts"):
        console.print(f"  Power      {power['average_watts']} avg W  |  {power.get('weighted_average_watts') or '-'} NP")
    if training.get("calories"):
        console.print(f"  Calories   {training['calories']}")
    if training.get("suffer_score"):
        console.print(f"  Suffer     {training['suffer_score']}")
    if equip.get("gear_name"):
        console.print(f"  Gear       {equip['gear_name']} ({equip.get('gear_type', '')})")

    active_flags = [k for k, v in flags.items() if v]
    if active_flags:
        console.print(f"  Flags      {', '.join(active_flags)}")

    if insights:
        drift = insights.get("hr_drift")
        if drift and drift.get("drift_bpm") is not None:
            console.print(f"  HR Drift   {drift['drift_bpm']:+.1f} bpm  ({drift.get('label', '')})")

    console.print()


def print_laps_table(laps: list[dict], activity_id: int) -> None:
    if not laps:
        console.print("[dim]No laps found.[/dim]")
        return

    console.print(f"\n[bold]Laps[/bold] for activity {activity_id}\n")
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("Lap", justify="right")
    table.add_column("Distance", justify="right")
    table.add_column("Time", justify="right")
    table.add_column("Pace", justify="right")
    table.add_column("HR", justify="right")
    table.add_column("Watts", justify="right")

    for lap in laps:
        lap_idx = str(lap.get("lap_index", ""))
        dist = lap.get("distance") or {}
        dist_km = dist.get("km")
        dist_str = f"{dist_km} km" if dist_km else "-"
        dur = (lap.get("duration") or {}).get("moving_time_formatted") or "-"
        speed = lap.get("average_speed_ms")
        pace_str = "-"
        if speed and speed > 0:
            secs = 1000 / speed
            m, s = int(secs // 60), int(secs % 60)
            pace_str = f"{m}:{s:02d}/km"
        hr = lap.get("heart_rate") or {}
        hr_str = str(int(hr["average_bpm"])) if hr.get("average_bpm") else "-"
        watts = lap.get("average_watts")
        watts_str = str(int(watts)) if watts else "-"
        table.add_row(lap_idx, dist_str, dur, pace_str, hr_str, watts_str)

    console.print(table)


def print_streams_summary(streams: dict, activity_id: int) -> None:
    console.print(f"\n[bold]Streams[/bold] for activity {activity_id}\n")
    if not streams:
        console.print("[dim]No streams cached.[/dim]")
        return
    for stream_type, info in streams.items():
        length = info.get("data_length") or (len(info.get("data") or []))
        console.print(f"  {stream_type:<25} {length} data points")
    console.print()


# ---------------------------------------------------------------------------
# Athlete
# ---------------------------------------------------------------------------

def print_athlete_profile(athlete: dict) -> None:
    console.print()
    console.print(f"[bold]{athlete.get('name') or 'Athlete'}[/bold]")
    if athlete.get("username"):
        console.print(f"  Username   @{athlete['username']}")
    loc_parts = [p for p in [athlete.get("city"), athlete.get("country")] if p]
    if loc_parts:
        console.print(f"  Location   {', '.join(loc_parts)}")
    if athlete.get("sex"):
        console.print(f"  Sex        {athlete['sex']}")
    if athlete.get("weight_kg"):
        console.print(f"  Weight     {athlete['weight_kg']} kg")
    equip = athlete.get("equipment") or {}
    bikes = equip.get("bikes") or []
    shoes = equip.get("shoes") or []
    console.print(f"  Bikes      {len(bikes)}")
    console.print(f"  Shoes      {len(shoes)}")
    console.print()


def print_athlete_stats(stats: dict) -> None:
    """Print cumulative Strava athlete stats."""
    console.print()

    def _print_totals(label: str, block: dict | None) -> None:
        if not block:
            return
        count = block.get("count", 0)
        dist_km = round(block.get("distance", 0) / 1000, 1) if block.get("distance") else 0
        time_h = round(block.get("moving_time", 0) / 3600, 1) if block.get("moving_time") else 0
        elev = block.get("elevation_gain", 0) or 0
        console.print(f"  [bold]{label}[/bold]   {count} activities  |  {dist_km} km  |  {time_h} h  |  +{int(elev)} m")

    _print_totals("All Runs (recent)", stats.get("recent_run_totals"))
    _print_totals("All Runs (YTD)",    stats.get("ytd_run_totals"))
    _print_totals("All Runs (total)",  stats.get("all_run_totals"))
    console.print()
    _print_totals("All Rides (recent)", stats.get("recent_ride_totals"))
    _print_totals("All Rides (YTD)",    stats.get("ytd_ride_totals"))
    _print_totals("All Rides (total)",  stats.get("all_ride_totals"))
    console.print()


def print_athlete_zones(zones: dict) -> None:
    console.print()
    hr_zones = zones.get("heart_rate") or {}
    hr_zone_list = hr_zones.get("zones") or []
    if hr_zone_list:
        console.print("[bold]Heart Rate Zones[/bold]")
        table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
        table.add_column("Zone", justify="right")
        table.add_column("Min bpm", justify="right")
        table.add_column("Max bpm", justify="right")
        for i, z in enumerate(hr_zone_list, 1):
            mn = str(z.get("min", "-"))
            mx = str(z.get("max", "-"))
            table.add_row(str(i), mn, mx)
        console.print(table)

    power_zones = zones.get("power") or {}
    pz_list = power_zones.get("zones") or []
    if pz_list:
        console.print("[bold]Power Zones[/bold]")
        table2 = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
        table2.add_column("Zone", justify="right")
        table2.add_column("Min W", justify="right")
        table2.add_column("Max W", justify="right")
        for i, z in enumerate(pz_list, 1):
            mn = str(z.get("min", "-"))
            mx = str(z.get("max", "-"))
            table2.add_row(str(i), mn, mx)
        console.print(table2)

    if not hr_zone_list and not pz_list:
        console.print("[dim]No zones configured in Strava.[/dim]")
    console.print()


def print_equipment_table(items: list[dict]) -> None:
    if not items:
        console.print("[dim]No equipment found.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Type", no_wrap=True)
    table.add_column("Strava Dist", justify="right", no_wrap=True)
    table.add_column("Local Dist", justify="right", no_wrap=True)
    table.add_column("Activities", justify="right", no_wrap=True)

    for item in items:
        name = item.get("name") or "-"
        if item.get("primary"):
            name += " [dim]*[/dim]"
        itype = item.get("type") or "-"
        strava_km = item.get("strava_total_distance_km") or 0
        local_km = item.get("local_activity_distance_km") or 0
        count = item.get("local_activity_count") or 0
        table.add_row(name, itype, f"{strava_km} km", f"{local_km} km", str(count))

    console.print(table)
    console.print("[dim]* = primary[/dim]")


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def print_sync_result(result: dict) -> None:
    sync_type = result.get("sync_type", "sync")
    created = result.get("activities_created", 0)
    updated = result.get("activities_updated", 0)
    pages = result.get("pages_fetched", 0)
    dur = result.get("duration_s", 0)
    console.print(
        f"[green]OK[/green] {sync_type.capitalize()} sync complete: "
        f"{created} created, {updated} updated  ({pages} pages, {dur}s)"
    )
    streams = result.get("streams")
    if streams:
        console.print(f"  Streams: {streams.get('streams_fetched', 0)} fetched, {streams.get('errors', 0)} errors")


def print_sync_streams_result(result: dict) -> None:
    fetched = result.get("streams_fetched", 0)
    errors = result.get("errors", 0)
    if result.get("message"):
        console.print(f"[dim]{result['message']}[/dim]")
    else:
        console.print(f"[green]OK[/green] Streams fetched: {fetched}  Errors: {errors}")


def print_sync_status(state: dict) -> None:
    console.print()
    last = state.get("last_sync_at") or "Never"
    total = state.get("activities_synced_total") or 0
    console.print(f"  Last sync        {last}")
    console.print(f"  Total synced     {total} activities")
    recent = state.get("recent_syncs") or []
    if recent:
        console.print()
        console.print("  Recent syncs:")
        for s in recent:
            ts = str(s.get("synced_at") or s.get("timestamp") or "")[:16]
            created = s.get("activities_created", 0)
            updated = s.get("activities_updated", 0)
            console.print(f"    {ts}   +{created} created  {updated} updated")
    console.print()


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def print_training_load(data: dict, today_only: bool) -> None:
    tl = data.get("training_load") or {}
    current = tl.get("current") or {}
    ctl = current.get("ctl")
    atl = current.get("atl")
    tsb = current.get("tsb")
    form = current.get("form_label") or ""
    date_str = current.get("date") or ""

    console.print()
    console.print(f"[bold]Training Load[/bold]  [dim]{date_str}[/dim]")
    console.print()
    if ctl is not None:
        console.print(f"  CTL (Fitness)   {ctl:.1f}")
    if atl is not None:
        console.print(f"  ATL (Fatigue)   {atl:.1f}")
    if tsb is not None:
        sign = "+" if tsb > 0 else ""
        console.print(f"  TSB (Form)      {sign}{tsb:.1f}  [{form}]")

    trend = tl.get("trend_7_days") or {}
    ramp = trend.get("ramp_rate_pct")
    ramp_label = trend.get("ramp_label")
    ctl_change = trend.get("ctl_change")
    if ramp is not None:
        sign = "+" if ramp > 0 else ""
        console.print(f"  7d Ramp Rate    {sign}{ramp}%  [{ramp_label or ''}]")
    if ctl_change is not None:
        sign = "+" if ctl_change > 0 else ""
        console.print(f"  7d CTL Change   {sign}{ctl_change}")

    ot = tl.get("overtraining_indicators") or {}
    if ot.get("risk_label"):
        console.print(f"  Overtraining    {ot['risk_label']}")

    if not today_only:
        history = tl.get("history") or []
        if history:
            console.print()
            table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
            table.add_column("Date", no_wrap=True)
            table.add_column("CTL", justify="right")
            table.add_column("ATL", justify="right")
            table.add_column("TSB", justify="right")
            table.add_column("TSS", justify="right")
            # Show last 14 entries to keep output manageable
            for d in history[-14:]:
                tsb_val = d.get("tsb") or 0
                sign = "+" if tsb_val > 0 else ""
                table.add_row(
                    str(d.get("date") or "")[:10],
                    f"{d.get('ctl') or 0:.1f}",
                    f"{d.get('atl') or 0:.1f}",
                    f"{sign}{tsb_val:.1f}",
                    str(int(d.get("daily_tss") or 0)),
                )
            console.print(table)

    console.print()


def print_vo2max(data: dict) -> None:
    v = data.get("vo2max") or {}
    console.print()
    console.print("[bold]VO2max Estimate[/bold]")
    console.print()
    if v.get("estimate"):
        conf = v.get("confidence_label") or ""
        console.print(f"  Estimate        {v['estimate']:.1f} ml/kg/min  [{conf}]")
    methods = v.get("method_estimates") or {}
    if methods.get("daniels_vdot"):
        console.print(f"  Daniels VDOT    {methods['daniels_vdot']:.1f}")
    if methods.get("cooper"):
        console.print(f"  Cooper          {methods['cooper']:.1f}")
    based = v.get("based_on_activity") or {}
    if based.get("name"):
        console.print(f"  Based on        {based['name']}  ({based.get('date') or ''})")
        console.print(f"                  {based.get('distance_km') or '-'} km  |  {based.get('pace_per_km') or '-'}/km")
    age_adj = v.get("age_adjusted") or {}
    if age_adj.get("adjusted_estimate"):
        console.print(f"  Age-adjusted    {age_adj['adjusted_estimate']:.1f} ml/kg/min  (age {age_adj.get('age')})")
    console.print()


def print_analytics_zones(data: dict) -> None:
    inference = data.get("zone_inference")
    if inference:
        console.print()
        console.print("[bold]Zone Inference[/bold]")
        console.print(f"  LTHR     {inference.get('lthr_inferred') or '-'} bpm")
        console.print(f"  Max HR   {inference.get('max_hr_inferred') or '-'} bpm")
        console.print(f"  Rest HR  {inference.get('resting_hr_inferred') or '-'} bpm")
        console.print(f"  Confidence  {inference.get('confidence') or '-'}  ({inference.get('activity_count')} activities)")
        console.print()
        return

    zones = data.get("zones") or {}
    method = zones.get("method") or ""
    zone_list = zones.get("zones") or []
    console.print()
    console.print(f"[bold]HR Zones[/bold]  [dim]method: {method}[/dim]")
    if zones.get("lthr"):
        console.print(f"  LTHR {zones['lthr']} bpm  |  Max HR {zones.get('max_hr') or '-'} bpm")
    console.print()
    if zone_list:
        table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
        table.add_column("Zone", justify="right")
        table.add_column("Name")
        table.add_column("Min bpm", justify="right")
        table.add_column("Max bpm", justify="right")
        for z in zone_list:
            mn = str(z.get("min_bpm") or z.get("min") or "-")
            mx = str(z.get("max_bpm") or z.get("max") or "-")
            table.add_row(str(z.get("zone") or ""), z.get("name") or "", mn, mx)
        console.print(table)
    console.print()


def print_trends(data: dict) -> None:
    t = data.get("trends") or {}
    console.print()
    console.print(f"[bold]Training Trends[/bold]  [dim]{t.get('summary_label') or ''}[/dim]")
    console.print(f"  Activities     {t.get('activity_count') or 0}")
    vol = t.get("volume_trend") or {}
    if vol.get("weekly_avg_km"):
        console.print(f"  Weekly avg     {vol['weekly_avg_km']} km")
    if vol.get("trend_label"):
        console.print(f"  Volume trend   {vol['trend_label']}")
    cons = t.get("consistency") or {}
    if cons.get("active_weeks_pct"):
        console.print(f"  Consistency    {cons['active_weeks_pct']}% active weeks")
    ot = t.get("overtraining_indicators") or {}
    if ot.get("risk_label"):
        console.print(f"  OT Risk        {ot['risk_label']}")
    console.print()


def print_performance(data: dict) -> None:
    p = data.get("performance") or {}
    console.print()
    console.print(f"[bold]Performance Metrics[/bold]  [dim]{p.get('sport') or ''}[/dim]")
    console.print(f"  Activities     {p.get('activity_count') or 0}")
    console.print(f"  Reliability    {p.get('overall_reliability') or '-'}")
    running = p.get("running") or {}
    if running:
        for k, v in running.items():
            if v is not None:
                console.print(f"  {k:<20} {v}")
    cycling = p.get("cycling") or {}
    if cycling:
        for k, v in cycling.items():
            if v is not None:
                console.print(f"  {k:<20} {v}")
    console.print()


def print_power_curve(data: dict) -> None:
    pc = data.get("power_curve") or {}
    console.print()
    console.print(f"[bold]Power Curve[/bold]  [dim]{pc.get('sport') or ''} | {pc.get('activity_count') or 0} activities[/dim]")
    if pc.get("critical_power_watts"):
        console.print(f"  Critical Power   {pc['critical_power_watts']:.0f} W")
    if pc.get("w_prime_joules"):
        console.print(f"  W'               {pc['w_prime_joules']:.0f} J")
    if pc.get("model_r_squared"):
        console.print(f"  Model R²         {pc['model_r_squared']:.3f}")
    pw = pc.get("power_to_weight") or {}
    if pw.get("cp_per_kg"):
        console.print(f"  CP/kg            {pw['cp_per_kg']:.2f} W/kg")
    mmp = pc.get("mean_maximal_power") or {}
    if mmp:
        console.print()
        console.print("  Mean Maximal Power:")
        for duration, watts in sorted(mmp.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0):
            if watts:
                console.print(f"    {duration}s  ->  {watts:.0f} W")
    console.print()


def print_pace_zones(data: dict) -> None:
    pz = data.get("pace_zones") or {}
    console.print()
    console.print(f"[bold]Pace Zones[/bold]  [dim]threshold: {pz.get('threshold_pace') or '-'}  ({pz.get('source') or ''})[/dim]")
    zone_list = pz.get("zones") or []
    if zone_list:
        table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
        table.add_column("Zone", justify="right")
        table.add_column("Name")
        table.add_column("Min pace", justify="right")
        table.add_column("Max pace", justify="right")
        for z in zone_list:
            table.add_row(
                str(z.get("zone") or ""),
                z.get("name") or "",
                z.get("min_pace") or "-",
                z.get("max_pace") or "-",
            )
        console.print(table)
    console.print()


def print_snapshot(data: dict) -> None:
    s = data.get("snapshot") or {}
    console.print()
    console.print(f"[bold]Snapshot saved[/bold]  [dim]{s.get('date') or ''}[/dim]")
    if s.get("ctl") is not None:
        console.print(f"  CTL     {s['ctl']:.1f}")
    if s.get("atl") is not None:
        console.print(f"  ATL     {s['atl']:.1f}")
    if s.get("tsb") is not None:
        console.print(f"  TSB     {s['tsb']:.1f}")
    if s.get("vo2max_estimate") is not None:
        console.print(f"  VO2max  {s['vo2max_estimate']:.1f} ml/kg/min")
    console.print()
