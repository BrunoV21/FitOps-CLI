# PRD — Phase 9: Race Analysis & Replay

**Status:** Draft
**Fits roadmap phase:** Post-Phase 8 (Race Simulation)
**Classification:** Differentiating feature

---

## 1. What This Is

A post-race analysis layer that transforms raw activity streams into a structured, visual breakdown of a race: who was where, when gaps opened, and why the race played out the way it did.

The analogy is F1 telemetry analysis — not broadcast TV, but the engineers' screen. Clear, data-dense, explainable.

This is **not a social feature**. FitOps is local-first and stays that way. Comparison athletes are imported as data, not accounts.

---

## 2. Strategic Fit

FitOps already has strong foundations to build on:

| Existing capability | How it's used here |
|---|---|
| Activity streams sync (GPS, pace, HR, cadence, elevation) | Primary data source for the primary athlete |
| `RaceCourse` + km-segments (Phase 8) | Course skeleton for alignment and segment detection |
| GAP / True Pace (Phase 7) | Effort-normalized comparison across terrain |
| Weather-adjusted pace | Performance normalization across conditions |
| CLI `--json` output | Feed analysis results to AI agents |

The gap: FitOps is single-athlete today. Race analysis is inherently multi-athlete. The solution is a **comparison stream import** model — not multi-account auth, but activity-level data ingestion by Strava activity ID or GPX/FIT file. The comparison athlete's streams are stored locally, scoped to the race. No login required on their end.

---

## 3. Core Concept: Race Sessions

A **Race Session** ties together:

