# Release Notes

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
uvx fitops-cli

# Using pip
pip install fitops-cli
```

See the [Getting Started guide](docs/customerfacing/getting-started/README.md) for authentication and first sync instructions.

---

### Requirements

- Python 3.11+
- A Strava account with API access

---

Co-authored by [Nova](https://www.compassap.ai/portfolio/nova.html)
