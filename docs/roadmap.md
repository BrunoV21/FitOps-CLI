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
