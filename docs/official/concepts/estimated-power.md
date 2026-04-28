# Estimated Running Power

FitOps estimates running power from pace streams using a calibrated proxy model. The estimate is computed once on the first `activity get` or dashboard detail view, then persisted to the DB so subsequent reads are instant.

## Formula

```text
Power (W) = Cdisplay × mass_kg × velocity (m/s)
```

Where `Cdisplay = 1.0 J/(kg·m)` is a calibrated displayed-power constant chosen to keep values in a realistic Garmin/Stryd-like running power range. Grade and wind effects are captured implicitly when the **true pace** stream is available.

## Pace stream priority

FitOps selects the best available pace source:

1. **`true_pace`** — grade- and wind-adjusted pace (most accurate)
2. **`gap_pace`** — grade-adjusted pace from Strava
3. **`velocity_smooth`** — raw GPS speed (fallback)

The `source` field in the `power` output block indicates which stream was used.

## Normalized Power (NP)

NP is computed as the fourth-root mean of a 30-second rolling window of `P^4`. It better represents the physiological cost of variable-intensity efforts than average power.

```
NP = ( mean( rolling_30s( P^4 ) ) )^(1/4)
```

## Calorie estimation

```text
kcal = Σ (metabolic_power × Δt) / 4184
```

Displayed watts are calibrated for user-facing running power. Calorie estimation uses a higher metabolic-cost model internally, so `est_kcal` remains closer to actual running energy expenditure than a direct conversion from the displayed watts would be.

## Output fields

| Field | Description |
|-------|-------------|
| `avg_w` | Average estimated power (W), rounded |
| `max_w` | Peak estimated power (W), rounded |
| `np_w` | Normalized power (W), rounded |
| `est_kcal` | Mechanical energy estimate (kcal) |
| `source` | Pace stream used: `true_pace`, `gap_pace`, or `velocity_smooth` |

## Example

```json
"power": {
  "avg_w": 248,
  "max_w": 412,
  "np_w": 255,
  "est_kcal": 830,
  "source": "true_pace"
}
```

## Limitations

- Requires body weight configured in athlete settings (`fitops athlete set weight_kg <value>`).
- Calibrated proxy, not device-native power. It is intended to land in realistic consumer running-power ranges, not to reproduce Garmin or Stryd exactly.
- No wind correction unless weather was fetched for the activity.
- Not comparable to cycling power (different efficiency and Cr constants).
