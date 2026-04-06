# fitops activities

Browse and query synced activities.

Output is a formatted table by default. Add `--json` to any command for raw JSON output (useful for scripting or AI agents).

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
| `--json` | false | Output raw JSON instead of the formatted table |

**Examples:**

```bash
fitops activities list
fitops activities list --sport Run --limit 10
fitops activities list --after 2026-01-01
fitops activities list --sport Ride --limit 5 --after 2025-12-01
fitops activities list --sport Run --json          # JSON for scripting or agents
```

See [Output Examples → Activities](../output-examples/activities.md) for sample output.

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
| `--json` | Output raw JSON instead of the formatted summary |

---

### `fitops activities streams <ID>`

Get time-series stream data for an activity (heart rate, pace, altitude, power, cadence, etc.).

```bash
fitops activities streams 12345678901 [--fresh]
```

Streams are fetched from Strava on first request and cached locally. Use `--fresh` to force a re-fetch.

**Output:**

```
Streams for activity 17972016511

  altitude              3492 data points
  heartrate             3492 data points
  cadence               3492 data points
  velocity_smooth       3492 data points
  distance              3492 data points
```

Use `--json` to get the raw data arrays for scripting or analysis.

---

## Sport Type Values

Common Strava sport types: `Run`, `TrailRun`, `Ride`, `VirtualRide`, `Swim`, `Walk`, `Hike`, `WeightTraining`, `Yoga`, `Workout`

## See Also

- [Output Examples → Activities](../output-examples/activities.md) — sample output
- [`fitops sync run`](./sync.md) — fetch activities from Strava

← [Commands Reference](./index.md)
