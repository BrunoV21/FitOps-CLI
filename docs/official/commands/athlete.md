# fitops athlete

View athlete profile, cumulative stats, and HR/power zones from Strava.

## Commands

### `fitops athlete profile`

Show athlete profile and equipment from the local database.

```bash
fitops athlete profile
```

**Output:**

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
    "profile_url": "https://dgalywyr863hv.cloudfront.net/...",
    "equipment": {
      "bikes": [
        { "id": "b123456", "name": "Canyon Endurace", "distance": 3240000 }
      ],
      "shoes": [
        { "id": "g987654", "name": "Nike Vaporfly 3", "distance": 520000 }
      ]
    }
  }
}
```

Requires a prior `fitops sync run` to populate locally.

---

### `fitops athlete stats`

Show cumulative statistics from Strava (live API call).

```bash
fitops athlete stats
```

Returns Strava's aggregate stats: total distance, moving time, and elevation for runs, rides, and swims — split into recent (year-to-date), all-time, and recent-totals.

---

### `fitops athlete zones`

Show HR and power zones configured in your Strava account (live API call).

```bash
fitops athlete zones
```

> **Note:** These are the zones you've configured in the Strava app. For computed zones based on LTHR or max HR, use [`fitops analytics zones`](./analytics.md).

---

### `fitops athlete equipment`

Show mileage and activity counts per piece of equipment (shoes and bikes).

```bash
fitops athlete equipment [OPTIONS]
```

**Options:**

| Flag | Description |
|------|-------------|
| `--type shoes\|bikes` | Filter to only shoes or only bikes. Omit to show all. |

```bash
fitops athlete equipment
fitops athlete equipment --type shoes
fitops athlete equipment --type bikes
```

Equipment is read from the local athlete record (synced from Strava). For each item the output includes:

- `strava_total_distance_km` — total lifetime distance Strava reports for this gear
- `local_activity_distance_km` — distance computed from locally-synced activities using this gear
- `local_activity_count` — number of locally-synced activities tagged to this gear

Requires a prior `fitops sync run`.

## See Also

- [Output Examples → Athlete](../output-examples/athlete.md) — full response samples
- [`fitops analytics zones`](./analytics.md) — computed HR zones from physiology settings

← [Commands Reference](./README.md)
