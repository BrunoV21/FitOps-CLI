# Commands Reference

Every FitOps feature is a CLI command. This is the complete reference.

FitOps commands are grouped by function. Each group covers a distinct part of your training data — syncing it, querying it, analysing it, or planning against it.

## Command Groups

| Group | What it does |
|-------|-------------|
| [`auth`](./auth.md) | Connect and manage your Strava account via OAuth |
| [`sync`](./sync.md) | Pull activities and time-series streams from Strava to your local DB |
| [`activities`](./activities.md) | Browse, filter, and inspect synced activities |
| [`athlete`](./athlete.md) | Athlete profile, cumulative stats, equipment, and Strava zones |
| [`analytics`](./analytics.md) | Training load (CTL/ATL/TSB), VO2max, HR zones, pace zones, trends, performance, power curves |
| [`weather`](./weather.md) | Fetch historical weather per activity, compute WAP factors, get race-day forecasts |
| [`workouts`](./workouts.md) | Define structured workouts in Markdown, link them to activities, score HR compliance per segment, simulate on a course |
| [`race`](./race.md) | Import GPX/TCX courses, generate per-km pacing plans with elevation and weather, simulate pacer strategy |
| [`notes`](./notes.md) | Markdown training journal — create, tag, link to activities, and query across sessions |
| [`backup`](./backup.md) | Back up your entire FitOps data directory to GitHub and restore it on any machine |
| [`dashboard`](../dashboard/) | Launch the local web dashboard |

## Getting Around

```bash
fitops --help                    # all command groups
fitops <group> --help            # commands in a group
fitops <group> <cmd> --help      # options for a specific command
```

## Output — Rich by Default

Commands print **rich, readable output by default** — formatted tables, plain-language summaries, and labelled values. This is what you see at the terminal day-to-day.

```bash
fitops activities list
```

```
  ID            Date        Sport   Dist      Duration  Pace/Speed  HR
 ──────────────────────────────────────────────────────────────────────
  17972016511   2026-04-04  Run     12.12 km  58:05     4:47/km     168
  17951234567   2026-04-02  Run     8.50 km   40:10     4:43/km     162
```

Add `--json` to get raw JSON for scripting or piping to an AI agent:

```bash
fitops activities list --json
```

| Mode | How | When to use |
|------|-----|-------------|
| Rich (default) | Formatted table / summary | Day-to-day use, terminal browsing |
| JSON | `--json` flag | Scripting, piping to AI agents, automation |

Errors are printed to stderr with a non-zero exit code.

## Typical Workflows

**Check your fitness right now:**
```bash
fitops analytics training-load --today
fitops analytics snapshot
```

**Explore a specific run:**
```bash
fitops activities list --sport Run --limit 10
fitops activities get 17972016511
```

**Configure zones and analytics:**
```bash
fitops analytics zones --infer           # detect from your HR stream data
fitops analytics vo2max                  # estimate from recent hard efforts
```

**Plan for a race:**
```bash
fitops race import berlin.gpx --name "Berlin Marathon 2026"
fitops race simulate 1 --target-time 3:15:00 --date 2026-09-29 --hour 9
```

**Open the visual dashboard:**
```bash
fitops dashboard serve                   # → http://localhost:8888
```

See [Output Examples](../output-examples/) for sample output from every command group.

← [Back to Docs Home](../index.md)
