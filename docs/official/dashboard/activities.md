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

**Official Race Result panel** (running race activities only):
- Recorded GPS distance and recorded race time
- Official race distance and chip time fields you can edit locally
- Corrected average pace plus the calibration factors used to rescale the splits

When you save an official race result, the activity detail page switches its split table to the corrected version. This is useful for road races where the watch recorded `9.82 km` but the official course was `10.00 km`.

**Stamp controls** update the Strava activity description with the same FitOps footer used by the Profile page backfill tool. When a cached training-load snapshot exists for the activity date, the stamp includes that day's CTL, ATL, TSB, and form label. Linked workout segments show true pace whenever segment true pace data exists, including when it displays the same value as raw segment pace. The activity page does not recompute training load while stamping; missing snapshots simply omit the form section.

**Insights panel** (when streams are available):
- **HR Drift** — cardiac decoupling percentage. < 5% means your aerobic system held steady; > 10% means you were pushing near your ceiling.
- **Aerobic training score** — estimated aerobic stimulus for the session
- **Anaerobic training score** — estimated anaerobic contribution

**Running Power panel** (runs only, when streams are available):
- **Avg Power** — average estimated running power in watts
- **Max Power** — peak estimated wattage during the session
- **Normalised Power** — intensity-weighted average (equivalent to NP for cycling)
- **Est. kcal** — energy expenditure estimated from the power model
- Source label confirms the value is model-derived (not a Stryd or footpod)

Power is computed at sync time and cached; the page never recomputes it on load. See [Estimated Running Power](/concepts/estimated-power) for the formula and accuracy notes.

**Charts** (when streams are available):
- Heart rate over time
- Pace over time (with grade-adjusted pace overlay if GPS data is present)
- Elevation profile
- Power (hidden by default — click the **Pwr** toggle to show the wattage series)

On mobile, the stream chart includes a scrubber below the plot so you can move through the activity without accidentally starting a zoom selection. When the chart is zoomed, the scrubber is constrained to that selected time or distance range, so horizontal movement stays inside the visible section. Expanding the stream chart fullscreen keeps the normal multi-stream chart layout and places the stream toggles in a compact row above the plot. Use the toggles to show or hide heart rate, pace, GAP, WAP, True Pace, altitude, cadence, or power without losing the wider fullscreen chart area.

On desktop, drag across the stream chart or click two positions to zoom into a specific time or distance range. On mobile, drag across the chart to zoom; a simple tap or scrub only moves the hover position. The visible y-axes rescale to the selected section, and **Reset Zoom** or a double-click restores the full activity.

The **Deep Analysis** view uses the same range selection feel across its stacked charts. Drag or click two points to inspect a range; the highlight follows the pointer after the first click, and double-click clears the selected range.

The Deep Analysis sidebar also shows paired average stats for the session, including available values such as average heart rate, average pace or speed, True Pace, GAP, WAP, cadence, power, normalized power, elevation, and TSS. Overall True Pace and WAP use the same activity-level values shown on the main activity page.

![Activity Analysis — streams, HR drift, scatter plots](../assets/dashboard-activity-analysis.png)

If streams are not yet cached for an activity, a **Fetch Streams** button appears. Click it to pull the full time-series data from Strava — this enables the charts, HR drift analysis, and zone-time breakdowns.

When a workout is linked to the activity, the workout segment table includes **In Target** and **Score** help icons. **In Target** is the share of valid samples inside the segment's target zone or pace/HR range. **Score** is the compliance score, combining time in target with the average deviation from target.

## See Also

- [Overview](./overview.md) — the 10 most recent activities also appear on the dashboard home
- [`fitops activities`](../commands/activities.md) — the CLI equivalent
- [Output Examples → Activities](../output-examples/activities.md)

← [Dashboard Overview](./index.md)
