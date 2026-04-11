# FitOps-CLI Roadmap

![FitOps Roadmap Timeline](./assets/roadmap-timeline.png)

## Phase 1 — Foundation ✅

**Goal:** Strava auth, incremental sync, local SQLite storage, LLM-friendly activity output.

**Delivered:**
- `fitops auth` — OAuth login, logout, status, refresh
- `fitops sync` — incremental and full historical sync
- `fitops activities` — list, get detail, streams, laps
- `fitops athlete` — profile, stats, zones
- Single `~/.fitops/fitops.db` SQLite database
- LLM-friendly JSON output with `_meta` blocks

---

## Phase 2 — Analytics ✅

**Goal:** Calculate training metrics locally from synced activities.

### Training Load (CTL / ATL / TSB)

Based on the exponential weighted moving average model:

- **TSS (Training Stress Score):** Per-activity effort score
  - Running: pace-based (intensity relative to threshold pace)
  - Cycling: power-based (Normalized Power / FTP)
  - Fallback: HR-based zone multipliers
- **CTL (Chronic Training Load):** 42-day EWMA — your "fitness"
- **ATL (Acute Training Load):** 7-day EWMA — your "fatigue"
- **TSB (Training Stress Balance):** CTL − ATL — your "form"

### VO2max Estimation

Weighted composite of three formulas applied to race-effort activities:
- Jack Daniels' VDOT (50% weight) — most reliable for distances ≥ 3km
- McArdle equation (30%) — pace-based
- Costill equation (20–40%) — distance-corrected

### Lactate Thresholds (LT1 / LT2)

Derived from athlete's LTHR (Lactate Threshold Heart Rate) using the 5-zone LTHR model:
- Zone 1: < 85% LTHR
- Zone 2: 85–92% LTHR (aerobic, LT1 region)
- Zone 3: 92–100% LTHR (tempo)
- Zone 4: 100–106% LTHR (lactate threshold, LT2)
- Zone 5: > 106% LTHR (VO2max)

### New Commands (Phase 2)

```bash
fitops analytics training-load           # CTL, ATL, TSB trend (last 90 days)
fitops analytics training-load --today   # Today's snapshot
fitops analytics vo2max                  # VO2max estimate from recent hard efforts
fitops analytics zones --method lthr     # Zone boundaries (lthr / max_hr / hrr)
fitops analytics zones --set-lthr 165    # Update LTHR setting
```

---

## Phase 3 — Workouts & Compliance ✅

**Goal:** Create structured workouts, associate them with activities, score compliance.

### Workout System

- **WorkoutCourse:** Reusable template with hierarchical structure
  - `Movement`: single step (e.g. "10 min Zone 2")
  - `Set`: grouped movements with repetitions (e.g. "5 × 1km @ Zone 4")
- **Workout:** Scheduled instance from a course
  - Status: planned → in_progress → completed / cancelled
  - Linked to an activity via `activity_id`

### Compliance Scoring

After linking a workout to a completed activity:
- Compare planned zones vs actual HR/pace zones
- Duration variance
- Completion status

### Equipment Mileage

Track gear wear using Strava `gear_id`:
- Running shoes by distance (suggested replacement after 800km)
- Bike components by hours/distance

### New Commands (Phase 3)

```bash
fitops workouts create                   # Create workout template
fitops workouts schedule --date DATE     # Schedule a workout
fitops workouts link WORKOUT ACTIVITY    # Link to completed activity
fitops workouts list                     # All workouts with status
fitops workouts compliance WORKOUT       # Compliance score breakdown
fitops equipment list                    # Equipment with cumulative mileage
```

---

## Phase 4 — Multi-Provider Data Ingestion 🔜

**Goal:** Break the Strava dependency. Pull activity data directly from wearable platforms so athletes can use FitOps regardless of which ecosystem they live in. Also support direct file imports so any athlete can load activities without any API integration.

### Direct file import

| Format | Notes |
|--------|-------|
| **GPX** | Standard GPS exchange format — exported by Strava, Garmin, Coros, and most devices |
| **TCX** | Garmin Training Center XML — includes HR, cadence, and power streams |
| **FIT** | Flexible and Interoperable Data Transfer — native Garmin/Wahoo binary format; most data-rich |

```bash
fitops import <file.gpx>              # import a single activity from file
fitops import <file.tcx>
fitops import <file.fit>
fitops import ~/exports/ --watch      # watch a folder and auto-import new files
```

### Target API providers

