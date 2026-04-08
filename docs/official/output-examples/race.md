# Output Examples — Race

All examples show default output. Add `--json` to any command for raw JSON.

---

## `fitops race courses`

```bash
fitops race courses
```

```
  ID   Name                    Source   Distance    Elevation   Imported
 ──────────────────────────────────────────────────────────────────────────
   1   Berlin Marathon 2026    gpx      42.20 km    +218 m      2026-03-01
   2   Local 10K               gpx      10.02 km    +48 m       2026-03-10
   3   Thursday Loop           strava   8.54 km     +62 m       2026-03-22
```

---

## `fitops race course <id>`

```bash
fitops race course 1
```

```
Berlin Marathon 2026
  Source      gpx
  Distance    42.20 km
  Elevation   +218 m gain  /  -215 m descent

  km    Δ elev    Grade    Cumulative
 ──────────────────────────────────────
   1    +4 m      +0.4%    1.00 km
   2    +8 m      +0.8%    2.00 km
   3    +12 m     +1.2%    3.00 km
   ...
  42    -3 m      -0.3%    42.20 km
```

---

## `fitops race splits <id>`

```bash
fitops race splits 1 --target-time 3:15:00
```

```
Berlin Marathon 2026  →  3:15:00 target  (even splits)

  km    Target Pace    Split      Elapsed
 ──────────────────────────────────────────
   1    4:37/km        4:37       0:04:37
   2    4:37/km        4:37       0:09:14
  ...
  42    4:37/km        4:37       3:15:00
```

---

## `fitops race simulate <id>`

```bash
fitops race simulate 1 --target-time 3:15:00 --temp 18 --humidity 55 --wind 2.5
```

```
Berlin Marathon 2026  →  3:15:00 target  (even effort)
Weather  18.0°C  55% RH  wind 2.5 m/s  |  WAP factor 1.012  |  WBGT 15.8°C 🟢

  km    Δ elev   Grade    WAP     Target Pace    Split      Elapsed
 ────────────────────────────────────────────────────────────────────
   1    +4 m     +0.4%    1.012   4:39/km        4:39       0:04:39
   2    +8 m     +0.8%    1.018   4:41/km        4:41       0:09:20
   5    -6 m     -0.6%    1.005   4:35/km        4:35       0:23:05
  10    +15 m    +1.5%    1.027   4:44/km        4:44       0:47:10
  20    -3 m     -0.3%    1.010   4:38/km        4:38       1:33:12
  30    +12 m    +1.2%    1.021   4:42/km        4:42       2:20:02
  40    -5 m     -0.5%    1.007   4:36/km        4:36       3:07:22
  42    +2 m     +0.2%    1.013   4:39/km        0:07:49    3:15:11

Projected finish: 3:15:11
```

### Pacer mode

```bash
fitops race simulate 1 --target-time 3:05:00 --pacer-pace 4:40 --drop-at-km 35
```

```
Berlin Marathon 2026  →  3:05:00 target  (pacer mode: 4:40/km → drop at km 35)
Weather  neutral (15°C / 40% RH)

  km    Mode      Target Pace    Split      Elapsed
 ────────────────────────────────────────────────────
   1    pacer     4:40/km        4:40       0:04:40
  ...
  35    pacer     4:40/km        4:40       2:43:40
  36    push      4:19/km        4:19       2:47:59
  ...
  42    push      4:22/km        4:22       3:04:53

Projected finish: 3:04:53
Required pace after drop: 4:20/km over 7.20 km
```

---

## JSON output (`--json`)

```bash
fitops race simulate 1 --target-time 3:15:00 --json
```

```json
{
  "_meta": { "generated_at": "2026-04-06T09:15:00+00:00" },
  "course": {
    "id": 1,
    "name": "Berlin Marathon 2026",
    "total_distance_m": 42195,
    "total_elevation_gain_m": 218.0
  },
  "simulation": {
    "mode": "splits",
    "strategy": "even",
    "target_time": "3:15:00",
    "weather": {
      "temperature_c": 15.0,
      "humidity_pct": 40.0,
      "wind_speed_ms": 0.0,
      "wind_direction_deg": 0.0
    },
    "weather_source": "neutral",
    "splits": [
      {
        "km": 1,
        "distance_m": 1000.0,
        "elevation_delta_m": 4.0,
        "grade_pct": 0.4,
        "gap_factor": 1.004,
        "wap_factor": 1.004,
        "target_pace": "4:37/km",
        "split_time": "4:37",
        "elapsed_time": "0:04:37"
      }
    ]
  }
}
```

← [Output Examples](./index.md)
