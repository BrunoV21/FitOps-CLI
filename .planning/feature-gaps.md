# FitOps-CLI — Feature Gaps from KineticRun

**Last updated:** 2026-03-11
**Reference:** `C:\Users\GL504GS\Desktop\repos\KineticRun\app\`
**Status:** Phase 2 ✅ Phase 3.1 ✅ Phase 3.2 ✅

---

## Phase 3 — Workouts ✅ COMPLETE

### 3.1 Markdown-based Workout Definitions ✅ DONE

**Concept:** Workouts are `.md` files that live in `~/.fitops/workouts/`. They are human-writable and editable in any text editor. When a workout is linked to an activity, the following are stored together in the `workouts` table:

- Raw markdown content of the workout file
- Physiology snapshot at link time: CTL, ATL, TSB, VO2max, LT1, LT2, zones method + values

This differs from KineticRun's JSON/DB-centric approach — it is intentionally simpler and more CLI-native.

**Workout file format (proposed):**

```markdown
---
name: Threshold Tuesday
sport: Run
target_duration_min: 60
tags: [threshold, quality]
---

## Warmup
10 min easy (Z1–Z2)

## Main Set
4 × 8 min @ Z4 (LT2 pace), 2 min Z1 recovery between

## Cooldown
8 min easy (Z1)
```

Front matter (YAML) is parsed for structured fields. Body is stored verbatim.

**CLI commands:**

```
fitops workouts list                        # list .md files in ~/.fitops/workouts/
fitops workouts show <name>                 # display a workout file
fitops workouts link <name> <activity_id>   # link workout to activity + save physiology snapshot
fitops workouts get <activity_id>           # retrieve linked workout + snapshot for an activity
fitops workouts history                     # list past linked workouts with compliance summary
```

**DB changes needed:**

`workouts` table (currently a stub) — add columns:
- `workout_file_name` TEXT — filename of the source .md file
- `workout_markdown` TEXT — raw content of the .md file at link time
- `workout_meta` JSON — parsed front matter fields
- `physiology_snapshot` JSON — `{ctl, atl, tsb, vo2max, lt1_hr, lt2_hr, zones_method, zones}`
- `linked_at` DATETIME
- `notes` TEXT — optional user notes at link time

**Reference:** `KineticRun/app/models/workout.py` — `Workout.link_to_activity()`, `track_modification()`

---

### 3.2 Workout Segment Compliance ✅ DONE

When a workout has named segments (e.g. "warmup / Z4 intervals / cooldown") and the linked activity has heart rate or power streams, score each segment against the target.

**New model: `WorkoutSegment`**

```
workout_id          FK → workouts.id
segment_index       INT
segment_name        TEXT              e.g. "Main Set Rep 1"
step_type           TEXT              warmup | interval | recovery | cooldown

-- Stream boundaries
start_index         INT               index into activity stream array
end_index           INT

-- Target
target_focus_type   TEXT              hr_zone | pace_zone | power_zone | rpe
target_zone         INT               e.g. 4

-- Pace/speed actuals
avg_pace_per_km     FLOAT
pace_consistency    FLOAT             0-1, 1.0 = perfectly even

-- HR actuals
avg_heartrate       FLOAT
hr_zone_distribution JSON             {"z1": 0.05, "z2": 0.10, "z3": 0.20, "z4": 0.60, "z5": 0.05}

-- Power actuals
avg_watts           FLOAT
normalized_power    FLOAT

-- Compliance
target_achieved     BOOL
deviation_pct       FLOAT             positive = above target
time_in_target_pct  FLOAT
time_above_pct      FLOAT
time_below_pct      FLOAT
compliance_score    FLOAT             0.0-1.0 overall

