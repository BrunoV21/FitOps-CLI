# Output Examples — Activities

## `fitops activities list`

```bash
fitops activities list --sport Run --limit 2
```

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "total_count": 2,
    "filters_applied": { "limit": 2, "sport_type": "Run" }
  },
  "activities": [
    {
      "strava_id": 12345678901,
      "name": "Morning Run",
      "sport_type": "Run",
      "start_date": "2026-03-10T07:15:00+00:00",
      "start_date_local": "2026-03-10T07:15:00",
      "timezone": "America/Los_Angeles",
      "duration": {
        "elapsed_time_seconds": 3720,
        "moving_time_seconds": 3650,
        "elapsed_time_formatted": "1:02:00",
        "moving_time_formatted": "1:00:50"
      },
      "distance": {
        "meters": 10234.0,
        "km": 10.23,
        "miles": 6.35
      },
      "pace": {
        "per_km": "5:55",
        "per_mile": "9:32"
      },
      "elevation": {
        "gain_meters": 87.0,
        "loss_meters": 84.0
      },
      "heart_rate": {
        "average_bpm": 152.0,
        "max_bpm": 174
      },
      "cadence": {
        "average_spm": 176
      },
      "power": {
        "average_watts": null,
        "max_watts": null
      },
      "gear": {
        "id": "g987654",
        "name": "Nike Vaporfly 3",
        "type": "shoes"
      },
      "flags": {
        "trainer": false,
        "commute": false,
        "manual": false,
        "private": false
      },
      "strava_url": "https://www.strava.com/activities/12345678901"
    },
    {
      "strava_id": 12345678800,
      "name": "Easy Recovery Jog",
      "sport_type": "Run",
      "start_date": "2026-03-08T08:00:00+00:00",
      "start_date_local": "2026-03-08T08:00:00",
      "timezone": "America/Los_Angeles",
      "duration": {
        "elapsed_time_seconds": 2100,
        "moving_time_seconds": 2070,
        "elapsed_time_formatted": "35:00",
        "moving_time_formatted": "34:30"
      },
      "distance": {
        "meters": 5120.0,
        "km": 5.12,
        "miles": 3.18
      },
      "pace": {
        "per_km": "6:44",
        "per_mile": "10:50"
      },
      "elevation": { "gain_meters": 12.0, "loss_meters": 11.0 },
      "heart_rate": { "average_bpm": 136.0, "max_bpm": 148 },
      "cadence": { "average_spm": 170 },
      "power": { "average_watts": null, "max_watts": null },
      "gear": { "id": "g987654", "name": "Nike Vaporfly 3", "type": "shoes" },
      "flags": { "trainer": false, "commute": false, "manual": false, "private": false },
      "strava_url": "https://www.strava.com/activities/12345678800"
    }
  ]
}
```

---

## `fitops activities streams <ID>`

```bash
fitops activities streams 12345678901
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "activity_strava_id": 12345678901,
  "streams": {
    "heartrate": {
      "data_length": 3650,
      "data": [140, 143, 146, 150, 152, 154, 155, 153, 152, 150]
    },
    "velocity_smooth": {
      "data_length": 3650,
      "data": [2.78, 2.81, 2.79, 2.83, 2.80, 2.75, 2.76, 2.78, 2.82, 2.80]
    },
    "altitude": {
      "data_length": 3650,
      "data": [45.2, 45.4, 45.8, 46.2, 46.5, 46.8, 47.0, 47.1, 46.9, 46.6]
    },
    "cadence": {
      "data_length": 3650,
      "data": [88, 89, 88, 87, 89, 90, 88, 89, 88, 87]
    }
  }
}
```

*Note: data arrays are truncated in this example. Actual streams contain one value per second.*

---

## `fitops activities laps <ID>`

```bash
fitops activities laps 12345678901
```

```json
{
  "_meta": { "total_count": 3, "generated_at": "2026-03-11T09:15:00+00:00" },
  "activity_strava_id": 12345678901,
  "laps": [
    {
      "lap_index": 1,
      "name": "Lap 1",
      "duration": { "moving_time_seconds": 355, "moving_time_formatted": "5:55" },
      "distance": { "meters": 1000.0, "km": 1.0 },
      "average_speed_ms": 2.82,
      "heart_rate": { "average_bpm": 148.0, "max_bpm": 156 },
      "average_watts": null
    },
    {
      "lap_index": 2,
      "name": "Lap 2",
      "duration": { "moving_time_seconds": 351, "moving_time_formatted": "5:51" },
      "distance": { "meters": 1000.0, "km": 1.0 },
      "average_speed_ms": 2.85,
      "heart_rate": { "average_bpm": 154.0, "max_bpm": 161 },
      "average_watts": null
    },
    {
      "lap_index": 3,
      "name": "Lap 3",
      "duration": { "moving_time_seconds": 349, "moving_time_formatted": "5:49" },
      "distance": { "meters": 1000.0, "km": 1.0 },
      "average_speed_ms": 2.86,
      "heart_rate": { "average_bpm": 161.0, "max_bpm": 168 },
      "average_watts": null
    }
  ]
}
```

← [Output Examples](./README.md)
