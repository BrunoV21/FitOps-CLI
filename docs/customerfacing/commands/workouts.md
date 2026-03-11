# fitops workouts

Markdown-based workout definitions with activity linking and segment compliance scoring.

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

See [Output Examples → Workouts](../output-examples/workouts.md) for the full JSON response.

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
- [Output Examples → Workouts](../output-examples/workouts.md) — full JSON samples
- [`fitops analytics zones`](./analytics.md) — configure your HR zones

← [Commands Reference](./README.md)
