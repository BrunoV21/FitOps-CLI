# FitOps CLI — Claude Code Instructions

## What This Project Is

Local-first fitness analytics tool. Syncs Strava activities to a local SQLite DB and exposes data through:
- **CLI** (`fitops <command>`) — for AI agents and scripting, always outputs JSON with `--json`
- **Dashboard** (`fitops dashboard serve` → `localhost:8888`) — browser UI for humans

Full agent guidelines and terminology: **read `AGENTS.md` before making any changes.**

---

## Commands You'll Use

```bash
pytest -v tests/                        # run all tests
pytest -v tests/test_analytics.py       # run one file
ruff check . && ruff format .           # lint + format
fitops dashboard serve                  # start dashboard
cd docs/official && npm run build       # build docs site
```

---

## The Non-Negotiable Rules

1. **Parity by default.** Every feature MUST exist in both the CLI and the dashboard. If a task mentions only one surface, implement both. Only skip one surface when the task explicitly says so.

2. **No logic duplication.** Shared computation lives in `fitops/analytics/`. CLI and dashboard handlers are thin — they call analytics modules, not duplicate them.

3. **Docs are required.** Every feature change MUST update `docs/official/`. See `AGENTS.md § Documentation Requirements` for the lookup table of which file to change.

4. **Tests are required.** Every feature MUST have tests: unit tests for logic, CLI tests for `--json` output shape, dashboard tests for HTTP 200. See `AGENTS.md § Testing Requirements`.

5. **Definition of done = logic + CLI + dashboard + docs + tests.** All five. Not four.

---

## Directory Map

```
fitops/
├── analytics/          # Shared computation — all business logic lives here
├── cli/                # Typer CLI handlers (thin — call analytics/)
├── dashboard/
│   ├── queries/        # SQL queries for dashboard routes
│   ├── routes/         # FastAPI route handlers (thin — call analytics/)
│   └── templates/      # Jinja2 HTML templates
├── db/                 # SQLModel models, migrations, session
└── output/             # Rich terminal formatters (CLI display layer)
tests/                  # pytest — one file per feature area
docs/official/          # VitePress docs site
├── commands/           # CLI command reference pages
├── dashboard/          # Dashboard page docs
├── concepts/           # Concept explanations (training load, zones, etc.)
└── output-examples/    # Sample CLI output
```

---

## When Adding a Feature

Follow this order — do not skip steps:

1. Logic in `fitops/analytics/`
2. Unit tests in `tests/test_<feature>.py`
3. CLI command in `fitops/cli/`
4. CLI tests (verify `--json` shape)
5. Dashboard route + template in `fitops/dashboard/`
6. Dashboard tests (HTTP 200 with and without data)
7. Wire nav in `fitops/dashboard/templates/base.html`
8. Update `docs/official/` (commands + dashboard pages)
9. Update `docs/official/.vitepress/config.mts` sidebar if a new doc page was added

---

## Never Do

- Duplicate logic between `cli/` and `dashboard/routes/`
- Make real network calls in tests (stub with `monkeypatch` / `respx`)
- Put raw SQL in CLI or dashboard handlers (use `fitops/dashboard/queries/`)
- Ship a feature that only works on one surface without an explicit exemption
- Skip the docs update
- Use `--no-verify` or bypass hooks

---

## Performance Rule: Compute Once at Sync, Read at Display

> **Expensive computations MUST be stored in the DB at sync time. Dashboard and CLI reads must never recompute what can be looked up.**

This is non-negotiable. The dashboard runs on every page load — recomputing EWMA warmups or running N+1 DB loops on every request kills responsiveness.

### The pattern

| When | What to do |
|------|------------|
| **Sync time** (`sync_engine.py`, `cli/sync.py`) | Compute derived values and persist them |
| **Read time** (dashboard route, CLI command) | SELECT the pre-computed value — no recomputation |

### Concrete rules

1. **CTL/ATL/TSB** — computed in `persist_training_load_snapshot()` after every sync, stored in `analytics_snapshots`. Dashboard reads that row; never calls `compute_training_load(days=1)` directly.

2. **VO2max per activity** — computed in `_fetch_streams_for_activities` from in-memory Strava stream data (zero extra DB queries), stored in `Activity.vo2max_estimate`. Dashboard reads that column; never calls `_estimate_from_streams` on page load.

3. **Aerobic / anaerobic scores** — same pattern: computed in `sync_engine.py`, stored on `Activity`. Do not recompute in routes.

4. **Any new metric that requires looping over activities or multi-day history** — follow the same pattern. Write a `persist_<metric>` function in `fitops/analytics/`, call it from the sync engine, read the cached value in dashboard/CLI.

### When adding a new computed metric

- Add a column to the relevant model (or a row to `analytics_snapshots`).
- Add the migration to `fitops/db/migrations.py`.
- Add `persist_<metric>()` to `fitops/analytics/`.
- Call it from `SyncEngine.run()` (or from `_fetch_streams_for_activities` if it needs stream data).
- Have the dashboard query read the cached value, with a lazy-compute fallback only for the cold-start case.

---

## Claude Code Notes

- A `/fitops` skill is available at `.claude/commands/fitops.md` — use it for FitOps-specific tasks.
- Memories for this project are stored in `~/.claude/projects/-Users-bv-mac-Desktop-repos-FitOps-CLI/memory/`.
- The `.planning/` directory contains phase plans and state — consult it for context on in-progress work before starting anything large.
