# Release Notes

## v0.1.1 — Activity Filtering & Pagination

> Date: 2026-04-09

This release adds flexible filtering and pagination to `fitops activities list`, making it easier for both humans and AI agents to navigate large activity histories.

---

### What's New

#### Activity List Filters
Four new options on `fitops activities list`:

- **`--offset N`** — skip the first N results; combine with `--limit` to page through all activities
- **`--before DATE`** — filter activities before a given date (`YYYY-MM-DD`), enabling precise date ranges alongside the existing `--after`
- **`--search TEXT`** — case-insensitive substring match on activity name/title
- **`--tag TAG`** — filter by a named tag: `race`, `trainer`, `commute`, `manual`, `private`

#### Pagination Envelope (JSON mode)
When using `--json`, the `_meta` block now includes pagination fields so agents can detect when more results exist and iterate automatically:

```json
{
  "_meta": {
    "total_count": 150,
    "returned_count": 20,
    "offset": 0,
    "has_more": true
  }
}
```

#### CLI Help Hint
The non-JSON table output now includes a footer tip pointing users to `--help` for available filter options.

#### Dashboard Parity
All new filters are available on the Activities dashboard page with matching UI controls.

---

### Upgrade

```bash
# Using uvx
uvx fitops@0.1.1

# Using pip
pip install --upgrade fitops
```

---

## v0.1.0 — Initial Release

> Date: 2026-04-06

Welcome to the first release of **FitOps CLI** — a local-first Strava analytics tool built for athletes who want full control over their training data. No subscriptions, no cloud lock-in, just your data and powerful analysis at your fingertips.

---

### Highlights

- **Local dashboard** — a web UI served from your machine to browse, analyse, and manage your training data
- **CLI-first design** — every feature is accessible from the terminal with clean, readable output
- **LLM-friendly JSON** — pipe any command's output to an AI assistant using the `--json` flag

---

### Features

#### 🏃 Activities & Training Analysis
- Browse and filter activities by sport type (run, cycle, or combined)
- Aerobic and anaerobic training scores per activity, calibrated against real heart rate data
- Deep activity analysis with performance insights
- VO2max estimation with automatic heart rate reference check before computing

#### 📊 Analytics & Trends
- Analytics dashboard with sport-type filtering and run/cycle/total view toggle
- Training load, pace zones, power curves, and zone distribution

#### 💪 Workouts
- Define structured workouts in Markdown and load them into FitOps
- Interval grouping and assignment flow in the dashboard
- Workout simulation engine — model expected pace and effort for any workout
- Cycling compliance uses speed (km/h) for gap pace output

#### 🗺️ Race & Course Simulation
- Import race courses directly from a Strava activity URL
- Simulate race pacing with wind, elevation, and split breakdowns
- Elevation, wind, and pace charts alongside an adjusted split table
- Course map view and wind badge support in the dashboard

#### 🌤️ Weather
- Weather data fetched and stored alongside activities
- Weather-adjusted pace analysis

#### 💾 Backup & Restore
- Back up your entire FitOps database and restore from archive
- GitHub-based backup provider support

#### 🖥️ Dashboard
- Self-service setup: configure Strava OAuth and trigger your first sync from the browser
- Sync button on empty states — no need to drop to the CLI
- Fullscreen chart support

#### ⌨️ CLI Experience
- Rich formatted output by default across all commands; add `--json` for machine-readable output
- macOS terminal compatibility fixes for authentication prompts

---

### Installation

```bash
# Using uvx (recommended)
uvx fitops

# Using pip
pip install fitops
```

See the [Getting Started guide](docs/customerfacing/getting-started/README.md) for authentication and first sync instructions.

---

### Requirements

- Python 3.11+
- A Strava account with API access

---

Co-authored by [Nova](https://www.compassap.ai/portfolio/nova.html)
