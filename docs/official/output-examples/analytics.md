# Output Examples — Analytics

All examples show default output. Add `--json` to any command for raw JSON.

---

## `fitops analytics training-load --today`

```bash
fitops analytics training-load --today
```

```
Training Load  2026-04-06

  CTL (Fitness)   42.2
  ATL (Fatigue)   54.0
  TSB (Form)      -11.8  [Overreaching — high adaptation, monitor recovery]
  7d Ramp Rate    +15.45%  [High risk — reduce load to prevent injury]
  7d CTL Change   +5.65

  Volume
  This week       0.0 km  /  0.0 h  (-100% WoW)
  Last week       114.0 km  /  6.6 h
  This month      102 km  /  5.7 h  (+362% vs same period last month)
  Last month      311 km  /  21.2 h
```

## `fitops analytics training-load --days 14 --sport Run`

With history, a table of daily values is appended below the summary:

```
Training Load  2026-04-06

  CTL (Fitness)   28.4
  ...

  Date          CTL    ATL     TSB   TSS
 ────────────────────────────────────────
  2026-03-24   26.9   32.2    -5.2    43
  2026-03-25   25.7   24.1    +1.6     0
  2026-04-04   31.3   42.3   -11.1    64
  2026-04-05   29.8   31.8    -1.9     0
```

---

## `fitops analytics vo2max`

```bash
fitops analytics vo2max
```

```
VO2max Estimate

  Estimate        55.4 ml/kg/min  [High]
  Daniels VDOT    53.7
  Cooper          58.0
  Based on        12KM - Salvaterra de Magos  (2026-03-22)
                  11.98 km  |  3:52/km

  Race Predictions  LT2 · from ? km @ ?/km
  5K           18:01       3:36/km
  10K          37:31       3:45/km
  Half         1:23:55     3:58/km
  Marathon     2:56:04     4:10/km
```

---

## `fitops analytics zones --method lthr`

```bash
fitops analytics zones --method lthr
```

```
HR Zones  method: lthr
  LT2 pace   3:54/km  (GAP)
```

---

## `fitops analytics snapshot`

```bash
fitops analytics snapshot
```

```
Snapshot saved  2026-04-06
  CTL     41.7
  ATL     54.0
  TSB     -12.3
  VO2max  55.4 ml/kg/min
```

---

## `fitops analytics performance --sport Run`

```bash
fitops analytics performance --sport Run
```

```
Performance Metrics  Run
  Activities           50
  Reliability          0.852
  Running economy      174.9 ml/kg/km
  Pace efficiency      85.2
  Max HR estimate      199 bpm
  Aerobic threshold    149 bpm
  Anaerobic threshold  169 bpm
```

---

## `fitops analytics trends --sport Run`

```bash
fitops analytics trends --sport Run --days 90
```

```
Training Trends  volume building, consistent training, pace improving
  Activities     38
```

---

## JSON output (`--json`)

All analytics commands support `--json`. Example:

```bash
fitops analytics training-load --today --json
```

```json
{
  "_meta": {
    "generated_at": "2026-04-06T09:15:00+00:00",
    "filters_applied": { "today_only": true }
  },
  "training_load": {
    "current": {
      "date": "2026-04-06",
      "ctl": 42.2,
      "atl": 54.0,
      "tsb": -11.8,
      "form_label": "Overreaching — high adaptation, monitor recovery"
    },
    "trend_7_days": {
      "ramp_rate_pct": 15.45,
      "ramp_label": "High risk — reduce load to prevent injury"
    }
  }
}
```

← [Output Examples](./index.md)
