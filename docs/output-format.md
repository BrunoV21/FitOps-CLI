# LLM-Friendly Output Format

All FitOps-CLI commands output JSON designed to be consumed by AI language models. Every response is independently interpretable — no raw integer IDs, no ambiguous abbreviations, all units explicit.

## Structure

Every response contains a `_meta` block at the top level:

```json
{
  "_meta": {
    "tool": "fitops",
    "version": "0.1.0",
    "generated_at": "2026-03-10T22:05:00+00:00",
    "total_count": 20,
    "filters_applied": {
      "sport_type": "Run",
      "limit": 20
    }
  }
}
```

## Activity Object

```json
{
  "strava_activity_id": 12345678901,
  "name": "Morning Run",
  "sport_type": "Run",
  "start_date_local": "2026-03-10T07:30:00",
  "start_date_utc": "2026-03-10T06:30:00+00:00",
  "timezone": "Europe/London",

  "duration": {
    "moving_time_seconds": 3720,
    "moving_time_formatted": "1:02:00",
    "elapsed_time_seconds": 3780
  },

  "distance": {
    "meters": 10250.4,
    "km": 10.25,
    "miles": 6.37
  },

  "pace": {
    "average_per_km": "6:03",
    "average_per_mile": "9:44"
  },

  "speed": {
    "average_ms": 2.75,
    "average_kmh": 9.9,
    "max_ms": 4.1
  },

  "elevation": {
    "total_gain_m": 85.0
  },

  "heart_rate": {
    "average_bpm": 148,
    "max_bpm": 172
  },

  "cadence": {
    "average_spm": 172
  },

  "power": null,

  "training_metrics": {
    "suffer_score": 42,
    "calories": 680,
    "training_stress_score": null
  },

  "equipment": {
    "gear_id": "g12345",
    "gear_name": "Nike Pegasus 40",
    "gear_type": "shoes"
  },

  "flags": {
    "trainer": false,
    "commute": false,
    "manual": false,
    "private": false
  },

  "social": {
    "kudos": 5,
    "comments": 1
  },

  "data_availability": {
    "has_gps": true,
    "has_heart_rate": true,
    "has_power": false,
    "streams_fetched": false,
    "laps_fetched": false,
    "detail_fetched": true
  }
}
```

## Sport-Specific Fields

| Field | Run | Ride | Swim |
|-------|-----|------|------|
| `pace` | ✅ (min/km, min/mile) | ❌ | ❌ |
| `power` | ❌ | ✅ (if device has power meter) | ❌ |
| `cadence.average_spm` | Steps per minute (doubled from raw) | RPM | Strokes/min |

## Unit Conventions

All field names carry their unit suffix:
- `_m` → meters
- `_km` → kilometers
- `_ms` → meters per second
- `_kmh` → kilometers per hour
- `_bpm` → beats per minute
- `_spm` → steps per minute
- `_s` → seconds
- `_kg` → kilograms

Pace is formatted as `"M:SS"` strings (e.g. `"6:03"` = 6 minutes 3 seconds per km).
Duration is formatted as `"H:MM:SS"` or `"M:SS"` depending on length.

## `data_availability` Block

Tells an LLM what additional data can be requested:

| Field | Meaning | How to get more |
|-------|---------|-----------------|
| `has_gps` | Activity has GPS coordinates | Included in base activity |
| `has_heart_rate` | HR data present | Included in base activity |
| `has_power` | Power meter data present | Included in base activity |
| `streams_fetched` | Time-series data loaded | `fitops activities streams ID` |
| `laps_fetched` | Lap splits loaded | `fitops activities laps ID` |
| `detail_fetched` | Full detail from Strava API | `fitops activities get ID --fresh` |

## Sync Result Output

```json
{
  "sync_type": "incremental",
  "activities_created": 3,
  "activities_updated": 1,
  "pages_fetched": 1,
  "duration_s": 4.2,
  "synced_at": "2026-03-10T22:05:00+00:00"
}
```
