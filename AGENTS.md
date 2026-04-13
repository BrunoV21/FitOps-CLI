# FitOps Agent Guidelines

## Project Overview

FitOps CLI is a local-first fitness analytics tool. It syncs activities from Strava into a local SQLite database and exposes that data through two first-class interfaces: a **CLI** (for AI agents and scripting) and a **dashboard** (a local web UI for humans). No cloud account. No third-party storage. Everything runs on your machine.

**Tech stack:** Python 3.11+, Typer (CLI), Rich (terminal output), FastAPI + Jinja2 (dashboard), SQLModel + SQLAlchemy async (ORM), SQLite (`~/.fitops/fitops.db`), pytest (tests), VitePress (docs site).

## Common Commands

```bash
# Run tests
pytest -v tests/

# Run a single test file
pytest -v tests/test_analytics.py

# Lint / format (if configured)
ruff check .
ruff format .

# Start the dashboard
fitops dashboard serve

# Build the docs site
cd docs/official && npm run build
```

---

## Core Philosophy: One Dataset, Two Audiences

FitOps is built on a single principle: **your fitness data is yours**, and it should be equally accessible to you and to the AI agents working on your behalf.

There are two first-class consumers of FitOps data:

| Consumer | Interface | Interaction style |
|----------|-----------|-------------------|
| **You (human)** | Dashboard (browser) | Visual exploration, charts, filters |
| **AI Agent** | CLI + JSON | Programmatic querying, analysis, automation |

Both read from the same local SQLite database (`~/.fitops/fitops.db`). Neither has privileged access. The CLI and the dashboard are two views into the same truth.

---

## The Parity Rule — Default Behaviour

> **Every feature MUST be available in both the CLI and the dashboard unless you are explicitly told otherwise.**

This is the default. It is not optional. A feature is not complete until both surfaces expose it.

**CLI serves agents** — structured JSON output that AI can read, script, and reason about.  
**Dashboard serves humans** — visual output that a person can navigate, filter, and understand at a glance.

If a task description only mentions one surface, implement both anyway. If a task explicitly says "CLI only" or "dashboard only", that exemption applies to that task alone — the next related change MUST re-evaluate parity.

### What parity looks like

| What you build | CLI side | Dashboard side |
|----------------|----------|----------------|
| New metric (e.g. TSS) | `fitops analytics <metric>` command with `--json` | Chart or stat card on the relevant dashboard page |
| New filter | `--flag` option on the CLI command | Dropdown / date picker on the dashboard page |
| New data source | CLI queries + `--json` output | Dashboard page or widget |
| New computed value | Field in JSON output with explicit unit | Labelled value or column in the dashboard |
| Updated calculation | Updated CLI output | Updated dashboard display |

---

## Definition of Done

A feature is **done** when ALL FIVE of the following are true. Missing any one means it is not done:

