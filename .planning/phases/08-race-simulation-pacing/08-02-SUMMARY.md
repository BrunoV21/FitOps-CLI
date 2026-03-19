---
phase: 08-race-simulation-pacing
plan: 02
subsystem: database
tags: [sqlalchemy, sqlite, race-course, migrations]

# Dependency graph
requires:
  - phase: 08-01
    provides: Phase foundation — no prior model dependencies; Base and init_db pattern established in earlier phases

provides:
  - RaceCourse SQLAlchemy model with full schema (race_courses table)
  - fitops/race/ Python package directory
  - init_db() automatically creates race_courses on first run

affects:
  - 08-03 (course parser — imports RaceCourse to create records)
  - 08-04 (simulation engine — reads RaceCourse.get_km_segments())
  - 08-05 (CLI commands — uses RaceCourse.to_summary_dict())
  - 08-06 (dashboard — lists courses from race_courses table)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SQLAlchemy mapped_column pattern with Float (not Real) for numeric columns"
    - "JSON-as-Text storage via get_course_points() / get_km_segments() helpers"
    - "to_summary_dict() lightweight projection method for CLI list output"

key-files:
  created:
    - fitops/db/models/race_course.py
    - fitops/race/__init__.py
  modified:
    - fitops/db/migrations.py

key-decisions:
  - "Used Float (not Real) for all numeric columns — Real is not exported at SQLAlchemy top level"
  - "km_segments_json is nullable (Text, nullable=True) — populated at import time, not required for model creation"
  - "course_points_json is non-nullable — every course must have waypoints"
  - "Registered RaceCourse via import side-effect in migrations.py; no ALTER TABLE needed since race_courses is a brand-new table"

patterns-established:
  - "JSON-as-Text column pattern: store list[dict] as Text, deserialise in helper method on model"
  - "New table registration: add noqa F401 import to migrations.py; create_all handles it automatically"

requirements-completed: [RACE-01]

# Metrics
duration: 2min
completed: 2026-03-19
---

# Phase 08 Plan 02: RaceCourse Model and Migrations Summary

**SQLAlchemy RaceCourse model with 13 columns (JSON waypoint storage, km-segment cache) registered in migrations so init_db() auto-creates race_courses table.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-19T10:55:22Z
- **Completed:** 2026-03-19T10:56:44Z
- **Tasks:** 2 / 2
- **Files modified:** 3

## Accomplishments

### Task 1: Create RaceCourse SQLAlchemy model

Created `fitops/db/models/race_course.py` with the full RaceCourse model:
- 13 columns: `id`, `name`, `source`, `source_ref`, `file_format`, `total_distance_m`, `total_elevation_gain_m`, `num_points`, `start_lat`, `start_lon`, `course_points_json`, `km_segments_json`, `imported_at`
- All numeric columns use `Float` (not `Real`)
- `course_points_json` non-nullable; `km_segments_json` nullable
- Helper methods: `get_course_points()`, `get_km_segments()`, `to_summary_dict()`
- Created `fitops/race/__init__.py` as empty package marker

Commit: `8af52c0`

### Task 2: Register RaceCourse in migrations

Added single import line to `fitops/db/migrations.py` after AnalyticsSnapshot:
```python
from fitops.db.models.race_course import RaceCourse  # noqa: F401
```
`init_db()` now creates `race_courses` via `Base.metadata.create_all` with no ALTER TABLE needed. All 165 existing tests still pass.

Commit: `93a1c92`

## Deviations from Plan

None - plan executed exactly as written.

Note: The plan context mentioned adding the import after `ActivityWeather`, but `ActivityWeather` is not present in this codebase version. The import was correctly placed after `AnalyticsSnapshot` (the last model import), which is functionally equivalent.

## Verification Results

All checks passed:
- `python -c "from fitops.db.models.race_course import RaceCourse; print(RaceCourse.__tablename__)"` → `race_courses`
- `python -c "from fitops.db.migrations import init_db; init_db(); print('ok')"` → `ok`
- `pytest tests/ --ignore=tests/test_race.py -q` → `165 passed`
- `fitops/race/__init__.py` confirmed present

## Self-Check: PASSED
