# fitops sync

Sync activities from Strava into the local database.

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

**Examples:**

```bash
# Incremental sync (fetch only new activities)
fitops sync run

# Full historical sync (first-time setup)
fitops sync run --full

# Sync from a specific date
fitops sync run --after 2025-01-01
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

## See Also

- [First Sync Guide](../getting-started/first-sync.md)
- [`fitops activities list`](./activities.md) — browse synced activities

← [Commands Reference](./README.md)
