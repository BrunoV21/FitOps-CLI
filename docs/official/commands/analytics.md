# fitops analytics

Training analytics computed from your local activity database.

All analytics commands require synced activities. Run `fitops sync run` first.

Output is human-readable by default. Add `--json` to any command for raw JSON output.

## Commands

### `fitops analytics training-load`

Show CTL (fitness), ATL (fatigue), and TSB (form) over time.

```bash
fitops analytics training-load [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--days N` | 90 | Days of history to return |
| `--sport TYPE` | all | Filter by sport type (e.g. `Run`, `Ride`) |
| `--today` | false | Return only today's current values (no history array) |
| `--json` | false | Output raw JSON instead of the formatted summary |

**Examples:**

```bash
fitops analytics training-load
fitops analytics training-load --days 42 --sport Run
fitops analytics training-load --today
```

![Training Load Chart](../assets/dashboard-training-load-detailed.png)

See [Concepts → Training Load](../concepts/training-load.md) for how CTL/ATL/TSB are calculated.

---

### `fitops analytics vo2max`

Estimate VO2max from recent run activities.

```bash
fitops analytics vo2max [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--activities N` | 50 | Number of recent qualifying activities to consider |
| `--age-adjusted` | false | Apply an age-based decline factor to the estimate |
| `--method METHOD` | composite | Method to display: `daniels`, `cooper`, or `composite` |
| `--save` | false | Save the selected method's result as a manual override |
| `--set-override VALUE` | — | Directly set a VO2max override value (ml/kg/min) |
| `--clear-override` | false | Clear any previously saved manual override |
| `--json` | false | Output raw JSON instead of the formatted summary |

Requires at least one run of 1500m or more. LTHR or max HR must be configured first (used to identify qualifying hard efforts). Uses a weighted composite of three formulas (VDOT 50%, McArdle 30%, Costill 20–40%).

```bash
fitops analytics vo2max
fitops analytics vo2max --activities 20
fitops analytics vo2max --age-adjusted

# Pin the VDOT estimate as your override
fitops analytics vo2max --method daniels --save

# Set override manually
fitops analytics vo2max --set-override 54.2

# Clear override and return to computed estimate
fitops analytics vo2max --clear-override
```

The `--age-adjusted` flag reads the athlete's birthday from the local database (synced from Strava) and applies a decline factor of 0.8% per year above age 25. The factor is floored at 0.5. See [Concepts → VO2max](../concepts/vo2max.md) for full methodology.

---

### `fitops analytics zones`

Calculate heart rate training zones from your physiology settings.

```bash
fitops analytics zones [OPTIONS]
```

**Options:**

| Flag | Description |
|------|-------------|
| `--method METHOD` | Zone method: `lthr`, `max-hr`, `hrr`. Auto-selected if omitted. |
| `--set-lthr BPM` | Save your lactate threshold HR |
| `--set-max-hr BPM` | Save your maximum HR |
| `--set-resting-hr BPM` | Save your resting HR |
| `--set-lt1 BPM` | Manually override the LT1 (aerobic threshold) display value |
| `--set-lt2 BPM` | Manually override the LT2 (lactate threshold) display value |
| `--clear-lt1` | Clear LT1 override and return to computed value |
| `--clear-lt2` | Clear LT2 override and return to computed value |
| `--infer` | Infer LTHR, max HR, and pace thresholds from cached activity streams |

**First-time setup — set your values manually:**

```bash
fitops analytics zones --set-lthr 165
fitops analytics zones --set-max-hr 192 --set-resting-hr 48
```

**Or infer from your activity data:**

```bash
fitops analytics zones --infer
```

The `--infer` flag analyses HR data from all activities with cached streams. It uses 20-minute rolling window averages to estimate LTHR (90th percentile of rolling averages), max HR (98th percentile), and resting HR (5th percentile). The result includes a confidence score (0–100) based on number of activities analysed, HR data quality, and consistency.

Inferred values are saved to `~/.fitops/athlete_settings.json` with source tagged as `"inferred"`. Zone display runs immediately after inference.

**Then compute zones:**

```bash
fitops analytics zones
fitops analytics zones --method lthr
fitops analytics zones --method hrr
```

Settings are stored in `~/.fitops/athlete_settings.json` and reused across runs.

See [Concepts → Zones](../concepts/zones.md) for zone method details.

---

### `fitops analytics trends`

Analyse training trends: volume, consistency, seasonal patterns, and performance.

```bash
fitops analytics trends [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--sport TYPE` | all | Filter by sport type (e.g. `Run`, `Ride`) |
| `--days N` | 180 | Days of history to analyse |

```bash
fitops analytics trends
fitops analytics trends --sport Run --days 365
```

**Output includes:**

- `volume_trend` — weekly distance with linear regression slope and direction (`increasing` / `decreasing` / `stable`)
- `consistency` — consistency score (0–1), weekly training frequency, average days between activities
- `seasonal` — per-season activity count, total distance, and average pace
- `performance_trend` — monthly pace and HR trends with improvement rate
- `summary_label` — plain-text summary (e.g. `"volume building, consistent training, pace improving"`)

---

### `fitops analytics performance`

Show performance metrics derived from recent activities.

```bash
fitops analytics performance [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--days N` | 365 | Days of history to analyse |
| `--sport TYPE` | Run | Sport type: `Run` or `Ride` |

```bash
fitops analytics performance --days 180
fitops analytics performance --sport Ride
```

**Running metrics:**