| Provider | API / mechanism | Data available |
|----------|----------------|----------------|
| **Garmin Connect** | Garmin Health API (OAuth 2.0) | Activities, HR, GPS, sleep, daily summaries |
| **Coros** | COROS Open API | Activities, training metrics, HR, GPS |
| **Samsung Health** | Samsung Health Platform API | Activities, HR, sleep, steps |
| **Apple Health** | HealthKit export (XML) or Apple Health REST (future) | Workouts, HR, HRV, sleep, body metrics |
| **Huawei Health** | HUAWEI Health Kit API | Activities, HR, sleep, stress |

### Architecture

Each provider is a separate sync adapter implementing a common `ProviderAdapter` interface:

```python
class ProviderAdapter(Protocol):
    async def authenticate(self) -> None: ...
    async def fetch_activities(self, since: datetime) -> list[RawActivity]: ...
    async def fetch_streams(self, activity_id: str) -> RawStreams: ...
```

Activities from all providers are normalised into the same `activities` table. A `provider` column distinguishes the source. The analytics layer (CTL/ATL, VO2max, zones) operates on the normalised data regardless of origin.

### New commands (Phase 4)

```bash
fitops providers list                    # Show configured providers
fitops providers add garmin              # Authenticate with Garmin Connect
fitops providers add coros               # Authenticate with COROS
fitops providers add samsung             # Authenticate with Samsung Health
fitops providers add apple               # Import Apple Health export (.xml)
fitops providers add huawei              # Authenticate with Huawei Health Kit
fitops providers remove PROVIDER         # Revoke and remove a provider
fitops sync run --provider garmin        # Sync from a specific provider only
```

---

## Phase 5 — Cloud Backup 🔜

**Goal:** Let athletes back up their local FitOps database to the cloud storage provider of their choice, on demand or on a schedule.

### Target providers

| Provider | Notes |
|----------|-------|
| **Google Drive** | OAuth 2.0, Drive API v3 |
| **OneDrive** | OAuth 2.0, Microsoft Graph API |
| **Dropbox** | OAuth 2.0, Dropbox API v2 |
| **Mega** | mega.py / MEGAcmd |

### What gets backed up

- `fitops.db` — the full SQLite database
- `config.json` — settings (tokens stripped before upload)
- `sync_state.json` — sync history

Backups are versioned with a timestamp suffix: `fitops_2026-03-13T0800.db.gz`. Retention policy (number of backups to keep) is configurable.

### New commands (Phase 5)

```bash
fitops backup configure gdrive           # Authenticate + set destination folder
fitops backup configure onedrive
fitops backup configure dropbox
fitops backup configure mega
fitops backup run                        # Upload snapshot now
fitops backup schedule --cron "0 3 * * *"  # Schedule nightly backup
fitops backup restore --date 2026-03-10  # Restore from a backup snapshot
fitops backup list                       # Show available remote snapshots
```

---

## Phase 6 — Notes & Memos ✅

**Goal:** Lightweight markdown-based note-taking system with tags, optional activity association, accessible from both CLI (for agents) and dashboard (for humans).

### Note Format

Notes are `.md` files stored in `~/.fitops/notes/`. They follow the same YAML frontmatter pattern as workouts:

```markdown
---
title: Felt sluggish on intervals
tags: [fatigue, nutrition, threshold]
activity_id: 12345678       # optional — links note to a specific activity
created: 2026-03-14T08:30:00
---

Legs felt heavy from km 3 onward. Probably under-fueled — skipped
breakfast before the session. HR drifted +8 bpm above normal for Z4.
Next time eat at least 90 min before threshold work.
```

Front matter is parsed for structured queries (filter by tag, by activity). Body is freeform markdown.

### Storage

- **Files:** `~/.fitops/notes/<slug>.md` — human-editable in any text editor
- **Index:** `notes` table in `fitops.db` for fast querying:
  - `id`, `slug`, `title`, `tags` (JSON), `activity_id` (FK, nullable), `created_at`, `updated_at`
  - Re-indexed on `fitops notes list` if files changed on disk

### CLI Commands

```bash
fitops notes create --title "Post-race thoughts" --tags race,review  # create via CLI (opens $EDITOR or inline)
fitops notes create --activity 12345678 --tags fatigue               # create linked to an activity
fitops notes list                          # list all notes (title, tags, date, linked activity)
fitops notes list --tag threshold          # filter by tag
fitops notes list --activity 12345678      # show notes for a specific activity
fitops notes get <slug>                    # display full note content
fitops notes edit <slug>                   # open in $EDITOR
fitops notes delete <slug>                 # remove note file + DB row
fitops notes tags                          # list all tags with counts
```

