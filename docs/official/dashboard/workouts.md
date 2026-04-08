# Dashboard — Workouts

The Workouts page (`/workouts`) is where you build structured training sessions, simulate how they'd play out on a real course, and review your workout history with compliance scores.

## Workout Library

The main workouts list shows every workout you've created. Each entry displays:

- Workout name and sport type
- Target duration
- Tags (e.g. `threshold`, `long run`, `recovery`)
- A link to the detail view

Click a workout to open its full detail — the structured segments, any linked Strava activities, and the compliance breakdown.

## Creating a Workout

Hit **New Workout** to open the workout editor. Fill in:

- **Name** — a short label for the session
- **Sport** — Run, Ride, etc.
- **Target duration** — total planned time in minutes
- **Tags** — comma-separated labels for grouping
- **Description / structure** — written in Markdown, using the same segment format as the CLI:

```markdown
## Warmup
10 min easy (Z1–Z2)

## Main Set
4 × 8 min @ Z4
2 min Z1 recovery jog between reps

## Cooldown
8 min easy Z1
```

Named `##` sections become scoreable segments — FitOps can compare them against your HR data when you link an activity.

## Simulate a Workout

The **Simulate** button on any workout (or the standalone Simulate tool) lets you preview a session before you do it. You pick a course, set your current fitness metrics, and FitOps projects:

- Projected total time and pace per segment
- Expected HR in each zone
- Effort distribution across the session
- Weather-adjusted targets if forecast data is available

This is useful for deciding whether a planned session is realistic on a given day.

## Workout Detail & Compliance

Once you link a workout to a Strava activity (via `fitops workouts link`), the detail view shows:

- A physiology snapshot at the time of the session (CTL, ATL, TSB, VO2max)
- Per-segment compliance scores — how closely your actual HR matched the zone targets
- A summary compliance grade for the whole session

## See Also

- [Concepts → Workouts & Compliance](../concepts/workouts.md)
- [`fitops workouts`](../commands/workouts.md) — CLI reference for creating and linking workouts

← [Dashboard Overview](./index.md)
