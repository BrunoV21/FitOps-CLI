# Output Examples — Analytics

## `fitops analytics training-load`

```bash
fitops analytics training-load --days 7 --sport Run
```

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "total_count": 7,
    "filters_applied": { "sport": "Run", "days": 7 }
  },
  "training_load": {
    "current": {
      "date": "2026-03-11",
      "ctl": 72.4,
      "atl": 68.1,
      "tsb": 4.3,
      "form_label": "Fresh — optimal race readiness window"
    },
    "trend_7_days": {
      "ramp_rate_pct": 3.2,
      "ramp_label": "Moderate build"
    },
    "history": [
      { "date": "2026-03-05", "ctl": 70.1, "atl": 74.8, "tsb": -4.7, "daily_tss": 65.0 },
      { "date": "2026-03-06", "ctl": 70.2, "atl": 71.4, "tsb": -1.2, "daily_tss": 0.0 },
      { "date": "2026-03-07", "ctl": 70.7, "atl": 73.2, "tsb": -2.5, "daily_tss": 78.0 },
      { "date": "2026-03-08", "ctl": 70.9, "atl": 70.6, "tsb": 0.3, "daily_tss": 0.0 },
      { "date": "2026-03-09", "ctl": 71.2, "atl": 72.1, "tsb": -0.9, "daily_tss": 55.0 },
      { "date": "2026-03-10", "ctl": 71.8, "atl": 70.4, "tsb": 1.4, "daily_tss": 0.0 },
      { "date": "2026-03-11", "ctl": 72.4, "atl": 68.1, "tsb": 4.3, "daily_tss": 0.0 }
    ]
  }
}
```

### `--today` flag

```bash
fitops analytics training-load --today
```

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "filters_applied": { "sport": null, "today_only": true }
  },
  "training_load": {
    "current": {
      "date": "2026-03-11",
      "ctl": 72.4,
      "atl": 68.1,
      "tsb": 4.3,
      "form_label": "Fresh — optimal race readiness window"
    },
    "trend_7_days": {
      "ctl_change": 2.3,
      "ramp_rate_pct": 3.2,
      "ramp_label": "Moderate build"
    }
  }
}
```

---

## `fitops analytics vo2max`

```bash
fitops analytics vo2max
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "vo2max": {
    "estimate": 52.8,
    "unit": "ml/kg/min",
    "confidence": 0.82,
    "confidence_label": "High",
    "method_estimates": {
      "vdot": 53.1,
      "mcardle": 52.4,
      "costill": 52.7
    },
    "based_on_activity": {
      "strava_id": 12345678901,
      "name": "Morning Run",
      "distance_km": 10.23,
      "pace_per_km": "5:55",
      "date": "2026-03-10"
    }
  }
}
```

---

## `fitops analytics zones`

```bash
fitops analytics zones --method lthr
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "zones": {
    "method": "lthr",
    "lthr": 165,
    "zones": [
      { "zone": 1, "name": "Recovery",  "min_bpm": 0,   "max_bpm": 140 },
      { "zone": 2, "name": "Aerobic",   "min_bpm": 140, "max_bpm": 148 },
      { "zone": 3, "name": "Tempo",     "min_bpm": 148, "max_bpm": 156 },
      { "zone": 4, "name": "Threshold", "min_bpm": 156, "max_bpm": 165 },
      { "zone": 5, "name": "VO2max",    "min_bpm": 165, "max_bpm": null }
    ]
  }
}
```

```bash
fitops analytics zones --method hrr
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "zones": {
    "method": "hrr",
    "max_hr": 192,
    "resting_hr": 48,
    "zones": [
      { "zone": 1, "name": "Recovery",  "min_bpm": 48,  "max_bpm": 115 },
      { "zone": 2, "name": "Aerobic",   "min_bpm": 115, "max_bpm": 130 },
      { "zone": 3, "name": "Tempo",     "min_bpm": 130, "max_bpm": 144 },
      { "zone": 4, "name": "Threshold", "min_bpm": 144, "max_bpm": 158 },
      { "zone": 5, "name": "VO2max",    "min_bpm": 158, "max_bpm": null }
    ]
  }
}
```

### `--age-adjusted` flag

```bash
fitops analytics vo2max --age-adjusted
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "vo2max": {
    "estimate": 52.8,
    "unit": "ml/kg/min",
    "confidence": 0.82,
    "confidence_label": "High",
    "method_estimates": {
      "vdot": 53.1,
      "mcardle": 52.4,
      "costill": 52.7
    },
    "based_on_activity": {
      "strava_id": 12345678901,
      "name": "Morning Run",
      "distance_km": 10.23,
      "pace_per_km": "5:55",
      "date": "2026-03-10"
    },
    "age_adjusted": {
      "age": 38,
      "age_factor": 0.896,
      "adjusted_estimate": 47.3,
      "unit": "ml/kg/min"
    }
  }
}
```

---

## `fitops analytics zones --infer`

```bash
fitops analytics zones --infer
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "zone_inference": {
    "lthr_inferred": 163,
    "max_hr_inferred": 188,
    "resting_hr_inferred": 44,
    "confidence": 72,
    "activity_count": 18,
    "method": "rolling_window"
  }
}
```

Followed immediately by the computed zones output using the inferred LTHR.

---

## `fitops analytics trends`

