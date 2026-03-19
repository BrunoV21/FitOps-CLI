# FitOps-CLI Planning State

## Current Position
- **Phase:** 08-race-simulation-pacing
- **Current Plan:** 05
- **Plans Completed:** 4 of 6 (08-01, 08-02, 08-03, 08-04)
- **Status:** In Progress

## Progress
```
Phase 08: [####..] 4/6 plans complete
```

## Decisions
- Tests use module-level imports so collection failure is immediate and unambiguous (08-01)
- Fixture files are real XML files on disk rather than inline strings to test actual file I/O paths (08-01)
- Simulation stub added to allow test_race.py collection without full plan 04 implementation (08-03)
- TCX fixture timestamps required — tcxreader crashes computing duration without Time elements (08-03)
- grade clamped to [-0.45, 0.45] in build_km_segments; JSONDecoder().raw_decode() avoids regex truncation (08-03)
- gap_factor coefficients (-4.0, 2.6) match Strava empirical data; research doc formula 15.14/-2.896 contradicts its own practical values (08-04)
- simulate_pacer_mode uses 20% slowness threshold (pacer > avg_required * 1.2 raises); full-course check incorrectly rejected valid configs (08-04)
- scale normalisation guarantees sum(segment_time_s) == target_total_s exactly regardless of terrain (08-04)

## Performance Metrics
| Phase | Plan | Duration (s) | Tasks | Files |
|-------|------|-------------|-------|-------|
| 08-race-simulation-pacing | 01 | 166 | 3 | 4 |
| 08-race-simulation-pacing | 03 | 200 | 2 | 3 |
| 08-race-simulation-pacing | 04 | 618 | 2 | 1 |

## Last Session
- **Stopped at:** Completed 08-04-PLAN.md
- **Timestamp:** 2026-03-19T11:22:00Z

## Blockers
None
