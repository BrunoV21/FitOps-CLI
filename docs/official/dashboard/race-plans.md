# Race Plans

Race Plans let you save a simulation snapshot — with target time, pacing strategy, and weather — and later compare it against your actual race performance.

Navigate to **Race → Plans** (`/race/plans`) to view all saved plans.

---

## Saving a Plan

After running a simulation on any course (`/race/<id>`), a **Save as Race Plan** panel appears below the splits table. Enter a name and click **Save Plan**. The simulation is re-run at save time and the per-km splits are stored with the plan.

You can re-save updated parameters at any time — the plan retains a single simulation snapshot.

---

## Plans List (`/race/plans`)

Displays all saved plans in a table:

| Column | Description |
|--------|-------------|
| Name | Link to the plan detail page |
| Course | Link to the course detail page |
| Date | Race date |
| Target | Target finish time |
| Strategy | Pacing strategy used |
| Activity | `linked ↗` if an activity was auto-matched, `pending` otherwise |
| Created | Plan creation date |

---

## Plan Detail (`/race/plans/<id>`)

Shows the full plan with:

- **Summary cards**: course, race date, target time, strategy, weather at save time
- **Simulation splits table**: per-km target pace, elapsed time, elevation change, and adjustment factors
- **Interactive map**: course polyline coloured by simulated pace zone, with km marker highlights on hover

If the plan has a linked activity:

- **Comparison cards**: actual finish vs target, actual average pace vs simulated
- **Split comparison chart**: dual-bar per km — simulated pace (blue) vs actual pace, coloured green (faster) or red (slower) relative to plan
- **Split comparison table**: km | Sim Pace | Actual | Δ | HR | Cadence

---

## Activity Auto-Matching

When `fitops sync` runs and fetches activity streams, the pipeline checks all unlinked plans. A plan is matched to an activity when:

1. The activity's sport type is a run (Run, TrailRun, VirtualRun, Walk, Hike)
2. The activity's start date is within ±1 day of the plan's `race_date`
3. The activity's GPS start point is within 500 m of the course start coordinates (haversine)

Matching is silent — no notification is shown. Once matched, the plan detail page automatically shows the comparison view.

To manually check whether a plan has been linked:

```bash
fitops race plan 1 --json | jq .activity_id
```

---

## CLI Equivalents

| Dashboard action | CLI command |
|-----------------|-------------|
| Save plan | `fitops race plan-save <course_id> --name "..." --target-time ...` |
| List all plans | `fitops race plans` |
| View plan detail | `fitops race plan <id>` |
| Compare vs actual | `fitops race plan-compare <id>` |
| Delete plan | `fitops race plan-delete <id>` |

See [`fitops race`](../commands/race.md) for full CLI reference.
