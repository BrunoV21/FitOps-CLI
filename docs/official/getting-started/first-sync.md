# First Sync

After [authenticating](./authentication.md), pull your activities from Strava.

## Run an Incremental Sync

```bash
fitops sync run
```

This fetches all activities not yet stored locally. Progress is printed as it runs:

```
Starting incremental sync...
Sync complete
  Type       incremental
  Created    142 activities
  Updated    3 activities
  Pages      8
  Duration   14.23s
  Synced at  2026-03-11T09:15:00
```

## Full Historical Sync

On first use, sync your entire Strava history:

```bash
fitops sync run --full
```

This can take a minute or two depending on how many activities you have.

## Sync from a Specific Date

```bash
fitops sync run --after 2025-01-01
```

## Check Sync Status

```bash
fitops sync status
```

## What Gets Stored

Each sync upserts your athlete profile and all activities into `~/.fitops/fitops.db`. Streams (heart rate, pace, power) and laps are fetched on demand when you request them.

## Next Steps

- [`fitops activities list`](../commands/activities.md) — Browse your synced activities
- [`fitops analytics training-load`](../commands/analytics.md) — See your fitness trend
- [`fitops athlete profile`](../commands/athlete.md) — View your profile and gear

← [← Authentication](./authentication.md) | [Commands Reference →](../commands/)
