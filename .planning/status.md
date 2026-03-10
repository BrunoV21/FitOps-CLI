# FitOps-CLI — Session Status

**Last updated:** 2026-03-10
**Branch:** main

---

## Phase 1 — Foundation ✅ COMPLETE

All Phase 1 deliverables shipped and verified.

### What Was Built

**Project scaffolding**
- `pyproject.toml` — `fitops` entry point, all deps (`typer`, `httpx`, `sqlalchemy[asyncio]`, `aiosqlite`, `pydantic`, `structlog`)
- Package installs via `pip install -e .`

**Config layer** (`fitops/config/`)
- `settings.py` — `FitOpsSettings` reads/writes `~/.fitops/config.json`; `get_settings()` singleton
- `state.py` — `SyncState` reads/writes `~/.fitops/sync_state.json`; tracks `last_sync_at`, sync history

**Utils layer** (`fitops/utils/`)
- `exceptions.py` — `FitOpsError`, `StravaAuthError`, `SyncError`, `ConfigError`, `NotAuthenticatedError`
- `logging.py` — structlog setup
- `cache.py` — `@cached` decorator over `functools.lru_cache` with `clear_all_caches()` registry

**Database layer** (`fitops/db/`)
- `base.py` — SQLAlchemy `DeclarativeBase`
- `session.py` — `get_async_session()` async context manager (commit/rollback)
- `migrations.py` — `init_db()` via `Base.metadata.create_all()`
- Models: `Athlete`, `Activity`, `ActivityStream`, `ActivityLap`
- Stub tables (no logic): `WorkoutCourse`, `Workout`, `AnalyticsSnapshot`

**Strava layer** (`fitops/strava/`)
- `oauth.py` — `StravaOAuth` + `LocalCallbackServer` (asyncio, port 8080), `validate_strava_token()` (5-min buffer), full login flow
- `client.py` — `StravaClient` (httpx, auto-refresh, all 7 endpoints)
- `sync_engine.py` — `SyncEngine.run()`: incremental sync with 3-day overlap, upsert athlete + activities

**Output layer** (`fitops/output/`)
- `formatter.py` — `format_activity_row()`, `make_meta()`, pace/duration formatters
- `schemas.py` — Pydantic output schemas

**CLI layer** (`fitops/cli/`)
- `auth.py` — `login`, `logout`, `status`, `refresh`
- `sync.py` — `run` (--full, --after), `status`
- `activities.py` — `list`, `get`, `streams`, `laps`
- `athlete.py` — `profile`, `stats`, `zones`
- `workouts.py` — Phase 3 stubs

**Documentation**
- `README.md` — full user-facing docs
- `docs/strava-endpoints.md` — all 10 Strava endpoints with params, scopes, rate limits
- `docs/architecture.md` — design decisions, module map, data flow
- `docs/oauth-flow.md` — step-by-step OAuth walkthrough
- `docs/output-format.md` — LLM-friendly JSON spec with full activity object
- `docs/roadmap.md` — Phase 2 (analytics) and Phase 3 (workouts) previews

**Tests** — 18/18 passing
- `test_oauth.py` — token validation (5 tests)
- `test_models.py` — cadence doubling, Athlete/Activity factory methods (5 tests)
- `test_output.py` — formatting functions, activity row formatter (5 tests)
- `test_sync.py` — overlap constants (2 tests)

### Known Issue Fixed
- SQLAlchemy `Real` → `Float` (not exported at top level in SQLAlchemy 2.x)

---

## What's Next — Phase 2: Analytics

**Planned commands:**
```
fitops analytics training-load     # CTL / ATL / TSB trend
fitops analytics vo2max            # VO2max estimate
fitops analytics zones             # LT1 / LT2 zone boundaries
```

**Files to create:**
- `fitops/analytics/__init__.py`
- `fitops/analytics/training_load.py` — TSS, CTL (42-day EWMA α≈0.0465), ATL (7-day EWMA α≈0.25), TSB
- `fitops/analytics/vo2max.py` — VDOT 50% + McArdle 30% + Costill 20-40% weighted
- `fitops/analytics/zones.py` — LTHR method (5-zone), max_hr method, Karvonen/HRR
- `fitops/cli/analytics.py` — analytics command group
- Populate `analytics_snapshots` table (stub table already created)

**Key algorithms from KineticRun to port:**
- `app/analytics/training_load.py` — CTL/ATL EWMA, sport-specific TSS weights
- `app/analytics/vo2max.py` — 3-formula weighted composite, confidence scoring
- `app/analytics/zone_calculator.py` — LTHR/max_hr/HRR zone methods

**User needs to provide (or infer from data):**
- `max_hr` — for max_hr and Karvonen zone methods
- `resting_hr` — for Karvonen method
- `lthr` (Lactate Threshold HR) — for LTHR method
- `threshold_pace` — for running TSS calculation
- `ftp` — for cycling power-based TSS

These could be stored as new columns in `athletes` table or a separate `athlete_settings.json` in `.fitops/`.

---

## Phase 3: Workouts (Future)

- Full `WorkoutCourse` + `Workout` logic (stub tables already created)
- Compliance scoring engine
- Equipment mileage tracking via `gear_id`

---

## File Structure (Current)

```
FitOps-CLI/
├── README.md
├── pyproject.toml
├── .gitignore
├── .planning/
│   └── status.md              ← YOU ARE HERE
├── docs/
│   ├── strava-endpoints.md
│   ├── architecture.md
│   ├── oauth-flow.md
│   ├── output-format.md
│   └── roadmap.md
├── fitops/
│   ├── __init__.py
│   ├── cli/          auth, sync, activities, athlete, workouts (stub)
│   ├── strava/       oauth, client, sync_engine
│   ├── db/           base, session, migrations, models/
│   ├── config/       settings, state
│   ├── output/       formatter, schemas
│   └── utils/        exceptions, logging, cache
└── tests/
    ├── test_oauth.py
    ├── test_models.py
    ├── test_output.py
    └── test_sync.py
```

## Verification Commands

```bash
# Install
pip install -e ".[dev]"

# CLI works
fitops --help
fitops auth --help

# Tests
pytest tests/ -v

# Authenticate (real Strava credentials needed)
fitops auth login

# Sync
fitops sync run

# Query
fitops activities list --sport Run --limit 5
fitops athlete profile
```
