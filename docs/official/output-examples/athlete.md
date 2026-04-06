# Output Examples — Athlete

All examples show default output. Add `--json` to any command for raw JSON.

---

## `fitops athlete profile`

```bash
fitops athlete profile
```

```
Bruno V.
  Sex        M
  Bikes      0
  Shoes      4
```

---

## `fitops athlete stats`

```bash
fitops athlete stats
```

```
  All Runs (recent)   16 activities  |  181.5 km  |  15.9 h  |  +358 m
  All Runs (YTD)      39 activities  |  403.4 km  |  37.5 h  |  +1273 m
  All Runs (total)    163 activities  |  1624.4 km  |  152.7 h  |  +3521 m

  All Rides (recent)  5 activities  |  182.6 km  |  6.6 h  |  +827 m
  All Rides (YTD)     8 activities  |  289.4 km  |  11.5 h  |  +1347 m
  All Rides (total)   29 activities  |  857.6 km  |  32.5 h  |  +3777 m
```

---

## `fitops athlete equipment --type shoes`

```bash
fitops athlete equipment --type shoes
```

```
  Name                       Type    Strava Dist   Local Dist   Activities
 ──────────────────────────────────────────────────────────────────────────
  Kiprun KS900.2             shoes     936.52 km    936.52 km           98
  Adidas Adizero SL2         shoes     354.24 km    354.24 km           32
  Adidas Adizero Boston 13   shoes      75.38 km     75.38 km            8
  Adidas Adistar 4           shoes     258.23 km    258.23 km           25
```

---

## `fitops athlete zones`

```bash
fitops athlete zones
```

Returns the HR zones configured in Strava (not the computed LTHR zones). For computed zones from your stream data, use [`fitops analytics zones`](../commands/analytics.md).

---

## JSON output (`--json`)

```bash
fitops athlete equipment --type shoes --json
```

```json
{
  "_meta": { "generated_at": "2026-04-06T09:15:00+00:00", "total_count": 4 },
  "equipment": [
    {
      "gear_id": "g987654",
      "name": "Kiprun KS900.2",
      "type": "shoes",
      "strava_total_distance_km": 936.52,
      "local_activity_distance_km": 936.52,
      "local_activity_count": 98,
      "primary": true
    }
  ]
}
```

← [Output Examples](./index.md)