1. **Logic** — implemented in `fitops/analytics/` (or the appropriate shared module), not duplicated in CLI or dashboard code.
2. **CLI** — a command in `fitops/cli/` that calls the shared logic and outputs JSON with a `_meta` block.
3. **Dashboard** — a route in `fitops/dashboard/routes/` and template in `fitops/dashboard/templates/` that calls the same shared logic.
4. **Docs** — the official documentation in `docs/official/` is updated or extended to cover the new behaviour (see [Documentation Requirements](#documentation-requirements)).
5. **Tests** — the test suite covers the new logic, CLI output, and dashboard route (see [Testing Requirements](#testing-requirements)).

Do not open a PR, mark a task complete, or declare a feature shipped if any of these five are missing.

---

## Shared Business Logic

CLI commands and dashboard routes MUST NOT duplicate logic. All computation lives in shared modules:

```
fitops/
├── analytics/          # Shared computation (training load, zones, VO2max, trends, etc.)
├── dashboard/
│   ├── queries/        # SQL queries used by dashboard routes (thin wrappers over analytics/)
│   └── routes/         # FastAPI route handlers — thin, call analytics/ modules
└── cli/                # Typer command handlers — thin, call analytics/ modules
```

A CLI command and a dashboard route covering the same metric must call the same underlying function. If you find yourself copying logic between `cli/` and `dashboard/routes/`, stop and extract it into `analytics/`.

---

## Performance Rule: Compute Once at Sync, Read at Display

> **Expensive computations MUST be stored in the DB at sync time. Page loads and CLI reads MUST never recompute what can be looked up.**

The dashboard runs on every navigation event. Recomputing multi-day EWMA warmups or running per-activity DB loops on every request will make the UI unresponsive.

### How it works

```
Sync time                     DB                      Read time
─────────────────────         ──────────────────────  ────────────────────────
SyncEngine.run()         →    activities.vo2max_est   ← dashboard / CLI SELECT
persist_training_load()  →    analytics_snapshots     ← dashboard / CLI SELECT
```

### Pre-computed values and where they live

| Metric | Stored in | Written by | Read by |
|--------|-----------|------------|---------|
| CTL / ATL / TSB | `analytics_snapshots` (sport_type=NULL) | `persist_training_load_snapshot()` → called from `SyncEngine.run()` | `get_current_training_load()` in `dashboard/queries/analytics.py` |
| VO2max per activity | `activities.vo2max_estimate` | `estimate_vo2max_from_stream_dict()` → called from `_fetch_streams_for_activities()` | `get_vo2max_history()` fast path |
| Aerobic score | `activities.aerobic_score` | `compute_aerobic_score()` → called in `SyncEngine._sync_activities_paginated()` | direct column read |
| Anaerobic score | `activities.anaerobic_score` | `compute_anaerobic_score()` → called in `SyncEngine._sync_activities_paginated()` | direct column read |

### Rules for new metrics

1. Add a column to the model **or** a row to `analytics_snapshots`.
2. Add the migration in `fitops/db/migrations.py`.
3. Write `persist_<metric>()` in `fitops/analytics/`.
4. Call it from `SyncEngine.run()` (or from `_fetch_streams_for_activities` if stream data is needed).
5. Dashboard/CLI queries read the cached column — with a lazy-compute fallback only for the first run before a sync.

**Never** call `compute_training_load(days=1)` or `_estimate_from_streams()` inside a route handler or CLI read path.

---

## Agent Interface Contract (CLI)

### Output format

All commands support `--json`. JSON output must include a `_meta` block:

```json
{
  "_meta": {
    "tool": "fitops",
    "version": "...",
    "generated_at": "ISO-8601 timestamp",
    "total_count": N,
    "filters_applied": {}
  },
  "<data_key>": [...]
}
```

### Field naming

- Units are explicit: `_seconds`, `_km`, `_bpm`, `_watts`
- Human-readable companions alongside raw values where useful: `"moving_time_seconds": 3720, "moving_time_formatted": "1:02:00"`
- IDs are resolved to names where possible (gear IDs → gear names)
- `data_availability` blocks indicate what additional detail can be fetched

### Agent-friendliness checklist

Before shipping a CLI command, confirm:

- [ ] The command runs with no interactive prompts
- [ ] `--json` output is valid JSON parseable without post-processing
- [ ] Output is deterministic given the same inputs
- [ ] All units are explicit and unambiguous in field names
- [ ] The `_meta` block describes which filters were applied
- [ ] A `data_availability` block tells an agent what to fetch next (if applicable)

---

## Dashboard Interface Contract

### Route structure

Routes live in `fitops/dashboard/routes/`. Each feature area gets its own module that mirrors the CLI command hierarchy:

```
CLI:        fitops analytics training-load
Dashboard:  /analytics  (training load section)

CLI:        fitops race simulate
Dashboard:  /race/simulate
```

### Human-friendliness checklist

Before shipping a dashboard page, confirm:

- [ ] The page shows a chart, table, or labelled values — not raw JSON
- [ ] Units are written in plain language ("beats per minute", not "bpm raw value")
- [ ] The page handles the empty state (no data synced yet) with a helpful message
- [ ] The page is reachable from the sidebar navigation
- [ ] Period / sport filters are present where relevant

---

## Documentation Requirements

> **Every feature change MUST include a documentation update. A PR with no doc change is incomplete.**

### Where the docs live

```
docs/official/
├── commands/       # One file per CLI command group (auth, sync, activities, …)
├── dashboard/      # One file per dashboard page (overview, analytics, race, …)
├── concepts/       # Explanations of underlying ideas (training load, zones, VO2max, …)
└── output-examples/ # Sample output from CLI commands
```

### What to update

| What you changed | Documentation to update |
|------------------|------------------------|
| New CLI command or flag | `docs/official/commands/<group>.md` |
| Changed CLI output format or field names | `docs/official/commands/<group>.md` + `docs/official/output-examples/<group>.md` if it has one |
| New dashboard page or screen | `docs/official/dashboard/<page>.md` (create if needed) + `docs/official/dashboard/index.md` page table |
| New dashboard UI control or widget | `docs/official/dashboard/<page>.md` |
| New concept or algorithm | `docs/official/concepts/<topic>.md` (create if needed) |
| Any of the above | Update `docs/official/.vitepress/config.mts` sidebar if a new page was added |

### How to write docs

- Write from the perspective of the person using the feature, not the person implementing it.
- For CLI pages: show the command signature, options table, and at least one realistic example.
- For dashboard pages: describe what the user sees and what they can do on the page — not the route handler or template structure.
- For concepts pages: explain the *why* and the *how* in plain language, with the formula or algorithm where it matters.
- Do not document implementation internals in official docs.

---

## Testing Requirements

> **Every feature MUST be covered by tests. "It works" is not a test.**

### Test locations

```
tests/
├── test_analytics.py       # Pure computation: formulas, calculations, edge cases
├── test_models.py          # DB model constraints, relationships
├── test_sync.py            # Data ingestion logic
├── test_weather.py         # Weather fetch and pace adjustment logic
├── test_workouts.py        # Workout parsing, linking, compliance scoring
├── test_race.py            # Course parsing, simulation, split generation
├── test_output.py          # CLI output formatting (rich text, JSON structure)
└── test_<feature>.py       # New feature tests go in a focused file
```

### What to test

**For every new analytics module (`fitops/analytics/`):**
- Core formula / calculation with known inputs and expected outputs
- Edge cases: zero values, missing data, single-activity inputs
- That the result type/shape is correct (field names, units)

**For every new CLI command:**
- `--json` output is valid JSON
- `--json` output contains a `_meta` block with required fields
- All supported flags produce the expected change in output
- The command exits cleanly (exit code 0) under normal conditions

**For every new dashboard route:**
- `GET /route` returns HTTP 200 when data exists
- `GET /route` returns HTTP 200 (with empty state, not 500) when no data exists
- POST/form routes return the expected redirect or response on valid input
- POST/form routes return a graceful error (not 500) on invalid input

**For new shared logic used by both CLI and dashboard:**
Write the tests once against the shared module, not duplicated per surface.

### Test style

- Use `pytest`. Tests live in `tests/`.
- Prefer plain functions over classes unless grouping is clearly warranted.
- Use fixtures for shared setup (db sessions, sample activities, mock weather responses).
- Do not mock the database for integration tests — use an in-memory SQLite instance.
- Keep tests fast: avoid network calls; use `monkeypatch` or `respx` to stub HTTP.
- Name tests descriptively: `test_ctl_increases_with_sustained_load`, not `test_ctl`.

---

## Adding a New Feature: Step-by-Step

Follow these steps in order. Do not skip steps or defer them to a follow-up PR.

1. **Implement shared logic** in `fitops/analytics/` (or extend an existing module).
2. **Write unit tests** for the logic in `tests/test_<feature>.py` before wiring it up.
3. **Add a CLI command** in `fitops/cli/` — thin handler, calls the shared logic, outputs JSON.
4. **Add a CLI test** — verify `--json` output shape and flag behaviour.
5. **Add a dashboard route** in `fitops/dashboard/routes/` and a template in `fitops/dashboard/templates/`.
6. **Add a dashboard query** in `fitops/dashboard/queries/` if the route needs SQL.
7. **Add a dashboard test** — verify HTTP 200 for the route with and without data.
8. **Wire navigation** — add the page to `fitops/dashboard/templates/base.html` sidebar.
9. **Update official docs** — update or create the relevant page(s) in `docs/official/`.
10. **Update the VitePress config** — add the new page to the sidebar in `docs/official/.vitepress/config.mts` if a new doc page was created.

---

## Boundaries — Never Do

- **Never duplicate logic** between `cli/` and `dashboard/routes/`. Extract shared code into `analytics/` first.
- **Never make network calls in tests.** Stub HTTP with `monkeypatch` or `respx`. Tests must pass offline.
- **Never put formatting or style rules in this file.** Those belong in `.ruff.toml` / pre-commit hooks, not here.
- **Never modify `~/.fitops/fitops.db` directly** in code outside of `fitops/db/`. All DB access goes through the session and model layer.
- **Never expose raw SQL to CLI or dashboard handlers.** SQL lives in `fitops/dashboard/queries/` or SQLModel query helpers.
- **Never skip the docs update.** A feature with no doc change is incomplete by definition.
- **Never ship a feature that only works on one surface** (CLI or dashboard) without an explicit exemption in the task description.

---

## Terminology

Domain terms used throughout this codebase:

| Term | Meaning |
|------|---------|
| **CTL** | Chronic Training Load — 42-day EWMA of daily TSS. Represents fitness base. |
| **ATL** | Acute Training Load — 7-day EWMA of daily TSS. Represents recent fatigue. |
| **TSB** | Training Stress Balance — CTL minus ATL. Positive = fresh, negative = fatigued. |
| **TSS** | Training Stress Score — effort score for a single activity (0–150+). |
| **LTHR** | Lactate Threshold Heart Rate — the HR at which lactate begins to accumulate. |
| **LT1 / LT2** | First and second lactate thresholds. LT2 ≈ LTHR. |
| **GAP** | Grade-Adjusted Pace — pace normalised for elevation gain/loss. |
| **WAP** | Weather-Adjusted Pace — pace normalised for temperature, humidity, and wind. |
| **True Pace** | GAP + WAP combined. The most accurate effort-normalised pace metric. |
| **WBGT** | Wet Bulb Globe Temperature — composite heat stress index used to flag running risk. |
| **VO2max** | Maximum oxygen uptake (ml/kg/min). Estimated from run activity data. |
| **MMP** | Mean Maximal Power — best average power at standard durations (power curve). |
| **CP** | Critical Power — the two-parameter aerobic ceiling model (`P = CP + W'/t`). |
| **W'** | W-prime — anaerobic work capacity in joules, from the CP model. |
| **HRR** | Heart Rate Reserve — zone method using (max HR − resting HR) as the range. |

---

## Why This Matters

An AI agent working on your training plan needs the same data quality and depth that you see on your dashboard. If the dashboard shows a Training Readiness score and the CLI does not, the agent is flying blind. If the CLI exposes raw streams but the dashboard does not visualize them, you are flying blind.

FitOps is a tool for human-AI collaboration over personal fitness data. That collaboration only works when both sides see the same picture — and when the code, docs, and tests are all in the same state.
