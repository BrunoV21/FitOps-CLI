# Dashboard — Profile

The Profile page (`/profile`) is where you configure your physiology. Set your threshold values once, and every analytics calculation across the dashboard and CLI will use them automatically.

## Athlete Info

At the top of the page, your Strava profile data is shown: name, location, profile photo, and body weight (if synced). Body weight is used for power-to-weight calculations in cycling analytics.

## Physiology Settings

The settings panel covers:

| Setting | What it's used for |
|---------|--------------------|
| **LTHR** (Lactate Threshold HR) | HR zone calculation, effort labelling, LT2 inference |
| **Max HR** | Zone calculation (max HR method), VO2max estimate |
| **Resting HR** | Zone calculation (HRR method) |
| **Threshold pace** | Pace zone boundaries for running |
| **LT1 override** | Manually set the aerobic threshold display value |
| **LT2 override** | Manually set the lactate threshold display value |

Fill in what you know and leave the rest blank. FitOps uses whichever values are available for each calculation.

## HR Zone Display

After saving physiology settings, your HR zones are displayed as a table — zone number, name, BPM range, and the method used to calculate them (LTHR, max HR, or HRR). The method is chosen automatically based on which values you've set.

## Pace Zone Display

If you've set a threshold pace, the running pace zones are shown below the HR zones — five zones from Easy to VO2max, with the pace range for each.

## VO2max

Your current VO2max estimate is shown on the profile page. You can:

- **Recalculate** — trigger a fresh estimate from your recent activity data
- **Set a manual override** — enter a known value from a lab test
- **Clear the override** — go back to the computed estimate

## Equipment

If you've synced gear from Strava (bikes, shoes), it appears here with cumulative usage.

## See Also

- [Concepts → HR Zones](../concepts/zones.md)
- [Concepts → VO2max](../concepts/vo2max.md)
- [`fitops analytics zones`](../commands/analytics.md#fitops-analytics-zones) — CLI equivalent for zone setup
- [`fitops analytics vo2max`](../commands/analytics.md#fitops-analytics-vo2max) — CLI equivalent for VO2max

← [Dashboard Overview](./index.md)
