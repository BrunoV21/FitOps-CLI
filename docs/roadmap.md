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
