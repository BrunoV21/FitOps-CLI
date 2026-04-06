# Output Examples — Athlete

## `fitops athlete profile`

```bash
fitops athlete profile
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "athlete": {
    "strava_id": 987654,
    "name": "Jane Smith",
    "username": "janesmith",
    "city": "Portland",
    "country": "US",
    "sex": "F",
    "weight_kg": 62.0,
    "premium": true,
    "profile_url": "https://dgalywyr863hv.cloudfront.net/pictures/athletes/987654/12345/2/large.jpg",
    "equipment": {
      "bikes": [
        {
          "id": "b123456",
          "name": "Canyon Endurace CF SL",
          "distance": 3240000,
          "primary": true
        }
      ],
      "shoes": [
        {
          "id": "g987654",
          "name": "Nike Vaporfly 3",
          "distance": 520000,
          "primary": true
        },
        {
          "id": "g987655",
          "name": "Brooks Ghost 15",
          "distance": 780000,
          "primary": false
        }
      ]
    }
  }
}
```

*Equipment `distance` is in meters.*

---

## `fitops athlete stats`

```bash
fitops athlete stats
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "stats": {
    "biggest_ride_distance": 152340.0,
    "biggest_climb_elevation_gain": 2140.0,
    "recent_ride_totals": {
      "count": 8,
      "distance": 412000.0,
      "moving_time": 54720,
      "elapsed_time": 57600,
      "elevation_gain": 3400.0
    },
    "all_ride_totals": {
      "count": 312,
      "distance": 18400000.0,
      "moving_time": 2160000,
      "elevation_gain": 142000.0
    },
    "recent_run_totals": {
      "count": 14,
      "distance": 143200.0,
      "moving_time": 48600,
      "elevation_gain": 820.0
    },
    "all_run_totals": {
      "count": 847,
      "distance": 8320000.0,
      "moving_time": 2880000,
      "elevation_gain": 52000.0
    },
    "recent_swim_totals": {
      "count": 0,
      "distance": 0.0,
      "moving_time": 0,
      "elevation_gain": 0.0
    },
    "all_swim_totals": {
      "count": 12,
      "distance": 24000.0,
      "moving_time": 36000,
      "elevation_gain": 0.0
    }
  }
}
```

*All distances in meters, times in seconds.*

---

## `fitops athlete zones`

```bash
fitops athlete zones
```

```json
{
  "_meta": { "generated_at": "2026-03-11T09:15:00+00:00" },
  "zones": {
    "heart_rate": {
      "custom_zones": false,
      "zones": [
        { "min": 0, "max": 115 },
        { "min": 115, "max": 152 },
        { "min": 152, "max": 171 },
        { "min": 171, "max": 190 },
        { "min": 190, "max": -1 }
      ]
    },
    "power": {
      "zones": []
    }
  }
}
```

*These are zones configured in Strava. For computed zones from LTHR or max HR, see [`fitops analytics zones`](../commands/analytics.md).*

---

## `fitops athlete equipment`

```bash
fitops athlete equipment
```

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "total_count": 3,
    "filters_applied": { "type": null }
  },
  "equipment": [
    {
      "gear_id": "g987654",
      "name": "Nike Vaporfly 3",
      "type": "shoes",
      "strava_total_distance_km": 520.0,
      "local_activity_distance_km": 312.4,
      "local_activity_count": 48,
      "primary": true
    },
    {
      "gear_id": "g987655",
      "name": "Brooks Ghost 15",
      "type": "shoes",
      "strava_total_distance_km": 780.0,
      "local_activity_distance_km": 198.7,
      "local_activity_count": 31,
      "primary": false
    },
    {
      "gear_id": "b123456",
      "name": "Canyon Endurace CF SL",
      "type": "bikes",
      "strava_total_distance_km": 3240.0,
      "local_activity_distance_km": 1842.3,
      "local_activity_count": 87,
      "primary": true
    }
  ]
}
```

```bash
fitops athlete equipment --type shoes
```

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "total_count": 2,
    "filters_applied": { "type": "shoes" }
  },
  "equipment": [
    {
      "gear_id": "g987654",
      "name": "Nike Vaporfly 3",
      "type": "shoes",
      "strava_total_distance_km": 520.0,
      "local_activity_distance_km": 312.4,
      "local_activity_count": 48,
      "primary": true
    },
    {
      "gear_id": "g987655",
      "name": "Brooks Ghost 15",
      "type": "shoes",
      "strava_total_distance_km": 780.0,
      "local_activity_distance_km": 198.7,
      "local_activity_count": 31,
      "primary": false
    }
  ]
}
```

← [Output Examples](./README.md)
