# VO2max Estimation

FitOps estimates VO2max from your run performance data using a weighted composite of three established formulas.

## Why Three Formulas?

Each formula was derived from a different population and methodology. A weighted composite is more robust than any single estimate.

| Formula | Weight | Basis |
|---------|--------|-------|
| VDOT (Daniels) | 50% | Pace-based; widely used in competitive running |
| McArdle | 30% | Distance + time on a fixed protocol |
| Costill | 20–40% | Speed-based field estimate |

The final estimate is a weighted average, and the spread between individual estimates determines a **confidence level**.

## Confidence Score

| Label | Meaning |
|-------|---------|
| High | All three methods agree closely |
| Medium | Two methods agree; one is an outlier |
| Low | Estimates vary widely — more data needed |

## What Counts as a Qualifying Activity?

- Sport type: `Run` or `TrailRun`
- Distance: at least 1500m
- The most recent qualifying activity is used as the primary estimate source

## Limitations

- VO2max is a physiological measurement. This is an estimate from field performance — not a lab value.
- Heat, altitude, fatigue, and pacing strategy all affect the estimate.
- For best accuracy, use a recent race or time trial where you ran close to maximal effort.

---

## Age Adjustment

VO2max naturally declines with age. The `--age-adjusted` flag applies a correction factor to account for this.

```bash
fitops analytics vo2max --age-adjusted
```

### Methodology

The adjustment uses a linear decline model anchored at age 25:

```
age_factor = max(0.5, 1.0 − (age − 25) × 0.008)
adjusted_estimate = raw_estimate × age_factor
```

Key properties:
- At age 25, the factor is exactly 1.0 (no adjustment)
- Each year above 25 reduces the factor by 0.8%
- The factor is floored at 0.5 to avoid unrealistic values for very old ages
- Athletes younger than 25 receive a factor above 1.0 (reflects higher typical VO2max in youth)

### Example

| Age | Factor | Raw 50.0 → Adjusted |
|-----|--------|---------------------|
| 20 | 1.040 | 52.0 |
| 25 | 1.000 | 50.0 |
| 35 | 0.920 | 46.0 |
| 45 | 0.840 | 42.0 |
| 60 | 0.720 | 36.0 |

### Requirement

Age adjustment requires the athlete's birthday to be stored in the local database. Strava includes birthday in the athlete profile, so running `fitops sync run` once should populate it automatically.

If the birthday is not available, the output includes an error message in the `age_adjusted` field and the raw estimate is still returned.

---

## Command

```bash
fitops analytics vo2max
fitops analytics vo2max --activities 20    # consider more recent runs
fitops analytics vo2max --age-adjusted     # include age-adjusted estimate
```

See [Output Examples → Analytics](../output-examples/analytics.md) for the VO2max JSON response.

← [Concepts](./README.md)