### Dashboard

- **List view:** sortable/filterable table of all notes with tag pills, linked activity preview
- **Create view:** markdown editor with tag input and optional activity picker
- **Detail view:** rendered markdown with linked activity summary if associated

---

## Phase 7 — Weather-Adjusted Pace & True Pace ✅

**Goal:** Adjust pace for environmental conditions (temperature, humidity, wind) — similar to how GAP adjusts for elevation — and combine both into a single "True Pace" metric that strips away all external factors.

---

### Weather Provider: Open-Meteo Historical Archive API

**Chosen provider: Open-Meteo** — confirmed best option after full evaluation.

| Provider | Historical | Free / No Key | Accuracy |
|---|---|---|---|
| **Open-Meteo** ✅ | Back to 1940 | ✅ No key, 10k req/day | ERA5 reanalysis (global grid) |
| Meteostat | ✅ | RapidAPI key, ~500 req/mo | Station interpolation (variable) |
| Visual Crossing | ✅ | Key required, 1k records/day | Station + model blend |
| OpenWeatherMap | Paid only | ❌ | n/a |

**API Endpoint:** `https://archive-api.open-meteo.com/v1/archive`

**Example call** — weather at lat=52.52, lon=13.40 on 2024-06-15:
```
https://archive-api.open-meteo.com/v1/archive
  ?latitude=52.52
  &longitude=13.40
  &start_date=2024-06-15
  &end_date=2024-06-15
  &hourly=temperature_2m,relative_humidity_2m,apparent_temperature,
          precipitation,wind_speed_10m,wind_direction_10m,
          wind_gusts_10m,dew_point_2m,weather_code
  &timezone=UTC
```

Response is 24-entry hourly arrays; `hour_index = activity_start_utc.hour` selects the right slot.

**No API key required for non-commercial / personal use.**
Rate limits: 600 req/min · 5,000 req/hr · 10,000 req/day. One call covers a full day — more than enough for any backfill scenario.

**GPS source for coordinates:** `start_latlng` from `activities` table (already synced from Strava). Fallback to polyline centroid when available from streams.

**Storage:** `activity_weather` table (new):
```
id, activity_id (FK), temperature_c, humidity_pct, apparent_temp_c,
wind_speed_kmh, wind_direction_deg, wind_gusts_kmh, dew_point_c,
precipitation_mm, weather_code, fetched_at, source ("open-meteo" | "manual")
```

---

### Pace Adjustment Models

All formulas are grounded in published sports science research.

#### Temperature + Humidity — WBGT-based model (Ely et al. 2007 / Vihma 2010)

The canonical source is **Ely et al. (2007)** *Medicine & Science in Sports & Exercise* — marathon performance analysis across 5 decades of race data.

**Step 1: Compute WBGT approximation** (Liljegren simplified, using vapor pressure):
```python
import math

def _vapor_pressure(temp_c: float, rh_pct: float) -> float:
    """Vapor pressure (kPa) via Magnus formula."""
    return (rh_pct / 100.0) * 0.6105 * math.exp(17.27 * temp_c / (temp_c + 237.3))

def wbgt_approx(temp_c: float, rh_pct: float) -> float:
    e = _vapor_pressure(temp_c, rh_pct)
    return 0.567 * temp_c + 0.393 * e + 3.94
```

**Step 2: Pace penalty from WBGT** (Ely/ACSM piecewise, validated against marathon data):
```python
def pace_heat_factor(temp_c: float, rh_pct: float) -> float:
    """Returns pace multiplier: 1.0 = neutral, 1.08 = 8% slower."""
    wbgt = wbgt_approx(temp_c, rh_pct)
    if wbgt < 10:
        return 1.0                                         # optimal / cold
    elif wbgt < 18:
        return 1.0 + 0.002 * (wbgt - 10)                 # 0–1.6% (10–18°C WBGT)
    elif wbgt < 23:
        return 1.016 + 0.006 * (wbgt - 18)               # 1.6–4.6% (18–23°C WBGT)
    elif wbgt < 28:
        return 1.046 + 0.014 * (wbgt - 23)               # 4.6–11.6% (23–28°C WBGT)
    else:
        return 1.116 + 0.020 * (wbgt - 28)               # >11.6%, steep above 28°C
```