-- Data quality
has_heartrate       BOOL
has_power           BOOL
has_gps             BOOL
data_completeness   FLOAT             0.0-1.0
```

**Compliance scoring (from KineticRun `segment_service.py`):**
- Asymmetric penalties: being below target zone penalised more than being above
- `compliance_score = time_in_target_pct * 0.6 + (1.0 - |deviation_pct|) * 0.4`
- Capped 0.0–1.0

**CLI command:**

```
fitops workouts compliance <activity_id>   # show per-segment compliance report
```

**Reference:** `KineticRun/app/models/workout_segment.py`, `app/services/segment_service.py`

---

## Phase 4 — Deep Analytics

### 4.1 Trend Analysis

**Module:** `fitops/analytics/trends.py`
**Command:** `fitops analytics trends [--sport TYPE] [--days N]`

**What to compute:**

| Metric | Method | Notes |
|--------|--------|-------|
| Weekly volume trend | Linear regression on distance/time/frequency grouped by week | slope > 0 = increasing |
| Consistency score | `1.0 - (gap_std_dev / 7.0)`, gap = days between activities | 0.0–1.0 |
| Weekly consistency | `weeks_with_activity / total_weeks` | — |
| Seasonal patterns | Group by Spring/Summer/Autumn/Winter, detect peak season | months 3-5/6-8/9-11/12-2 |
| Pace trend | Slope of monthly avg pace; slope < -0.01 = improving | speed slope for cyclists |
| HR trend | Slope of monthly avg HR; slope < -0.5 = improving | lower HR at same effort = fitter |
| Improvement rate | `(latest - earliest) / earliest * 100` per month | % change |

**Trend classification thresholds (from KineticRun):**
- Strength: `|slope| < 0.1` → weak, `< 0.3` → moderate, else → strong
- Direction: pace slope `> 0.01` → declining, `< -0.01` → improving, else → stable

**Output keys:** `volume_trend`, `consistency`, `seasonal`, `performance_trend`, `summary_label`

**Reference:** `KineticRun/app/analytics/trend_analysis.py` — `TrendAnalyzer`

---

### 4.2 Power Curves (cyclists and advanced runners)

**Module:** `fitops/analytics/power_curves.py`
**Command:** `fitops analytics power-curve [--sport Ride]`

**Standard durations (seconds):**
```
5, 10, 15, 20, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200
```

**Critical Power model:** `P = CP + W'/t`
- **CP** (Critical Power) = sustainable power threshold (≈ FTP)
- **W'** (W prime) = anaerobic capacity in joules
- Fit with `scipy.optimize.curve_fit`; store R² as confidence

**For runners:** replace power with mean-maximal pace per duration (pace curve).

**Training zones derived from CP (from KineticRun):**
- Z1 Active Recovery: < 55% CP
- Z2 Endurance: 56–75% CP
- Z3 Tempo: 76–90% CP
- Z4 Lactate Threshold: 91–105% CP
- Z5 VO2max: 106–120% CP
- Z6 Neuromuscular: > 150% CP

**Output keys:** `mean_maximal_power`, `critical_power`, `w_prime`, `r_squared`, `zones`, `power_to_weight`

**Reference:** `KineticRun/app/analytics/power_curves.py` — `PowerCurveAnalyzer`

---

### 4.3 Performance Metrics

**Module:** `fitops/analytics/performance_metrics.py`
**Command:** `fitops analytics performance [--sport Run|Ride]`

**Running metrics:**

| Metric | Formula | Notes |
|--------|---------|-------|
| Running economy (energy cost) | `200 + (pace_min_per_km - 4.0) * 10` ml/kg/km | Lower = more efficient |
| Pace efficiency score | `100 - (pace_cv * 100)` | CV = std/mean of pace |
| Aerobic threshold HR | `max_hr * 0.75` | Estimated |
| Anaerobic threshold HR | `max_hr * 0.85` | Estimated |
| Max HR estimate | 98th percentile across all activities | |

**Cycling metrics:**

| Metric | Formula | Notes |
|--------|---------|-------|
| FTP estimate | `mean_power * 0.95` | From all rides |
| Power-to-weight (W/kg) | `ftp / weight_kg` | Needs weight from athlete profile |
| Normalized power ratio | `weighted_avg_watts / avg_watts` | Pacing quality |
| Power consistency | `100 - (power_cv * 100)` | |

