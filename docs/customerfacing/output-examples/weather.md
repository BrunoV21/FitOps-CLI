# Output Examples — Weather

Sample responses for all `fitops weather` commands.

---

## `fitops weather fetch <activity_id>`

```bash
fitops weather fetch 12345678901
```

```json
{
  "_meta": {
    "generated_at": "2026-03-19T09:14:22+00:00"
  },
  "weather": {
    "activity_id": 12345678901,
    "temperature_c": 22.1,
    "humidity_pct": 68.0,
    "wind_speed_ms": 3.2,
    "wind_direction_deg": 270.0,
    "weather_code": 1,
    "source": "open-meteo",
    "wbgt_c": 19.84,
    "pace_heat_factor": 1.0348,
    "condition": "Mainly clear",
    "wbgt_flag": "yellow"
  }
}
```

---

## `fitops weather fetch --all --limit 5`

```bash
fitops weather fetch --all --limit 5
```

```json
{
  "_meta": {
    "generated_at": "2026-03-19T09:14:40+00:00",
    "total_count": 3
  },
  "fetched": 3,
  "activities": [
    {
      "activity_id": 12345678901,
      "name": "Morning Run",
      "result": {
        "activity_id": 12345678901,
        "temperature_c": 22.1,
        "humidity_pct": 68.0,
        "wind_speed_ms": 3.2,
        "wind_direction_deg": 270.0,
        "weather_code": 1,
        "source": "open-meteo",
        "wbgt_c": 19.84,
        "pace_heat_factor": 1.0348
      }
    },
    {
      "activity_id": 12345678899,
      "name": "Long Run",
      "result": {
        "activity_id": 12345678899,
        "temperature_c": 18.5,
        "humidity_pct": 55.0,
        "wind_speed_ms": 1.8,
        "wind_direction_deg": 180.0,
        "weather_code": 0,
        "source": "open-meteo",
        "wbgt_c": 15.89,
        "pace_heat_factor": 1.0118
      }
    },
    {
      "activity_id": 12345678888,
      "name": "Tempo Run",
      "result": {
        "activity_id": 12345678888,
        "temperature_c": 8.0,
        "humidity_pct": 82.0,
        "wind_speed_ms": 5.1,
        "wind_direction_deg": 315.0,
        "weather_code": 61,
        "source": "open-meteo",
        "wbgt_c": 7.82,
        "pace_heat_factor": 1.0
      }
    }
  ]
}
```

---

## `fitops weather show <activity_id>`

Includes WAP factor, actual pace, weather-adjusted pace, course bearing, and VO2max heat factor.

```bash
fitops weather show 12345678901
```

```json
{
  "_meta": {
    "generated_at": "2026-03-19T09:15:01+00:00"
  },
  "weather": {
    "activity_id": 12345678901,
    "temperature_c": 22.1,
    "humidity_pct": 68.0,
    "wind_speed_ms": 3.2,
    "wind_direction_deg": 270.0,
    "weather_code": 1,
    "source": "open-meteo",
    "wbgt_c": 19.84,
    "pace_heat_factor": 1.0348,
    "condition": "Mainly clear",
    "wbgt_flag": "yellow",
    "wap_factor": 1.0412,
    "course_bearing_deg": 92.3,
    "vo2max_heat_factor": 0.9984,
    "actual_pace": "5:12/km",
    "wap": "4:59/km"
  }
}
```

**Interpretation:** The run was done at 5:12/km actual pace. Heat and a westerly headwind (course bearing ~east, wind from west) increased the effort by ~4.1%. The weather-adjusted equivalent pace in neutral conditions would have been 4:59/km.

---

## `fitops weather forecast`

### Default (formatted table)

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
  Flag               🟡 YELLOW — mild heat stress
  Pace heat factor   +0.6% (1.006)
  VO2max capacity    99.7% (−0.3%)

  Wind Adjustment (Pugh 1971)
  ──────────────────────────────────────────────────
  Headwind penalty   +4.8%

  Combined WAP Factor
  ──────────────────────────────────────────────────
  wap_factor         1.0540  — conditions 5.4% harder than neutral
```

### JSON (--json flag)

```bash
fitops weather forecast --lat 51.5074 --lng -0.1278 --date 2026-04-19 --hour 10 --course-bearing 90 --json
```

```json
{
  "_meta": {
    "generated_at": "2026-03-19T09:16:00+00:00"
  },
  "forecast": {
    "date": "2026-04-19",
    "hour_local": 10,
    "timezone": "Europe/London",
    "lat": 51.5074,
    "lng": -0.1278,
    "temperature_c": 14.2,
    "humidity_pct": 72.0,
    "wind_speed_ms": 4.1,
    "wind_direction_deg": 225.0,
    "weather_code": 2,
    "condition": "Partly cloudy",
    "wbgt_c": 13.18,
    "wbgt_flag": "yellow",
    "pace_heat_factor": 1.0064,
    "vo2max_heat_factor": 0.9968,
    "headwind_ms": 2.9,
    "wind_direction_compass": "SW",
    "wap_factor": 1.054,
    "course_bearing_deg": 90.0
  }
}
```

---

## `fitops weather set <activity_id>`

Manual override with temperature and humidity — WBGT and pace heat factor are auto-computed.

```bash
fitops weather set 12345678901 --temp 24.5 --humidity 75 --wind 3.0 --wind-dir 270
```

```json
{
  "_meta": {
    "generated_at": "2026-03-19T09:17:00+00:00"
  },
  "weather": {
    "activity_id": 12345678901,
    "temperature_c": 24.5,
    "humidity_pct": 75.0,
    "wind_speed_ms": 3.0,
    "wind_direction_deg": 270.0,
    "wbgt_c": 22.31,
    "pace_heat_factor": 1.0679,
    "source": "manual"
  }
}
```

---

## Error responses

### Activity not in database

```json
{
  "error": "Activity 99999999 not found in DB."
}
```

### Activity has no GPS coordinates

```json
{
  "error": "No GPS coordinates for this activity.",
  "activity_id": 12345678901
}
```

### No weather data stored (show command)

```json
{
  "error": "No weather data for activity 12345678901.",
  "hint": "Run: fitops weather fetch 12345678901"
}
```

### Forecast beyond 16-day window

```json
{
  "error": "Failed to fetch forecast from Open-Meteo. Date may be beyond 16-day window."
}
```

← [Output Examples](./README.md)
