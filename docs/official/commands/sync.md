# fitops sync

Sync activities from Strava into the local database.

Sync commands print a progress summary by default. Add `--json` for structured output.

## Commands

### `fitops sync run`

Fetch new and updated activities from Strava.

```bash
fitops sync run [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--full` | false | Full historical sync from the beginning |
| `--after DATE` | — | Sync activities after this date (YYYY-MM-DD) |
| `--streams` | false | Also fetch streams for newly synced activities |
| `--force-streams` | false | Re-fetch streams for all activities (slow — ~1 req/sec) |

**Examples:**

```bash
# Incremental sync (fetch only new activities)
fitops sync run

# Full historical sync (first-time setup)
fitops sync run --full

# Sync from a specific date
fitops sync run --after 2025-01-01

# Sync and immediately fetch streams for new activities
fitops sync run --streams
```

**Output:**

```json
{
  "sync_type": "incremental",
  "activities_created": 5,
  "activities_updated": 1,
  "pages_fetched": 1,
  "duration_s": 2.41,
  "synced_at": "2026-03-11T09:15:00+00:00"
}
```

When `--streams` is used and new activities are created, the output also includes a `streams` block and a `weather` block (weather is auto-fetched for activities with GPS):

```json
{
  "sync_type": "incremental",
  "activities_created": 3,
  "activities_updated": 0,
  "pages_fetched": 1,
  "duration_s": 5.12,
  "synced_at": "2026-03-11T09:15:00+00:00",
  "streams": { "streams_fetched": 3, "errors": 0 },
  "weather": { "weather_fetched": 3, "weather_errors": 0 }
}
```

---

### `fitops sync streams`

Fetch and cache streams for activities that don't have them yet.

```bash
fitops sync streams [OPTIONS]
```

Use this to backfill streams for activities synced before streams were fetched, or to populate streams needed for zone inference, HR drift analysis, and power curves.

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | 0 (all) | Max number of activities to fetch streams for |
| `--force` | false | Re-fetch streams even for activities that already have them |

**Examples:**

```bash
# Backfill streams for all activities that don't have them
fitops sync streams

# Backfill up to 50 most recent activities
fitops sync streams --limit 50

# Re-fetch streams for the 20 most recent activities (force refresh)
fitops sync streams --limit 20 --force
```

Rate-limited to approximately 1 request per second to stay within Strava's 100 requests/15 min limit. For large backlogs, expect roughly 1 minute per 60 activities.

---

### `fitops sync status`

Show sync history and totals.

```bash
fitops sync status
```

**Output:**

```json
{
  "last_sync_at": "2026-03-11T09:15:00+00:00",
  "activities_synced_total": 847,
  "recent_syncs": [
    {
      "synced_at": "2026-03-11T09:15:00+00:00",
      "sync_type": "incremental",
      "activities_created": 5,
      "activities_updated": 1
    }
  ]
}
```

## How Sync Works

- **Incremental:** fetches activities since `last_sync_at` minus a 3-day overlap window, to catch late uploads
- **Full:** fetches all activities from the beginning of your Strava history
- Activities are upserted — running sync twice is safe
- **Weather auto-fetch:** for each newly synced activity that has GPS coordinates, weather conditions are automatically fetched from Open-Meteo and stored. This enables WAP, True Pace, and heat factor calculations without any extra steps.

To backfill weather for older activities synced before weather support was added:

```bash
fitops weather fetch --all
```

## See Also

- [First Sync Guide](../getting-started/first-sync.md)
- [`fitops activities list`](./activities.md) — browse synced activities
- [`fitops weather`](./weather.md) — weather commands and backfill

← [Commands Reference](./index.md)