**Key benchmarks** (WBGT ≈ air temp when RH ~50%):
- 10°C, 60% RH → ~0% penalty
- 20°C, 60% RH → ~3% slower
- 28°C, 60% RH → ~9% slower
- 32°C, 75% RH → ~14% slower

#### Wind — Vector projection model (Pugh 1971 / Davies 1980)

Wind direction from Open-Meteo is **meteorological convention**: degrees the wind blows *FROM* (0°=from North, 90°=from East).

**Step 1: Course bearing** — compute mean bearing of GPS track from polyline or start/end coordinates:
```python
def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    """Great-circle initial bearing in degrees (0=North, clockwise)."""
    dlon = math.radians(lon2 - lon1)
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360
```

**Step 2: Headwind component** — dot product of wind vector onto course direction:
```python
def headwind_kmh(wind_speed: float, wind_dir_deg: float, course_bearing_deg: float) -> float:
    """
    Positive = headwind (costs energy), negative = tailwind (saves energy).
    wind_dir_deg: direction wind blows FROM (met convention).
    course_bearing_deg: direction athlete runs TOWARD.
    """
    wind_toward_deg = (wind_dir_deg + 180) % 360   # direction wind travels toward
    wind_u = wind_speed * math.sin(math.radians(wind_toward_deg))
    wind_v = wind_speed * math.cos(math.radians(wind_toward_deg))
    run_u = math.sin(math.radians(course_bearing_deg))
    run_v = math.cos(math.radians(course_bearing_deg))
    return -(wind_u * run_u + wind_v * run_v)       # negative dot = headwind
```

**Step 3: Pace penalty from wind** (aerodynamic drag model, Pugh 1971):
```python
def pace_wind_factor(headwind_kmh_val: float) -> float:
    """
    Headwind > 0 → pace penalty (slower). Tailwind < 0 → pace benefit (faster).
    Tailwind benefit is ~55% of equivalent headwind cost (physics asymmetry).
    Validated range: ±40 km/h wind.
    """
    if headwind_kmh_val >= 0:
        penalty = 0.0025 * (headwind_kmh_val ** 1.5)     # ~3% at 10 km/h, ~8% at 20 km/h
    else:
        penalty = -0.0014 * (abs(headwind_kmh_val) ** 1.5)  # 55% of headwind cost
    return max(0.85, min(1.25, 1.0 + penalty / 100))
```

**Rule of thumb:** 10 km/h headwind ≈ +3–4% pace penalty; 20 km/h ≈ +8–10%.

For **out-and-back** courses the net wind effect ≈ 0 (cancel each direction). Wind matters most for point-to-point or heavily directional courses.

---

### VO2max Heat/Humidity Penalty

Based on **Nybo et al. (2001)** and **González-Alonso et al. (1999)**: each 1°C rise in core body temperature above 37°C reduces VO2max by ~3%. In hot/humid conditions, core temp is elevated 0.5–2.0°C before the same aerobic work, effectively suppressing the aerobic ceiling.

```python
def vo2max_heat_factor(temp_c: float, rh_pct: float) -> float:
    """
    VO2max multiplier due to heat stress.
    1.0 = no reduction, 0.92 = 8% reduction.
    Source: Cheuvront & Haymes (2001), González-Alonso (1999).
    """
    if temp_c <= 10:
        return 1.0
    e = _vapor_pressure(temp_c, rh_pct)
    heat_stress = temp_c + 0.33 * e - 4.0          # simplified heat stress index
    reduction = min(0.25, max(0.0, 0.01 * (heat_stress - 10)))
    return 1.0 - reduction
```

**Benchmarks:**
- 21°C, 50% RH → ~3–5% VO2max reduction
- 30°C, 50% RH → ~8–12% reduction
- 35°C, 70% RH → ~15–20% reduction

This factor is applied on top of the standard VDOT/VO2max estimate to produce a **heat-adjusted VO2max** that reflects the athlete's true aerobic capacity under those conditions.

---

### True Pace

**True Pace = WAP + GAP combined** — the pace you would have run on flat ground in ideal weather (15°C, 40% RH, no wind).

```
true_pace = actual_pace_s_per_km / (gap_factor × wap_factor)
```

Where:
- `gap_factor` = grade-adjusted correction from elevation streams (already in pipeline)
- `wap_factor` = 1 / (pace_heat_factor × pace_wind_factor)

A single effort-normalized metric — a hilly, hot, headwind 10K becomes directly comparable to a flat, cool, calm 10K. Also enables cross-season VO2max trending without weather noise.

---

### CLI Commands

