# FitOps-CLI Roadmap

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

## Phase 2 — Analytics 🔜

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

## Phase 3 — Workouts & Compliance 🔜

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

**Goal:** Break the Strava dependency. Pull activity data directly from wearable platforms so athletes can use FitOps regardless of which ecosystem they live in.

### Target providers

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

## Phase 6 — Notes & Memos 🔜

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

## Phase 7 — Weather-Adjusted Pace & True Pace 🔜

**Goal:** Adjust pace for environmental conditions (temperature, humidity, wind) — similar to how GAP adjusts for elevation — and combine both into a single "True Pace" metric that strips away all external factors.

### Weather Data

Fetch historical weather for each activity using GPS start coordinates + start time:

| Source | Notes |
|--------|-------|
| **Open-Meteo Historical API** | Free, no API key, hourly resolution, covers global history |
| **Fallback: manual input** | `fitops weather set <activity_id> --temp 32 --humidity 80 --wind 15` |

Store per-activity weather in `activity_weather` table or JSON column on `activities`:
- `temperature_c`, `humidity_pct`, `wind_speed_kmh`, `wind_direction_deg`, `conditions` (rain/sun/etc.)

### Pace Adjustment Models

**Temperature adjustment** (based on research — Ely et al., Vihma 2010):
- Optimal range: 8–15°C (no adjustment)
- Per degree above 15°C: +0.3–0.5% pace penalty (exponential above 25°C)
- Per degree below 5°C: +0.1–0.2% pace penalty
- Above 30°C: additional humidity multiplier

**Humidity adjustment:**
- Below 40%: negligible
- 40–60%: +0.5–1.0% when temp > 20°C
- Above 75%: +2–4% when temp > 25°C (heat index interaction)

**Wind adjustment:**
- Headwind: +0.3% per km/h (above 10 km/h threshold)
- Tailwind: −0.15% per km/h (capped — less benefit than headwind cost)
- Crosswind: 50% of headwind effect
- Requires course direction vs wind direction (from GPS track bearing)

### True Pace

**True Pace = WAP + GAP combined** — the pace you would have run on flat ground in ideal weather.

```
true_pace = actual_pace × gap_factor × wap_factor
```

Where:
- `gap_factor` = grade-adjusted correction (already available from elevation streams)
- `wap_factor` = weather-adjusted correction (temperature + humidity + wind)

This gives athletes a single "effort-normalized" pace metric that is comparable across all conditions — a hilly, hot, windy 10K becomes directly comparable to a flat, cool, calm 10K.

### CLI Commands

```bash
fitops weather fetch <activity_id>          # fetch + store weather for an activity
fitops weather fetch --all                  # backfill weather for all activities with GPS
fitops weather show <activity_id>           # display weather conditions
fitops weather set <activity_id> --temp 28 --humidity 70 --wind 12  # manual override

fitops analytics wap <activity_id>          # show Weather-Adjusted Pace vs actual
fitops analytics true-pace <activity_id>    # show True Pace (WAP + GAP combined)
fitops analytics true-pace --list --sport Run --limit 10  # True Pace for recent runs
```

### Dashboard

- Weather conditions badge on activity cards
- WAP / GAP / True Pace comparison chart per activity
- True Pace trend over time (flat, comparable line across seasons)

---

## Phase 8 — Race Simulation & Pacing 🔜

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
