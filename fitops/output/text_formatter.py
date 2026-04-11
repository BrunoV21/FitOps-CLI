from __future__ import annotations

from rich import box
from rich.console import Console
from rich.table import Table

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
        hr = (
            str(int(hr_block["average_bpm"]))
            if hr_block and hr_block.get("average_bpm")
            else "-"
        )
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
    console.print(
        f"\n[bold]{activity.get('name', 'Activity')}[/bold]  "
        f"[dim]{activity.get('sport_type', '')}  |  {date_str}[/dim]"
    )
    console.print()

    # Overview
    dist_km = dist.get("km")
    dist_str = f"{dist_km} km" if dist_km else "-"
    console.print(f"  Distance   {dist_str}")
    console.print(f"  Duration   {dur.get('moving_time_formatted') or '-'}")
    if pace.get("average_per_km"):
        console.print(
            f"  Pace       {pace['average_per_km']}/km  |  {pace.get('average_per_mile', '-')}/mi"
        )
    elif speed.get("average_kmh"):
        console.print(f"  Speed      {speed['average_kmh']} km/h")
    if elev.get("total_gain_m"):
        console.print(f"  Elevation  +{elev['total_gain_m']} m")
    if hr.get("average_bpm"):
        console.print(
            f"  Heart Rate {int(hr['average_bpm'])} avg bpm  |  {hr.get('max_bpm') or '-'} max"
        )
    if power.get("average_watts"):
        console.print(
            f"  Power      {power['average_watts']} avg W  |  {power.get('weighted_average_watts') or '-'} NP"
        )
    if training.get("calories"):
        console.print(f"  Calories   {training['calories']}")
    if training.get("suffer_score"):
        console.print(f"  Suffer     {training['suffer_score']}")
    if equip.get("gear_name"):
        console.print(
            f"  Gear       {equip['gear_name']} ({equip.get('gear_type', '')})"
        )

    active_flags = [k for k, v in flags.items() if v]
    if active_flags:
        console.print(f"  Flags      {', '.join(active_flags)}")

    if insights:
        ae = insights.get("aerobic_training_score")
        an = insights.get("anaerobic_training_score")
        if ae is not None or an is not None:
            ae_str = f"{ae}" if ae is not None else "-"
            an_str = f"{an}" if an is not None else "-"
            console.print(
                f"  Training   Aerobic [bold]{ae_str}[/bold]  |  Anaerobic [bold]{an_str}[/bold]"
            )
        drift = insights.get("hr_drift")
        if drift and drift.get("drift_bpm") is not None:
            console.print(
                f"  HR Drift   {drift['drift_bpm']:+.1f} bpm  ({drift.get('label', '')})"
            )

    # Avg GAP / True Pace (top-level fields from stream analytics)
    avg_gap = activity.get("avg_gap")
    weather = activity.get("weather") or {}
    true_pace_fmt = weather.get("true_pace_fmt")
    if avg_gap or true_pace_fmt:
        parts = []
        if avg_gap:
            parts.append(f"GAP {avg_gap}")
        if true_pace_fmt:
            parts.append(f"True Pace {true_pace_fmt}")
        console.print(f"  Effort     {'  |  '.join(parts)}")

    # Weather conditions
    if weather:
        temp = weather.get("temp_fmt")
        condition = weather.get("condition")
        wbgt_flag = weather.get("wbgt_flag")
        wind_kmh = weather.get("wind_speed_kmh")
        wind_dir = weather.get("wind_dir_compass")
        precip = weather.get("precipitation_mm")

        weather_parts = []
        if temp:
            weather_parts.append(temp)
        if condition:
            weather_parts.append(condition)
        if wind_kmh is not None:
            wind_str = f"{wind_kmh} km/h"
            if wind_dir:
                wind_str += f" {wind_dir}"
            weather_parts.append(f"wind {wind_str}")
        if precip:
            weather_parts.append(f"{precip} mm rain")

        flag_colour = {
            "green": "green",
            "yellow": "yellow",
            "red": "red",
            "black": "white on black",
        }.get(wbgt_flag or "green", "green")
        flag_str = f" [{flag_colour}]●[/{flag_colour}]" if wbgt_flag else ""
        if weather_parts:
            console.print(f"  Weather{flag_str}   {',  '.join(weather_parts)}")

        wap_fmt = weather.get("wap_fmt")
        wap_pct = weather.get("wap_factor_pct")
        if wap_fmt and wap_pct is not None:
            direction = "harder" if wap_pct > 0 else "easier"
            console.print(
                f"  Adj Pace   {wap_fmt}  [dim]({wap_pct:+.1f}% conditions {direction})[/dim]"
            )

    console.print()

    # Tip footer — show available sub-commands
    sport = activity.get("sport_type") or ""
    is_run = sport in {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
    tips = []
    if is_run and activity.get("km_splits"):
        tips.append("--splits")
    if activity.get("workout"):
        tips.append("--workout")
    if activity.get("analytics") or activity.get("km_splits"):
        tips.append("--chart")
    if tips:
        aid = activity.get("strava_activity_id") or ""
        tip_flags = "  ·  ".join(f"fitops activities get {aid} {f}" for f in tips)
        console.print(f"[dim]  tip: {tip_flags}[/dim]")
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

    for lap in laps[:50]:  # cap at 50 laps — typical activities have < 30
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


def print_splits_table(splits: list[dict], activity_id: int) -> None:
    """Print per-km splits as a Rich table."""
    if not splits:
        console.print(
            "[dim]No splits available (requires streams for a running activity).[/dim]"
        )
        return

    has_true_pace = any(s.get("avg_true_pace") for s in splits)
    has_hr = any(s.get("avg_hr") for s in splits)
    has_cad = any(s.get("avg_cad") for s in splits)
    has_elev = any(
        s.get("elev_gain") is not None or s.get("elev_loss") is not None for s in splits
    )

    console.print(f"\n[bold]Km Splits[/bold]  (activity {activity_id})\n")
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("Km", justify="right")
    table.add_column("Pace", justify="right")
    if has_true_pace:
        table.add_column("True Pace", justify="right")
    if has_hr:
        table.add_column("HR", justify="right")
    if has_cad:
        table.add_column("Cad", justify="right")
    if has_elev:
        table.add_column("Elev+", justify="right")
        table.add_column("Elev−", justify="right")

    for s in splits:
        label = s.get("label") or str(s.get("km", ""))
        pace = s.get("pace") or "-"
        row = [label, pace]
        if has_true_pace:
            tp = s.get("avg_true_pace") or "-"
            row.append(tp)
        if has_hr:
            hr = str(s["avg_hr"]) if s.get("avg_hr") is not None else "-"
            row.append(hr)
        if has_cad:
            cad = str(s["avg_cad"]) if s.get("avg_cad") is not None else "-"
            row.append(cad)
        if has_elev:
            gain = f"+{s['elev_gain']}m" if s.get("elev_gain") is not None else "-"
            loss = f"-{s['elev_loss']}m" if s.get("elev_loss") is not None else "-"
            row.extend([gain, loss])
        table.add_row(*row)

    console.print(table)


def print_activity_workout_compliance(activity: dict) -> None:
    """Print linked workout plan and compliance summary."""
    workout = activity.get("workout")
    if not workout:
        console.print("[dim]No linked workout for this activity.[/dim]")
        return

    compliance_pct = workout.get("compliance_pct")
    pct_str = f"{compliance_pct}%" if compliance_pct is not None else "-"
    console.print(
        f"\n[bold]{workout.get('name', 'Workout')}[/bold]  compliance: {pct_str}\n"
    )

    segs = workout.get("segments") or []
    if not segs:
        console.print("[dim]No segments.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("Segment")
    table.add_column("Target", justify="right")
    table.add_column("Actual Pace", justify="right")
    table.add_column("Actual HR", justify="right")
    table.add_column("Compliance", justify="right")

    for seg in segs:
        name = seg.get("name") or "-"
        target = seg.get("target_description") or seg.get("target_pace") or "-"
        actuals = seg.get("actuals") or {}
        actual_pace = (
            actuals.get("avg_pace_formatted") or seg.get("avg_pace_per_km") or "-"
        )
        avg_hr = actuals.get("avg_heartrate")
        hr_str = str(round(avg_hr)) if avg_hr else "-"
        seg_compliance = seg.get("compliance_pct")
        compliance_str = f"{seg_compliance}%" if seg_compliance is not None else "-"
        table.add_row(name, str(target), str(actual_pace), hr_str, compliance_str)

    console.print(table)


def print_workout_splits(activity: dict) -> None:
    """Print km splits segmented by workout plan intervals."""
    workout = activity.get("workout")
    km_splits = activity.get("km_splits") or []

    if not workout:
        console.print("[dim]No linked workout — showing standard km splits.[/dim]")
        print_splits_table(km_splits, activity.get("strava_activity_id", 0))
        return

    if not km_splits:
        console.print("[dim]No km splits available (requires streams).[/dim]")
        return

    segs = workout.get("segments") or []
    if not segs:
        print_splits_table(km_splits, activity.get("strava_activity_id", 0))
        return

    has_true_pace = any(s.get("avg_true_pace") for s in km_splits)
    has_hr = any(s.get("avg_hr") for s in km_splits)

    console.print(
        f"\n[bold]{workout.get('name', 'Workout')}[/bold] — km splits by interval\n"
    )

    for seg in segs:
        seg_name = seg.get("name") or "Segment"
        start_km = seg.get("start_index")
        end_km = seg.get("end_index")

        actuals = seg.get("actuals") or {}
        actual_pace = (
            actuals.get("avg_pace_formatted") or seg.get("avg_pace_per_km") or "-"
        )
        compliance_pct = seg.get("compliance_pct")
        pct_str = (
            f" | compliance: {compliance_pct}%" if compliance_pct is not None else ""
        )

        console.print(f"  [bold]{seg_name}[/bold]  avg pace: {actual_pace}{pct_str}")

        # Filter km splits that fall within this segment's stream index range
        if start_km is not None and end_km is not None:
            # km_splits are 1-indexed; start_index/end_index are stream array indices
            # Map stream indices to approximate km numbers
            seg_splits = [
                s
                for s in km_splits
                if start_km <= (s.get("km", 0) - 1) * 1000 <= end_km
            ]
        else:
            seg_splits = km_splits

        if seg_splits:
            table = Table(box=box.SIMPLE, show_header=True, header_style="dim")
            table.add_column("Km", justify="right")
            table.add_column("Pace", justify="right")
            if has_true_pace:
                table.add_column("True Pace", justify="right")
            if has_hr:
                table.add_column("HR", justify="right")

            for s in seg_splits:
                label = s.get("label") or str(s.get("km", ""))
                pace = s.get("pace") or "-"
                row = [label, pace]
                if has_true_pace:
                    row.append(s.get("avg_true_pace") or "-")
                if has_hr:
                    hr = str(s["avg_hr"]) if s.get("avg_hr") is not None else "-"
                    row.append(hr)
                table.add_row(*row)
            console.print(table)

    console.print()


def print_stream_chart(
    _activity_id: int,
    stream_type: str,
    data: list[float],
    x_values: list[float],
    x_label: str,
    width: int,
    height: int,
    resolution: int | None = None,
) -> None:
    from fitops.output.ascii_chart import render_ascii_chart

    chart_str = render_ascii_chart(
        data=data,
        x_values=x_values,
        stream_type=stream_type,
        width=width,
        height=height,
        x_label=x_label,
        resolution=resolution,
    )
    console.print()
    console.print(chart_str, markup=False, highlight=False)
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

    phys = athlete.get("physiology") or {}
    has_phys = any(
        phys.get(k) for k in ("max_hr", "resting_hr", "lthr", "ftp", "lt1_pace", "lt2_pace", "vo2max")
    )
    if has_phys:
        console.print()
        console.print("[bold]Physiology[/bold]")
        if phys.get("max_hr"):
            console.print(f"  Max HR         {phys['max_hr']} bpm")
        if phys.get("lthr"):
            console.print(f"  LTHR           {phys['lthr']} bpm")
        if phys.get("resting_hr"):
            console.print(f"  Resting HR     {phys['resting_hr']} bpm")
        if phys.get("ftp"):
            console.print(f"  FTP            {phys['ftp']} W")
        if phys.get("lt1_pace"):
            console.print(f"  LT1 pace       {phys['lt1_pace']}  [dim](aerobic threshold)[/dim]")
        if phys.get("lt2_pace"):
            console.print(f"  LT2 pace       {phys['lt2_pace']}  [dim](lactate threshold)[/dim]")
        if phys.get("vo2max_pace"):
            console.print(f"  vVO2max        {phys['vo2max_pace']}  [dim](from VDOT)[/dim]")
        vo2max = phys.get("vo2max") or {}
        if vo2max.get("estimate"):
            conf = vo2max.get("confidence_label") or ""
            console.print(f"  VO2max         {vo2max['estimate']:.1f} ml/kg/min  [dim][{conf}][/dim]")
            based = vo2max.get("based_on_activity") or {}
            if based.get("name"):
                console.print(
                    f"                 based on: {based['name']}  ({based.get('date') or ''})"
                )

    console.print()


def print_athlete_stats(stats: dict) -> None:
    """Print cumulative Strava athlete stats."""
    console.print()

    def _print_totals(label: str, block: dict | None) -> None:
        if not block:
            return
        count = block.get("count", 0)
        dist_km = (
            round(block.get("distance", 0) / 1000, 1) if block.get("distance") else 0
        )
        time_h = (
            round(block.get("moving_time", 0) / 3600, 1)
            if block.get("moving_time")
            else 0
        )
        elev = block.get("elevation_gain", 0) or 0
        console.print(
            f"  [bold]{label}[/bold]   {count} activities  |  {dist_km} km  |  {time_h} h  |  +{int(elev)} m"
        )

    _print_totals("All Runs (recent)", stats.get("recent_run_totals"))
    _print_totals("All Runs (YTD)", stats.get("ytd_run_totals"))
    _print_totals("All Runs (total)", stats.get("all_run_totals"))
    console.print()
    _print_totals("All Rides (recent)", stats.get("recent_ride_totals"))
    _print_totals("All Rides (YTD)", stats.get("ytd_ride_totals"))
    _print_totals("All Rides (total)", stats.get("all_ride_totals"))
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


def print_athlete_computed_zones(data: dict) -> None:
    """Display computed HR + pace zones from local physiology settings."""
    zones = data.get("zones") or {}
    method = zones.get("method") or ""
    zone_list = zones.get("heart_rate_zones") or []
    thresholds = zones.get("thresholds") or {}
    pace_zones = data.get("pace_zones") or []

    console.print()
    console.print(f"[bold]HR Zones[/bold]  [dim]method: {method}[/dim]")
    if zones.get("lthr_bpm"):
        parts = [f"LTHR {zones['lthr_bpm']} bpm"]
        if zones.get("max_hr_bpm"):
            parts.append(f"Max HR {zones['max_hr_bpm']} bpm")
        if zones.get("resting_hr_bpm"):
            parts.append(f"Resting HR {zones['resting_hr_bpm']} bpm")
        console.print(f"  {' | '.join(parts)}")
    th = zones.get("thresholds") or {}
    if th.get("lt1_bpm"):
        console.print(f"  LT1  {th['lt1_bpm']} bpm")
    if th.get("lt2_bpm"):
        console.print(f"  LT2  {th['lt2_bpm']} bpm")
    if thresholds.get("lt1_pace_fmt"):
        console.print(f"  LT1 pace   {thresholds['lt1_pace_fmt']}  [dim](GAP)[/dim]")
    if thresholds.get("lt2_pace_fmt"):
        console.print(f"  LT2 pace   {thresholds['lt2_pace_fmt']}  [dim](GAP)[/dim]")
    if thresholds.get("vo2max_pace_fmt"):
        console.print(f"  vVO2max    {thresholds['vo2max_pace_fmt']}  [dim](from VDOT)[/dim]")
    console.print()
    if zone_list:
        hr_table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
        hr_table.add_column("Zone", justify="right")
        hr_table.add_column("Name")
        hr_table.add_column("Min bpm", justify="right")
        hr_table.add_column("Max bpm", justify="right")
        for z in zone_list:
            mn = str(z.get("min_bpm") or "-")
            mx_raw = z.get("max_bpm")
            mx = str(mx_raw) if mx_raw and mx_raw < 999 else "-"
            hr_table.add_row(str(z.get("zone") or ""), z.get("name") or "", mn, mx)
        console.print(hr_table)

    if pace_zones:
        console.print()
        console.print("[bold]Pace Zones[/bold]")
        console.print()
        pz_table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
        pz_table.add_column("Zone", justify="right")
        pz_table.add_column("Name")
        pz_table.add_column("Min pace", justify="right")
        pz_table.add_column("Max pace", justify="right")
        for z in pace_zones:
            mn = z.get("min_pace_fmt") or "-"
            mx = z.get("max_pace_fmt") or "-"
            pz_table.add_row(str(z.get("zone") or ""), z.get("name") or "", mn, mx)
        console.print(pz_table)

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
        console.print(
            f"  Streams: {streams.get('streams_fetched', 0)} fetched, {streams.get('errors', 0)} errors"
        )


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

    vol = tl.get("volume_summary") or {}
    if vol:
        console.print()
        console.print("  [bold]Volume[/bold]")
        tw = vol.get("this_week") or {}
        lw = vol.get("last_week") or {}
        tm = vol.get("this_month") or {}
        lm = vol.get("last_month") or {}
        wpct = (vol.get("pct_change_week") or {}).get("distance")
        mpct = (vol.get("pct_change_month") or {}).get("distance")
        wpct_str = (
            f"  ({'+' if wpct > 0 else ''}{wpct:.0f}% WoW)" if wpct is not None else ""
        )
        mpct_str = (
            f"  ({'+' if mpct > 0 else ''}{mpct:.0f}% vs same period last month)"
            if mpct is not None
            else ""
        )
        console.print(
            f"  This week       {tw.get('distance_km', 0):.1f} km  /  {tw.get('duration_h', 0):.1f} h{wpct_str}"
        )
        console.print(
            f"  Last week       {lw.get('distance_km', 0):.1f} km  /  {lw.get('duration_h', 0):.1f} h"
        )
        console.print(
            f"  This month      {tm.get('distance_km', 0):.0f} km  /  {tm.get('duration_h', 0):.1f} h{mpct_str}"
        )
        console.print(
            f"  Last month      {lm.get('distance_km', 0):.0f} km  /  {lm.get('duration_h', 0):.1f} h"
        )

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
        console.print(
            f"                  {based.get('distance_km') or '-'} km  |  {based.get('pace_per_km') or '-'}/km"
        )
    age_adj = v.get("age_adjusted") or {}
    if age_adj.get("adjusted_estimate"):
        console.print(
            f"  Age-adjusted    {age_adj['adjusted_estimate']:.1f} ml/kg/min  (age {age_adj.get('age')})"
        )
    race = v.get("race_predictions") or {}
    preds = race.get("predictions") or {}
    if preds:
        console.print()
        console.print(
            f"  [bold]Race Predictions[/bold]  [dim]{race.get('method', 'riegel').upper()} · from {race.get('source_distance_km', '?')} km @ {race.get('source_pace', '?')}/km[/dim]"
        )
        for label, pred in preds.items():
            console.print(
                f"  {label:<12} {pred.get('hms', '-'):<10}  {pred.get('predicted_pace', '-')}/km"
            )
    console.print()


def print_analytics_zones(data: dict) -> None:
    inference = data.get("zone_inference")
    if inference:
        console.print()
        console.print("[bold]Zone Inference[/bold]")
        console.print(f"  LTHR     {inference.get('lthr_inferred') or '-'} bpm")
        if inference.get("lt2_pace_inferred"):
            console.print(
                f"  LT2 pace {inference.get('lt2_pace_inferred')}  [dim](grade-adjusted)[/dim]"
            )
        console.print(f"  Max HR   {inference.get('max_hr_inferred') or '-'} bpm")
        console.print(f"  Rest HR  {inference.get('resting_hr_inferred') or '-'} bpm")
        console.print(
            f"  Confidence  {inference.get('confidence') or '-'}  ({inference.get('activity_count')} activities)"
        )
        console.print()
        return

    zones = data.get("zones") or {}
    method = zones.get("method") or ""
    zone_list = zones.get("heart_rate_zones") or []
    console.print()
    console.print(f"[bold]HR Zones[/bold]  [dim]method: {method}[/dim]")
    if zones.get("lthr_bpm"):
        parts = [f"LTHR {zones['lthr_bpm']} bpm"]
        if zones.get("max_hr_bpm"):
            parts.append(f"Max HR {zones['max_hr_bpm']} bpm")
        if zones.get("resting_hr_bpm"):
            parts.append(f"Resting HR {zones['resting_hr_bpm']} bpm")
        console.print(f"  {' | '.join(parts)}")
    thresholds = zones.get("thresholds") or {}
    if thresholds.get("lt1_pace_fmt"):
        console.print(f"  LT1 pace   {thresholds['lt1_pace_fmt']}  [dim](GAP)[/dim]")
    if thresholds.get("lt2_pace_fmt"):
        console.print(f"  LT2 pace   {thresholds['lt2_pace_fmt']}  [dim](GAP)[/dim]")
    if thresholds.get("vo2max_pace_fmt"):
        console.print(
            f"  vVO2max    {thresholds['vo2max_pace_fmt']}  [dim](from VDOT)[/dim]"
        )
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
    console.print(
        f"[bold]Training Trends[/bold]  [dim]{t.get('summary_label') or ''}[/dim]"
    )
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
    console.print(
        f"[bold]Performance Metrics[/bold]  [dim]{p.get('sport') or ''}[/dim]"
    )
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
    console.print(
        f"[bold]Power Curve[/bold]  [dim]{pc.get('sport') or ''} | {pc.get('activity_count') or 0} activities[/dim]"
    )
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
        for duration, watts in sorted(
            mmp.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0
        ):
            if watts:
                console.print(f"    {duration}s  ->  {watts:.0f} W")
    console.print()


def print_pace_zones(data: dict) -> None:
    pz = data.get("pace_zones") or {}
    console.print()
    console.print(
        f"[bold]Pace Zones[/bold]  [dim]threshold: {pz.get('threshold_pace') or '-'}  ({pz.get('source') or ''})[/dim]"
    )
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
                z.get("min_pace_fmt") or "-",
                z.get("max_pace_fmt") or "-",
            )
        console.print(table)
    console.print()


def print_weather_forecast(forecast: dict) -> None:
    """Print race-day weather forecast as rich formatted output."""
    date = forecast.get("date") or ""
    hour = forecast.get("hour_local")
    tz = forecast.get("timezone") or "UTC"
    lat = forecast.get("lat")
    lng = forecast.get("lng")

    temp_c = forecast.get("temperature_c")
    apparent_c = forecast.get("apparent_temp_c")
    humidity = forecast.get("humidity_pct")
    dew_c = forecast.get("dew_point_c")
    precip = forecast.get("precipitation_mm")
    condition = forecast.get("condition") or "-"
    wind_speed = forecast.get("wind_speed_ms")
    wind_gusts = forecast.get("wind_gusts_ms")
    wind_dir_deg = forecast.get("wind_direction_deg")
    wind_compass = forecast.get("wind_direction_compass") or "-"
    wbgt = forecast.get("wbgt_c")
    wbgt_flag_val = forecast.get("wbgt_flag") or "-"
    pace_heat = forecast.get("pace_heat_factor")
    vo2_heat = forecast.get("vo2max_heat_factor")
    headwind = forecast.get("headwind_ms")
    wap = forecast.get("wap_factor")
    bearing = forecast.get("course_bearing_deg")

    # Header
    loc_str = (
        f"[dim]{lat:.4f}, {lng:.4f}[/dim]"
        if lat is not None and lng is not None
        else ""
    )
    console.print()
    console.print(
        f"[bold]Race Day Forecast[/bold]  [dim]{date}  {hour:02d}:00 local  ({tz})[/dim]  {loc_str}"
    )
    console.print()

    # Conditions table
    cond_table = Table(
        box=box.SIMPLE_HEAD, show_header=True, header_style="bold", expand=False
    )
    cond_table.add_column("Condition", style="dim")
    cond_table.add_column("Value", justify="right")

    def _c(v, fmt=".1f", suffix=""):
        return f"{v:{fmt}}{suffix}" if v is not None else "-"

    # WBGT flag colour
    _flag_colour = {
        "green": "green",
        "yellow": "yellow",
        "red": "red",
        "black": "bold red",
    }
    flag_markup = (
        f"[{_flag_colour.get(wbgt_flag_val, 'dim')}]{wbgt_flag_val.upper()}[/]"
        if wbgt_flag_val != "-"
        else "-"
    )

    cond_table.add_row(
        "Temperature",
        f"{_c(temp_c, suffix=' °C')}  (feels {_c(apparent_c, suffix=' °C')})",
    )
    cond_table.add_row("Humidity", _c(humidity, fmt=".0f", suffix=" %"))
    cond_table.add_row("Dew Point", _c(dew_c, suffix=" °C"))
    cond_table.add_row("Precipitation", _c(precip, fmt=".1f", suffix=" mm"))
    cond_table.add_row("Condition", condition)
    cond_table.add_row(
        "Wind Speed",
        f"{_c(wind_speed, fmt='.1f', suffix=' m/s')}  (gusts {_c(wind_gusts, fmt='.1f', suffix=' m/s')})",
    )
    cond_table.add_row(
        "Wind Direction", f"{wind_compass}  ({_c(wind_dir_deg, fmt='.0f', suffix='°')})"
    )
    console.print(cond_table)

    # Race factors table
    console.print("[bold]Race Adjustment Factors[/bold]")
    console.print()
    factors_table = Table(
        box=box.SIMPLE_HEAD, show_header=True, header_style="bold", expand=False
    )
    factors_table.add_column("Factor", style="dim")
    factors_table.add_column("Value", justify="right")
    factors_table.add_column("Meaning")

    wbgt_str = f"{wbgt:.2f} °C" if wbgt is not None else "-"
    pace_heat_str = f"{pace_heat:.4f}" if pace_heat is not None else "-"
    pace_pct = (
        f"+{(pace_heat - 1) * 100:.1f}% slower"
        if pace_heat and pace_heat > 1
        else ("no penalty" if pace_heat else "-")
    )
    vo2_str = f"{vo2_heat:.4f}" if vo2_heat is not None else "-"
    vo2_pct = (
        f"{(vo2_heat - 1) * 100:.1f}% capacity"
        if vo2_heat and vo2_heat < 1
        else ("full capacity" if vo2_heat else "-")
    )

    hw_str = "-"
    hw_meaning = "provide --course-bearing for wind calc"
    if headwind is not None:
        hw_str = f"{headwind:+.2f} m/s"
        hw_meaning = (
            "tailwind"
            if headwind < 0
            else ("headwind" if headwind > 0 else "crosswind")
        )

    wap_str = "-"
    wap_meaning = "provide --course-bearing for full WAP"
    if wap is not None:
        wap_str = f"{wap:.4f}"
        wap_pct = (wap - 1) * 100
        sign = "+" if wap_pct > 0 else ""
        wap_meaning = (
            f"{sign}{wap_pct:.1f}% pace {'penalty' if wap_pct > 0 else 'benefit'}"
        )

    bearing_str = f"{bearing:.0f}°" if bearing is not None else "-"

    factors_table.add_row("WBGT", wbgt_str, flag_markup)
    factors_table.add_row("Pace heat factor", pace_heat_str, pace_pct)
    factors_table.add_row("VO2max heat factor", vo2_str, vo2_pct)
    factors_table.add_row("Headwind", hw_str, hw_meaning)
    factors_table.add_row("WAP factor", wap_str, wap_meaning)
    factors_table.add_row("Course bearing", bearing_str, "")
    console.print(factors_table)
    console.print()


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


def print_notes_list(data: dict) -> None:
    notes = data.get("notes") or []
    if not notes:
        console.print("[dim]No notes found.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("Slug", style="dim", no_wrap=True)
    table.add_column("Title")
    table.add_column("Tags", no_wrap=True)
    table.add_column("Date", no_wrap=True)
    table.add_column("Preview", style="dim")

    for n in notes:
        tags = ", ".join(n.get("tags") or []) or "-"
        date = (n.get("created") or "")[:10]
        preview = (n.get("body_preview") or "").replace("\n", " ")[:60]
        table.add_row(n.get("slug") or "", n.get("title") or "", tags, date, preview)

    console.print(table)


def print_note_detail(data: dict) -> None:
    n = data.get("note") or {}
    console.print()
    console.print(
        f"[bold]{n.get('title') or 'Note'}[/bold]  [dim]{(n.get('created') or '')[:10]}[/dim]"
    )
    tags = ", ".join(n.get("tags") or [])
    if tags:
        console.print(f"  Tags   {tags}")
    if n.get("activity_id"):
        console.print(f"  Activity  {n['activity_id']}")
    console.print()
    body = n.get("body") or ""
    if body:
        console.print(body)
    console.print()


def print_note_tags(data: dict) -> None:
    tags = data.get("tags") or []
    if not tags:
        console.print("[dim]No tags found.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("Tag")
    table.add_column("Count", justify="right")

    for t in tags:
        table.add_row(t.get("tag") or "", str(t.get("count") or 0))

    console.print(table)


# ---------------------------------------------------------------------------
# Workouts
# ---------------------------------------------------------------------------


def print_workouts_list(data: dict) -> None:
    workouts = data.get("workouts") or []
    if not workouts:
        d = data.get("workouts_dir") or "~/.fitops/workouts/"
        console.print(f"[dim]No workout files found in {d}.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("File", style="dim", no_wrap=True)
    table.add_column("Name")
    table.add_column("Sport", no_wrap=True)
    table.add_column("Duration", justify="right", no_wrap=True)
    table.add_column("Tags")

    for w in workouts:
        dur = w.get("target_duration_min")
        dur_str = f"{dur} min" if dur else "-"
        tags = ", ".join(w.get("tags") or []) or "-"
        table.add_row(
            w.get("file_name") or "",
            w.get("name") or "",
            w.get("sport") or "-",
            dur_str,
            tags,
        )

    console.print(table)


def print_workout_detail(data: dict) -> None:
    w = data.get("workout") or {}
    console.print()
    console.print(
        f"[bold]{w.get('name') or 'Workout'}[/bold]  [dim]{w.get('sport') or ''}[/dim]"
    )
    if w.get("target_duration_min"):
        console.print(f"  Duration   {w['target_duration_min']} min")
    tags = ", ".join(w.get("tags") or [])
    if tags:
        console.print(f"  Tags       {tags}")
    console.print()
    body = w.get("body") or ""
    if body:
        console.print(body)
    console.print()


def print_workout_history(data: dict) -> None:
    workouts = data.get("workouts") or []
    if not workouts:
        console.print("[dim]No linked workouts found.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("Date", no_wrap=True)
    table.add_column("Workout")
    table.add_column("Sport", no_wrap=True)
    table.add_column("Activity ID", no_wrap=True, style="dim")
    table.add_column("Compliance", justify="right", no_wrap=True)
    table.add_column("Status", no_wrap=True)

    for w in workouts:
        date = str(w.get("linked_at") or "")[:10]
        score = w.get("compliance_score")
        score_str = f"{score:.0f}%" if score is not None else "-"
        act_id = str(w.get("activity_strava_id") or w.get("activity_id") or "-")
        table.add_row(
            date,
            w.get("name") or "",
            w.get("sport_type") or "-",
            act_id,
            score_str,
            w.get("status") or "-",
        )

    console.print(table)


def print_workout_compliance(data: dict) -> None:
    workout_name = data.get("workout_name") or "Workout"
    overall = data.get("overall_compliance_score")
    segments = data.get("segments") or []

    console.print()
    score_str = f"{overall:.0f}%" if overall is not None else "N/A"
    console.print(
        f"[bold]{workout_name}[/bold]  overall compliance: [bold]{score_str}[/bold]"
    )
    console.print()

    if not segments:
        console.print("[dim]No segments.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Segment")
    table.add_column("Target")
    table.add_column("Actual HR", justify="right", no_wrap=True)
    table.add_column("Actual Pace", justify="right", no_wrap=True)
    table.add_column("Score", justify="right", no_wrap=True)
    table.add_column("In Target", justify="right", no_wrap=True)

    for seg in segments:
        idx = str(seg.get("segment_index", ""))
        name = seg.get("segment_name") or "-"
        target_z = seg.get("target_zone") or "-"
        target_hr = seg.get("target_hr_range") or {}
        if target_hr.get("min_bpm") and target_hr.get("max_bpm"):
            target = f"Z{target_z} ({target_hr['min_bpm']}–{target_hr['max_bpm']} bpm)"
        else:
            target = f"Z{target_z}" if target_z != "-" else "-"
        actuals = seg.get("actuals") or {}
        hr = actuals.get("avg_heartrate_bpm")
        hr_str = str(int(hr)) if hr else "-"
        pace = (
            actuals.get("avg_pace_formatted") or actuals.get("avg_gap_formatted") or "-"
        )
        comp = seg.get("compliance") or {}
        score = comp.get("compliance_score")
        score_str = f"{score:.0f}%" if score is not None else "-"
        in_target = comp.get("time_in_target_pct")
        in_str = f"{in_target:.0f}%" if in_target is not None else "-"
        table.add_row(idx, name, target, hr_str, pace, score_str, in_str)

    console.print(table)
    console.print()


def print_workout_simulate(data: dict) -> None:
    segments = data.get("segments") or []
    workout_name = data.get("workout_name") or "Workout"
    total_time = data.get("total_est_workout_time_fmt") or "-"
    total_km = data.get("total_est_workout_distance_km") or "-"
    weather = data.get("weather") or {}
    weather_source = data.get("weather_source") or "neutral"

    console.print()
    console.print(f"[bold]{workout_name}[/bold]  est. {total_km} km  ·  {total_time}")
    temp = weather.get("temperature_c")
    hum = weather.get("humidity_pct")
    if temp is not None:
        console.print(f"  Weather  {temp}°C  {hum}% RH  [{weather_source}]")

    mismatch = data.get("distance_mismatch_warning")
    if mismatch:
        console.print(f"  [yellow]Warning: {mismatch}[/yellow]")
    console.print()

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("Segment")
    table.add_column("Type", no_wrap=True)
    table.add_column("Target", no_wrap=True)
    table.add_column("Est. Pace", justify="right", no_wrap=True)
    table.add_column("Est. Time", justify="right", no_wrap=True)
    table.add_column("Est. Dist", justify="right", no_wrap=True)

    for seg in segments:
        name = seg.get("segment_name") or seg.get("name") or "-"
        step_type = seg.get("step_type") or "-"
        target = seg.get("target_label") or seg.get("target_zone") or "-"
        pace = seg.get("est_pace_fmt") or seg.get("est_adjusted_pace_fmt") or "-"
        time_fmt = seg.get("est_time_fmt") or seg.get("est_segment_time_fmt") or "-"
        dist = seg.get("est_distance_km")
        dist_str = f"{dist:.2f} km" if dist is not None else "-"
        table.add_row(name, step_type, str(target), pace, time_fmt, dist_str)

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Race
# ---------------------------------------------------------------------------


def print_courses_list(data: dict) -> None:
    courses = data.get("courses") or []
    if not courses:
        console.print("[dim]No courses imported yet.[/dim]")
        console.print("  Import one with: fitops race import <file.gpx> --name <name>")
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("ID", justify="right", style="dim", no_wrap=True)
    table.add_column("Name")
    table.add_column("Source", no_wrap=True)
    table.add_column("Distance", justify="right", no_wrap=True)
    table.add_column("Elevation", justify="right", no_wrap=True)
    table.add_column("Imported", no_wrap=True)

    for c in courses:
        dist_m = c.get("total_distance_m") or 0
        dist_str = f"{dist_m / 1000:.2f} km" if dist_m else "-"
        elev = c.get("total_elevation_gain_m")
        elev_str = f"+{elev:.0f} m" if elev else "-"
        date = str(c.get("created_at") or "")[:10]
        table.add_row(
            str(c.get("id") or ""),
            c.get("name") or "",
            c.get("source") or "-",
            dist_str,
            elev_str,
            date,
        )

    console.print(table)


def print_course_detail(data: dict) -> None:
    c = data.get("course") or {}
    segs = data.get("km_segments") or []

    console.print()
    dist_m = c.get("total_distance_m") or 0
    elev = c.get("total_elevation_gain_m") or 0
    console.print(
        f"[bold]{c.get('name') or 'Course'}[/bold]  [dim]ID {c.get('id')}[/dim]"
    )
    console.print(f"  Distance   {dist_m / 1000:.2f} km")
    console.print(f"  Elevation  +{elev:.0f} m")
    console.print(f"  Source     {c.get('source') or '-'}")
    console.print()

    if segs:
        table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
        table.add_column("km", justify="right")
        table.add_column("Dist", justify="right", no_wrap=True)
        table.add_column("Elev Δ", justify="right", no_wrap=True)
        table.add_column("Avg Grade", justify="right", no_wrap=True)
        table.add_column("GAF", justify="right", no_wrap=True)

        for s in segs:
            km = s.get("km_marker") or s.get("km") or ""
            dist = s.get("distance_m") or 0
            dist_str = f"{dist:.0f} m"
            elev_delta = s.get("elevation_delta_m") or s.get("elev_delta_m")
            elev_str = f"{elev_delta:+.1f} m" if elev_delta is not None else "-"
            grade = s.get("avg_grade_pct") or s.get("grade_pct")
            grade_str = f"{grade:+.1f}%" if grade is not None else "-"
            gaf = s.get("grade_adjusted_factor") or s.get("gaf")
            gaf_str = f"{gaf:.3f}" if gaf is not None else "-"
            table.add_row(str(km), dist_str, elev_str, grade_str, gaf_str)

        console.print(table)
    console.print()


def print_race_simulate(data: dict) -> None:
    sim = data.get("simulation") or {}
    course = data.get("course") or {}
    splits = sim.get("splits") or []

    console.print()
    console.print(
        f"[bold]{course.get('name') or 'Course'}[/bold]  target: [bold]{sim.get('target_time') or '-'}[/bold]  strategy: {sim.get('strategy') or sim.get('mode') or '-'}"
    )
    weather = sim.get("weather") or {}
    wsrc = sim.get("weather_source") or "neutral"
    temp = weather.get("temperature_c")
    if temp is not None:
        console.print(
            f"  Weather  {temp}°C  {weather.get('humidity_pct', '-')}% RH  [{wsrc}]"
        )
    console.print()

    if not splits:
        console.print("[dim]No splits generated.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("km", justify="right")
    table.add_column("Pace", justify="right", no_wrap=True)
    table.add_column("Elapsed", justify="right", no_wrap=True)
    table.add_column("Elev Δ", justify="right", no_wrap=True)
    table.add_column("Adj Factor", justify="right", no_wrap=True)

    for s in splits:
        km = s.get("km_marker") or s.get("km") or ""
        pace = s.get("adjusted_pace_fmt") or s.get("pace_fmt") or s.get("pace") or "-"
        elapsed = s.get("elapsed_fmt") or s.get("elapsed") or "-"
        elev = s.get("elevation_delta_m") or s.get("elev_delta_m")
        elev_str = f"{elev:+.1f} m" if elev is not None else "-"
        factor = s.get("total_adjustment_factor") or s.get("adj_factor")
        factor_str = f"{factor:.3f}" if factor is not None else "-"
        table.add_row(str(km), pace, elapsed, elev_str, factor_str)

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Weather (activity)
# ---------------------------------------------------------------------------


def print_weather_activity(data: dict) -> None:
    """Print stored weather data for a single activity (fetch/show result)."""
    w = data.get("weather") or data
    console.print()
    temp = w.get("temperature_c")
    hum = w.get("humidity_pct")
    cond = w.get("condition") or "-"
    wbgt = w.get("wbgt_c")
    flag = w.get("wbgt_flag") or "-"
    source = w.get("source") or "-"
    act_id = w.get("activity_id")

    if act_id:
        console.print(f"[bold]Weather[/bold]  activity {act_id}  [dim]{source}[/dim]")
    else:
        console.print(f"[bold]Weather[/bold]  [dim]{source}[/dim]")
    console.print()

    table = Table(box=box.SIMPLE_HEAD, show_header=False, header_style="bold")
    table.add_column("Field", style="dim")
    table.add_column("Value", justify="right")

    def _v(val, fmt=".1f", suffix=""):
        return f"{val:{fmt}}{suffix}" if val is not None else "-"

    table.add_row(
        "Temperature",
        f"{_v(temp, suffix=' °C')}  ({_v(hum, fmt='.0f', suffix='% RH')})",
    )
    table.add_row("Condition", cond)
    wind = w.get("wind_speed_ms")
    wind_dir = w.get("wind_direction_deg")
    wind_str = _v(wind, fmt=".1f", suffix=" m/s")
    if wind_dir is not None:
        wind_str += f"  {_v(wind_dir, fmt='.0f', suffix='°')}"
    table.add_row("Wind", wind_str)
    table.add_row("WBGT", f"{_v(wbgt, fmt='.2f', suffix=' °C')}  [{flag.upper()}]")
    table.add_row("Pace heat factor", _v(w.get("pace_heat_factor"), fmt=".4f"))
    table.add_row("VO2max heat factor", _v(w.get("vo2max_heat_factor"), fmt=".4f"))
    table.add_row("WAP factor", _v(w.get("wap_factor"), fmt=".4f"))
    if w.get("actual_pace"):
        table.add_row("Actual pace", w["actual_pace"])
    if w.get("wap"):
        table.add_row("WAP (adj. pace)", w["wap"])

    console.print(table)
    console.print()


def print_weather_fetch_all(data: dict) -> None:
    """Print summary of bulk weather fetch."""
    fetched = data.get("fetched", 0)
    activities = data.get("activities") or []
    console.print(f"[green]OK[/green] Weather fetched for {fetched} activities")
    errors = [a for a in activities if "error" in (a.get("result") or {})]
    if errors:
        console.print(f"  [yellow]{len(errors)} errors[/yellow]")
        for e in errors:
            console.print(f"    {e.get('activity_id')}  {e['result'].get('error')}")


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
