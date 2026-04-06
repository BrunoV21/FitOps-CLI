# Output Examples — Activities

All examples show default output. Add `--json` to any command for raw JSON.

---

## `fitops activities list`

```bash
fitops activities list --sport Run --limit 3
```

```
  ID            Date        Sport   Dist      Duration  Pace/Speed  HR
 ──────────────────────────────────────────────────────────────────────
  17972016511   2026-04-04  Run     12.12 km  58:05     4:47/km     168
  17954157500   2026-04-02  Run     16.52 km  1:27:11   5:16/km     154
  17930412200   2026-03-30  Run     10.05 km  50:22     5:00/km     161
```

---

## `fitops activities get <ID>`

```bash
fitops activities get 17972016511
```

```
Outdoor run  Run  |  2026-04-04

  Distance   12.12 km  (7.53 mi)
  Duration   58:05
  Pace       4:47/km  |  7:42/mi
  Elevation  +29.4 m
  Heart Rate 168 avg bpm  |  190 max
  Calories   720
  Gear       Adidas Adizero SL2 (shoes)
  Training   Aerobic 3.5  |  Anaerobic 1.4
```

---

## `fitops activities streams <ID>`

```bash
fitops activities streams 17972016511
```

```
Streams for activity 17972016511

  altitude                  3492 data points
  latlng                    3492 data points
  grade_adjusted_speed      3492 data points
  moving                    3492 data points
  cadence                   3492 data points
  velocity_smooth           3492 data points
  time                      3492 data points
  heartrate                 3492 data points
  grade_smooth              3492 data points
  distance                  3492 data points
```

Use `--json` to get the full data arrays for scripting or analysis:

```bash
fitops activities streams 17972016511 --json
```

```json
{
  "_meta": { "generated_at": "2026-04-04T09:15:00+00:00" },
  "activity_strava_id": 17972016511,
  "streams": {
    "heartrate": { "data_length": 3492, "data": [142, 145, 148, ...] },
    "velocity_smooth": { "data_length": 3492, "data": [3.1, 3.2, ...] },
    "altitude": { "data_length": 3492, "data": [45.2, 45.4, ...] }
  }
}
```

*Data arrays contain one value per second.*

← [Output Examples](./index.md)