```bash
fitops analytics trends --sport Run --days 180
```

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "filters_applied": { "sport": "Run", "days": 180 }
  },
  "trends": {
    "activity_count": 64,
    "summary_label": "volume building, consistent training, pace improving",
    "volume_trend": {
      "slope_km_per_week": 1.24,
      "direction": "increasing",
      "strength": "moderate",
      "weekly_averages": [
        { "week": "2025-W40", "distance_km": 38.2, "activity_count": 4 },
        { "week": "2025-W41", "distance_km": 41.5, "activity_count": 5 }
      ]
    },
    "consistency": {
      "consistency_score": 0.812,
      "weekly_consistency": 0.867,
      "avg_days_between_activities": 2.8
    },
    "seasonal": {
      "seasons": {
        "Autumn": {
          "activity_count": 28,
          "total_distance_km": 312.4,
          "avg_pace_min_per_km": 5.82
        },
        "Winter": {
          "activity_count": 22,
          "total_distance_km": 241.8,
          "avg_pace_min_per_km": 6.01
        },
        "Spring": {
          "activity_count": 14,
          "total_distance_km": 183.6,
          "avg_pace_min_per_km": 5.71
        }
      },
      "peak_season": "Autumn"
    },
    "performance_trend": {
      "pace_slope": -0.028,
      "pace_direction": "improving",
      "hr_slope": -1.2,
      "hr_direction": "improving",
      "improvement_rate_pct_per_month": -0.48
    }
  }
}
```

---

## `fitops analytics performance`

```bash
fitops analytics performance --sport Run
```

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "filters_applied": { "sport": "Run" }
  },
  "performance": {
    "sport": "Run",
    "activity_count": 42,
    "overall_reliability": 0.873,
    "running": {
      "running_economy_ml_kg_km": 218.2,
      "pace_efficiency_score": 87.3,
      "variability_index": 0.0127,
      "max_hr_estimate": 187,
      "aerobic_threshold_hr": 140,
      "anaerobic_threshold_hr": 159
    },
    "cycling": null
  }
}
```

```bash
fitops analytics performance --sport Ride
```

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "filters_applied": { "sport": "Ride" }
  },
  "performance": {
    "sport": "Ride",
    "activity_count": 31,
    "overall_reliability": 0.841,
    "running": null,
    "cycling": {
      "ftp_estimate_watts": 241.5,
      "power_to_weight_w_kg": 3.89,
      "normalized_power_ratio": 1.047,
      "power_consistency": 84.1,
      "variability_index": 0.0159
    }
  }
}
```

---

## `fitops analytics power-curve`

```bash
fitops analytics power-curve --sport Ride --activities 20
```

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "filters_applied": { "sport": "Ride", "max_activities": 20 }
  },
  "power_curve": {
    "sport": "Ride",
    "activity_count": 17,
    "mean_maximal_power": {
      "5":    821.0,
      "10":   712.0,
      "15":   648.0,
      "20":   601.0,
      "30":   543.0,
      "60":   461.0,
      "120":  398.0,
      "300":  321.0,
      "600":  284.0,
      "1200": 258.0,
      "1800": 248.0,
      "3600": 231.0,
      "7200": null
    },
    "critical_power_watts": 247.3,
    "w_prime_joules": 18420.0,
    "model_r_squared": 0.981,
    "zones_from_cp": [
      { "zone": 1, "name": "Active Recovery",    "min_watts": 0,   "max_watts": 136 },
      { "zone": 2, "name": "Endurance",           "min_watts": 138, "max_watts": 185 },
      { "zone": 3, "name": "Tempo",               "min_watts": 188, "max_watts": 222 },
      { "zone": 4, "name": "Lactate Threshold",   "min_watts": 225, "max_watts": 260 },
      { "zone": 5, "name": "VO2max",              "min_watts": 262, "max_watts": 297 },
      { "zone": 6, "name": "Neuromuscular",       "min_watts": 371, "max_watts": null }
    ],
    "power_to_weight": {
      "ftp_estimate_watts": 247.3,
      "weight_kg": 62.0,
      "w_per_kg": 3.99
    }
  }
}
```

For runners, `critical_power_watts`, `w_prime_joules`, `model_r_squared`, and `zones_from_cp` are `null`. `mean_maximal_power` values are in m/s (velocity).

---

## `fitops analytics pace-zones`

```bash
fitops analytics pace-zones --set-threshold-pace 5:00
```

```
Threshold pace set: 5:00/km
```

```bash
fitops analytics pace-zones
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "pace_zones": {
    "threshold_pace": "5:00/km",
    "threshold_pace_s": 300,
    "source": "manual",
    "zones": [
      { "zone": 1, "name": "Easy",      "min_s_per_km": 348, "max_s_per_km": null, "min_pace_fmt": "5:48", "max_pace_fmt": null },
      { "zone": 2, "name": "Aerobic",   "min_s_per_km": 324, "max_s_per_km": 348,  "min_pace_fmt": "5:24", "max_pace_fmt": "5:48" },
      { "zone": 3, "name": "Tempo",     "min_s_per_km": 306, "max_s_per_km": 324,  "min_pace_fmt": "5:06", "max_pace_fmt": "5:24" },
      { "zone": 4, "name": "Threshold", "min_s_per_km": 288, "max_s_per_km": 306,  "min_pace_fmt": "4:48", "max_pace_fmt": "5:06" },
      { "zone": 5, "name": "VO2max",    "min_s_per_km": null, "max_s_per_km": 288, "min_pace_fmt": null,   "max_pace_fmt": "4:48" }
    ]
  }
}
```

*`min_s_per_km` is the faster (lower) boundary; `max_s_per_km` is the slower (higher) boundary. `null` means unbounded.*

---

## `fitops analytics snapshot`

```bash
fitops analytics snapshot
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "snapshot": {
    "date": "2026-03-11",
    "ctl": 72.4,
    "atl": 68.1,
    "tsb": 4.3,
    "vo2max_estimate": 52.8,
    "lt1_hr": 151,
    "lt2_hr": 165
  }
}
```

← [Output Examples](./README.md)
