# FitOps-CLI Architecture

## Design Goals

1. **LLM-first output** — every field is independently meaningful; units explicit; labels resolved
2. **Offline-first** — Strava is only contacted for auth and sync; all queries run locally
3. **Async throughout** — `httpx` for HTTP, `aiosqlite` + SQLAlchemy async for DB
4. **Single-user, single-database** — no sharding, no multi-tenancy complexity
5. **No heavy infrastructure** — `functools.lru_cache` instead of Redis; `asyncio` instead of Celery

## Module Map

```
fitops/
├── cli/            Typer command groups — thin wrappers over async business logic
├── strava/         Strava API layer: OAuth, HTTP client, sync engine
├── db/             SQLAlchemy models, async session, migrations (create_all on startup)
├── config/         FitOpsSettings (config.json) + SyncState (sync_state.json)
├── output/         LLM-friendly JSON formatting and Pydantic output schemas
└── utils/          Exceptions, logging (structlog), LRU cache registry
```

## Data Flow

```
fitops sync run
  │
  ├─ config/settings.py  →  read credentials from ~/.fitops/config.json
  ├─ config/state.py     →  read last_sync_at from ~/.fitops/sync_state.json
  ├─ strava/oauth.py     →  auto-refresh token if within 5-minute expiry buffer
  ├─ strava/client.py    →  GET /api/v3/athlete/activities (paginated)
  ├─ db/models/          →  upsert Athlete + Activity rows into fitops.db
  └─ config/state.py     →  write updated last_sync_at + sync history
```

## Storage Layout

### `~/.fitops/config.json`
Stores Strava OAuth credentials and user preferences. Written by `fitops auth login` and `fitops auth refresh`. Never committed to git (in `.gitignore`).

### `~/.fitops/sync_state.json`
Tracks incremental sync state: last sync timestamp, total activity count, and a ring buffer of the last 50 sync runs.

### `~/.fitops/fitops.db`
Single SQLite database containing:

| Table | Purpose |
|-------|---------|
| `athletes` | Athlete profile and equipment JSON |
| `activities` | All synced Strava activities |
| `activity_streams` | Time-series data per activity (HR, pace, power) |
| `activity_laps` | Lap splits per activity |
| `workout_courses` | Phase 3 stub — workout templates |
| `workouts` | Phase 3 stub — scheduled workout instances |
| `analytics_snapshots` | Phase 2 stub — daily CTL/ATL/TSB/VO2max |

## Caching

`fitops/utils/cache.py` provides a `@cached` decorator backed by `functools.lru_cache`. All registered caches are cleared on `fitops auth logout` via `clear_all_caches()`. This avoids stale zone or stats data after re-authentication.

## Token Lifecycle

1. **Login:** Browser OAuth → `LocalCallbackServer` on port 8080 captures code → exchange for tokens → save to `config.json`
2. **Auto-refresh:** Before every Strava API call, `validate_strava_token()` checks expiry with a 5-minute buffer. If expired, `refresh_access_token()` is called automatically and new tokens are saved.
3. **Logout:** `POST /oauth/deauthorize` → clear tokens from `config.json` → clear all LRU caches

## Incremental Sync

The 3-day overlap window (`OVERLAP_DAYS = 3`) ensures activities uploaded late (common with GPS watches syncing hours after a workout) are captured on the next sync run. The sync engine:

1. Reads `last_sync_at` from `sync_state.json`
2. Sets `after = last_sync_at - 3 days`
3. Pages through `/api/v3/athlete/activities` (up to 100 pages × 30 per page = 3,000 activities per run)
4. Upserts each activity by `strava_id`
5. Writes `sync_state.json` with new `last_sync_at = now()`
