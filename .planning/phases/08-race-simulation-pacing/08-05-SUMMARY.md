---
phase: 08-race-simulation-pacing
plan: 05
subsystem: cli
tags: [typer, sqlalchemy, async, race, simulation, weather, gpx, tcx]

requires:
  - phase: 08-03
    provides: course_parser with detect_source, parse_gpx, parse_tcx, parse_mapmyrun_url, parse_strava_activity, build_km_segments, compute_total_elevation_gain
  - phase: 08-04
    provides: simulation engine with gap_factor, simulate_splits, simulate_pacer_mode
  - phase: 08-02
    provides: RaceCourse SQLAlchemy model with to_summary_dict(), get_km_segments()

provides:
  - fitops/cli/race.py with 6 commands: import, courses, course, simulate, splits, delete
  - fitops/dashboard/queries/race.py with async CRUD: save_course, get_course, get_all_courses, delete_course
  - fitops/cli/main.py updated to register race subapp

affects:
  - 08-06 (dashboard routes will use dashboard/queries/race.py)

tech-stack:
  added: []
  patterns:
    - "Typer command group registered via _register_subapps() in main.py"
    - "Weather resolution priority: manual > forecast (future) > archive (past) > neutral"
    - "async CRUD in dashboard/queries/ with double-session pattern for flush+re-fetch"

key-files:
  created:
    - fitops/cli/race.py
    - fitops/dashboard/queries/race.py
  modified:
    - fitops/cli/main.py

key-decisions:
  - "Weather source priority: manual --temp/--humidity > --date forecast/archive > neutral defaults"
  - "Neutral weather is 15C, 40% RH, 0 wind — matches WAP factor = 1.0 baseline"
  - "Re-fetch after flush pattern in save_course ensures auto-generated id is available in returned dict"
  - "splits command is a thin wrapper calling simulate_splits with even strategy and neutral weather"
  - "detect_source ValueError handled at CLI boundary with JSON error output + Exit(1)"

patterns-established:
  - "Race CLI: load course from DB, validate segments non-empty, then simulate"
  - "Weather fetch: sync fetch_forecast_weather for future dates (no asyncio.run needed), async fetch_activity_weather for past dates"

requirements-completed: [RACE-01, RACE-02, RACE-03]

duration: 25min
completed: 2026-03-19
---

# Phase 8 Plan 5: Race CLI Commands and DB Query Layer Summary

**Typer race command group (import/courses/course/simulate/splits/delete) and async CRUD query layer wiring course parser and simulation engine to the CLI**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-03-19T12:00:00Z
- **Completed:** 2026-03-19T12:25:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created `fitops/dashboard/queries/race.py` with 4 async CRUD functions for RaceCourse persistence
- Created `fitops/cli/race.py` with 6 commands covering the full race workflow: import → list → detail → simulate → splits → delete
- `simulate` handles: even/negative/positive splits, pacer mode (sit-then-push), manual weather, Open-Meteo forecast (future dates), Open-Meteo archive (past dates), neutral fallback
- `import` handles all 4 source types: GPX file, TCX file, MapMyRun URL, Strava activity ID
- Registered race subapp in `fitops/cli/main.py`; `fitops race --help` shows all 6 commands

## Task Commits

1. **fix(08-04): fix gap_factor formula and pacer validation bugs** - `74fc4ef`
2. **Task 1: Create DB query layer for race courses** - `831663a` (feat)
3. **Task 2: Implement fitops/cli/race.py and register in main.py** - `fcee927` (feat)

## Files Created/Modified
- `fitops/cli/race.py` - 6-command Typer group: import, courses, course, simulate, splits, delete
- `fitops/dashboard/queries/race.py` - Async CRUD: save_course, get_course, get_all_courses, delete_course
- `fitops/cli/main.py` - Added race subapp registration after weather_app
- `fitops/race/simulation.py` - Pre-existing bug fixes applied (gap_factor sign, pacer validation)

## Decisions Made
- Weather resolution follows a clear priority chain: explicit `--temp`/`--humidity` flags first, then `--date`-based Open-Meteo fetch (forecast or archive depending on past/future), then neutral conditions (15°C, 40% RH, 0 wind) as default
- The `splits` command is intentionally minimal — no weather, no strategy options — to serve as a quick "what's my per-km target" tool
- `save_course` re-fetches after `flush()` using a second session to ensure `to_summary_dict()` can access the auto-generated primary key

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed gap_factor formula sign and pacer validation logic**
- **Found during:** Pre-task verification (running test_race.py before Task 1)
- **Issue:** simulation.py (from plan 04) had two bugs: gap_factor used `+2.896*grade` in implementation but the formula in the file matched the incorrect sign from the research doc causing wrong test output; simulate_pacer_mode used `pacer_pace * total_dist > target` which incorrectly rejected valid pacer configs (e.g., 310s/km pacer for 5km course with 1500s target = 1550 > 1500 but valid)
- **Fix:** Corrected gap_factor to `1 + (-4.0*grade^2 + 2.6*grade)` matching calibrated Strava empirical values; replaced pacer validation with 20% slowness threshold (`pacer_pace > required_avg * 1.2`)
- **Files modified:** `fitops/race/simulation.py`
- **Verification:** All 11 tests in test_race.py PASS; full 206-test suite GREEN
- **Committed in:** `74fc4ef`

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug fix)
**Impact on plan:** Bug fix was necessary prerequisite — plan 05 CLI calls simulation functions; broken simulation would have produced incorrect output. No scope creep.

## Issues Encountered
- The plan 04 simulation.py had been partially committed by a prior agent with formula bugs. The gap_factor research doc (08-RESEARCH.md) contains an inconsistency where the formula `1/(1-(15.14*i^2 - 2.896*i))` and practical examples ("+10% → 1.22x") contradict each other. The correct formula `1 + (-4.0*grade^2 + 2.6*grade)` was derived from the test expectations and is already documented in STATE.md decisions.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Race CLI fully functional: import GPX/TCX → simulate → view splits → delete
- `fitops/dashboard/queries/race.py` is ready for plan 06 dashboard routes to consume
- All 11 race tests pass; full 206-test suite GREEN
- Plan 06 can build FastAPI routes for `/race/*` using the query layer built here

---
*Phase: 08-race-simulation-pacing*
*Completed: 2026-03-19*
