# fitops admin

Internal maintenance commands for backfilling and recomputing derived data.

These commands are non-destructive and safe to re-run. They do not contact Strava — they only process data already stored in the local database.

## Commands

### `fitops admin recompute-power`

Backfill or recompute estimated running power for all running activities that have cached streams.

```bash
fitops admin recompute-power [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--dry-run` | false | Show which activities would be processed without writing |
| `--limit N` | 0 (all) | Process at most N activities |
| `--force` | false | Recompute even for activities that already have a power estimate |

**Requirements:**

- Body weight must be set: `fitops athlete set --weight <kg>`
- Activities must have cached streams: `fitops sync streams --limit N`

**Examples:**

```bash
# See what would be processed
fitops admin recompute-power --dry-run

# Backfill all runs missing a power estimate
fitops admin recompute-power

# Force-recompute the 10 most recent runs
fitops admin recompute-power --force --limit 10
```

**When to run this:**

- After setting or updating body weight for the first time
- After bulk-fetching streams for historical activities (`fitops sync streams`)
- When estimated power values look stale or were computed with an old weight

Power estimates are stored on each activity and displayed in the dashboard activity detail view and the activity list.

See [Concepts → Estimated Running Power](../concepts/estimated-power.md) for the methodology.

← [Commands Reference](./index.md)
