# FitOps-CLI

A local, async-first Python CLI that connects your Strava account to a local SQLite database and exposes your training data in **LLM-friendly JSON** — designed so an AI agent can analyze your fitness, spot patterns, and guide your training.

## Why FitOps-CLI?

Most Strava dashboards are built for humans browsing graphs. FitOps-CLI is built for **AI-assisted coaching**:

- **Everything is local.** Your data lives in `~/.fitops/fitops.db`. No cloud, no subscriptions.
- **Structured JSON output.** Every command outputs richly annotated JSON with human-readable labels, explicit units, and a `_meta` context block — exactly what an LLM needs.
- **Incremental sync.** Authenticate once, then run `fitops sync run` whenever you want fresh data. Only new activities are fetched.
- **Async-first.** Built on `httpx` and `aiosqlite` for non-blocking I/O throughout.

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — Foundation | ✅ Done | Auth, sync, activities, athlete profile |
| 2 — Analytics | 🔜 Next | CTL/ATL/TSB, VO2max, LT1/LT2 thresholds |
| 3 — Workouts | 🔜 Future | Workout plans, scheduling, compliance scoring |

## Installation

**Requirements:** Python 3.11+

```bash
git clone https://github.com/yourname/FitOps-CLI.git
cd FitOps-CLI
pip install -e .
```

## Quick Start

### 1. Create a Strava API Application

1. Go to [https://www.strava.com/settings/api](https://www.strava.com/settings/api)
2. Create an application — set the **Authorization Callback Domain** to `localhost`
3. Note your **Client ID** and **Client Secret**

### 2. Authenticate

```bash
fitops auth login
# → Prompts for Client ID and Secret on first run
# → Opens your browser to Strava OAuth
# → Captures callback on localhost:8080
# → Saves tokens to ~/.fitops/config.json
```

### 3. Sync Activities

```bash
fitops sync run          # Incremental sync (from last sync date)
fitops sync run --full   # Full historical sync (all time)
fitops sync status       # Show sync state
```

### 4. Query Your Data

```bash
# List recent activities
fitops activities list

# Filter by sport and date
fitops activities list --sport Run --limit 50 --after 2026-01-01

# Get full detail for one activity
fitops activities get 12345678901

# Get stream data (HR, pace, power over time)
fitops activities streams 12345678901

# Get lap splits
fitops activities laps 12345678901

# Athlete profile + equipment
fitops athlete profile

# Cumulative Strava stats
fitops athlete stats

# HR and power zones
fitops athlete zones
```

## Commands Reference

```
fitops auth login               Authenticate with Strava
fitops auth logout              Revoke token and clear credentials
fitops auth status              Show token validity and athlete info
fitops auth refresh             Force token refresh

fitops sync run                 Incremental sync (since last sync - 3 days)
fitops sync run --full          Full historical sync
fitops sync run --after DATE    Sync from specific date (YYYY-MM-DD)
fitops sync status              Show sync state and history

fitops activities list          Last 20 activities as JSON
fitops activities list --sport Run --limit 50 --after 2026-01-01
fitops activities get ID        Full detail for one activity
fitops activities streams ID    Time-series stream data
fitops activities laps ID       Lap splits

fitops athlete profile          Athlete profile + bikes/shoes
fitops athlete stats            Strava cumulative statistics
fitops athlete zones            HR and power training zones

fitops workouts list            (Phase 3 — coming soon)
fitops workouts create          (Phase 3 — coming soon)
```

## Storage Layout

```
~/.fitops/
├── config.json          # Strava credentials + preferences
├── sync_state.json      # Sync history and last sync timestamp
└── fitops.db            # SQLite database (activities, streams, laps, athlete)
```

Override the directory with the `FITOPS_DIR` environment variable.

## LLM-Friendly Output

All commands output structured JSON with a `_meta` block:

```json
{
  "_meta": {
    "tool": "fitops-cli",
    "version": "0.1.0",
    "generated_at": "2026-03-10T22:05:00+00:00",
    "total_count": 3,
    "filters_applied": {"sport_type": "Run", "limit": 3}
  },
  "activities": [
    {
      "strava_activity_id": 12345678901,
      "name": "Morning Run",
      "sport_type": "Run",
      "start_date_local": "2026-03-10T07:30:00",
      "duration": {
        "moving_time_seconds": 3720,
        "moving_time_formatted": "1:02:00"
      },
      "distance": {"meters": 10250, "km": 10.25, "miles": 6.37},
      "pace": {"average_per_km": "6:03", "average_per_mile": "9:44"},
      "heart_rate": {"average_bpm": 148, "max_bpm": 172},
      "equipment": {
        "gear_id": "g12345",
        "gear_name": "Nike Pegasus 40",
        "gear_type": "shoes"
      },
      "data_availability": {
        "has_heart_rate": true,
        "has_power": false,
        "streams_fetched": false
      }
    }
  ]
}
```

Design principles:
- Units are explicit in every field name (`_m`, `_km`, `_ms`, `_bpm`, `_s`)
- Gear IDs are resolved to names
- Paces formatted as `"6:03"` (not raw m/s)
- `data_availability` tells the LLM what additional detail can be fetched

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE)
