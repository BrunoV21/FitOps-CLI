# Dashboard — Activities

The Activities page (`/activities`) is your full training history in one place. Browse every synced session, filter down to what you care about, and spot patterns across your log.

## The Activity List

Every synced activity appears in a table, newest first. For each session you can see:

- **Sport** — shown as an icon (runner, bike, wave, etc.) plus the type name
- **Name** — the activity title from Strava
- **Date** — local start date
- **Distance** — in kilometres
- **Duration** — moving time
- **Pace / Speed** — min/km for running sports, km/h for cycling and others
- **Avg HR** — average heart rate in bpm
- **TSS** — Training Stress Score

Click an activity name to open it directly on Strava.

## Filtering & Search

Use the filter bar to focus the list:

- **Search** — free-text match on activity name (case-insensitive substring)
- **Sport type** — pick a specific activity type (Run, Ride, Walk, Swim, …)
- **Tag** — filter to activities flagged as Race, Trainer, Commute, Manual, or Private
- **After / Before** — date range pickers (YYYY-MM-DD) to zoom into a period
- **Per page** — 25 / 50 / 100 / 200 / 500 results

All filters stack and carry across pagination pages. Hit **Reset** to clear everything.

## Activity Detail

Click any activity row to open its detail page (`/activities/{id}`). The detail view shows everything FitOps knows about a single session:

**Summary panel:**
- Sport type, date, name
- Distance, duration, pace or speed
- Elevation gain
- Heart rate (average + max)
- Calories and gear

**Insights panel** (when streams are available):
- **HR Drift** — cardiac decoupling percentage. < 5% means your aerobic system held steady; > 10% means you were pushing near your ceiling.
- **Aerobic training score** — estimated aerobic stimulus for the session
- **Anaerobic training score** — estimated anaerobic contribution

**Charts** (when streams are available):
- Heart rate over time
- Pace over time (with grade-adjusted pace overlay if GPS data is present)
- Elevation profile

![Activity Analysis — streams, HR drift, scatter plots](../assets/dashboard-activity-analysis.png)

If streams are not yet cached for an activity, a **Fetch Streams** button appears. Click it to pull the full time-series data from Strava — this enables the charts, HR drift analysis, and zone-time breakdowns.

## See Also

- [Overview](./overview.md) — the 10 most recent activities also appear on the dashboard home
- [`fitops activities`](../commands/activities.md) — the CLI equivalent
- [Output Examples → Activities](../output-examples/activities.md)

← [Dashboard Overview](./index.md)
