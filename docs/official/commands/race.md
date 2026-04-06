# fitops race

Import race courses and simulate per-kilometre pacing plans adjusted for elevation and weather. Supports target-time, target-pace, and pacer-following strategies.

Output is human-readable by default. Add `--json` for raw JSON output.

## Commands

### `fitops race import <source>`

Import a race course from a GPX or TCX file, a Strava activity ID, or a MapMyRun URL.

```bash
fitops race import <source> --name "Course Name"
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `SOURCE` | GPX/TCX file path, Strava activity ID, or MapMyRun URL |

**Options:**

| Flag | Required | Description |
|------|----------|-------------|
| `--name TEXT` | Yes | Display name for the course |

**Examples:**

```bash
# Import from a GPX file
fitops race import berlin-marathon.gpx --name "Berlin Marathon 2026"

# Import from a TCX file
fitops race import course.tcx --name "Local 10K"

# Build course from a Strava activity you've already done
fitops race import --activity 12345678901 --name "My Race Course"
```

**Output:**

```
Imported: Berlin Marathon 2026  (42.19 km  +218 m)  ID 1
```

Courses are stored in the local database. Use the returned ID with `fitops race simulate`.

---

### `fitops race courses`

List all imported race courses.

```bash
fitops race courses
```

**Output:**

```
  ID   Name                  Source  Distance   Elevation  Imported
 ────────────────────────────────────────────────────────────────────
   1   Berlin Marathon 2026  gpx     42.20 km   +218 m     2026-03-01
   2   Local 10K             gpx     10.02 km   +48 m      2026-03-10
```

---

### `fitops race course <id>`

Show course details and the per-km segment profile.

```bash
fitops race course 1
```

**Output includes:**
- Course summary (name, distance, total elevation gain)
- Per-km segments: distance, elevation delta, grade%, cumulative distance

---

### `fitops race splits <id>`

Quick even-split plan with no weather or strategy options.

```bash
fitops race splits <id> --target-time 3:15:00
fitops race splits <id> --target-pace 4:37
```

**Options:**

| Flag | Description |
|------|-------------|
| `--target-time HH:MM:SS` | Target finish time |
| `--target-pace MM:SS` | Target average pace per km |

One of `--target-time` or `--target-pace` is required.

---

### `fitops race simulate <id>`

Full simulation: per-km splits adjusted for elevation, weather, and pacing strategy.

```bash
fitops race simulate <id> [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--target-time HH:MM:SS` | — | Target finish time |
| `--target-pace MM:SS` | — | Target average pace per km |
| `--strategy STRATEGY` | `even` | Pacing strategy: `even`, `negative`, or `positive` |
| `--pacer-pace MM:SS` | — | Pacer pace per km (enables pacer mode) |
| `--drop-at-km N` | — | Km marker to break from the pacer (required with `--pacer-pace`) |
| `--temp C` | — | Temperature °C (manual override) |
| `--humidity PCT` | — | Relative humidity % (manual override) |
| `--wind MS` | — | Wind speed m/s |
| `--wind-dir DEG` | — | Wind direction degrees (0=N) |
| `--date YYYY-MM-DD` | — | Fetch weather for race day (future = forecast, past = archive) |
| `--hour N` | 9 | Race start hour local time (0–23) for weather fetch |

One of `--target-time` or `--target-pace` is required.

**Examples:**

```bash
# Even-split plan for 3:15 marathon
fitops race simulate 1 --target-time 3:15:00

# Negative split strategy
fitops race simulate 1 --target-time 3:15:00 --strategy negative

# With manual weather override
fitops race simulate 1 --target-time 3:15:00 --temp 22 --humidity 65 --wind 3.5

# With race-day weather forecast (auto-fetched from Open-Meteo)
fitops race simulate 1 --target-time 3:15:00 --date 2026-10-25 --hour 9

# Pacer strategy: sit with 4:40/km pacer, push after km 35
fitops race simulate 1 --target-time 3:05:00 --pacer-pace 4:40 --drop-at-km 35
```

#### Pacing Strategies

**`even`** (default): Constant effort output — faster on downhills, slower on uphills, but equal power/effort throughout.

**`negative`**: Start slightly conservative, finish strong. Energy is distributed to reserve ~2% for the second half.

**`positive`**: Start slightly faster and manage a slowdown. Useful when the course front-loads climbs.

**Pacer mode** (`--pacer-pace` + `--drop-at-km`): Match the pacer's exact pace until the drop point, then calculate the required pace to hit the target finish given remaining distance and course profile.

#### Per-Split Output

Each row in the output shows:

| Column | Description |
|--------|-------------|
| `km` | Kilometre marker |
| `elevation_delta_m` | Elevation change for this segment |
| `grade_pct` | Average gradient (%) |
| `gap_factor` | Grade-adjusted pace multiplier |
| `wap_factor` | Weather-adjusted pace multiplier |
| `target_pace` | Target pace for this km (MM:SS/km) |
| `split_time` | Time to complete this km |
| `elapsed_time` | Cumulative time at end of km |

---

### `fitops race delete <id>`

Remove a course from the database.

```bash
fitops race delete 1
```

---

## Weather Auto-Fetch

When `--date` is provided and the course has GPS coordinates (start lat/lng), FitOps automatically fetches weather from Open-Meteo:

- **Future date** (within 16 days): uses the Open-Meteo forecast API
- **Past date**: uses the Open-Meteo historical archive

Manual `--temp` + `--humidity` always override auto-fetched weather. If weather fetch fails (network error, date beyond forecast window), neutral conditions (15°C, 40% RH, no wind) are used and a warning is printed.

## See Also

- [Concepts → Weather & Pace](../concepts/weather-pace.md) — WAP and GAP adjustment models
- [`fitops workouts simulate`](./workouts.md) — simulate a structured workout on a course
- [`fitops weather forecast`](./weather.md) — standalone race-day forecast

← [Commands Reference](./index.md)