- One or more activity streams (primary + comparisons)
- An optional course (from Phase 8's `RaceCourse`)
- A set of computed alignment frames, gap series, and event detections
- An optional replay state (playback position, selected athletes)

Race Sessions are stored in `~/.fitops/fitops.db` and are queryable via CLI just like activities.

---

## 4. Feature Scope

### Phase 9.1 — Data Foundation (MVP)

**Multi-stream ingestion**

- Primary athlete: existing synced activity (by Strava ID)
- Comparison athletes: imported automatically from the grouped activity, i.e run with option with supprot to manually add more activities, by Strava activity ID (fetch public streams via API) or GPX file
- Store comparison streams in a new `comparison_streams` table keyed to a `race_session_id`
- No comparison athlete account required — public stream data only

**Race alignment engine**

Three alignment frames, all computed at import time and stored:

1. **Distance-aligned** — normalize all athletes onto `[0, total_distance_km]` regardless of start time differences. Primary frame for segment analysis.
2. **Time-aligned** — normalize onto shared elapsed time from each athlete's start. Used for replay.
3. **Gap series** — for each distance/time step: gap in seconds and meters between each athlete and the leader. The core analytical output.

Interpolate streams to a common resolution (5-second or 10-metre grid, configurable). Smooth GPS jitter with a rolling 3-point median. Handle missing HR/cadence gracefully (null segments, not errors).

**Segment detection**

Auto-detect from the course profile (if a `RaceCourse` is linked):

- Climbs (grade > +3% sustained over 200m+)
- Descents (grade < -3% sustained)
- Flats (everything else)
- Key turns (high turn density zones, from GPS bearing changes)

Manual segments can be added as `[start_km, end_km, label]`.

For each segment × each athlete: elapsed time, GAP, time gained/lost vs. field, rank.

---

### Phase 9.2 — Analysis Layer

**Gap & delta analysis**

Core computed outputs:

- `gap_series`: array of `{distance_km, time_s, gap_to_leader_s, gap_to_leader_m, position}` per athlete
- `delta_series`: derivative of gap — positive = gaining, negative = losing
- Crossover events: timestamps where position rankings change

**Event detection**

Rules-based engine, not ML. Deterministic and explainable.

| Event | Detection rule |
|---|---|
| Surge | Pace increases > 15% above 60s rolling average, sustained 20s+ |
| Drop | Gap to leader increases > 10s over 500m and continues growing |
| Bridge | Gap decreases > 10s over 500m |
| Fade | Pace drift: 30s rolling pace degrades > 10% in second half of race |
| Final sprint | Last 400m, pace > 10% faster than race average |
| Separation | Any athlete falls more than 30s behind the leader for the first time |

Each event: `{event_type, athlete_label, distance_km, elapsed_s, impact_s, description}`.

**Performance metrics**

Running:
- GAP (grade-adjusted pace) per segment — already implemented
- Cadence stability (std dev across race and per segment)
- HR drift ratio (HR/pace ratio second half vs first half — fatigue signal)
- Pace variability index (std dev / mean pace)

Cycling (when power data available):
- Normalized power (30s rolling RMS)
- Variability index (NP/AP ratio)
- Power-to-speed efficiency per segment

---

### Phase 9.3 — CLI Surface

Commands under `fitops race`:

```bash
# Create a race session
fitops race session-create --activity <strava_id> --name "My Race"

# Add a comparison athlete's activity
fitops race session-add-athlete <session_id> --activity <strava_id> --label "Athlete B"
fitops race session-add-athlete <session_id> --gpx <file.gpx> --label "Athlete C"

# List sessions
fitops race sessions [--json]

# Session overview: athletes, gap summary, top events
fitops race session <session_id> [--json]

# Gap series output
fitops race session <session_id> gaps [--json]

# Segment breakdown (all athletes)
fitops race session <session_id> segments [--json]

# Events list
fitops race session <session_id> events [--json]

# Delete
fitops race session-delete <session_id>
```

All commands support `--json`. The structured output is designed for AI agent consumption — an agent can load `fitops race session <id> events --json` and reason about decisive race moments without touching the dashboard.

---

### Phase 9.4 — Dashboard Surface

**Race Sessions list page** (`/race/sessions`)

Table: session name, date, athletes, course (if linked), decisive event summary.

**Race Session detail page** (`/race/sessions/<id>`)

Three-panel layout:

```
┌─────────────────────┬──────────────────────────┐
│                     │                          │
│   Map + Replay      │   Gap / Pace Chart       │
│   (primary panel)   │   (synced to map)        │
│                     │                          │
├─────────────────────┴──────────────────────────┤
│         Segment Table  |  Events Timeline       │
└────────────────────────────────────────────────┘
```

**Map panel**

- Leaflet.js map (lightweight, no API key required)
- Color-coded athlete markers
- Animated playback: play/pause, speed (1×/2×/4×), scrub slider
- Trail lines per athlete (toggleable)
- Gap label between leader and each other athlete updates live during replay
- Playhead scrubber synced to all charts

**Gap/Pace chart panel**

- Primary chart: gap to leader vs. distance (Y axis: seconds; X axis: km)
- Toggle to: gap vs. time, pace vs. distance, HR vs. distance
- Event markers overlaid on chart (icons with hover tooltips: time gained/lost, context)
- Chart cursor syncs with map playhead
- Athlete toggle (show/hide individual lines)

**Segment table**

- Columns: Segment | Distance | Gradient | [per-athlete: Time | GAP | Time vs. Leader | Rank]
- Sortable by time gained/lost
- Best performer per segment highlighted
- Click segment → map zooms + highlights that section

**Events timeline**

- Vertical timeline in chronological order
- Each event: icon, type label, athletes involved, km marker, impact ("gained 14s")
- Click event → scrubs map + chart to that moment

**Race Story panel** (stretch goal for 9.4)

Auto-generated 3–5 bullet narrative from the event detection output. Template-driven from detected events, no LLM required:

> "The race was decided at km 8.4 (second climb). Athlete A surged and gained 18s over 600m. Athlete B never recovered, fading further in the final 3km."

---

## 5. Architecture Notes

**What stays the same**

- All computation in `fitops/analytics/` (new module: `race_analysis.py`)
- CLI handlers thin — call analytics
- Dashboard routes thin — call analytics
- No logic in templates or CLI handlers

**New DB tables**

```
race_sessions           id, name, primary_activity_id, course_id?, created_at
race_session_athletes   id, session_id, activity_id?, athlete_label, stream_json
race_session_gaps       id, session_id, athlete_label, gap_series_json, delta_series_json
race_session_events     id, session_id, event_type, athlete_label, distance_km, elapsed_s, impact_s, description
race_session_segments   id, session_id, segment_label, start_km, end_km, gradient_type, [per-athlete metrics as JSON]
```

`stream_json` stores the interpolated, smoothed comparison stream inline. A 10km race at 5s resolution is ~2400 rows — well within SQLite's comfort zone.

**Strava API constraint**

Fetching comparison athlete streams via Strava requires their activity to be public and uses the primary athlete's OAuth token. This works with current Strava API for public activities. Comparison athletes with private activities must use GPX file import instead. This should be clearly documented.

---

## 6. What's Out of Scope

| Item | Why |
|---|---|
| Live race tracking | Requires real-time Strava webhook + push — incompatible with local-first |
| Pack dynamics / drafting detection | Requires sub-second GPS resolution — Strava doesn't provide this |
| LLM-generated race story | Template-driven story sufficient for MVP; LLM integration is Phase 10+ |
| Social sharing / embeds | FitOps is local-first — no data leaves the machine |
| Power-only sessions (no GPS) | Alignment requires GPS; power-only is a future extension |
| More than 8 athletes | UI and performance constraint |

---

## 7. Definition of Done

Following CLAUDE.md non-negotiable rules — a feature is done when all five are complete:

1. **Logic** — `fitops/analytics/race_analysis.py` (alignment, gap series, event detection, segment metrics)
2. **Unit tests** — `tests/test_race_analysis.py` covering alignment, gap computation, each event detection rule
3. **CLI** — all `fitops race session-*` commands with `--json` output and tested JSON shape
4. **Dashboard** — session list + session detail with map + charts + segment table + events
5. **Docs** — `docs/official/commands/race.md` updated, `docs/official/dashboard/race-analysis.md` added

---

## 8. Phasing Recommendation

| Phase | Scope | Delivers |
|---|---|---|
| 9.1 | DB models, comparison stream ingestion (Strava ID + GPX), alignment engine, gap series, segment detection | Data layer complete, CLI queryable |
| 9.2 | Event detection engine, performance metrics per athlete/segment | Full analytical output in CLI |
| 9.3 | Dashboard: session list + detail page (charts + segment table + events timeline) | Human-readable analysis |
| 9.4 | Dashboard: animated map replay + synchronized playhead | The North Star replay experience |

9.4 is the differentiating experience but 9.1–9.3 are complete and useful on their own.

---

## 9. Key Risks

| Risk | Mitigation |
|---|---|
| Strava public stream access fails for some athletes | GPX file import as fallback; clear error messaging |
| GPS inaccuracy corrupts alignment | 3-point median smoothing + optional snap-to-course when a `RaceCourse` is linked |
| Different start times break time-aligned view | Distance-aligned view is primary; time-aligned is secondary |
| Map replay performance with large streams | Downsample replay to 10s resolution for animation; keep full resolution for analysis |
| Feature scope creep into social/sharing | Hard constraint: no data leaves the local machine |
