from __future__ import annotations

import math

Y_MARGIN = 8  # characters wide for y-axis labels + border

# Stream display metadata
_STREAM_META: dict[str, dict] = {
    "heartrate":       {"label": "Heart Rate (bpm)",           "unit": "bpm",    "fmt": "int"},
    "velocity_smooth": {"label": "Pace (min/km)",              "unit": "min/km", "fmt": "pace",    "invert_y": True},
    "speed":           {"label": "Speed (km/h)",               "unit": "km/h",   "fmt": "one_dec"},
    "gap":             {"label": "Grade Adj. Pace (min/km)",   "unit": "min/km", "fmt": "pace",    "invert_y": True},
    "wap":             {"label": "Weighted Avg Pace (min/km)", "unit": "min/km", "fmt": "pace",    "invert_y": True},
    "altitude":        {"label": "Altitude (m)",               "unit": "m",      "fmt": "one_dec"},
    "cadence":         {"label": "Cadence (spm)",              "unit": "spm",    "fmt": "int"},
    "watts":           {"label": "Power (W)",                  "unit": "W",      "fmt": "int"},
    "distance":        {"label": "Distance (m)",               "unit": "m",      "fmt": "one_dec"},
    "temp":            {"label": "Temperature (\u00b0C)",      "unit": "\u00b0C","fmt": "one_dec"},
}

_CHAR_MID = "\u25aa"   # ▪  midpoint of bucket — primary trace
_CHAR_RANGE = "\u00b7" # ·  range fill — shows variance without dominating


