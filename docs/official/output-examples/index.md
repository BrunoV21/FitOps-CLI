# Output Examples

Sample output for every FitOps command group.

All examples show the **default rich terminal output** — formatted tables, labelled values, and plain-language summaries. This is what you see when you run a command at the terminal without any flags.

At the end of each page, there's a brief section showing the `--json` equivalent for scripting and agent use.

## What to Expect

FitOps output is designed to be readable at a glance. Here's a quick taste:

```bash
$ fitops analytics training-load --today
```
```
Training Load  2026-04-06
  CTL (Fitness)   42.2
  ATL (Fatigue)   54.0
  TSB (Form)      -11.8  [Overreaching — high adaptation, monitor recovery]
  7d Ramp Rate    +15.45%  [High risk — reduce load to prevent injury]
```

```bash
$ fitops activities list --sport Run --limit 3
```
```
  ID            Date        Sport   Dist      Duration  Pace/Speed  HR
 ──────────────────────────────────────────────────────────────────────
  17972016511   2026-04-04  Run     12.12 km  58:05     4:47/km     168
  17951234567   2026-04-02  Run     8.50 km   40:10     4:43/km     162
  17930987654   2026-03-30  Run     15.00 km  1:14:30   4:58/km     155
```

## Sections

| Section | Commands Covered |
|---------|-----------------|
| [Activities](./activities.md) | `activities list`, `activities get`, `activities streams` |
| [Athlete](./athlete.md) | `athlete profile`, `athlete stats`, `athlete zones`, `athlete equipment` |
| [Analytics](./analytics.md) | `analytics training-load`, `analytics vo2max`, `analytics zones`, `analytics trends`, `analytics performance`, `analytics power-curve`, `analytics pace-zones`, `analytics snapshot` |
| [Workouts](./workouts.md) | `workouts list`, `workouts link`, `workouts compliance`, `workouts get`, `workouts history` |
| [Weather](./weather.md) | `weather fetch`, `weather show`, `weather forecast` |

## JSON Mode (`--json`)

Add `--json` to any command for raw JSON output — useful for scripting or piping to an AI agent. Every `--json` response includes a `_meta` block:

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

← [Back to Docs Home](../index.md)
