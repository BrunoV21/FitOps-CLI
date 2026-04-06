# fitops workouts

Markdown-based workout definitions with activity linking and segment compliance scoring.

Commands print human-readable output by default. Add `--json` for raw JSON (useful for scripting or AI agents).

Workouts are plain `.md` files you write and store in `~/.fitops/workouts/`. When you link a workout to a Strava activity, FitOps captures a physiology snapshot (CTL, ATL, TSB, VO2max, LT1/LT2) and — if the workout has named segments — scores each segment against the activity's heart rate stream.

## Workout File Format

Create `.md` files in `~/.fitops/workouts/`:

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

**Frontmatter fields** (all optional):

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name (defaults to filename stem) |
| `sport` | string | `Run`, `Ride`, etc. |
| `target_duration_min` | int | Total target duration |
| `tags` | list | `[threshold, quality, run]` |

**Segments** are defined with `##` headings in the body. Each heading becomes a scoreable segment when the workout is linked to an activity. Duration (`10 min`, `4 × 8 min`) and target zone (`Z4`, `Zone 3`, `Z2–Z3`) are parsed automatically from the text below each heading.

---

## Commands

### `fitops workouts list`

List all workout files in `~/.fitops/workouts/`.

```bash
fitops workouts list
```

---

### `fitops workouts show <name>`

Display the contents and parsed metadata of a workout file.

```bash
fitops workouts show threshold-tuesday
fitops workouts show "Threshold Tuesday"
fitops workouts show threshold-tuesday.md
```

---

### `fitops workouts link <name> <activity_id>`

Link a workout to a synced activity and capture a physiology snapshot.

```bash
fitops workouts link threshold-tuesday 12345678901
fitops workouts link threshold-tuesday 12345678901 --notes "Felt strong, legs fresh"
```

**What gets stored:**
- Raw markdown content of the workout file at link time
- Parsed frontmatter metadata
- Physiology snapshot: CTL, ATL, TSB, VO2max, LT1/LT2, zones method and values

If the activity already has a linked workout, it is overwritten.

**Options:**

| Flag | Description |
|------|-------------|
| `--notes TEXT` | Optional notes for this workout instance |

---

### `fitops workouts get <activity_id>`

Retrieve the workout and physiology snapshot linked to a specific activity.

```bash
fitops workouts get 12345678901
```

---

### `fitops workouts compliance <activity_id>`

Score each workout segment against the activity's heart rate stream.

```bash
fitops workouts compliance 12345678901
fitops workouts compliance 12345678901 --recalculate
```

Requires:
1. A workout linked to the activity (`fitops workouts link` first)
2. Heart rate stream data (fetched from Strava automatically if not cached)
3. Zone settings configured (`fitops analytics zones --set-lthr 165`)

Each `##` segment in the workout file is matched to a time slice of the HR stream, proportional to the durations specified. For example, a 10 min warmup + 32 min main set + 2 min recovery + 8 min cooldown (52 min total) maps onto the actual moving time of the activity.

**Options:**

| Flag | Description |
|------|-------------|
| `--recalculate` | Force re-score even if segment results are already cached |

See [Output Examples → Workouts](../output-examples/workouts.md) for sample output.

---

### `fitops workouts unlink <activity_id>`

Remove the workout–activity association for an activity.

```bash
fitops workouts unlink 12345678901
```

The workout file itself is not deleted — only the DB record linking it to the activity is removed.

---

### `fitops workouts create <name> <source>`

Create a workout markdown file from a JSON definition.

```bash
fitops workouts create "Threshold Tuesday" workout.json
cat workout.json | fitops workouts create "Threshold Tuesday" -
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `NAME` | Display name for the workout (e.g. `"10 Mar Intervals"`) |
| `SOURCE` | Path to a JSON file, or `-` to read from stdin |

**JSON format:**

```json
{
  "sport": "run",
  "segments": [
    { "name": "Warmup", "type": "warmup", "duration_min": 10, "zone": 2 },
    { "name": "Intervals", "type": "interval", "reps": 5, "duration_min": 4, "zone": 4 },
    { "name": "Recovery", "type": "recovery", "reps": 5, "duration_min": 2, "zone": 1 },
    { "name": "Cooldown", "type": "cooldown", "duration_min": 10, "zone": 1 }
  ]
}
```

The command generates a `.md` file in `~/.fitops/workouts/` with YAML frontmatter and human-readable segment headings that the compliance scorer can parse.

---

### `fitops workouts simulate <name>`

Simulate a workout on a course or past activity route, applying terrain and weather adjustments per segment.

```bash
fitops workouts simulate threshold-tuesday --course 3
fitops workouts simulate tempo-run --activity 12345678901 --base-pace 5:10
fitops workouts simulate long-run --course 1 --date 2026-04-20 --hour 8
fitops workouts simulate tempo-run --course 2 --temp 28 --humidity 70
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `NAME` | Workout filename or name (e.g. `threshold-tuesday`) |

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--course ID` | — | RaceCourse ID (from `fitops race courses`) |
| `--activity ID` | — | Strava activity ID — uses cached GPS streams as the course |
| `--base-pace MM:SS` | — | Base pace per km for HR-zone segments with no explicit pace target |
| `--temp C` | — | Temperature °C (manual override) |
| `--humidity PCT` | — | Relative humidity % (manual override) |
| `--wind MS` | — | Wind speed m/s |
| `--wind-dir DEG` | — | Wind direction degrees (0=N) |
| `--date YYYY-MM-DD` | — | Fetch weather for this date (future = forecast, past = archive) |
| `--hour N` | 9 | Start hour local time (0–23) for weather fetch |

Either `--course` or `--activity` is required (not both). Manual `--temp`/`--humidity` override auto-fetched weather when both are provided.

**Output:** Per-segment plan showing segment name, target zone, planned duration, GAP/WAP-adjusted pace, estimated HR, and cumulative time.

---

### `fitops workouts history`

List all workouts that have been linked to activities.

```bash
fitops workouts history
fitops workouts history --limit 10 --sport Run
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | 20 | Max entries to return |
| `--sport TYPE` | all | Filter by sport type |

---

## Compliance Scoring

Each segment gets a `compliance_score` (0.0–1.0) computed as:

```
compliance_score = time_in_target_pct × 0.6 + (1 − |deviation| / 2) × 0.4
```

Where:
- `time_in_target_pct` — fraction of the segment spent in the target zone
- `deviation` — how many zones above/below the target your average HR landed

Being **below** target is penalised the same as being above (symmetric formula). A score ≥ 0.8 is generally considered a successful segment.

The `overall_compliance_score` is a duration-weighted average across all scored segments.

## See Also

- [Concepts → Zones](../concepts/zones.md) — zone methods and thresholds
- [Output Examples → Workouts](../output-examples/workouts.md) — sample output
- [`fitops analytics zones`](./analytics.md) — configure your HR zones

← [Commands Reference](./index.md)
