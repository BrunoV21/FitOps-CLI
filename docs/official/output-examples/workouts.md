# Output Examples — Workouts

All examples show default output. Add `--json` to any command for raw JSON.

---

## `fitops workouts list`

```bash
fitops workouts list
```

```
  threshold-tuesday.md   Threshold Tuesday   Run   60 min   [threshold, quality]
  long-run-sunday.md     Long Run Sunday     Run   90 min   [aerobic, base]
  vo2max-wednesday.md    VO2max Wednesday    Run   50 min   [vo2max, intervals]
```

---

## `fitops workouts link <name> <activity_id>`

```bash
fitops workouts link threshold-tuesday 17972016511
```

```
Linked  Threshold Tuesday  →  activity 17972016511

  Snapshot saved
  CTL     42.2
  ATL     54.0
  TSB     -11.8
  VO2max  55.4 ml/kg/min
```

---

## `fitops workouts compliance <activity_id>`

```bash
fitops workouts compliance 17972016511
```

```
Workout Compliance  Threshold Tuesday  →  17972016511

  Overall score   0.84  ✓

  Segment              Duration   Zone   Score   In-zone   Deviation
 ─────────────────────────────────────────────────────────────────────
  Warmup               10:00      Z1-2   0.91    94%       -0.1 zones
  Main Set (4×8min)    32:00      Z4     0.82    79%       +0.2 zones
  Cooldown              8:00      Z1     0.88    91%        0.0 zones
```

A score ≥ 0.8 per segment is a successful execution.

---

## `fitops workouts history`

```bash
fitops workouts history --limit 5
```

```
  Date        Activity                      Workout              Score
 ───────────────────────────────────────────────────────────────────────
  2026-04-04  Outdoor run (17972016511)     Threshold Tuesday    0.84
  2026-03-28  Morning Run (17930412200)     Long Run Sunday      0.91
  2026-03-22  Salvaterra 12K (17910000000)  —                    —
```

---

## JSON output (`--json`)

```bash
fitops workouts compliance 17972016511 --json
```

```json
{
  "_meta": { "generated_at": "2026-04-06T09:15:00+00:00" },
  "activity_id": 17972016511,
  "workout_name": "Threshold Tuesday",
  "overall_compliance_score": 0.84,
  "segments": [
    {
      "name": "Warmup",
      "duration_seconds": 600,
      "target_zone": 2,
      "time_in_target_pct": 0.94,
      "average_hr_bpm": 141,
      "zone_deviation": -0.1,
      "compliance_score": 0.91
    },
    {
      "name": "Main Set",
      "duration_seconds": 1920,
      "target_zone": 4,
      "time_in_target_pct": 0.79,
      "average_hr_bpm": 168,
      "zone_deviation": 0.2,
      "compliance_score": 0.82
    },
    {
      "name": "Cooldown",
      "duration_seconds": 480,
      "target_zone": 1,
      "time_in_target_pct": 0.91,
      "average_hr_bpm": 132,
      "zone_deviation": 0.0,
      "compliance_score": 0.88
    }
  ]
}
```

← [Output Examples](./index.md)
