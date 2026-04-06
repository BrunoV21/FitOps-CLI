# Workouts & Compliance Scoring

FitOps lets you define structured workouts in plain Markdown, link them to completed Strava activities, and score how well you executed each segment against your actual heart rate stream.

---

## Workout Files

Workouts are `.md` files stored in `~/.fitops/workouts/`. You write them by hand (or generate them via CLI) — they're just text.

```markdown
---
name: Threshold Tuesday
sport: Run
target_duration_min: 60
tags: [threshold, quality]
---

## Warmup
10 min easy (Z1–Z2)

## Main Set
4 × 8 min @ Z4
2 min Z1 recovery jog between reps

## Cooldown
8 min easy Z1
```

**Frontmatter** (all optional) sets the display name, sport, target duration, and tags. If `name` is omitted, the filename stem is used.

**Segments** are defined by `##` headings. Everything under a heading — duration, zone target, rep structure — is parsed automatically and becomes a scoreable unit when the workout is linked to an activity.

---

## Segments

Each `##` heading in the workout body is a segment. FitOps parses:

- **Duration** — from patterns like `10 min`, `4 × 8 min`, `2 min`
- **Zone target** — from patterns like `Z4`, `Zone 3`, `Z2–Z3`
- **Rep structure** — `4 × 8 min` expands to 4 repetitions of 8 minutes each

Segments are used in two ways:

1. **Compliance scoring** — each segment is mapped to a time slice of the activity's HR stream and scored against the target zone
2. **Workout simulation** — each segment is projected onto a course with terrain and weather adjustments applied per-segment

---

## Linking a Workout to an Activity

```bash
fitops workouts link threshold-tuesday 12345678901
```

Linking stores:
- The raw Markdown content of the workout file at link time
- Parsed frontmatter metadata (name, sport, tags, target duration)
- A **physiology snapshot**: CTL, ATL, TSB, VO2max, LT1/LT2, and the zone method/values active at that moment

The physiology snapshot lets you look back at any past workout and see exactly what your fitness and fatigue state was when you did it — even if your zones have since been updated.

---

## Compliance Scoring

Compliance scoring answers: *how well did you actually execute this workout?*

### How it works

FitOps maps each segment onto the activity's heart rate stream, proportional to duration. For example, a workout with a 10 min warmup + 32 min main set + 8 min cooldown (50 min total) is mapped onto the actual moving time of the activity. Each segment gets the corresponding slice of HR data.

For each segment, FitOps computes:

```
compliance_score = time_in_target_pct × 0.6 + (1 − |deviation| / 2) × 0.4
```

Where:
- `time_in_target_pct` — fraction of segment time spent in the target HR zone (0.0–1.0)
- `deviation` — how many zones above or below the target your average HR landed

Being **below** target is penalised equally to being above — the formula is symmetric. A score of **≥ 0.8** is generally a successful segment.

The `overall_compliance_score` is a duration-weighted average across all scored segments.

### Example output

```
Compliance  activity 12345678901  Threshold Tuesday

  Segment     Duration  Target  Avg HR  Time in Zone  Score
 ──────────────────────────────────────────────────────────
  Warmup      10 min    Z1–Z2   138     94%           0.96
  Main Set    32 min    Z4      162     78%           0.86
  Cooldown    8 min     Z1      141     62%           0.73

  Overall compliance  0.86  [Good]
```

### Requirements

1. A workout linked to the activity (`fitops workouts link` first)
2. HR stream data for the activity (auto-fetched from Strava if not cached)
3. Zone thresholds configured (`fitops analytics zones --set-lthr 165` or `--infer`)

---

## Workout Simulation

Before you do a workout, you can simulate how it will play out on a specific course — accounting for terrain and weather per segment.

```bash
fitops workouts simulate threshold-tuesday --course 3
fitops workouts simulate tempo-run --activity 12345678901 --base-pace 5:10
fitops workouts simulate long-run --course 1 --date 2026-04-20 --hour 8
```

For each segment, the simulation computes:
- The terrain effect from the course's elevation profile at that segment's distance slice
- The weather effect (heat + wind) from the date/conditions provided
- A GAP- and WAP-adjusted target pace for the segment

This gives you a realistic per-segment pace plan before race or workout day — not just a flat pace target, but one that accounts for the actual course and expected conditions.

See [Weather & Pace](./weather-pace.md) for the GAP and WAP models behind the adjustment.

---

## Commands

```bash
fitops workouts list                              # list all workout files
fitops workouts show threshold-tuesday            # display parsed workout
fitops workouts create "Threshold Tuesday" def.json  # create from JSON
fitops workouts link threshold-tuesday <id>       # link to an activity
fitops workouts get <activity_id>                 # retrieve linked workout
fitops workouts compliance <activity_id>          # score HR compliance
fitops workouts compliance <activity_id> --recalculate
fitops workouts simulate threshold-tuesday --course 3
fitops workouts history --limit 10                # recent linked workouts
fitops workouts unlink <activity_id>              # remove link
```

See [Commands → workouts](../commands/workouts.md) for the full reference.

← [Concepts](./index.md)
