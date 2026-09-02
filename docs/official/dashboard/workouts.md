# Dashboard — Workouts

The Workouts page (`/workouts`) is where you build structured training sessions, simulate how they'd play out on a real course, and review your workout history with compliance scores.

## Workout Library

The Workouts page starts with a summary dashboard for the selected period and sport. It shows:

- Completed workout sessions
- Number of different workouts completed
- Average compliance from stored scores
- Total workout time and distance
- Scored coverage, so you can see how many sessions have compliance data
- Segment in-target rate from stored segment scores
- Most repeated workout, best compliance workout, and latest completed workout

Use the period tabs (`This Week`, `This Month`, `This Year`, `All Time`) and sport tabs (`Run`, `Cycle`, `Total`) to change the dashboard. The cards use saved workout links, saved segment compliance, and activity summary rows; the page does not rescore workouts or fetch streams while rendering.

Below the dashboard, the main workouts list shows every workout you've created. Each entry displays:

- Workout name and sport type
- Last linked date
- Number of linked sessions
- Average stored compliance score
- Stored segment count

Click a workout to open its full detail — the structured segments, any linked Strava activities, and the compliance breakdown.

## Creating & Managing Workouts

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

Open any workout detail page to manage it:

- **Edit** opens the visual workout builder, pre-filled from the saved definition, with compact section navigation for basic info, warmup, intervals, cooldown, and preview. You can update the structure without editing JSON by hand.
- **Delete** removes the workout definition, its workout-activity links, stored segment scores, and the markdown file from `~/.fitops/workouts/`.

Saving an edit clears cached segment compliance for that workout, because the stored segment slices may no longer match the new definition. Re-score linked activities when you want fresh compliance analytics.

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
- Workout analytics for the selected workout: period TSS, share of training load, estimated CTL/ATL contribution, compliance-weighted TSS, and true pace change across executions
- A contribution trend chart with stored TSS, compliance, and true pace per linked execution
- Per-segment compliance scores — how closely your actual HR matched the zone targets
- A summary compliance grade for the whole session
- Linked activity rows with cached TSS, aerobic score, anaerobic score, weather, and compliance

The **In Target** and **Score** column headers include help icons. **In Target** is the percentage of valid segment samples inside the target zone or pace/HR range. **Score** is the compliance score, which weights in-target time and average deviation from the target.

The contribution analytics use saved `activities.training_stress_score`, `activity_weather.true_pace_s_per_km`, `workout_activity_links`, and `workout_segments` rows. The page does not fetch streams, compute true pace, rescore compliance, or estimate missing TSS while rendering. If older linked activities are missing cached TSS or true pace, the chart and cards show coverage so you can tell how complete the attribution is.

## See Also

- [Concepts → Workouts & Compliance](../concepts/workouts.md)
- [`fitops workouts`](../commands/workouts.md) — CLI reference for creating and linking workouts

← [Dashboard Overview](./index.md)
