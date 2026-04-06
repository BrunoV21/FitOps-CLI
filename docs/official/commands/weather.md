# fitops weather

Fetch, store, and inspect weather conditions for your activities. Compute pace and VO2max adjustment factors for heat, humidity, and wind.

Output is human-readable by default. Add `--json` for raw JSON output.

## Commands

### `fitops weather fetch`

Fetch weather from the Open-Meteo historical archive and store it for one or more activities.

```bash
fitops weather fetch [ACTIVITY_ID] [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `ACTIVITY_ID` | Strava activity ID (optional if using `--all`) |

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--all` | false | Backfill all GPS activities that are missing weather |
| `--limit N` | 50 | Max number of activities to process when using `--all` |

**Examples:**

```bash
# Fetch weather for a specific activity
fitops weather fetch 12345678901

# Backfill weather for the 50 most recent activities missing it
fitops weather fetch --all

# Backfill up to 200 activities
fitops weather fetch --all --limit 200
```

Weather is fetched automatically for newly synced activities. Use `--all` only to backfill older activities synced before weather support was added.

**Output (single activity):**

```json
{
  "_meta": { "generated_at": "2026-03-19T09:00:00+00:00" },
  "weather": {
    "activity_id": 12345678901,
    "temperature_c": 22.1,
    "humidity_pct": 68.0,
    "wind_speed_ms": 3.2,
    "wind_direction_deg": 270.0,
    "weather_code": 1,
    "source": "open-meteo",
    "wbgt_c": 19.84,
    "pace_heat_factor": 1.0348,
    "condition": "Mainly clear",
    "wbgt_flag": "yellow"
  }
}
```

**Output (--all mode):**

```json
{
  "_meta": { "generated_at": "2026-03-19T09:00:00+00:00", "total_count": 3 },
  "fetched": 3,
  "activities": [
    { "activity_id": 12345678901, "name": "Morning Run", "result": { ... } },
    { "activity_id": 12345678902, "name": "Evening Run", "result": { ... } }
  ]
}
```

---

### `fitops weather show`

Display stored weather data and computed WAP (Weather-Adjusted Pace) factors for an activity.

```bash
fitops weather show <ACTIVITY_ID>
```

**Example:**

```bash
fitops weather show 12345678901
```

**Output:**

```json
{
  "_meta": { "generated_at": "2026-03-19T09:00:00+00:00" },
  "weather": {
    "activity_id": 12345678901,
    "temperature_c": 22.1,
    "humidity_pct": 68.0,
    "wind_speed_ms": 3.2,
    "wind_direction_deg": 270.0,
    "weather_code": 1,
    "wbgt_c": 19.84,
    "pace_heat_factor": 1.0348,
    "condition": "Mainly clear",
    "wbgt_flag": "yellow",
    "source": "open-meteo",
    "wap_factor": 1.0412,
    "course_bearing_deg": 92.3,
    "vo2max_heat_factor": 0.9984,
    "actual_pace": "5:12/km",
    "wap": "4:59/km"
  }
}
```

**Additional fields vs `fetch`:**

| Field | Description |
|-------|-------------|
| `wap_factor` | Combined heat + wind adjustment factor (>1 means conditions made it harder) |
| `course_bearing_deg` | Bearing from activity start to end (degrees, 0=N) — used for headwind/tailwind calc |
| `vo2max_heat_factor` | Aerobic capacity multiplier (1.0 = full capacity, 0.90 = 10% reduced) |
| `actual_pace` | Activity average pace (mm:ss/km) from Strava |
| `wap` | Weather-Adjusted Pace — actual pace normalised for conditions |

If no weather data exists for the activity, an error with a hint to run `fitops weather fetch <id>` is returned.

---

### `fitops weather forecast`

Fetch an Open-Meteo forecast for a future race location and compute pace adjustment factors. Available up to 16 days ahead.

```bash
fitops weather forecast --lat LAT --lng LNG --date DATE [OPTIONS]
```

**Required options:**

| Flag | Description |
|------|-------------|
| `--lat` | Latitude of the race location |
| `--lng` | Longitude of the race location |
| `--date` | Race date (YYYY-MM-DD) |

**Optional options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--hour N` | 9 | Race start hour in local time (0–23) |
| `--course-bearing DEG` | — | Course bearing in degrees (0=N, 90=E) — enables headwind/tailwind calc |
| `--json` | false | Output raw JSON instead of the formatted rich table |

**Examples:**

```bash
# Basic forecast for a morning race
fitops weather forecast --lat 51.5074 --lng -0.1278 --date 2026-04-19

