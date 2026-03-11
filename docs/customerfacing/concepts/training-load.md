# Training Load — CTL, ATL, TSB

FitOps models your training using three metrics derived from daily Training Stress Score (TSS).

## The Three Numbers

| Metric | Name | Window | What it means |
|--------|------|--------|----------------|
| CTL | Chronic Training Load (Fitness) | 42-day EWMA | Long-term fitness built up over weeks |
| ATL | Acute Training Load (Fatigue) | 7-day EWMA | Short-term fatigue from recent training |
| TSB | Training Stress Balance (Form) | CTL − ATL | Readiness: positive = fresh, negative = fatigued |

## Formulas

Both CTL and ATL use an exponential weighted moving average (EWMA):

```
CTL_today = CTL_yesterday + α_ctl × (TSS_today − CTL_yesterday)
ATL_today = ATL_yesterday + α_atl × (TSS_today − ATL_yesterday)

α_ctl = 2 / (42 + 1) ≈ 0.0465
α_atl = 2 / (7 + 1)  = 0.25

TSB = CTL − ATL
```

On rest days, TSS = 0, so both values decay toward zero.

## TSS Calculation

TSS is estimated from activity duration and intensity:

- **Running:** based on average heart rate zone (z1–z5) if HR data is available, otherwise scaled by duration
- **Cycling:** power-based if watts are recorded; HR-based otherwise

Sport-specific multipliers are applied so that a hard run and a hard ride contribute comparably to load.

## Form Labels

FitOps interprets TSB with descriptive labels:

| TSB Range | Label |
|-----------|-------|
| ≥ 15 | Very fresh — possibly detrained |
| 0 to 15 | Fresh — optimal race readiness window |
| −10 to 0 | Productive — slight fatigue, good adaptation zone |
| −20 to −10 | Overreaching — high adaptation, monitor recovery |
| < −20 | Overtraining risk — reduce load |

## Ramp Rate

FitOps also computes the 7-day CTL ramp rate as a percentage change:

```
ramp_rate_pct = ((CTL_today − CTL_7_days_ago) / CTL_7_days_ago) × 100
```

A ramp rate above ~5–7% per week is generally considered a high injury risk for runners.

## Command

```bash
fitops analytics training-load
fitops analytics training-load --today     # current values only
fitops analytics training-load --days 42 --sport Run
```

See [Output Examples → Analytics](../output-examples/analytics.md) for the full JSON response.

← [Concepts](./README.md)
