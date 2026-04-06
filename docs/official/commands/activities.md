# fitops activities

Browse and query synced activities.

## Commands

### `fitops activities list`

List recent activities with full metrics.

```bash
fitops activities list [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--sport TYPE` | all | Filter by sport type (e.g. `Run`, `Ride`, `Swim`) |
| `--limit N` | 20 | Max number of activities to return |
| `--after DATE` | — | Filter activities after this date (YYYY-MM-DD) |

**Examples:**

```bash
fitops activities list
fitops activities list --sport Run --limit 10
fitops activities list --after 2026-01-01
fitops activities list --sport Ride --limit 5 --after 2025-12-01
```

See [Output Examples → Activities](../output-examples/activities.md) for the full JSON shape.

---

### `fitops activities get <ID>`

Get detailed info for a single activity.

```bash
fitops activities get 12345678901 [--fresh]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `ID` | Strava activity ID (required) |

**Options:**

| Flag | Description |
|------|-------------|
| `--fresh` | Re-fetch detail from Strava API (bypasses local cache) |

---

### `fitops activities streams <ID>`

Get time-series stream data for an activity (heart rate, pace, altitude, power, cadence, etc.).

```bash
fitops activities streams 12345678901 [--fresh]
```

Streams are fetched from Strava on first request and cached locally. Use `--fresh` to force a re-fetch.

**Output shape:**

```json
{
  "_meta": { ... },
  "activity_strava_id": 12345678901,
  "streams": {
    "heartrate": { "data_length": 3600, "data": [142, 145, 148, ...] },
    "velocity_smooth": { "data_length": 3600, "data": [3.1, 3.2, ...] },
    "altitude": { "data_length": 3600, "data": [120.5, 121.0, ...] }
  }
}
```

---

### `fitops activities laps <ID>`

Get lap splits for an activity.

```bash
fitops activities laps 12345678901 [--fresh]
```

**Output shape:**

```json
{
  "_meta": { "total_count": 4 },
  "activity_strava_id": 12345678901,
  "laps": [
    {
      "lap_index": 1,
      "name": "Lap 1",
      "duration": { "moving_time_seconds": 360, "moving_time_formatted": "6:00" },
      "distance": { "meters": 1000.0, "km": 1.0 },
      "average_speed_ms": 2.78,
      "heart_rate": { "average_bpm": 158.0, "max_bpm": 172 },
      "average_watts": null
    }
  ]
}
```

## Sport Type Values

Common Strava sport types: `Run`, `TrailRun`, `Ride`, `VirtualRide`, `Swim`, `Walk`, `Hike`, `WeightTraining`, `Yoga`, `Workout`

## See Also

- [Output Examples → Activities](../output-examples/activities.md) — full response samples
- [`fitops sync run`](./sync.md) — fetch activities from Strava

← [Commands Reference](./README.md)
