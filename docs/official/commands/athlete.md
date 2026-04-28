# fitops athlete

View athlete profile, physiology, cumulative stats, and computed HR/pace zones.

Output is human-readable by default. Add `--json` to any command for raw JSON output.

## Commands

### `fitops athlete profile`

Show athlete profile, equipment, and physiology from the local database.

```bash
fitops athlete profile
fitops athlete profile --json
```

**JSON output shape:**

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "athlete": {
    "strava_id": 987654,
    "name": "Jane Smith",
    "username": "janesmith",
    "city": "Portland",
    "country": "US",
    "sex": "F",
    "weight_kg": 62.0,
    "premium": true,
    "profile_url": "https://dgalywyr863hv.cloudfront.net/...",
    "equipment": {
      "bikes": [
        { "id": "b123456", "name": "Canyon Endurace", "distance": 3240000 }
      ],
      "shoes": [
        { "id": "g987654", "name": "Nike Vaporfly 3", "distance": 520000 }
      ]
    },
    "physiology": {
      "max_hr": 190,
      "resting_hr": 45,
      "lthr": 170,
      "ftp": 280,
      "lt1_pace": "5:30/km",
      "lt2_pace": "4:55/km",
      "vo2max_pace": "4:20/km",
      "vo2max": {
        "estimate": 55.2,
        "vdot": 53.1,
        "confidence": 0.85,
        "confidence_label": "high",
        "based_on_activity": {
          "name": "Threshold Tuesday",
          "date": "2026-03-15",
          "distance_km": 12.5,
          "pace_per_km": "4:52"
        }
      }
    }
  }
}
```

**Physiology block fields:**

| Field | Description |
|-------|-------------|
| `max_hr` | Max heart rate (bpm) — from local physiology settings |
| `resting_hr` | Resting heart rate (bpm) |
| `lthr` | Lactate threshold heart rate (bpm) |
| `ftp` | Functional threshold power in watts (cyclists) |
| `lt1_pace` | LT1 (aerobic threshold) pace, e.g. `"5:30/km"` |
| `lt2_pace` | LT2 (lactate threshold) pace, e.g. `"4:55/km"` |
| `vo2max_pace` | Velocity at VO2max (vVO2max), derived from VDOT |
| `vo2max` | VO2max estimate block (see below), or `null` if no estimate |

`vo2max` is estimated from recent activities when available. Fields: `estimate` (ml/kg/min), `vdot`, `confidence` (0–1), `confidence_label` (`"low"` / `"medium"` / `"high"`), and `based_on_activity` (the activity the estimate was derived from).

Requires a prior `fitops sync run` to populate locally. Physiology values are configured via `fitops athlete set` and `fitops analytics zones`.

---

### `fitops athlete stats`

Show cumulative statistics from Strava (live API call).

```bash
fitops athlete stats
```

Returns Strava's aggregate stats: total distance, moving time, and elevation for runs, rides, and swims — split into recent (year-to-date), all-time, and recent-totals.

---

### `fitops athlete zones`

Show computed HR and pace zones derived from local physiology settings.

```bash
fitops athlete zones
fitops athlete zones --json
```

Zones are computed locally from your LTHR, max HR, and resting HR — the same values used by the dashboard profile page. No network call required.

**JSON output shape:**

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "zones": {
    "method": "lthr",
    "lthr_bpm": 170,
    "max_hr_bpm": 190,
    "resting_hr_bpm": 45,
    "heart_rate_zones": [
      { "zone": 1, "name": "Recovery",   "min_bpm": 0,   "max_bpm": 139, "description": "Active recovery" },
      { "zone": 2, "name": "Aerobic",    "min_bpm": 140, "max_bpm": 156, "description": "Aerobic base" },
      { "zone": 3, "name": "Tempo",      "min_bpm": 157, "max_bpm": 166, "description": "Comfortably hard" },
      { "zone": 4, "name": "Threshold",  "min_bpm": 167, "max_bpm": 176, "description": "Threshold effort" },
      { "zone": 5, "name": "VO2max",     "min_bpm": 177, "max_bpm": 999, "description": "High intensity" }
    ],
    "thresholds": {
      "lt1_bpm": 156,
      "lt2_bpm": 170,
      "lt1_pace_fmt": "5:30/km",
      "lt1_pace_s": 330.0,
      "lt2_pace_fmt": "4:55/km",
      "lt2_pace_s": 295.0,
      "vo2max_pace_fmt": "4:20/km",
      "vo2max_pace_s": 260.0
    }
  },
  "pace_zones": [
    { "zone": 1, "name": "Easy",      "min_s_per_km": 342, "max_s_per_km": null, "min_pace_fmt": "5:42", "max_pace_fmt": null },
    { "zone": 2, "name": "Aerobic",   "min_s_per_km": 318, "max_s_per_km": 342,  "min_pace_fmt": "5:18", "max_pace_fmt": "5:42" },
    { "zone": 3, "name": "Tempo",     "min_s_per_km": 301, "max_s_per_km": 318,  "min_pace_fmt": "5:01", "max_pace_fmt": "5:18" },
    { "zone": 4, "name": "Threshold", "min_s_per_km": 283, "max_s_per_km": 301,  "min_pace_fmt": "4:43", "max_pace_fmt": "5:01" },
    { "zone": 5, "name": "VO2max",    "min_s_per_km": null, "max_s_per_km": 283, "min_pace_fmt": null,   "max_pace_fmt": "4:43" }
  ]
}
```

`pace_zones` is only present when a threshold pace is configured. `max_bpm` of `999` in zone 5 means "no upper bound" (displayed as `—` in the terminal).

If no zone parameters are set, the command exits with an error and a hint to configure LTHR via `fitops analytics zones --set-lthr`.

---

### `fitops athlete set`

Set physiology values used for analytics.

```bash
fitops athlete set [OPTIONS]
```

**Options:**

| Flag | Description |
|------|-------------|
| `--weight KG` | Body weight in kg |
| `--height CM` | Height in cm |
| `--birthday YYYY-MM-DD` | Date of birth |
| `--ftp WATTS` | FTP in watts (cyclists) |

```bash
fitops athlete set --weight 68.5
fitops athlete set --ftp 280
fitops athlete set --birthday 1990-06-15
```

---

### `fitops athlete equipment`

Show mileage and activity counts per piece of equipment (shoes and bikes).

```bash
fitops athlete equipment [OPTIONS]
```

**Options:**

| Flag | Description |
|------|-------------|
| `--type shoes\|bikes` | Filter to only shoes or only bikes. Omit to show all. |

```bash
fitops athlete equipment
fitops athlete equipment --type shoes
fitops athlete equipment --type bikes
```

Equipment is read from the local athlete record (synced from Strava). For each item the output includes:

- `strava_total_distance_km` — total lifetime distance Strava reports for this gear
- `local_activity_distance_km` — distance computed from locally-synced activities using this gear
- `local_activity_count` — number of locally-synced activities tagged to this gear

Requires a prior `fitops sync run`.

## See Also

- [Output Examples → Athlete](../output-examples/athlete.md) — full response samples
- [`fitops analytics zones`](./analytics.md) — set LTHR, max HR, and other zone parameters

← [Commands Reference](./index.md)
