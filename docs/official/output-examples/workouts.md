# Output Examples — Workouts

## `fitops workouts list`

```bash
fitops workouts list
```

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "total_count": 3
  },
  "workouts_dir": "/Users/jane/.fitops/workouts",
  "workouts": [
    {
      "file_name": "long-run-sunday.md",
      "name": "Long Run Sunday",
      "sport": "Run",
      "target_duration_min": 90,
      "tags": ["aerobic", "base", "long-run"]
    },
    {
      "file_name": "threshold-tuesday.md",
      "name": "Threshold Tuesday",
      "sport": "Run",
      "target_duration_min": 60,
      "tags": ["threshold", "quality", "run"]
    },
    {
      "file_name": "vo2max-wednesday.md",
      "name": "VO2max Wednesday",
      "sport": "Run",
      "target_duration_min": 50,
      "tags": ["vo2max", "intervals"]
    }
  ]
}
```

---

## `fitops workouts link`

```bash
fitops workouts link threshold-tuesday 12345678901
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "linked": {
    "workout_name": "Threshold Tuesday",
    "activity_id": 12345678901,
    "activity_name": "Morning Run",
    "sport_type": "Run",
    "linked_at": "2026-03-11T09:15:00+00:00",
    "physiology_snapshot": {
      "ctl": 72.4,
      "atl": 68.1,
      "tsb": 4.3,
      "form_label": "Fresh — optimal race readiness window",
      "vo2max": 52.8,
      "vo2max_confidence": "High",
      "lt2_hr": 165,
      "lt1_hr": 151,
      "max_hr": 192,
      "zones_method": "lthr",
      "zones": {
        "method": "lthr",
        "lthr_bpm": 165,
        "heart_rate_zones": [
          { "zone": 1, "name": "Recovery",  "min_bpm": 0,   "max_bpm": 140 },
          { "zone": 2, "name": "Aerobic",   "min_bpm": 140, "max_bpm": 151 },
          { "zone": 3, "name": "Tempo",     "min_bpm": 151, "max_bpm": 165 },
          { "zone": 4, "name": "Threshold", "min_bpm": 165, "max_bpm": 174 },
          { "zone": 5, "name": "VO2max",    "min_bpm": 174, "max_bpm": 999 }
        ]
      }
    }
  }
}
```

---

## `fitops workouts compliance`

```bash
fitops workouts compliance 12345678901
```

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "total_count": 4
  },
  "workout_name": "Threshold Tuesday",
  "activity_strava_id": 12345678901,
  "overall_compliance_score": 0.81,
  "zones_method": "lthr",
  "segments": [
    {
      "index": 0,
      "name": "Warmup",
      "step_type": "warmup",
      "target_zone": 2,
      "duration_min": 10.0,
      "stream_slice": { "start_index": 0, "end_index": 600 },
      "actuals": {
        "avg_heartrate_bpm": 142.3,
        "actual_zone": 2,
        "hr_zone_distribution": { "z1": 0.18, "z2": 0.72, "z3": 0.10, "z4": 0.0, "z5": 0.0 }
      },
      "compliance": {
        "target_achieved": true,
        "compliance_score": 0.89,
        "deviation_pct": 0.0,
        "time_in_target_pct": 0.72,
        "time_above_pct": 0.10,
        "time_below_pct": 0.18
      },
      "data_quality": {
        "has_heartrate": true,
        "has_power": false,
        "data_completeness": 1.0
      }
    },
    {
      "index": 1,
      "name": "Main Set",
      "step_type": "interval",
      "target_zone": 4,
      "duration_min": 32.0,
      "stream_slice": { "start_index": 600, "end_index": 2520 },
      "actuals": {
        "avg_heartrate_bpm": 168.1,
        "actual_zone": 4,
        "hr_zone_distribution": { "z1": 0.0, "z2": 0.02, "z3": 0.08, "z4": 0.74, "z5": 0.16 }
      },
      "compliance": {
        "target_achieved": true,
        "compliance_score": 0.83,
        "deviation_pct": 0.0,
        "time_in_target_pct": 0.74,
        "time_above_pct": 0.16,
        "time_below_pct": 0.10
      },
      "data_quality": {
        "has_heartrate": true,
        "has_power": false,
        "data_completeness": 0.98
      }
    },
    {
      "index": 2,
      "name": "Recovery",
      "step_type": "recovery",
      "target_zone": 1,
      "duration_min": 2.0,
      "stream_slice": { "start_index": 2520, "end_index": 2640 },
      "actuals": {
        "avg_heartrate_bpm": 148.5,
        "actual_zone": 2,
        "hr_zone_distribution": { "z1": 0.12, "z2": 0.78, "z3": 0.10, "z4": 0.0, "z5": 0.0 }
      },
      "compliance": {
        "target_achieved": false,
        "compliance_score": 0.57,
        "deviation_pct": 100.0,
        "time_in_target_pct": 0.12,
        "time_above_pct": 0.88,
        "time_below_pct": 0.0
      },
      "data_quality": {
        "has_heartrate": true,
        "has_power": false,
        "data_completeness": 1.0
      }
    },
    {
      "index": 3,
      "name": "Cooldown",
      "step_type": "cooldown",
      "target_zone": 1,
      "duration_min": 8.0,
      "stream_slice": { "start_index": 2640, "end_index": 3120 },
      "actuals": {
        "avg_heartrate_bpm": 135.2,
        "actual_zone": 1,
        "hr_zone_distribution": { "z1": 0.83, "z2": 0.17, "z3": 0.0, "z4": 0.0, "z5": 0.0 }
      },
      "compliance": {
        "target_achieved": true,
        "compliance_score": 0.93,
        "deviation_pct": 0.0,
        "time_in_target_pct": 0.83,
        "time_above_pct": 0.17,
        "time_below_pct": 0.0
      },
      "data_quality": {
        "has_heartrate": true,
        "has_power": false,
        "data_completeness": 1.0
      }
    }
  ]
}
```