def _pace_str(min_per_km: float) -> str:
    minutes = int(min_per_km)
    seconds = int(round((min_per_km - minutes) * 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}"


def _fmt_value(v: float, fmt: str) -> str:
    if fmt == "int":
        return str(int(round(v)))
    if fmt == "pace":
        return _pace_str(v)
    if fmt == "one_dec":
        return f"{v:.1f}"
    return f"{v:.1f}"


def _fmt_x(v: float, x_label: str) -> str:
    if "time" in x_label:
        total_s = int(round(v))
        m, s = divmod(total_s, 60)
        return f"{m}:{s:02d}"
    if "distance" in x_label:
        return f"{v / 1000:.1f}km"
    return str(int(round(v)))


def _convert_data(data: list[float], stream_type: str) -> list[float | None]:
    """Convert raw stream values to display values. Returns None for gaps."""
    if stream_type in ("velocity_smooth", "gap", "wap"):
        # m/s → min/km
        result: list[float | None] = []
        for v in data:
            if v is None or v <= 0:
                result.append(None)
            else:
                result.append((1000.0 / v) / 60.0)
        return result
    if stream_type == "speed":
        # m/s → km/h
        return [None if (v is None or v <= 0) else float(v) * 3.6 for v in data]
    return [None if v is None else float(v) for v in data]


def _bucket(display_data: list[float | None], n_buckets: int) -> tuple[
    list[float | None], list[float | None], list[float | None]
]:
    """
    Reduce data into n_buckets using min/max/mean per bucket.
    Returns (col_min, col_max, col_mid) each of length n_buckets.
    """
    n = len(display_data)
    col_min: list[float | None] = []
    col_max: list[float | None] = []
    col_mid: list[float | None] = []

    if n == 0:
        return [None] * n_buckets, [None] * n_buckets, [None] * n_buckets

    bucket_size = n / n_buckets
    for i in range(n_buckets):
        lo = math.floor(i * bucket_size)
        hi = math.floor((i + 1) * bucket_size)
        if hi == lo:
            hi = lo + 1
        bucket = [v for v in display_data[lo:hi] if v is not None]
        if bucket:
            col_min.append(min(bucket))
            col_max.append(max(bucket))
            col_mid.append(sum(bucket) / len(bucket))
        else:
            col_min.append(None)
            col_max.append(None)
            col_mid.append(None)

    return col_min, col_max, col_mid


def _interp_midpoints(
    col_mid: list[float | None], n_buckets: int, width: int
) -> list[float | None]:
    """
    Linearly interpolate n_buckets midpoint values to exactly width columns.
    This ensures the chart is always dense (no empty-column gaps) even at low resolution.
    """
    result: list[float | None] = []
    for col_i in range(width):
        if n_buckets == 1:
            result.append(col_mid[0])
            continue
        t = col_i / (width - 1) * (n_buckets - 1)
        bi_lo = int(t)
        bi_hi = min(bi_lo + 1, n_buckets - 1)
        frac = t - bi_lo
        v_lo = col_mid[bi_lo]
        v_hi = col_mid[bi_hi]
        if v_lo is None and v_hi is None:
            result.append(None)
        elif v_lo is None:
            result.append(v_hi)
        elif v_hi is None:
            result.append(v_lo)
        else:
            result.append(v_lo * (1 - frac) + v_hi * frac)
    return result


def render_ascii_chart(
    data: list[float],
    x_values: list[float],
    stream_type: str,
    width: int = 80,
    height: int = 20,
    *,
    x_label: str = "time (s)",
    resolution: int | None = None,
) -> str:
    """
    Render a stream as an ASCII chart.

    resolution = number of source data buckets (default: width — one per column).
    Lower resolution → fewer buckets → midpoints linearly interpolated across the
    full chart width, giving a smooth curve. Higher = more detail / noisier.
    Both modes always fill every column densely; no isolated dots.
    """
    if width < 3:
        return f"[chart] width must be >= 3 (got {width})"
    if height < 3:
        return f"[chart] height must be >= 3 (got {height})"

    meta = _STREAM_META.get(stream_type, {"label": stream_type, "unit": "", "fmt": "one_dec"})
    fmt = meta["fmt"]
    invert_y: bool = meta.get("invert_y", False)
    stream_label: str = meta["label"]

    display_data = _convert_data(data, stream_type)
    non_null = [v for v in display_data if v is not None]

    if not non_null:
        return f"[chart] No valid data points for stream '{stream_type}'."

    # Stats (always over full data)
    stat_min = min(non_null)
    stat_max = max(non_null)
    stat_avg = sum(non_null) / len(non_null)
    n_samples = len(non_null)

    if stream_type in ("velocity_smooth", "gap", "wap"):
        stats_line = (
            f"fastest: {_fmt_value(stat_min, fmt)}/km  "
            f"avg: {_fmt_value(stat_avg, fmt)}/km  "
            f"slowest: {_fmt_value(stat_max, fmt)}/km  "
            f"samples: {n_samples}"
        )
    else:
        unit = meta.get("unit", "")
        unit_str = f" {unit}" if unit else ""
        stats_line = (
            f"min: {_fmt_value(stat_min, fmt)}{unit_str}  "
            f"avg: {_fmt_value(stat_avg, fmt)}{unit_str}  "
            f"max: {_fmt_value(stat_max, fmt)}{unit_str}  "
            f"samples: {n_samples}"
        )

    # n_buckets: how many data segments we compute stats for.
    # Default = width (1 bucket per column, no interpolation needed).
    n_buckets = max(1, min(resolution if resolution is not None else width, width, len(display_data)))

    col_min, col_max, col_mid = _bucket(display_data, n_buckets)

    # Y range
    global_min = stat_min
    global_max = stat_max
    if global_min == global_max:
        global_min -= 1.0
        global_max += 1.0
    value_range = global_max - global_min

    def _val_to_row(v: float) -> int:
        row = int(round((v - global_min) / value_range * (height - 1)))
        row = max(0, min(height - 1, row))
        if invert_y:
            row = (height - 1) - row
        return row

    # Build grid (row 0 = top)
    grid = [[" "] * width for _ in range(height)]

    if n_buckets < width:
        # Low resolution: interpolate midpoints to fill every column.
        # No range dots — the smooth line speaks for itself.
        plot_mid = _interp_midpoints(col_mid, n_buckets, width)
        for col_i, mid in enumerate(plot_mid):
            if mid is not None:
                grid[_val_to_row(mid)][col_i] = _CHAR_MID
    else:
        # Full resolution (n_buckets == width): one bucket per column.
        # Show range dots only when each bucket is small (zoomed in / fine detail).
        samples_per_bucket = len(display_data) / n_buckets
        show_range = samples_per_bucket <= 10

        for bi in range(n_buckets):
            mn = col_min[bi]
            mx = col_max[bi]
            mid = col_mid[bi]
            if mid is None:
                continue
            row_mid = _val_to_row(mid)
            if show_range and mn is not None and mx is not None:
                row_lo = _val_to_row(mn)
                row_hi = _val_to_row(mx)
                for r in range(min(row_lo, row_hi), max(row_lo, row_hi) + 1):
                    grid[r][bi] = _CHAR_RANGE
            grid[row_mid][bi] = _CHAR_MID

    # Y-axis labels
    if invert_y:
        label_top = global_min
        label_mid = (global_min + global_max) / 2
        label_bot = global_max
    else:
        label_top = global_max
        label_mid = (global_min + global_max) / 2
        label_bot = global_min

    def _y_margin(row: int) -> str:
        if row == 0:
            lbl = _fmt_value(label_top, fmt)
        elif row == height // 2:
            lbl = _fmt_value(label_mid, fmt)
        elif row == height - 1:
            lbl = _fmt_value(label_bot, fmt)
        else:
            lbl = ""
        return f"{lbl:>7s}|"

    chart_rows = [_y_margin(r) + "".join(grid[r]) for r in range(height)]

    # X-axis
    x_axis_row = "-------+" + "-" * width

    if x_values:
        x_left = _fmt_x(x_values[0], x_label)
        x_mid = _fmt_x(x_values[len(x_values) // 2], x_label)
        x_right = _fmt_x(x_values[-1], x_label)
    else:
        x_left = x_mid = x_right = ""

    total_width = Y_MARGIN + width
    tick_line = [" "] * total_width

    for i, ch in enumerate(x_left):
        pos = Y_MARGIN + i
        if pos < total_width:
            tick_line[pos] = ch

    mid_start = Y_MARGIN + width // 2 - len(x_mid) // 2
    for i, ch in enumerate(x_mid):
        pos = mid_start + i
        if 0 <= pos < total_width:
            tick_line[pos] = ch

    right_start = total_width - len(x_right)
    for i, ch in enumerate(x_right):
        pos = right_start + i
        if 0 <= pos < total_width:
            tick_line[pos] = ch

    tick_str = "".join(tick_line)

    title_line = f"Activity chart  |  {stream_label}  over {x_label}  [res: {n_buckets}]"

    return "\n".join([title_line, stats_line, "", *chart_rows, x_axis_row, tick_str])