| Field | Description |
|-------|-------------|
| `running_economy_ml_kg_km` | Estimated oxygen cost per km (proxy from average pace) |
| `pace_efficiency_score` | 0–100 score based on pace consistency across recent runs |
| `variability_index` | Coefficient of variation across pace values |
| `aerobic_efficiency_trend` | Early-vs-recent speed per heartbeat trend, including estimated HR change at the recent benchmark pace |

**Cycling metrics:**

| Field | Description |
|-------|-------------|
| `ftp_estimate_watts` | 95% of mean power from recent rides |
| `power_to_weight_w_kg` | FTP estimate / athlete body weight |
| `normalized_power_ratio` | Mean NP/AP ratio across recent rides |
| `power_consistency` | 0–100 score based on power consistency |
| `variability_index` | Coefficient of variation across power values |

**Shared context:**

| Field | What it means |
|-------|--------------|
| `current_load` | Current CTL / ATL / TSB snapshot used by the dashboard and CLI |
| `trends` | Training trend summary for the selected sport and time window |

The dashboard performance page uses the same underlying data and adds a sport switch plus a profile link so you can compare current fitness, recent load, and threshold settings in one place.

---

### `fitops analytics power-curve`

Compute mean maximal power (MMP) curve and fit a critical power model.

```bash
fitops analytics power-curve [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--sport TYPE` | Ride | Sport type: `Ride` or `Run` |
| `--activities N` | 20 | Max number of recent activities with streams to use |

```bash
fitops analytics power-curve
fitops analytics power-curve --sport Run --activities 10
```

Requires activities with cached streams (`fitops activities streams <id>` or bulk sync).

**Output includes:**

- `mean_maximal_power` — best average power/speed at standard durations (5s, 10s, ..., 7200s)
- `critical_power_watts` — CP from the two-parameter `P = CP + W'/t` model (cycling only, requires `scipy`)
- `w_prime_joules` — anaerobic work capacity in joules
- `model_r_squared` — goodness of fit for the CP model
- `zones_from_cp` — 6-zone power zones derived from CP
- `power_to_weight` — FTP estimate and W/kg (if athlete weight is stored)

If `scipy` is not installed, the CP model is skipped and only MMP values are returned.

---

### `fitops analytics pace-zones`

Show or configure running pace zones based on threshold pace.

```bash
fitops analytics pace-zones [OPTIONS]
```

**Options:**

| Flag | Description |
|------|-------------|
| `--set-threshold-pace MM:SS` | Set your threshold pace per km (e.g. `5:00` or `4:45`) |

This command does not require authentication — it reads and writes local settings only.

```bash
# Set threshold pace
fitops analytics pace-zones --set-threshold-pace 5:00

# View current pace zones
fitops analytics pace-zones
```

**5-zone structure** (derived from threshold pace `T`):

| Zone | Name | Range |
|------|------|-------|
| 1 | Easy | > T × 1.16 |
| 2 | Aerobic | T × 1.08 – T × 1.16 |
| 3 | Tempo | T × 1.02 – T × 1.08 |
| 4 | Threshold | T × 0.96 – T × 1.02 |
| 5 | VO2max | < T × 0.96 |

**Pace signal preference:** when assigning laps or efforts to zones, FitOps uses the best available pace metric:

1. **True Pace** — GAP + weather normalised, if streams and weather data are available *(most accurate on hilly or windy courses)*
2. **GAP** (Grade-Adjusted Pace) — if streams are available but weather is missing
3. **Raw pace** — fallback if neither streams nor weather are available

This hierarchy also applies to **LT2 inference**: inferred threshold estimates are significantly more reliable when computed from True Pace rather than raw pace. See [Concepts → Weather & Pace](../concepts/weather-pace.md) for details.

Threshold pace is stored in `~/.fitops/athlete_settings.json`.

---

### `fitops analytics recalculate-scores`

Recompute aerobic and anaerobic scores for all activities and persist them to the database.

```bash
fitops analytics recalculate-scores [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--json` | false | Output raw JSON instead of the formatted summary |

```bash
fitops analytics recalculate-scores
fitops analytics recalculate-scores --json
```

Scores are derived from each activity's pace, HR, and current physiology settings (`~/.fitops/athlete_settings.json`). Run this command after updating LTHR, max HR, or threshold pace so that historical scores reflect your current settings.

**JSON output:**

```json
{
  "_meta": { ... },
  "recalculated": 312
}
```

This command does not contact Strava — it only reads and writes the local database.

---

### `fitops analytics snapshot`

Compute and save today's analytics snapshot (CTL, ATL, TSB, VO2max) to the database.

```bash
fitops analytics snapshot
```

This command is useful for automation — run it daily via cron to build a historical record of your fitness metrics. It is idempotent per day, safe to run multiple times.

```
Snapshot saved  2026-04-06
  CTL     41.7
  ATL     54.0
  TSB     -12.3
  VO2max  55.4 ml/kg/min
```

## Physiology Settings

Analytics that depend on HR-based calculations (`zones`, `snapshot`) read from `~/.fitops/athlete_settings.json`. Set your values once with `--set-*` flags and they persist.

| Setting | Flag | Used By |
|---------|------|---------|
| LTHR (lactate threshold HR) | `--set-lthr` | `zones`, `snapshot` |
| Max HR | `--set-max-hr` | `zones` |
| Resting HR | `--set-resting-hr` | `zones` (HRR method) |
| Threshold pace | `--set-threshold-pace` | `pace-zones` |

## See Also

- [Concepts → Training Load](../concepts/training-load.md)
- [Concepts → VO2max](../concepts/vo2max.md)
- [Concepts → Zones](../concepts/zones.md)
- [Output Examples → Analytics](../output-examples/analytics.md)

← [Commands Reference](./index.md)