**Universal metrics:**
- `variability_index` = std/mean (lower = more consistent pacing/effort)
- `overall_reliability` = mean of pace_consistency, power_consistency (0–1)

**Reference:** `KineticRun/app/analytics/performance_metrics.py` — `PerformanceAnalyzer`

---

### 4.4 Zone Inference from Activity Data

When the user hasn't manually set LTHR or max HR, infer from stream data.

**Module:** `fitops/analytics/zone_inference.py`
**Trigger:** Auto-runs when `fitops analytics zones` is called with no stored settings.

**LTHR inference:**
1. For each activity with HR stream, compute 20-minute rolling window average
2. Take 90th percentile across all rolling window averages across activities
3. Fallback: 85th percentile of all raw HR values

**Max HR estimation:**
- 98th percentile of all observed HR values across all activities
- Fallback: `max_avg_hr * 1.1`
- Hard cap: 220 bpm

**Resting HR:**
- 5th percentile of all HR values

**Confidence score (0–100):**
- Activity count: 10+ → 40pts, 5–9 → 25pts, 2–4 → 15pts, <2 → 5pts
- Data quality: `quality_score * 30`
- Consistency: `consistency_score * 30`

Stores inferred values in `~/.fitops/athlete_settings.json` with `source: "inferred"` and confidence score.

**CLI:** `fitops analytics zones --infer` — run inference from stream data.

**Reference:** `KineticRun/app/analytics/zone_inference.py` — `ZoneInference`

---

## Phase 5 — Data Quality & Enrichment

### 5.1 Pace Zones

Currently FitOps only computes HR zones. Pace zones are equally important for runners.

**Module:** `fitops/analytics/pace_zones.py`
**Command:** `fitops analytics pace-zones [--set-threshold-pace MM:SS]`

**Model:** Extend `athlete_settings.json`:
```json
{
  "threshold_pace_per_km_s": 360,
  "pace_zones_source": "manual",
  "pace_zones": [
    {"zone": 1, "name": "Easy",        "min_s_per_km": 420, "max_s_per_km": null},
    {"zone": 2, "name": "Aerobic",     "min_s_per_km": 390, "max_s_per_km": 420},
    {"zone": 3, "name": "Tempo",       "min_s_per_km": 368, "max_s_per_km": 390},
    {"zone": 4, "name": "Threshold",   "min_s_per_km": 346, "max_s_per_km": 368},
    {"zone": 5, "name": "VO2max",      "min_s_per_km": null, "max_s_per_km": 346}
  ]
}
```

Zones are derived as percentages of threshold pace (LT2 pace):
- Z1: > 116% of threshold pace (easy)
- Z2: 108–116%
- Z3: 102–108%
- Z4: 96–102% (threshold)
- Z5: < 96%

**Reference:** `KineticRun/app/models/zones.py` — `UserPaceZones`

---

### 5.2 Equipment Distance Tracking

Currently gear is stored as a JSON blob in `Athlete.bikes` and `Athlete.shoes`. A dedicated query would let athletes track mileage per shoe/bike.

**Command:** `fitops athlete equipment [--type shoes|bikes]`

**What it shows:**
- Equipment name, type, Strava ID
- Total distance from `Athlete.bikes[].distance` (Strava provides this in meters)
- Distance since last sync (computed from activities with matching `gear_id`)

No new model needed — computed from existing `Activity.gear_id` and `Athlete.bikes/shoes[].distance`.

**Reference:** `KineticRun/app/services/equipment_service.py`

---

### 5.3 Age-Adjusted VO2max

Currently FitOps computes raw VO2max. KineticRun adjusts for age:

```python
decline_rate = 0.008  # 0.8% per year after age 25
age_factor = 1.0 - ((age - 25) * decline_rate)
age_factor = max(0.5, age_factor)  # floor at 50%
adjusted_vo2max = raw_estimate * age_factor
```

Requires `athlete.birthday` to be stored. Strava provides `birthday` in the athlete profile response — add to `Athlete` model.

**Reference:** `KineticRun/app/analytics/vo2_estimation.py`

---

## Not Porting (Web App Specific)

