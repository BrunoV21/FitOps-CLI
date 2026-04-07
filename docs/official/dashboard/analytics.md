# Dashboard — Analytics

The Analytics page (`/analytics`) lets you explore your training load over time and dig into performance metrics — all visually, without running CLI commands.

## Training Load Chart

A time-series chart showing three lines across your training history:

- **CTL** (Chronic Training Load) — your fitness base, built up over weeks
- **ATL** (Acute Training Load) — recent fatigue from the past 7–10 days
- **TSB** (Training Stress Balance) — how fresh or fatigued you are on any given day

Hover over any point on the chart to see the exact values for that date.

**Controls:**

- **Days** — how many days of history to display (default: 90)
- **Sport view** — Run / Cycle / Total (same filter as the Overview)

Use this chart to understand the shape of your training blocks — a widening gap between CTL and ATL after a hard week, a recovery period where TSB climbs back positive, or a fitness plateau when CTL has stopped rising.

## Performance Metrics

Below the training load chart, a set of derived numbers based on your recent activity history:

**For runners:**

| Metric | What it means |
|--------|--------------|
| Running economy | Estimated oxygen cost per km (proxy from average pace) |
| Pace efficiency | 0–100 score based on how consistent your paces are across recent runs |
| Aerobic threshold HR | Estimated HR at the boundary of Zone 2 |
| Anaerobic threshold HR | Estimated HR at the boundary of Zone 4/5 |

**For cyclists:**

| Metric | What it means |
|--------|--------------|
| FTP estimate | Functional Threshold Power estimated from recent ride data |
| Power-to-weight | FTP / body weight (W/kg) |
| Normalized power ratio | Average NP/AP ratio — an indicator of ride pacing variability |
| Power consistency | 0–100 score based on power distribution across recent rides |

**Time range:** use the **Days** slider to change how many days of activities feed into these calculations.

## See Also

- [Overview](./overview.md) — today's CTL/ATL/TSB snapshot
- [Concepts → Training Load](../concepts/training-load.md)
- [Concepts → VO2max](../concepts/vo2max.md)
- [Concepts → Zones](../concepts/zones.md)
- [`fitops analytics`](../commands/analytics.md) — CLI equivalent

← [Dashboard Overview](./index.md)