*Note: the recovery segment has low compliance because HR stayed elevated in Z2 during the 2-min recovery — a common finding that signals residual fatigue.*

---

## `fitops workouts get`

```bash
fitops workouts get 12345678901
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "workout": {
    "id": 3,
    "name": "Threshold Tuesday",
    "sport_type": "Run",
    "file_name": "threshold-tuesday.md",
    "linked_at": "2026-03-11 09:15:00+00:00",
    "status": "completed",
    "notes": "Felt strong, legs fresh",
    "compliance_score": 0.81,
    "meta": {
      "name": "Threshold Tuesday",
      "sport": "Run",
      "target_duration_min": 60,
      "tags": ["threshold", "quality", "run"]
    },
    "physiology_snapshot": {
      "ctl": 72.4,
      "atl": 68.1,
      "tsb": 4.3,
      "vo2max": 52.8,
      "lt2_hr": 165,
      "lt1_hr": 151,
      "zones_method": "lthr"
    },
    "body": "---\nname: Threshold Tuesday\n..."
  }
}
```

---

## `fitops workouts history`

```bash
fitops workouts history --limit 3
```

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "total_count": 3,
    "filters_applied": { "limit": 3 }
  },
  "workouts": [
    {
      "id": 5,
      "name": "Threshold Tuesday",
      "sport_type": "Run",
      "workout_file": "threshold-tuesday.md",
      "activity_id": 12345678901,
      "linked_at": "2026-03-11 09:15:00+00:00",
      "compliance_score": 0.81,
      "status": "completed"
    },
    {
      "id": 4,
      "name": "Long Run Sunday",
      "sport_type": "Run",
      "workout_file": "long-run-sunday.md",
      "activity_id": 12345678800,
      "linked_at": "2026-03-08 08:30:00+00:00",
      "compliance_score": 0.92,
      "status": "completed"
    },
    {
      "id": 3,
      "name": "VO2max Wednesday",
      "sport_type": "Run",
      "workout_file": "vo2max-wednesday.md",
      "activity_id": 12345678700,
      "linked_at": "2026-03-05 06:45:00+00:00",
      "compliance_score": 0.76,
      "status": "completed"
    }
  ]
}
```

← [Output Examples](./README.md)