# With course bearing for wind calculations
fitops weather forecast --lat 51.5074 --lng -0.1278 --date 2026-04-19 --hour 10 --course-bearing 90

# JSON output for scripting
fitops weather forecast --lat 51.5074 --lng -0.1278 --date 2026-04-19 --json
```

**Default output:** A formatted rich table showing temperature, humidity, wind, WBGT, heat stress flag, and pace factors.

**JSON output (--json flag):**

```json
{
  "_meta": { "generated_at": "2026-03-19T09:00:00+00:00" },
  "forecast": {
    "date": "2026-04-19",
    "hour_local": 9,
    "timezone": "Europe/London",
    "lat": 51.5074,
    "lng": -0.1278,
    "temperature_c": 14.2,
    "humidity_pct": 72.0,
    "wind_speed_ms": 4.1,
    "wind_direction_deg": 225.0,
    "weather_code": 2,
    "condition": "Partly cloudy",
    "wbgt_c": 13.18,
    "wbgt_flag": "yellow",
    "pace_heat_factor": 1.0064,
    "vo2max_heat_factor": 0.9968,
    "headwind_ms": 2.9,
    "wind_direction_compass": "SW",
    "wap_factor": 1.0568,
    "course_bearing_deg": 90.0
  }
}
```

**Output fields:**

| Field | Description |
|-------|-------------|
| `temperature_c` | Dry-bulb temperature (°C) |
| `humidity_pct` | Relative humidity (%) |
| `wind_speed_ms` | Wind speed (m/s) |
| `wind_direction_deg` | Wind direction — meteorological FROM direction (degrees, 0=N) |
| `wind_direction_compass` | 16-point compass label (e.g. `SW`) |
| `weather_code` | WMO weather interpretation code |
| `condition` | Human-readable condition (e.g. `"Partly cloudy"`) |
| `wbgt_c` | Wet Bulb Globe Temperature (°C) |
| `wbgt_flag` | Heat stress category: `green` / `yellow` / `red` / `black` |
| `pace_heat_factor` | Pace multiplier from heat/humidity (1.0 = no effect) |
| `vo2max_heat_factor` | VO2max capacity multiplier (1.0 = full capacity) |
| `headwind_ms` | Headwind component (m/s, positive = into runner's face). Only if `--course-bearing` provided |
| `wap_factor` | Combined heat + wind factor. Only if temp and humidity available |

---

### `fitops weather set`

Manually set weather conditions for an activity. Useful when automatic fetch fails or you have more accurate on-course data.

```bash
fitops weather set <ACTIVITY_ID> [OPTIONS]
```

**Options:**

| Flag | Description |
|------|-------------|
| `--temp C` | Temperature (°C) |
| `--humidity PCT` | Relative humidity (%) |
| `--wind MS` | Wind speed (m/s) |
| `--wind-dir DEG` | Wind direction (degrees from north, 0=N) |

At least one field is required. If both `--temp` and `--humidity` are provided, `wbgt_c` and `pace_heat_factor` are computed automatically.

**Examples:**

```bash
# Set temperature and humidity (WBGT and heat factor computed automatically)
fitops weather set 12345678901 --temp 24.5 --humidity 75

# Full manual override
fitops weather set 12345678901 --temp 24.5 --humidity 75 --wind 3.0 --wind-dir 270
```

**Output:**

```json
{
  "_meta": { "generated_at": "2026-03-19T09:00:00+00:00" },
  "weather": {
    "activity_id": 12345678901,
    "temperature_c": 24.5,
    "humidity_pct": 75.0,
    "wind_speed_ms": 3.0,
    "wind_direction_deg": 270.0,
    "wbgt_c": 22.31,
    "pace_heat_factor": 1.0679,
    "source": "manual"
  }
}
```

Data set via `fitops weather set` has `source: "manual"` and will not be overwritten by a subsequent `fitops weather fetch` for the same activity.

---

## Weather Data Source

FitOps fetches historical and forecast data from [Open-Meteo](https://open-meteo.com/), a free, open-source weather API. No API key is required. Data is stored in the local database at `~/.fitops/fitops.db`.

## See Also

- [Concepts → Weather & Pace](../concepts/weather-pace.md) — how WBGT, WAP, True Pace, and wind physics work
- [Output Examples → Weather](../output-examples/weather.md) — full response examples
- [`fitops sync run`](./sync.md) — weather is fetched automatically during sync

← [Commands Reference](./index.md)
