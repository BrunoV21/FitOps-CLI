# Commands Reference

Complete reference for all FitOps-CLI commands.

## Command Groups

| Group | Description |
|-------|-------------|
| [`auth`](./auth.md) | Strava authentication |
| [`sync`](./sync.md) | Sync activities from Strava |
| [`activities`](./activities.md) | Browse and query activities |
| [`athlete`](./athlete.md) | Athlete profile, stats, and zones |
| [`analytics`](./analytics.md) | Training load, VO2max, HR zones, pace zones, trends, performance, power curves |
| [`weather`](./weather.md) | Fetch, store, and inspect activity weather; race-day forecast; WAP factors |
| [`workouts`](./workouts.md) | Markdown workout definitions, activity linking, segment compliance |

## Global Behavior

All commands output JSON to stdout. Errors go to stderr with a non-zero exit code.

```bash
fitops <group> --help     # Show help for any command group
fitops <group> <cmd> --help  # Show help for a specific command
```

## Output Format

Every response includes a `_meta` object:

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "total_count": 20,
    "filters_applied": { "sport_type": "Run", "limit": 20 }
  }
}
```

See [Output Examples](../output-examples/README.md) for full response shapes.

← [Back to Docs Home](../README.md)
