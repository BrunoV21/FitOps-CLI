---
phase: 08-race-simulation-pacing
plan: "06"
subsystem: dashboard
tags: [fastapi, jinja2, chartjs, race, simulation, pacing, ui]
dependency_graph:
  requires: [08-05]
  provides: [race-dashboard-ui]
  affects: [fitops/dashboard/server.py, fitops/dashboard/templates/base.html]
tech_stack:
  added: []
  patterns:
    - FastAPI router with Jinja2Templates (register pattern)
    - Chart.js bar chart with color-coded bars and line overlay
    - O(n+m) single-pass elevation profile builder
    - Pacer mode split table with sit/push phase separator row
key_files:
  created:
    - fitops/dashboard/routes/race.py
    - fitops/dashboard/templates/race/index.html
    - fitops/dashboard/templates/race/course.html
    - fitops/dashboard/templates/race/simulate.html
  modified:
    - fitops/dashboard/server.py
    - fitops/dashboard/templates/base.html
decisions:
  - "Pacer mode chart uses null values past drop_at_km so the purple line terminates cleanly at the break point"
  - "Pace y-axis is reversed (lower s/km = faster = top) for intuitive reading"
  - "Pacer mode sit splits use constant pacer_pace_s; cumulative times computed inline in route to avoid extra simulation calls"
metrics:
  duration_s: 204
  completed_date: "2026-03-19"
  tasks_completed: 2
  files_created: 4
  files_modified: 2
---

# Phase 8 Plan 6: Race Dashboard UI Summary

**One-liner:** FastAPI race router + 3 Jinja2/Chart.js templates for course list, elevation profile, and color-coded pace simulation with pacer overlay.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Create FastAPI race router and register in dashboard app | 57f6e45 | fitops/dashboard/routes/race.py, fitops/dashboard/server.py, fitops/dashboard/templates/base.html |
| 2 | Create race HTML templates | 0058a7f | fitops/dashboard/templates/race/index.html, fitops/dashboard/templates/race/course.html, fitops/dashboard/templates/race/simulate.html |

## What Was Built

**`GET /race`** — Course list table with ID, Name, Source, Distance, Elevation Gain, Imported At, and action links (Profile / Simulate). Empty state guides user to `fitops race import`.

**`GET /race/{id}`** — Course profile page with:
- Stats summary cards (distance, elevation gain, source, GPS points)
- Chart.js line chart: elevation profile using O(n+m) single-pass pointer scan
- Per-km segment stats table (elevation gain, grade %, bearing °)
- "Simulate Race" CTA button

**`GET /race/{id}/simulate`** — Blank simulation form with collapsible pacer and weather sections.

**`POST /race/{id}/simulate`** — Runs simulation and renders:
- Results summary cards (distance, target finish, strategy, pacer pace if active)
- Chart.js bar chart: per-km target pace, color-coded green/orange/red vs. average
- Pacer mode: purple dashed horizontal line overlay from km 0 to drop_at_km
- Split detail table with sit/push phase separator row when pacer mode active

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

## Key Design Decisions

1. **Pacer chart line terminates at break point** — null values past `drop_at_km` so the purple overlay line ends cleanly rather than spanning the full chart.
2. **Y-axis reversed on pace chart** — lower s/km (faster) appears at the top, matching running convention.
3. **Pacer sit splits computed inline** — the route constructs sit-phase split dicts manually using `pacer_pace_s` rather than calling `simulate_splits` with a pacer pace, avoiding a separate simulation invocation and keeping the logic explicit.
4. **`_fmt_duration` imported inside POST handler** — avoids circular import at module scope while keeping the import co-located with its usage.

## Verification

- `python -c "from fitops.dashboard.routes.race import router, register; print('ok')"` — PASS
- `python -c "import os; assert all(...); print('templates ok')"` — PASS
- `pytest tests/ -q` — 206 passed

## Self-Check: PASSED

- fitops/dashboard/routes/race.py — FOUND
- fitops/dashboard/templates/race/index.html — FOUND
- fitops/dashboard/templates/race/course.html — FOUND
- fitops/dashboard/templates/race/simulate.html — FOUND
- Commit 57f6e45 — FOUND
- Commit 0058a7f — FOUND
