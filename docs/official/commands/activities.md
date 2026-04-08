# fitops activities

Browse and query synced activities.

Output is a formatted table by default. Add `--json` to any command for raw JSON output (useful for scripting or AI agents).

## Commands

### `fitops activities list`

List recent activities with full metrics.

```bash
fitops activities list [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--sport TYPE` | all | Filter by sport type (e.g. `Run`, `Ride`, `Swim`) |
| `--limit N` | 20 | Max number of activities to return |
| `--after DATE` | — | Filter activities after this date (YYYY-MM-DD) |
| `--json` | false | Output raw JSON instead of the formatted table |

**Examples:**

```bash
fitops activities list
fitops activities list --sport Run --limit 10
fitops activities list --after 2026-01-01
fitops activities list --sport Ride --limit 5 --after 2025-12-01
fitops activities list --sport Run --json          # JSON for scripting or agents
```

See [Output Examples → Activities](../output-examples/activities.md) for sample output.

---

### `fitops activities get <ID>`

Get detailed info for a single activity.

```bash
fitops activities get 12345678901 [--fresh]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `ID` | Strava activity ID (required) |

**Options:**

| Flag | Description |
|------|-------------|
| `--fresh` | Re-fetch detail from Strava API (bypasses local cache) |
| `--json` | Output raw JSON instead of the formatted summary |

---

### `fitops activities streams <ID>`

Get time-series stream data for an activity (heart rate, pace, altitude, power, cadence, etc.).

```bash
fitops activities streams 12345678901 [--fresh]
```

Streams are fetched from Strava on first request and cached locally. Use `--fresh` to force a re-fetch.

**Output:**

```
Streams for activity 17972016511

  altitude              3492 data points
  heartrate             3492 data points
  cadence               3492 data points
  velocity_smooth       3492 data points
  distance              3492 data points
```

Use `--json` to get the raw data arrays for scripting or analysis.

---

### `fitops activities chart <ID>`

Render a time-series stream as an ASCII chart directly in the terminal — useful for quick visual inspection and for AI agents that consume plain text.

```bash
fitops activities chart 12345678901 [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `ID` | Strava activity ID (required) |

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--stream STREAM` | `heartrate` | Stream to plot (see table below) |
| `--x-axis VALUE` | `time` | X-axis type: `time` or `distance` |
| `--from N` | — | Start of zoom window (seconds or metres) |
| `--to N` | — | End of zoom window (seconds or metres) |
| `--width N` | auto | Chart width in characters (default: terminal width) |
| `--height N` | `20` | Chart height in rows |
| `--resolution N` | auto | Number of data buckets (lower = smoother curve) |

**Supported streams:**

| Stream | Display | Notes |
|--------|---------|-------|
| `heartrate` | Heart Rate (bpm) | |
| `pace` / `velocity_smooth` | Pace (min/km) | Y-axis inverted: faster = higher |
| `speed` | Speed (km/h) | Auto-selected for cycling when `velocity_smooth` is requested |
| `gap` | Grade Adj. Pace (min/km) | Derived — requires `velocity_smooth` + `grade_smooth` streams |
| `wap` | Weighted Avg Pace (min/km) | Derived — 30-sample rolling mean of pace |
| `altitude` | Altitude (m) | |
| `cadence` | Cadence (spm) | |
| `watts` | Power (W) | |
| `distance` | Distance (m) | |

> **Sport-aware display:** requesting `pace` or `velocity_smooth` on a cycling activity automatically switches to `speed` (km/h).

**Examples:**

```bash
# Heart rate over the full run
fitops activities chart 17985851162

# Pace chart
fitops activities chart 17985851162 --stream pace

# Grade-adjusted pace (GAP) over distance
fitops activities chart 17985851162 --stream gap --x-axis distance

# Zoom into km 5–10
fitops activities chart 17985851162 --stream heartrate --x-axis distance --from 5000 --to 10000

# Smooth curve with low resolution
fitops activities chart 17985851162 --stream heartrate --resolution 30

# Tall, wide chart
fitops activities chart 17985851162 --stream altitude --width 120 --height 30
```

**Chart anatomy:**

```
Activity chart  |  Heart Rate (bpm)  over time (s)  [res: 71]
min: 142 bpm  avg: 163 bpm  max: 190 bpm  samples: 3492

    190|    ▪▪▪▪  ▪ ▪▪▪▪▪▪▪  ▪ ▪ ▪▪▪▪▪▪▪▪▪▪▪▪▪ ▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪
        |  ▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪
    166|▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪
        | ...
    142|▪
-------+-----------------------------------------------------------------------
        0:00                             66:39                           133:17
```

- `▪` — midpoint of each data bucket (primary trace)
- `·` — min–max range indicator (shown only when zoomed in tightly)
- Y-axis labels: top, mid, and bottom values
- X-axis labels: start, midpoint, and end of the window
- `[res: N]` in the title shows the active bucket count

See [Output Examples → Activities](../output-examples/activities.md#fitops-activities-chart) for a full rendered example.

---

## Sport Type Values

Common Strava sport types: `Run`, `TrailRun`, `Ride`, `VirtualRide`, `Swim`, `Walk`, `Hike`, `WeightTraining`, `Yoga`, `Workout`

## See Also

- [Output Examples → Activities](../output-examples/activities.md) — sample output
- [`fitops sync run`](./sync.md) — fetch activities from Strava

← [Commands Reference](./index.md)
