# FitOps-CLI

Your fitness data is yours. FitOps gives you **two first-class ways to work with it**: a local dashboard for human exploration and a structured CLI for AI agents — both reading from the same SQLite database on your machine.

```
You (human)  →  Dashboard (browser)  ─┐
                                       ├─  ~/.fitops/fitops.db
AI Agent     →  CLI + JSON           ─┘
```

Sync your Strava activities once, then explore them however you like — visually in the browser or programmatically through an agent. No cloud, no subscriptions. Your data never leaves your machine.

## Why FitOps?

Most fitness tools are built for one audience. FitOps is built for two:

- **For humans:** A local dashboard with charts, period filters, and training analytics you can browse at `http://localhost:5000`.
- **For agents:** Every data view is also a CLI command that outputs richly annotated JSON — explicit units, resolved IDs, `_meta` context blocks, and `data_availability` hints so an LLM always knows what to fetch next.
- **Same data, always.** The dashboard and the CLI are two views into the same truth. There is no separate "agent API" — if you can see it in the browser, an agent can query it from the terminal.
- **Everything is local.** Your data lives in `~/.fitops/fitops.db`. No cloud, no subscriptions.
- **Incremental sync.** Authenticate once, then run `fitops sync run` whenever you want fresh data. Only new activities are fetched.
- **Async-first.** Built on `httpx` and `aiosqlite` for non-blocking I/O throughout.

See [AGENTS.md](AGENTS.md) for guidelines on how new functionality should maintain parity across both surfaces.

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — Foundation | ✅ Done | Auth, sync, activities, athlete profile |
| 2 — Analytics | ✅ Done | CTL/ATL/TSB, VO2max, LT1/LT2 thresholds, dashboard |
| 3 — Workouts | 🔜 Planned | Workout plans, scheduling, compliance scoring |
| 4 — More providers | 🔜 Planned | Direct sync from Garmin, Coros, Samsung Health, Apple Health, Huawei Health |
| 5 — Cloud backup | 🔜 Planned | Back up your local database to Google Drive, OneDrive, Dropbox, or Mega |

Phases 4 and 5 are about making FitOps device-agnostic and resilient: connect whichever platform your watch syncs to, and keep your data safe with automated cloud backups to the storage provider you already use. See the [full roadmap](docs/customerfacing/roadmap.md) for details.

## Installation

**Requirements:** Python 3.11+

```bash
git clone https://github.com/yourname/FitOps-CLI.git
cd FitOps-CLI
pip install -e .
```

## Quick Start

### Start the Dashboard

```bash
fitops dashboard start
# → Opens http://localhost:5000
```

The dashboard shows an overview of recent training, activity history, analytics (training load, trends, performance), and your athlete profile — all sourced from the local database.

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
