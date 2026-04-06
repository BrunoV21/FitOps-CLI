# Output Examples

Sample JSON responses for every command group.

## Sections

| Section | Commands Covered |
|---------|-----------------|
| [Activities](./activities.md) | `activities list`, `activities get`, `activities streams`, `activities laps` |
| [Athlete](./athlete.md) | `athlete profile`, `athlete stats`, `athlete zones`, `athlete equipment` |
| [Analytics](./analytics.md) | `analytics training-load`, `analytics vo2max`, `analytics zones`, `analytics trends`, `analytics performance`, `analytics power-curve`, `analytics pace-zones`, `analytics snapshot` |
| [Workouts](./workouts.md) | `workouts list`, `workouts link`, `workouts compliance`, `workouts get`, `workouts history` |

## General Shape

Every response has a `_meta` block at the top:

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "total_count": 20,
    "filters_applied": { "sport_type": "Run", "limit": 20 }
  },
  "<data_key>": { ... }
}
```

Errors are returned as:

```json
{ "error": "No qualifying run activities found. Need at least 1500m run." }
```

← [Back to Docs Home](../README.md)
