---
phase: 08-race-simulation-pacing
verified: 2026-03-19T13:06:46Z
status: passed
score: 18/18 must-haves verified
re_verification: false
---

# Phase 8: Race Simulation & Pacing Verification Report

**Phase Goal:** Import a race course, simulate effort across the profile factoring in elevation and weather, and produce a per-split pacing plan. Supports both target-time and pacer-following strategies.
**Verified:** 2026-03-19T13:06:46Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | GPX and TCX files are parsed into normalised CoursePoint dicts | VERIFIED | `parse_gpx` / `parse_tcx` in `course_parser.py` — full implementations, tests pass |
| 2  | `build_km_segments()` produces per-km segments with grade, bearing, elevation | VERIFIED | Lines 300-352 of `course_parser.py`; `test_km_segments` PASS |
| 3  | `gap_factor()` returns Strava-model pace multiplier clamped to ±0.45 | VERIFIED | `simulation.py` lines 17-35; formula produces `gap_factor(0.10)==1.22`; tests pass |
| 4  | `simulate_splits()` (even strategy) produces total time within 1s of target | VERIFIED | Scale-normalisation in `simulation.py` lines 99-105; `test_even_split_total_time` PASS |
| 5  | `simulate_splits()` (hilly, even) exercises scale normalisation | VERIFIED | `test_even_split_total_time_hilly` PASS |
| 6  | `simulate_splits()` (negative strategy) produces faster second-half avg pace | VERIFIED | Lines 84-86 `simulation.py`; `test_negative_split_halves` PASS |
| 7  | `simulate_pacer_mode()` sit_time + push_total_time == target (within 1s) | VERIFIED | `test_pacer_mode_total_time` PASS |
| 8  | `simulate_pacer_mode()` raises ValueError "too slow" when pacer exceeds limit | VERIFIED | Lines 156-162 `simulation.py`; `test_pacer_too_slow_error` PASS; message contains "too slow" |
| 9  | `fitops race` CLI exposes import, courses, course, simulate, splits, delete | VERIFIED | `fitops/cli/race.py` has all 6 commands; `registered_commands` confirmed |
| 10 | `fitops race import <gpx>` stores course in DB with segments | VERIFIED | `import_course()` calls `save_course()` with points+segments; wired end-to-end |
| 11 | `fitops race simulate <id> --target-time` outputs per-km split table | VERIFIED | `simulate()` in CLI calls `simulate_splits()` and returns JSON splits array |
| 12 | `fitops race simulate --pacer-pace --drop-at-km` produces pacer plan | VERIFIED | `simulate_pacer_mode()` path in CLI `simulate()` command |
| 13 | Weather can be manual, forecast, historical archive, or neutral fallback | VERIFIED | All four branches in `cli/race.py` lines 187-246 |
| 14 | RaceCourse model has all required columns and is registered in DB migrations | VERIFIED | `fitops/db/models/race_course.py`; `fitops/db/migrations.py` line 22 imports RaceCourse |
| 15 | GET /race lists courses; GET /race/{id} shows elevation profile chart | VERIFIED | `fitops/dashboard/routes/race.py` routes 56-89; `course.html` with `new Chart` |
| 16 | GET /race/{id}/simulate shows form; POST runs simulation with split bar chart | VERIFIED | Routes 91-268; `simulate.html` contains Chart.js with color-coded bars |
| 17 | Pacer mode visualization shows sit/push phase separator and overlay line | VERIFIED | `simulate.html` lines 149-166 (phase separator row); lines 184-218 (pacer line chart overlay) |
| 18 | Full test suite passes with no regressions | VERIFIED | `pytest tests/ -q` → 206 passed |

