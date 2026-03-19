# FitOps-CLI Roadmap

## Phase 1: Foundation ✅
**Goal:** Strava auth, incremental sync, local SQLite storage, LLM-friendly activity output.

## Phase 2: Analytics ✅
**Goal:** Calculate training metrics locally from synced activities.

## Phase 3: Workouts & Compliance ✅
**Goal:** Create structured workouts, associate them with activities, score compliance.

## Phase 4: Multi-Provider Data Ingestion 🔜
**Goal:** Break the Strava dependency. Pull activity data directly from wearable platforms.

## Phase 5: Cloud Backup 🔜
**Goal:** Let athletes back up their local FitOps database to the cloud storage provider of their choice.

## Phase 6: Notes & Memos ✅
**Goal:** Lightweight markdown-based note-taking system with tags, optional activity association.

## Phase 7: Weather-Adjusted Pace & True Pace ✅
**Goal:** Adjust pace for environmental conditions (temperature, humidity, wind) and combine with GAP into True Pace.

## Phase 8: Race Simulation & Pacing 🔜
**Goal:** Import a race course, simulate effort across the profile factoring in elevation and weather, and produce a per-split pacing plan. Supports both target-time and pacer-following strategies.

### Key capabilities
- Course import from: local GPX/TCX file, MapMyRun URL (scrape embedded JSON), Strava activity streams
- Weather fetch via Open-Meteo (historical archive or forecast) keyed to race date and location
- Per-km simulation engine: GAP (elevation) + WAP (weather) adjustments per segment bearing
- Pacing strategies: even split, negative split (conservative start), pacer mode (sit-then-push)
- CLI commands: `fitops race import/courses/course/simulate/splits/delete`
- Dashboard: course elevation profile, split overlay, pacer visualization, scenario comparison

### CLI Commands
```bash
fitops race import <file_or_url_or_activity_id>  # import course
fitops race courses                               # list courses
fitops race course <id>                           # course profile
fitops race delete <id>                           # remove course
fitops race simulate <course_id> --target-time HH:MM:SS
fitops race simulate <course_id> --target-pace MM:SS
fitops race simulate <course_id> --target-time HH:MM:SS --pacer-pace MM:SS --drop-at-km N
fitops race simulate <course_id> --target-time HH:MM:SS --weather --temp T --humidity H --wind W --wind-dir DEG
fitops race simulate <course_id> --strategy negative-split|even|positive-split
fitops race splits <course_id> --target-time HH:MM:SS
```

**Plans:** 6 plans

Plans:
- [x] 08-01-PLAN.md — Test scaffold, fixtures, and new deps (gpxpy, tcxreader)
- [x] 08-02-PLAN.md — RaceCourse DB model and migration
- [x] 08-03-PLAN.md — Course parser module (GPX, TCX, MapMyRun, Strava streams)
- [x] 08-04-PLAN.md — Simulation engine (GAP factor, even/negative/pacer strategies)
- [x] 08-05-PLAN.md — CLI race commands and DB query layer
- [ ] 08-06-PLAN.md — Dashboard routes and Chart.js templates
