# Dashboard — Analytics

The Analytics page (`/analytics`) lets you explore your training load over time and dig into performance metrics — all visually, without running CLI commands.

## Training Load Chart

A time-series chart showing three lines across your training history:

- **CTL** (Chronic Training Load) — your fitness base, built up over weeks
- **ATL** (Acute Training Load) — recent fatigue from the past 7–10 days
- **TSB** (Training Stress Balance) — how fresh or fatigued you are on any given day

Hover over any point on the chart to see the exact values for that date. On mobile, the chart panels can be expanded fullscreen and are sized to the available browser viewport so the full plot remains visible after entering or exiting fullscreen.

![Training Load Chart](../assets/dashboard-training-load-detailed.png)

**Controls:**

- **Days** — how many days of history to display (default: 90)
- **Sport view** — Run / Cycle / Total (same filter as the Overview)

Use this chart to understand the shape of your training blocks — a widening gap between CTL and ATL after a hard week, a recovery period where TSB climbs back positive, or a fitness plateau when CTL has stopped rising.

## Performance Metrics

The Performance page (`/analytics/performance`) surfaces derived numbers from your last 50 activities and now lets you switch between Run and Ride views. It also shows your current load snapshot, a trend summary, and a direct link back to Profile so the page reads like a full training context, not just a metric dump.

**Controls:**

- **Days** - how many days of history to analyse
- **Sport** - Run or Ride

The top row on the page brings together:

- **Current Load** - CTL, ATL, TSB, and form label from the cached training load snapshot
- **Trend Snapshot** - a short summary of recent volume and pace/HR direction
- **Profile Link** - a reminder that VO₂max override, LTHR, threshold pace, and zones all live in Profile

The VO₂max and pace threshold charts use the same fullscreen behavior as Training Load, including mobile viewport-aware sizing.

### Running Efficiency panel

| Metric | What it means |
|--------|--------------|
| Running economy | Estimated O₂ cost per km (ml/kg/km) from Daniels VO₂ demand model — lower = more efficient |
| Pace efficiency | 0–100 score based on pace consistency across recent runs (100 − CV×100) |
| Pace variability | Coefficient of variation of paces — lower means more even training |
| Reliability | Pace efficiency expressed as a 0–1 fraction |

### Aerobic Efficiency Trend (within Running Intensity Thresholds panel)

| Metric | How it's derived |
|--------|-----------------|
| Aerobic efficiency trend | Change in speed per heartbeat between the early and recent halves of the selected run window |
| HR at benchmark pace | Estimated recent heart rate at the current benchmark pace |
| Baseline at same pace | Estimated early-window heart rate at that same benchmark pace |

This sits alongside the pace-based LT1/LT2/vVO₂max thresholds so you can see whether the same run pace now costs fewer heartbeats. A lower recent HR at the benchmark pace suggests improving aerobic durability.

### Cycling metrics

Ride view uses the same command and dashboard logic as the run view, but shows cycling-specific metrics instead of running economy and HR thresholds:

| Metric | What it means |
|--------|--------------|
| FTP estimate | Functional Threshold Power estimated from recent ride data |
| Power-to-weight | FTP / body weight (W/kg) |
| Normalized power ratio | Average NP/AP ratio — an indicator of ride pacing variability |
| Power consistency | 0–100 score based on power distribution across recent rides |

## See Also

- [Overview](./overview.md) — today's CTL/ATL/TSB snapshot
- [Concepts → Training Load](../concepts/training-load.md)
- [Concepts → VO2max](../concepts/vo2max.md)
- [Concepts → Zones](../concepts/zones.md)
- [`fitops analytics`](../commands/analytics.md) — CLI equivalent

← [Dashboard Overview](./index.md)
