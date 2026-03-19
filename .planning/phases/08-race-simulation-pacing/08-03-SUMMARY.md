---
phase: 08-race-simulation-pacing
plan: 03
subsystem: race
tags: [course-parser, gpx, tcx, mapmyrun, strava, segments]
dependency_graph:
  requires: [08-01, 08-02]
  provides: [fitops/race/course_parser.py, fitops/race/simulation.py (stub)]
  affects: [08-04-simulation-engine, 08-05-race-cli]
tech_stack:
  added: [gpxpy, tcxreader]
  patterns: [TypedDict, haversine, JSONDecoder.raw_decode, math.ceil segment bucketing]
key_files:
  created:
    - fitops/race/course_parser.py
    - fitops/race/simulation.py
  modified:
    - tests/fixtures/sample.tcx
decisions:
  - Simulation stub added to allow test_race.py collection without full plan 04 implementation
  - TCX fixture timestamps added — tcxreader crashes computing duration without Time elements
  - Grade clamped to [-0.45, 0.45] in build_km_segments per success_criteria spec
  - JSONDecoder().raw_decode() at brace position prevents regex group capture truncation for MapMyRun HTML
metrics:
  duration_s: 200
  completed_date: "2026-03-19"
  tasks_completed: 2
  files_created: 2
  files_modified: 1
---

# Phase 08 Plan 03: Course Parser Module Summary

**One-liner:** GPX/TCX/MapMyRun/Strava course import parsers with 1-km segment builder using JSONDecoder.raw_decode and haversine fallback.

## What Was Built

`fitops/race/course_parser.py` is the data-intake layer for the race simulation engine. It exports:

- `CoursePoint` — TypedDict with lat, lon, elevation_m, distance_from_start_m
- `detect_source(arg)` — dispatches to (mapmyrun|gpx|tcx|strava, value)
- `parse_gpx(file_path)` — tracks → routes → waypoints priority; cumulative distance via `distance_2d()`
- `parse_tcx(file_path)` — haversine fallback when tp.distance is None
- `parse_mapmyrun_html(html_str)` — `JSONDecoder().raw_decode()` at brace position to avoid regex truncation
- `parse_mapmyrun_url(url)` — async httpx fetch with login-redirect detection
- `parse_strava_activity(id, session)` — async; zips latlng/altitude/distance streams from ActivityStream table
- `build_km_segments(points)` — 1-km buckets with math.ceil, grade clamped to [-0.45, 0.45], bearing via compute_bearing
- `_fmt_pace`, `_fmt_duration`, `_parse_time`, `compute_total_elevation_gain` — formatter helpers

A minimal `fitops/race/simulation.py` stub was also created so pytest can collect `test_race.py` without plan 04 being complete.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement GPX, TCX, and MapMyRun parsers | 2e10e70 | fitops/race/course_parser.py, fitops/race/simulation.py, tests/fixtures/sample.tcx |
| 2 | Add formatter helpers to course_parser.py | 2e10e70 | fitops/race/course_parser.py |

## Verification Results

- `test_parse_gpx` — PASS
- `test_parse_tcx` — PASS
- `test_parse_mapmyrun_html` — PASS
- `test_km_segments` — PASS
- `test_gap_factor`, `test_grade_clamp` — fail with NotImplementedError (expected, plan 04 not yet done)
- Full suite (195 tests, excluding test_race.py) — all GREEN

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added simulation.py stub to enable test collection**
- **Found during:** Task 1 — running pytest
- **Issue:** `test_race.py` imports `from fitops.race.simulation import gap_factor, ...` at module level; pytest could not collect any test functions because the module didn't exist
- **Fix:** Created `fitops/race/simulation.py` with stub functions that raise `NotImplementedError`
- **Files modified:** fitops/race/simulation.py (created)
- **Commit:** 2e10e70

**2. [Rule 1 - Bug] Added Time elements to sample.tcx fixture**
- **Found during:** Task 1 — test_parse_tcx execution
- **Issue:** `tcxreader` crashed with `TypeError: unsupported operand type(s) for -: 'NoneType' and 'NoneType'` when computing duration because trackpoints had no `<Time>` elements
- **Fix:** Added `<Time>` elements at 30-second intervals to all 5 trackpoints in `tests/fixtures/sample.tcx`
- **Files modified:** tests/fixtures/sample.tcx
- **Commit:** 2e10e70

## Self-Check: PASSED
