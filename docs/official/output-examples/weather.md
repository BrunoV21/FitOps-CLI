# Output Examples — Weather

All examples show default output. Add `--json` to any command for raw JSON.

---

## `fitops weather fetch <activity_id>`

```bash
fitops weather fetch 17972016511
```

```
Weather  activity 17972016511  open-meteo

  Temperature           13.7 °C  (65% RH)
  Condition                     Clear sky
  Wind                       1.6 m/s  92°
  WBGT                 11.03 °C  [YELLOW]
  Pace heat factor                 1.0021
  VO2max heat factor                    -
  WAP factor                            -
```

---

## `fitops weather show <activity_id>`

Includes WAP factor, actual pace, and weather-adjusted pace (requires streams to be synced).

```bash
fitops weather show 17972016511
```

```
Weather  activity 17972016511  open-meteo

  Temperature           13.7 °C  (65% RH)
  Condition                     Clear sky
  Wind                       1.6 m/s  92°
  WBGT                 11.03 °C  [YELLOW]
  Pace heat factor                 1.0021
  VO2max heat factor               0.9897
  WAP factor                       1.0021
  Actual pace                     4:47/km
  WAP (adj. pace)                 4:47/km
```

**Reading the output:** WAP factor of 1.0021 means conditions added ~0.2% effort. Near-neutral — cool day, light wind. Actual and weather-adjusted pace are the same.

---

## `fitops weather forecast`

```bash
fitops weather forecast --lat 51.5074 --lng -0.1278 --date 2026-04-19 --hour 10 --course-bearing 90
```

```
Race Day Forecast — 2026-04-19 at 10:00 local
Location: 51.5074, -0.1278

  Conditions
  ──────────────────────────────────────────────────
  Temperature        14.2°C
  Humidity           72%
  Wind               4.1 m/s from SW (225°)
  Headwind           2.9 m/s (into runner — course 090°)
  Sky                Partly cloudy

  Heat Stress
  ──────────────────────────────────────────────────
  WBGT               13.2°C
  Flag               YELLOW — mild heat stress
  Pace heat factor   +0.6% (1.006)
  VO2max capacity    99.7% (−0.3%)

  Wind Adjustment (Pugh 1971)
  ──────────────────────────────────────────────────
  Headwind penalty   +4.8%

  Combined WAP Factor
  ──────────────────────────────────────────────────
  wap_factor         1.0540  — conditions 5.4% harder than neutral
```

**Reading the output:** A 5.4% WAP factor means the race effort is notably harder than neutral. If your target is 4:00/km in neutral conditions, expect to run ~4:13/km at equivalent effort.

---

## JSON output (`--json`)

```bash
fitops weather show 17972016511 --json
```

```json
{
  "_meta": { "generated_at": "2026-04-06T09:15:00+00:00" },
  "weather": {
    "activity_id": 17972016511,
    "temperature_c": 13.7,
    "humidity_pct": 65.0,
    "wind_speed_ms": 1.6,
    "wind_direction_deg": 92.0,
    "source": "open-meteo",
    "wbgt_c": 11.03,
    "wbgt_flag": "yellow",
    "pace_heat_factor": 1.0021,
    "vo2max_heat_factor": 0.9897,
    "wap_factor": 1.0021,
    "actual_pace": "4:47/km",
    "wap": "4:47/km"
  }
}
```

← [Output Examples](./index.md)
