---
phase: 08-race-simulation-pacing
plan: "01"
subsystem: race
tags: [tdd, fixtures, dependencies, scaffold]
dependency_graph:
  requires: []
  provides:
    - gpxpy and tcxreader installed in project venv
    - tests/fixtures/sample.gpx (valid GPX 1.1, 5 trackpoints)
    - tests/fixtures/sample.tcx (valid TCX 2, 5 trackpoints)
    - tests/test_race.py (11 failing test stubs — RED state)
  affects:
    - 08-03-PLAN.md (course_parser module must make test_parse_gpx/tcx/mapmyrun pass)
    - 08-04-PLAN.md (simulation module must make remaining 8 tests pass)
tech_stack:
  added:
    - gpxpy>=1.6.2 (GPX file parsing)
    - tcxreader>=0.4.11 (TCX file parsing)
  patterns:
    - TDD RED/GREEN/REFACTOR cycle — tests written before implementation
    - Fixture-based test data (XML files, not inline strings)
key_files:
  created:
    - tests/test_race.py
    - tests/fixtures/sample.gpx
    - tests/fixtures/sample.tcx
  modified:
    - pyproject.toml
decisions:
  - "Tests use module-level imports (not lazy) so collection failure is immediate and unambiguous"
  - "Fixture files are real XML files on disk rather than inline strings to test actual file I/O paths"
metrics:
  duration_s: 166
  tasks_completed: 3
  tasks_total: 3
  files_changed: 4
  completed_date: "2026-03-19"
requirements:
  - RACE-01
  - RACE-02
  - RACE-03
---

# Phase 08 Plan 01: Test scaffold, fixtures, and new deps (gpxpy, tcxreader) Summary

**One-liner:** TDD Wave 0 scaffold — gpxpy+tcxreader added, GPX/TCX fixtures created, 11 failing test stubs written covering all race simulation behaviors.

## What Was Built

Installed two new parsing libraries (gpxpy, tcxreader) as project dependencies, created minimal but valid GPX 1.1 and TCX 2 fixture files with 5 trackpoints each, and wrote 11 failing test stubs in `tests/test_race.py`. All tests deliberately fail with `ModuleNotFoundError: No module named 'fitops.race'` — the correct RED state for TDD Wave 0.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add gpxpy and tcxreader to pyproject.toml | 3ccd580 | pyproject.toml |
| 2 | Create GPX and TCX fixture files | eced620 | tests/fixtures/sample.gpx, tests/fixtures/sample.tcx |
| 3 | Write failing test stubs (RED state) | c65c3a8 | tests/test_race.py |

## Tests Written (11 total — all RED)

- `test_parse_gpx` — expects 5 dicts with lat/lon/elevation_m/distance_from_start_m
- `test_parse_tcx` — expects >=3 points, non-zero lat
- `test_parse_mapmyrun_html` — scrapes mock window.__STATE__ JSON
- `test_km_segments` — 2 segments from 2km flat course, checks km/distance_m/grade/bearing keys
- `test_gap_factor` — flat=1.0, 10% grade≈1.22, negative grade<1.0
- `test_grade_clamp` — grade capped at ±45% (gap_factor(0.50)==gap_factor(0.45))
- `test_even_split_total_time` — flat 5km, sum of segment times within 1s of target
- `test_even_split_total_time_hilly` — hilly 5km, exercises scale normalisation path
- `test_negative_split_halves` — second half avg pace < first half avg pace
- `test_pacer_mode_total_time` — sit_time + push_time == target (within 1s)
- `test_pacer_too_slow_error` — raises ValueError("too slow") when pacer pace exceeds target

## Verification

```
python -c "import gpxpy; import tcxreader; print('ok')"  # → ok
ls tests/fixtures/  # → sample.gpx  sample.tcx
pytest tests/test_race.py 2>&1 | grep ModuleNotFoundError  # → ModuleNotFoundError: No module named 'fitops.race'
pytest tests/ --ignore=tests/test_race.py -q  # → 195 passed
```

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- [x] pyproject.toml has gpxpy>=1.6.2 and tcxreader>=0.4.11
- [x] Both libraries importable
- [x] tests/fixtures/sample.gpx exists and parses via gpxpy
- [x] tests/fixtures/sample.tcx exists
- [x] tests/test_race.py has 11 test functions
- [x] All 11 tests in RED state (ModuleNotFoundError on fitops.race)
- [x] Existing 195 tests still pass
- [x] Commits: 3ccd580, eced620, c65c3a8