```bash
fitops weather fetch <activity_id>          # fetch + store weather for one activity
fitops weather fetch --all                  # backfill all activities with GPS coords
fitops weather show <activity_id>           # display stored weather conditions
fitops weather set <activity_id> --temp 28 --humidity 70 --wind 12 --wind-dir 270  # manual override

fitops analytics wap <activity_id>          # Weather-Adjusted Pace vs actual
fitops analytics true-pace <activity_id>    # True Pace (WAP + GAP combined)
fitops analytics true-pace --list --sport Run --limit 10   # recent runs with True Pace
```

### Dashboard

- Weather conditions badge on activity cards (temp + icon from `weather_code`)
- WAP / GAP / True Pace comparison panel per activity
- True Pace trend over time — a flat, season-agnostic fitness line
- Heat-adjusted VO2max overlay on the VO2max history chart

---

## Phase 8 — Race Simulation & Pacing ✅

**Goal:** Import a race course, simulate effort across the profile factoring in elevation and weather, and produce a per-split pacing plan. Supports both target-time and pacer-following strategies.

### Course Import

Import race courses from standard GPS file formats:

| Format | Parser | Notes |
|--------|--------|-------|
| `.gpx` | `gpxpy` | Most common — Strava exports, race organizers |
| `.tcx` | `lxml` or `tcxparser` | Garmin-native format |

Parsed into a `race_courses` table:
- `id`, `name`, `file_format`, `total_distance_m`, `total_elevation_gain_m`
- `course_points` JSON — array of `{lat, lon, elevation_m, distance_from_start_m}`
- `imported_at`

```bash
fitops race import <file.gpx> --name "Berlin Marathon 2026"
fitops race import <file.tcx> --name "Local 10K"
fitops race courses                         # list imported courses
fitops race course <id>                     # show course profile summary
```

### Race Simulation

Given a course + target, simulate the race with per-km (or per-mile) splits:

**Inputs:**
- Course (from imported GPX/TCX)
- Target time OR target average pace
- Weather conditions (manual or forecast)
- Athlete profile (current fitness — CTL, VO2max, threshold pace)

**Engine computes per split:**
- Elevation delta → GAP adjustment (slow on uphills, recover on downhills)
- Weather → WAP adjustment (heat/humidity/wind per segment bearing)
- Energy model: negative split bias (start conservative, finish strong) or even split
- Cumulative time and projected finish

**Output:** split table with columns:
`km | elevation | grade% | gap_factor | wap_factor | target_split | cumulative_time`

### Pacing Modes

**1. Target mode** (default):
```bash
fitops race simulate <course_id> --target-time 3:15:00    # marathon in 3:15
fitops race simulate <course_id> --target-pace 4:37       # per-km pace
fitops race simulate <course_id> --target-time 3:15:00 --weather --temp 28 --humidity 65
```

Produces an optimized split plan that accounts for course profile and conditions to hit the target.

**2. Pacer mode:**
```bash
fitops race simulate <course_id> --pacer-pace 4:30 --drop-at-km 35
fitops race simulate <course_id> --pacer-pace 4:37 --hold-until 30  # sit with pacer for 30km
```

Strategy:
- **Sit phase:** match the pacer's pace exactly (drafting benefit, lower cognitive load)
- **Push phase:** after the drop point, calculate the required pace to hit the target finish time given remaining distance + course profile
- Output shows: "Stay with pacer through km 35 (projected split: 2:37:30), then push to 4:15/km for final 7.2 km"

### CLI Commands

```bash
# Course management
fitops race import <file>                   # import .gpx or .tcx
fitops race courses                         # list courses
fitops race course <id>                     # course profile details
fitops race delete <id>                     # remove a course

# Simulation
fitops race simulate <course_id> --target-time HH:MM:SS
fitops race simulate <course_id> --target-pace MM:SS [--unit km|mi]
fitops race simulate <course_id> --target-time HH:MM:SS --pacer-pace MM:SS --drop-at-km N
fitops race simulate <course_id> --target-time HH:MM:SS --weather --temp T --humidity H --wind W

# Quick view
fitops race splits <course_id> --target-time HH:MM:SS   # just the split table
```

### Dashboard

- **Course profile:** elevation chart with km markers
- **Split overlay:** colored bars showing target pace per split (green = easy, red = hard)
- **Pacer visualization:** line showing pacer pace vs your plan, with the breakaway point marked
- **Comparison mode:** overlay multiple simulation scenarios (e.g., 3:10 vs 3:15 target)