| Feature | Why skip |
|---------|----------|
| Trainer-athlete relationships | Multi-user; not relevant for local single-user CLI |
| Notification system | No daemon/server running |
| Multi-database sharding | Unnecessary at local single-user scale |
| Celery background tasks | No server; `asyncio.run()` is sufficient |
| Admin endpoints | N/A |
| BetaCreds / feature flags | N/A |

---

## Implementation Order

```
Phase 3  →  3.1 Markdown workouts (list/show/link/get/history)
         →  3.2 Workout segment compliance (WorkoutSegment model + scoring)

Phase 4  →  4.4 Zone inference from streams (enables better defaults)
         →  4.1 Trend analysis (volume + consistency + seasonal)
         →  4.3 Performance metrics (running economy, FTP, efficiency)
         →  4.2 Power curves (cyclists; optional for runners as pace curve)

Phase 5  →  5.1 Pace zones
         →  5.2 Equipment distance tracking
         →  5.3 Age-adjusted VO2max

Phase 6  →  Notes & Memos (md files, tags, activity linking, CLI + dashboard)

Phase 7  →  Weather data fetching (Open-Meteo)
         →  WAP (Weather-Adjusted Pace)
         →  True Pace (WAP + GAP combined)

Phase 8  →  Course import (GPX/TCX)
         →  Race simulation engine (GAP + WAP + energy model)
         →  Target mode pacing
         →  Pacer mode strategy
```

---

## Phase 6 — Notes & Memos

- Markdown files in `~/.fitops/notes/` with YAML frontmatter (title, tags, optional activity_id)
- `notes` table for fast querying, re-indexed from disk
- CLI: `fitops notes create/list/get/edit/delete/tags`
- Dashboard: list + create + filter by tag, rendered markdown detail view

## Phase 7 — Weather-Adjusted Pace & True Pace

- Fetch historical weather via Open-Meteo (free, no key) for activity GPS coords + time
- `activity_weather` storage: temp, humidity, wind speed/direction
- **WAP:** pace adjustment for temperature (Ely et al.), humidity, wind (head/tail/cross)
- **True Pace = WAP + GAP:** single effort-normalized metric comparable across all conditions
- CLI: `fitops weather fetch/show/set`, `fitops analytics wap/true-pace`

## Phase 8 — Race Simulation & Pacing

- Import courses via `.gpx` (gpxpy) or `.tcx` (lxml)
- `race_courses` table with parsed course points
- Simulation engine: per-split GAP + WAP adjustments, energy model, negative/even split
- **Target mode:** input target time or pace → optimized split plan
- **Pacer mode:** input pacer pace + drop point → sit-then-push strategy
- CLI: `fitops race import/courses/simulate/splits`
- Dashboard: course profile chart, split overlay, pacer visualization

---

## Key Algorithms & Constants (quick reference)

```python
# Trend slope thresholds
TREND_WEAK      = 0.1   # |slope| < 0.1
TREND_MODERATE  = 0.3   # |slope| < 0.3
PACE_IMPROVING  = -0.01 # slope < this = improving pace
HR_IMPROVING    = -0.5  # slope < this = improving HR efficiency

# Zone inference
LTHR_PERCENTILE     = 90  # of 20-min rolling window averages
MAX_HR_PERCENTILE   = 98  # of all observed HR values
RESTING_HR_PCTILE   = 5   # of all observed HR values
MAX_HR_CAP          = 220

# Critical power model: P = CP + W'/t
# Fit with scipy.optimize.curve_fit

# Power zones from CP
CP_ZONES = {1: 0.55, 2: 0.75, 3: 0.90, 4: 1.05, 5: 1.20, 6: 1.50}

# Running economy
ENERGY_COST_ML_KG_KM = 200 + (pace_min_per_km - 4.0) * 10

# Age VO2max adjustment
VO2_AGE_DECLINE_RATE = 0.008  # per year after 25
VO2_AGE_FACTOR_FLOOR = 0.5

# Compliance scoring
COMPLIANCE = time_in_target_pct * 0.6 + (1.0 - abs(deviation_pct)) * 0.4
```