**Score:** 18/18 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/test_race.py` | 11 test stubs, all GREEN | VERIFIED | 11 tests collected, 11 passed |
| `tests/fixtures/sample.gpx` | Valid GPX 1.1, 5 trackpoints | VERIFIED | Parseable by gpxpy; `test_parse_gpx` PASS |
| `tests/fixtures/sample.tcx` | Valid TCX 2, 5 trackpoints | VERIFIED | Parseable by tcxreader; `test_parse_tcx` PASS |
| `fitops/race/__init__.py` | Package marker | VERIFIED | Exists; `fitops.race` importable |
| `fitops/race/course_parser.py` | All parsers + segment builder | VERIFIED | 393 lines; exports CoursePoint, parse_gpx, parse_tcx, parse_mapmyrun_html, parse_mapmyrun_url, parse_strava_activity, build_km_segments, detect_source, formatter helpers |
| `fitops/race/simulation.py` | GAP formula + simulation engine | VERIFIED | 198 lines; exports gap_factor, simulate_splits, simulate_pacer_mode |
| `fitops/db/models/race_course.py` | RaceCourse SQLAlchemy model | VERIFIED | All required columns present; get_course_points(), get_km_segments(), to_summary_dict() implemented |
| `fitops/db/migrations.py` | RaceCourse registered | VERIFIED | Line 22: `from fitops.db.models.race_course import RaceCourse  # noqa: F401` |
| `fitops/cli/race.py` | 6 CLI commands | VERIFIED | import, courses, course, simulate, splits, delete all present and wired |
| `fitops/dashboard/queries/race.py` | CRUD query functions | VERIFIED | save_course, get_course, get_all_courses, delete_course all implemented |
| `fitops/dashboard/routes/race.py` | FastAPI router for /race/* | VERIFIED | GET /race, GET /race/{id}, GET+POST /race/{id}/simulate |
| `fitops/dashboard/templates/race/index.html` | Course list table | VERIFIED | Exists; contains empty-state and action links |
| `fitops/dashboard/templates/race/course.html` | Elevation profile chart | VERIFIED | Exists; `new Chart` present with elevation_profile_json |
| `fitops/dashboard/templates/race/simulate.html` | Simulation form + pace bar chart | VERIFIED | Exists; Chart.js bar chart, color-coded bars, pacer line overlay |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `fitops/race/course_parser.py` | `fitops/analytics/weather_pace.py` | `from fitops.analytics.weather_pace import compute_bearing` | WIRED | Line 20; used in `build_km_segments()` |
| `fitops/race/simulation.py` | `fitops/analytics/weather_pace.py` | `from fitops.analytics.weather_pace import compute_wap_factor` | WIRED | Line 13; used in `simulate_splits()` |
| `fitops/race/simulation.py` | `fitops/race/course_parser.py` | `from fitops.race.course_parser import _fmt_pace, _fmt_duration` | WIRED | Line 14; both used in split output dicts |
| `fitops/cli/race.py` | `fitops/race/course_parser.py` | `from fitops.race.course_parser import ...` | WIRED | Lines 13-22; detect_source, parse_*, build_km_segments all called |
| `fitops/cli/race.py` | `fitops/race/simulation.py` | `from fitops.race.simulation import simulate_pacer_mode, simulate_splits` | WIRED | Line 23; both called in simulate() |
| `fitops/cli/race.py` | `fitops/dashboard/queries/race.py` | `from fitops.dashboard.queries.race import ...` | WIRED | Lines 24-29; save_course, get_course, get_all_courses, delete_course all called |
| `fitops/cli/main.py` | `fitops/cli/race.py` | `app.add_typer(race_app, name="race")` | WIRED | Lines 23+33 in main.py |
| `fitops/dashboard/routes/race.py` | `fitops/dashboard/queries/race.py` | `from fitops.dashboard.queries.race import get_all_courses, get_course` | WIRED | Line 10; both called in route handlers |
| `fitops/dashboard/routes/race.py` | `fitops/race/simulation.py` | `from fitops.race.simulation import simulate_pacer_mode, simulate_splits` | WIRED | Line 12; both called in POST handler |
| `fitops/dashboard/server.py` | `fitops/dashboard/routes/race.py` | `race.register(templates)` → `app.include_router(...)` | WIRED | Lines 16+106 in server.py |
| `fitops/dashboard/templates/base.html` | `/race` | Nav link | WIRED | Line 88 of base.html |

---

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| RACE-01 | 08-01, 08-02, 08-03, 08-05 | Course import from GPX, TCX, MapMyRun, Strava | SATISFIED | `course_parser.py` implements all 4 parsers; `fitops race import` command; RaceCourse model stores parsed data |
| RACE-02 | 08-01, 08-03, 08-05 | 1km segment builder with grade and bearing | SATISFIED | `build_km_segments()` fully implemented; stored in `km_segments_json`; CLI course detail shows segments |
| RACE-03 | 08-01, 08-04, 08-05 | Simulation engine (even/negative/positive, pacer mode) | SATISFIED | `simulate_splits()` + `simulate_pacer_mode()` both implemented and tested; CLI `simulate` and `splits` commands expose them |
| RACE-04 | 08-06 | Dashboard UI with elevation profile, simulation form, split chart | SATISFIED | FastAPI routes + 3 Jinja2 templates with Chart.js; registered in dashboard app and base.html nav |

---

## Anti-Patterns Found

None. The `return []` instances in `course_parser.py`, `simulation.py`, and the dashboard route are all legitimate guard clauses for empty-input conditions (no GPX tracks, no course points, no segments). No TODO/FIXME/PLACEHOLDER comments were found in any race module file.

**Note on GAP formula deviation:** The plan specified `1 + (15.14 * grade^2 - 2.896 * grade)`. The implementation uses `1 + (-4.0 * grade^2 + 2.6 * grade)` (commit `74fc4ef` explicitly fixes this). The test suite validates `gap_factor(0.10) ≈ 1.22 ± 0.05`, `gap_factor(0.0) == 1.0`, and `gap_factor(-0.05) < 1.0` — all of which pass. The formula was intentionally recalibrated to match Strava's empirical data; the observable behaviour is correct.

**Note on pacer validation deviation:** The plan used `pacer_full_time > target_total_s` as the guard. The implementation uses `pacer_pace_s > required_avg_pace_s * 1.2` (20% threshold). The test case `pacer_pace=400, target=1500, dist=5km` triggers both conditions (400 > 300 × 1.2 = 360), so the test passes and the ValueError with "too slow" is raised correctly.

---

## Human Verification Required

### 1. Dashboard Route Navigation

**Test:** Run `fitops dashboard start`, navigate to http://localhost:8000/race, import a GPX file via CLI, then refresh the page.
**Expected:** Course list table renders with the imported course; "Profile" and "Simulate" links work; elevation chart renders on course detail page.
**Why human:** Jinja2 template rendering and Chart.js visualizations require a browser.

### 2. Pacer Mode Simulation Chart Overlay

**Test:** On the simulate page, enter a target time, pacer pace, and drop-at-km, then submit.
**Expected:** Bar chart shows pace bars, with a purple dashed horizontal line ending at the drop-at-km marker; sit-phase rows are grayed in the split table; separator row shows break point.
**Why human:** Chart.js rendering with conditional `null` values past the break point must be validated visually.

### 3. Weather Forecast Integration

**Test:** `fitops race simulate <id> --target-time 1:00:00 --date 2026-03-25 --hour 9` (future date within 16-day window, course with lat/lon).
**Expected:** Weather is fetched from Open-Meteo forecast API; `weather_source: "forecast"` in JSON output; simulation uses actual forecast values.
**Why human:** Requires live API call and a real imported course with lat/lon coordinates.

---

## Gaps Summary

No gaps found. All phase goal requirements are met:

- Course import pipeline is fully wired from file/URL/Strava → parser → normalised CoursePoints → segment builder → DB storage.
- Simulation engine correctly applies GAP and WAP factors, distributes time across segments, and normalises so totals are exact.
- All three strategies (even, negative, positive) and pacer mode are implemented and tested.
- CLI exposes the full workflow with weather resolution (manual, forecast, archive, neutral).
- Dashboard provides visual course profile and simulation form with color-coded pace chart and pacer overlay.
- 206 tests pass with no regressions.

---

_Verified: 2026-03-19T13:06:46Z_
_Verifier: Claude (gsd-verifier)_
