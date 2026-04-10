# FitOps

![FitOps Banner](https://raw.githubusercontent.com/BrunoV21/FitOps-CLI/main/docs/official/assets/fitops_banner.png)

[![PyPI version](https://img.shields.io/pypi/v/fitops?color=blue)](https://pypi.org/project/fitops/)
[![PyPI downloads](https://img.shields.io/pypi/dm/fitops?label=PyPI%20downloads)](https://pypi.org/project/fitops/)
[![Python versions](https://img.shields.io/pypi/pyversions/fitops)](https://pypi.org/project/fitops/)
[![License: MIT](https://img.shields.io/github/license/brunov21/fitops)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/brunov21/fitops?style=social)](https://github.com/brunov21/fitops/stargazers)
[![CI](https://img.shields.io/github/actions/workflow/status/brunov21/fitops/python-package.yml?label=CI)](https://github.com/brunov21/fitops/actions/workflows/python-package.yml)
[![uv compatible](https://img.shields.io/badge/uv-compatible-5C4EE5?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Your fitness data is yours. FitOps gives you **two first-class ways to work with it**: a local dashboard for human exploration and a structured CLI for AI agents — both reading from the same SQLite database on your machine.

```
You (human)  →  Dashboard (browser)  ─┐
                                       ├─  ~/.fitops/fitops.db
AI Agent     →  CLI (Rich + JSON)    ─┘
```

![FitOps Dashboard](https://raw.githubusercontent.com/brunov21/fitops/main/docs/official/assets/dashboard-overview-hero.png)

Sync your Strava activities once, then explore them however you like — visually in the browser or programmatically through an agent. No cloud, no subscriptions. Your data never leaves your machine.

> **Current data source:** Strava (via OAuth sync). Direct file import (GPX / TCX / FIT) and native integrations with Garmin, Coros, Apple Health, and Huawei are planned — see the [Roadmap](#roadmap).

## Why FitOps?

- **For humans:** A local dashboard with charts, period filters, and training analytics at `http://localhost:8888` — activities, analytics, workouts, notes, weather, and race simulation.
- **For agents:** Every data view is also a CLI command. Commands output **Rich formatted tables** for quick human scanning, or structured JSON with `_meta` context blocks and `data_availability` hints so an LLM always knows what to fetch next. JSON output is token-optimized — **21.9% fewer tokens** vs v0.1.0 (~56 tokens saved per activity). Training notes are Markdown files an agent can read and write — persistent, tagged, activity-linked memory that survives across sessions.
- **Same data, always.** The dashboard and the CLI are two views into the same truth. If you can see it in the browser, an agent can query it from the terminal.
- **Everything is local.** Your data lives in `~/.fitops/fitops.db`. No cloud, no subscriptions.
- **Strava sync today, more providers coming.** Authenticate once with Strava and run `fitops sync run` for fresh data. Direct GPX / TCX / FIT file import and native Garmin, Coros, Apple Health, and Huawei sync are on the roadmap.
- **Async-first.** Built on `httpx` and `aiosqlite` for non-blocking I/O throughout.

## How FitOps Compares

> ✅ Supported · ⚡ Partial / limited · ❌ Not available · 🔜 Planned
>
> Based on real user experiences from r/running, r/cycling, r/triathlon, the Intervals.icu forum, TrainerRoad, and Slowtwitch. See **[docs/comparison.md](docs/comparison.md)** for the full breakdown with sources.

| | FitOps | TrainingPeaks | Intervals.icu | Strava | Garmin Connect |
|---|---|---|---|---|---|
| **Price** | Free | ~$135/yr | Free | ~$132/yr | Free (device req.) |
| **Open source** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Local / offline** | ✅ | ❌ | ❌ | ❌ | ⚡ device only |
| **Data ownership** | ✅ Your machine | ❌ | ❌ | ❌ Sold to 3rd parties | ⚡ |
| **Open API / scripting** | ✅ Native CLI | ❌ | ✅ documented | ✅ rate-limited | ❌ $5K fee |
| **LLM / AI agent native** | ✅ Designed for it | ❌ | ⚡ via API | ❌ | ❌ |
| **Training load (CTL/ATL/TSB)** | ✅ | ✅ | ✅ | ⚡ premium | ⚡ own model |
| **VO2max estimation** | ✅ 3-formula composite | ❌ | ✅ | ⚡ premium | ✅ on-device |
| **HR + pace zones** | ✅ LTHR/MaxHR/HRR | ✅ | ✅ | ⚡ premium | ✅ |
| **Workout compliance scoring** | ✅ per-segment | ✅ premium | ✅ | ❌ | ✅ on-device |
| **Race simulation (per-km splits)** | ✅ full engine | ⚡ pace calc | ❌ | ❌ | ❌ |
| **Weather-adjusted pace (WAP)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Workout simulation on course** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Training calendar / planner** | ❌ | ✅ | ✅ | ❌ | ✅ |
| **Coach–athlete platform** | ✅ AI / agent coach | ✅ human coach | ✅ human coach | ❌ | ❌ |
| **Mobile app** | ❌ | ✅ | ❌ | ✅ | ✅ |
| **Social / segments / community** | ❌ | ❌ | ❌ | ✅ core feature | ⚡ |
| **Device integrations** | 1 (5+ 🔜) | 80+ | 15+ | 10+ | Garmin only |
| **HRV / sleep / body battery** | ❌ | ❌ | ❌ | ❌ | ✅ |

**What the community says:** TrainingPeaks raised prices to ~$135/yr in April 2025 and is widely described as stagnating — the most common reason users cite for switching to Intervals.icu, which covers the same analytics for free. Strava has faced repeated privacy controversies including selling user location data to governments and a 2025 incident where it published private coaching notes without consent. Garmin Connect's API requires a $5,000 fee and is effectively closed to personal use.

**FitOps unique capabilities** not found in any alternative:

- **Weather-Adjusted Pace (WAP)** — per-activity historical weather from Open-Meteo (no API key), WBGT heat stress model, Pugh 1971 wind drag model. Makes a hot humid run directly comparable to a cool calm one.
- **True Pace** — single effort-normalized metric combining grade (GAP) and weather (WAP) adjustments, enabling cross-season VO2max trending without weather noise.
- **Race simulation engine** — per-km split plan adjusted for elevation, temperature, humidity, and wind per segment. Supports pacer strategy (sit-then-push) and forecast weather for race day.
- **Workout simulation on course** — simulate how a structured workout plays out on a GPX course with terrain and weather adjustments per segment.
- **LLM-native output** — every CLI command returns structured JSON with `_meta` blocks, explicit units in field names, and `data_availability` hints so any AI agent can chain commands without parsing hacks.
- **Persistent agent memory** — training notes are Markdown files in `~/.fitops/notes/`, tagged and optionally linked to activities. An AI agent can write observations, flag patterns, and read them back in future sessions — durable memory that outlives any single conversation.

![FitOps vs Alternatives](https://raw.githubusercontent.com/brunov21/fitops/main/docs/official/assets/comparison-animated-feature-tour.gif)

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — Foundation | ✅ Done | Auth, sync, activities, athlete profile |
| 2 — Analytics | ✅ Done | CTL/ATL/TSB, VO2max, LT1/LT2 thresholds, dashboard |
| 3 — Workouts | ✅ Done | Workout plans, compliance scoring, simulation |
| 4 — Multi-Provider | 🔜 Planned | GPX / TCX / FIT file import; Garmin, Coros, Apple Health, Huawei native sync |
| 5 — Cloud Backup | 🔜 Planned | Google Drive, OneDrive, Dropbox, Mega |
| 6 — Notes | ✅ Done | Markdown training notes with tags and activity linking |
| 7 — Weather-Adjusted Pace | ✅ Done | WAP, True Pace, Open-Meteo historical/forecast weather |
| 8 — Race Simulation | ✅ Done | Course import, per-split pacing, pacer strategy |

## Quick Setup for AI Agents

> **One command installs FitOps _and_ places the skill in the right directory for your agent.**

```bash
curl -fsSL https://raw.githubusercontent.com/brunov21/fitops/main/install.sh | bash
```

The script auto-detects Claude Code, Cursor, Codex, Windsurf, Cline, OpenCode, and GitHub Copilot. To target a specific agent:

```bash
AGENT=cursor  bash <(curl -fsSL https://raw.githubusercontent.com/brunov21/fitops/main/install.sh)
AGENT=codex   bash <(curl -fsSL https://raw.githubusercontent.com/brunov21/fitops/main/install.sh)
AGENT=claude  bash <(curl -fsSL https://raw.githubusercontent.com/brunov21/fitops/main/install.sh)
```

**What the script does:**
1. Checks for `uvx` → installs via `uvx fitops` (isolated, no global install)
2. Falls back to `pip install fitops` if Python 3.11+ is available
3. Errors with instructions if neither is found
4. Downloads `.claude/commands/fitops.md` from this repo into every detected agent directory
5. Prints the Strava auth steps so you're never left guessing

**After installation:**

```bash
fitops auth login    # Enter your Strava Client ID + Secret when prompted
fitops sync run      # Pull your activity history
```

> Need a Strava API key? Go to [strava.com/settings/api](https://www.strava.com/settings/api)
> and follow the [full authentication guide](https://brunov21.github.io/fitops/getting-started/authentication).

Then invoke the skill from Claude Code with `/fitops <your question>` — it has the full command reference, error recovery table, and coaching workflows built in.

The skill uses `fitops notes` as persistent memory: observations written in one session are readable in the next via `fitops notes list --tag <tag>`.

---

## Installation

**Requirements:** Python 3.11+ (or [uv](https://docs.astral.sh/uv/) — manages Python for you)

### Recommended — one-line installer (CLI + skill)

```bash
curl -fsSL https://raw.githubusercontent.com/brunov21/fitops/main/install.sh | bash
```

Installs FitOps and places the agent skill file for every detected coding assistant. See [Quick Setup for AI Agents](#quick-setup-for-ai-agents) above.

### Run without installing — uvx

```bash
uvx fitops auth login
uvx fitops sync run
uvx fitops dashboard serve
```

[`uvx`](https://docs.astral.sh/uv/guides/tools/) runs FitOps in an isolated environment. Install `uv` once with `curl -LsSf https://astral.sh/uv/install.sh | sh`.

### Install from PyPI

```bash
pip install fitops
```

### Install from source

```bash
git clone https://github.com/brunov21/fitops.git
cd fitops
pip install -e .
```

## Quick Start

### Start the Dashboard

```bash
fitops dashboard serve
# → Opens http://localhost:8888
```

The dashboard covers: activity history, analytics (training load, VO2max, trends, performance), workouts, training notes, weather conditions, and race course simulation.

### 1. Create a Strava API Application

To ensure the best experience and bypass rate limits, beta users must use their own Strava API credentials. Follow the [Strava Getting Started Guide](https://developers.strava.com/docs/getting-started/) to create an app.

Go to [https://www.strava.com/settings/api](https://www.strava.com/settings/api) and use **these exact settings**:

| Field | Value |
|-------|-------|
| Application Name | `Surge` |
| Category | `Performance Analysis` |
| Website | `https://brunov21.github.io/Surge/` |
| Authorization Callback Domain | `mclovinittt-kinetic-run-api.hf.space` |

Copy your **Client ID** and **Client Secret** from the Strava API Settings page. See the [full authentication guide](https://brunov21.github.io/fitops/getting-started/authentication) for details.

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
fitops sync streams      # Backfill GPS/HR streams for all activities
fitops sync status       # Show sync state
```

### 4. Query Your Data

```bash
# List recent activities (Rich table)
fitops activities list
fitops activities list --sport Run --limit 50 --after 2026-01-01

# Full detail for one activity (JSON)
fitops activities get 12345678901

# Stream data — HR, pace, power over time (JSON)
fitops activities streams 12345678901

# Athlete profile and physiology settings
fitops athlete profile
fitops athlete stats
fitops athlete zones
fitops athlete set --ftp 280 --max-hr 185
```

![fitops activities list — Rich terminal output](https://raw.githubusercontent.com/brunov21/fitops/main/docs/official/assets/cli-output-activities-list.png)

## Commands Reference

### `fitops auth` — Authentication

```
fitops auth login               Authenticate with Strava (OAuth)
fitops auth logout              Revoke token and clear credentials
fitops auth status              Show token validity and athlete info
fitops auth refresh             Force token refresh
```

### `fitops sync` — Data Sync

```
fitops sync run                 Incremental sync (since last sync − 3 days)
fitops sync run --full          Full historical sync
fitops sync run --after DATE    Sync from specific date (YYYY-MM-DD)
fitops sync streams             Backfill GPS/HR/power streams for all activities
fitops sync status              Show sync state and last sync timestamp
```

### `fitops activities` — Activity Data

```
fitops activities list                              Last 20 activities (Rich table)
fitops activities list --sport Run --limit 50       Filter by sport type
fitops activities list --after 2026-01-01           Filter by date
fitops activities get ID                            Full activity detail (JSON)
fitops activities streams ID                        Time-series stream data (JSON)
```

### `fitops athlete` — Athlete Profile

```
fitops athlete profile                              Profile + bikes/shoes (Rich)
fitops athlete stats                                Cumulative Strava statistics (JSON)
fitops athlete zones                                HR and power training zones (Rich)
fitops athlete set --ftp N --max-hr N               Set physiology values for analytics
fitops athlete equipment                            Equipment with distance and activity counts
```

### `fitops analytics` — Training Analytics

```
fitops analytics training-load                      CTL/ATL/TSB trend (last 90 days, Rich)
fitops analytics training-load --today              Today's snapshot: fitness, fatigue, form
fitops analytics vo2max                             VO2max estimate from recent hard efforts
fitops analytics zones                              Heart rate zone boundaries
fitops analytics zones --method lthr                Zone method: lthr | max_hr | hrr
fitops analytics trends                             Volume, consistency, seasonal patterns
fitops analytics performance                        Running economy, FTP, efficiency scores
fitops analytics power-curve                        Mean maximal power + critical power model
fitops analytics pace-zones                         Show/configure running pace zones
fitops analytics snapshot                           Compute and save today's analytics snapshot
```

Output example (`training-load --today`):
```
Training Load  2026-03-19

  CTL (Fitness)   32.5
  ATL (Fatigue)   32.0
  TSB (Form)      +0.5  [Fresh — optimal race readiness window]
  7d Ramp Rate    +12.88%
```

![Training Load Dashboard](https://raw.githubusercontent.com/brunov21/fitops/main/docs/official/assets/dashboard-training-load-detailed.png)

### `fitops workouts` — Workout Plans & Compliance

Workouts are Markdown files in `~/.fitops/workouts/` with optional YAML frontmatter. Segments can be defined as time-in-zone, pace-range, or HR-range steps.

```
fitops workouts list                                List workout files (JSON)
fitops workouts show NAME                           Display workout definition (Rich)
fitops workouts create                              Create a workout from a JSON definition
fitops workouts link NAME ACTIVITY_ID               Link a workout to a completed activity
fitops workouts get ACTIVITY_ID                     Workout linked to a specific activity (JSON)
fitops workouts history                             All linked workouts with compliance scores
fitops workouts compliance NAME                     Score each segment vs actual HR stream
fitops workouts unlink NAME                         Remove workout–activity link
fitops workouts simulate NAME                       Simulate workout on a course (see below)
```

#### Workout Simulation

Simulate how your workout will play out on a specific course — per-segment paces adjusted for terrain grade and weather:

```bash
fitops workouts simulate threshold-tuesday --course 3
fitops workouts simulate tempo-run --activity 17716814972   # use any Strava activity as course
fitops workouts simulate long-run --course 1 --base-pace 5:30
fitops workouts simulate tempo-run --course 3 --temp 28 --humidity 70
fitops workouts simulate long-run --course 1 --date 2026-04-06 --hour 8  # auto-fetch weather
```

![Workout Compliance Scoring](https://raw.githubusercontent.com/brunov21/fitops/main/docs/official/assets/dashboard-workout-compliance.png)

### `fitops race` — Race Courses & Simulation

Import courses from `.gpx`, `.tcx`, Strava activity URLs, or Strava activity IDs.

```
fitops race import FILE_OR_URL --name "Berlin Marathon"     Import a race course
fitops race import --activity 17716814972 --name "Local 10K"  Import from Strava activity
fitops race courses                                          List all imported courses (JSON)
fitops race course ID                                        Course profile + per-km segments
fitops race delete ID                                        Remove a course
fitops race splits ID --target-time 3:15:00                 Quick even-split table
fitops race simulate ID --target-time 3:15:00               Full simulation (Rich table)
fitops race simulate ID --target-pace 4:37
fitops race simulate ID --target-time 3:15:00 --pacer-pace 4:40 --drop-at-km 35
fitops race simulate ID --target-time 3:15:00 --temp 22 --humidity 65 --wind 3.5
fitops race simulate ID --target-time 3:15:00 --date 2026-10-25 --hour 9  # forecast weather
```

Output example (race simulate):
```
12KM Salvaterra — Simulation  4:52/km avg
 km  | Elev  | Grade  | Headwind   | Effects        | Target Pace | Split   | Elapsed
 1   | +18m  | +1.8%  | 3.2 m/s ↑ | hill +3% env+2% | 5:04/km    | 5:04    | 0:05:04
 2   | -6m   | -0.6%  | 1.1 m/s → |  —             | 4:51/km    | 4:51    | 0:09:55
 ...
```

![Race Simulation Results](https://raw.githubusercontent.com/brunov21/fitops/main/docs/official/assets/dashboard-race-simulate-results.png)

### `fitops weather` — Activity Weather

Fetches historical and forecast weather from Open-Meteo (no API key required).

```
fitops weather fetch ACTIVITY_ID                    Fetch + store weather for one activity
fitops weather fetch --all                          Backfill weather for all activities
fitops weather show ACTIVITY_ID                     Display conditions + WAP factors
fitops weather forecast --lat L --lon L --date D    Race-day forecast + pace adjustment
fitops weather set ACTIVITY_ID --temp 28 --humidity 70 --wind 12 --wind-dir 270
```

### `fitops notes` — Training Notes

Markdown notes stored in `~/.fitops/notes/` — tagged, optionally linked to activities, queryable via CLI or browsable in the dashboard.

```
fitops notes create --title "Post-race thoughts" --tags race,review
fitops notes create --activity 12345678 --tags fatigue
fitops notes list                                   All notes (newest first)
fitops notes list --tag threshold                   Filter by tag
fitops notes get SLUG                               Display full note content
fitops notes edit SLUG                              Open in $EDITOR, then re-sync DB
fitops notes delete SLUG                            Remove note file and DB row
fitops notes tags                                   All tags with usage counts
fitops notes sync                                   Re-index note files into DB
```

### `fitops dashboard` — Local Dashboard

> **Dashboard = human interface. CLI = agent interface. Every feature is available on both — 1:1 parity.**
>
> If you can chart it in the browser, an agent can query it from the terminal. If an agent can query it, a human can see it visually. No analytics are CLI-only; no visualisations are dashboard-only.

```
fitops dashboard serve                              Start dashboard at http://localhost:8888
fitops dashboard serve --port 8080                  Custom port
```

**Dashboard pages and their CLI equivalents:**

| Dashboard page | URL | Equivalent CLI command |
|----------------|-----|------------------------|
| Overview | `/` | `fitops analytics snapshot` |
| Activities | `/activities` | `fitops activities list / get ID` |
| Training Load | `/analytics/training-load` | `fitops analytics training-load` |
| Trends | `/analytics/trends` | `fitops analytics trends` |
| Performance | `/analytics/performance` | `fitops analytics performance` |
| Workouts | `/workouts` | `fitops workouts list / compliance ID` |
| Workout Simulate | `/workouts/simulate` | `fitops workouts simulate NAME --course ID` |
| Notes | `/notes` | `fitops notes list / get SLUG` |
| Weather | `/weather` | `fitops weather show ID / fetch --all` |
| Race Courses | `/race` | `fitops race courses` |
| Course Detail | `/race/course/ID` | `fitops race course ID` |
| Race Simulate | `/race/simulate/ID` | `fitops race simulate ID --target-time H:MM:SS` |
| Import Course | `/race/import` | `fitops race import FILE --name "..."` |
| Athlete Profile | `/profile` | `fitops athlete profile / zones / equipment` |

## Storage Layout

```
~/.fitops/
├── config.json          # Strava credentials + physiology settings
├── sync_state.json      # Sync history and last sync timestamp
├── fitops.db            # SQLite database (all data)
├── workouts/            # Markdown workout definition files
└── notes/               # Markdown training note files
```

Override the base directory with the `FITOPS_DIR` environment variable.

## Output Format

FitOps uses **Rich** for human-facing output (formatted tables, colour-coded metrics, panels). Commands that return structured data for agent consumption can output **JSON** with a `_meta` block by passing the `--json` flag:

```json
{
  "_meta": {
    "tool": "fitops",
    "version": "0.1.0",
    "generated_at": "2026-03-19T22:00:00+00:00",
    "total_count": 3,
    "filters_applied": {"sport_type": "Run"}
  },
  "activities": [
    {
      "strava_activity_id": 12345678901,
      "name": "Morning Run",
      "sport_type": "Run",
      "start_date_local": "2026-03-19T07:30:00",
      "duration": {"moving_time_seconds": 3720, "moving_time_formatted": "1:02:00"},
      "distance": {"meters": 10250, "km": 10.25},
      "pace": {"average_per_km": "6:03"},
      "heart_rate": {"average_bpm": 148, "max_bpm": 172},
      "data_availability": {
        "has_heart_rate": true,
        "has_power": false,
        "streams_fetched": true
      }
    }
  ]
}
```

Design principles:
- Units explicit in every field name (`_m`, `_km`, `_s`, `_bpm`)
- Gear IDs resolved to names
- Paces formatted as `"6:03"` (not raw m/s)
- `data_availability` tells an agent what additional detail can be fetched

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE)
