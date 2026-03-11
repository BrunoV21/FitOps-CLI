# Heart Rate Zones

FitOps computes a 5-zone HR model using one of three methods, depending on what physiology data you've provided.

## Zone Methods

### LTHR (Lactate Threshold Heart Rate)

Best method if you know your lactate threshold HR from a field test or lab.

Zones are set as percentages of LTHR:

| Zone | Name | % of LTHR | Purpose |
|------|------|-----------|---------|
| Z1 | Recovery | < 85% | Active recovery |
| Z2 | Aerobic | 85–89% | Base building, long runs |
| Z3 | Tempo | 90–94% | Comfortably hard, marathon pace |
| Z4 | Threshold | 95–99% | Lactate threshold work |
| Z5 | VO2max | ≥ 100% | High-intensity intervals |

Set your LTHR:
```bash
fitops analytics zones --set-lthr 165
```

---

### Max HR

Uses maximum heart rate to derive zones as fixed percentages.

| Zone | % of Max HR |
|------|-------------|
| Z1 | < 60% |
| Z2 | 60–70% |
| Z3 | 70–80% |
| Z4 | 80–90% |
| Z5 | > 90% |

Set your max HR:
```bash
fitops analytics zones --set-max-hr 192
```

---

### HRR (Heart Rate Reserve / Karvonen)

Uses the reserve between resting and max HR. More personalized than max-HR-only.

```
HR_reserve = max_hr − resting_hr
Zone_N = resting_hr + (intensity_% × HR_reserve)
```

Requires both max HR and resting HR:
```bash
fitops analytics zones --set-max-hr 192 --set-resting-hr 48
```

## Method Auto-Selection

If you don't specify `--method`, FitOps picks the best available method in priority order:

1. `lthr` — if LTHR is set
2. `hrr` — if both max_hr and resting_hr are set
3. `max-hr` — if only max_hr is set
4. Error — if no parameters are configured

---

## Zone Inference

If you don't have HR values from a lab test, FitOps can infer them from your cached activity streams.

```bash
fitops analytics zones --infer
```

### How it works

1. All activities with cached HR streams are loaded from the local database.
2. For each activity, 20-minute rolling window averages are computed over the HR stream. These approximate the sustained HR you can hold for an extended effort — a proxy for LTHR.
3. Across all activities:
   - **LTHR** = 90th percentile of all 20-min rolling averages
   - **Max HR** = 98th percentile of all raw HR values
   - **Resting HR** = 5th percentile of all raw HR values
4. If no valid rolling averages exist (e.g., activities are too short), a fallback uses the 85th percentile of raw HR values as LTHR.

### Confidence score

The inference result includes a `confidence` value (0–100):

| Component | Weight |
|-----------|--------|
| Number of activities with HR data | 40 pts (max) |
| Mean data quality (% valid HR samples) | 30 pts |
| HR consistency across rolling averages | 30 pts |

Inferred values are saved to `~/.fitops/athlete_settings.json` with `_source` fields set to `"inferred"`. They are used immediately for zone calculation.

### Fetch streams first

The `--infer` flag only works with activities that have been stream-fetched:

```bash
# Fetch streams for specific activities
fitops activities streams <activity_id>

# Or fetch all streams during sync (if your sync fetches streams)
fitops sync run
```

---

## Pace Zones

For running, FitOps also supports 5-zone pace zones based on threshold pace.

```bash
# Set your threshold pace
fitops analytics pace-zones --set-threshold-pace 5:00

# View zones
fitops analytics pace-zones
```

Zones are derived as multiples of your threshold pace `T` (in seconds per km):

| Zone | Name | Range |
|------|------|-------|
| 1 | Easy | Slower than T × 1.16 |
| 2 | Aerobic | T × 1.08 – T × 1.16 |
| 3 | Tempo | T × 1.02 – T × 1.08 |
| 4 | Threshold | T × 0.96 – T × 1.02 |
| 5 | VO2max | Faster than T × 0.96 |

Threshold pace is your race-effort pace — roughly the fastest pace you could hold for 60 minutes. Common proxies include 10K race pace + ~5 s/km or a 30-minute time trial.

The `pace-zones` command works offline with no authentication required.

## Command

```bash
fitops analytics zones
fitops analytics zones --method lthr
fitops analytics zones --method hrr
fitops analytics zones --infer
fitops analytics pace-zones --set-threshold-pace 5:00
fitops analytics pace-zones
```

See [Output Examples → Analytics](../output-examples/analytics.md) for the zones JSON response.

← [Concepts](./README.md)
