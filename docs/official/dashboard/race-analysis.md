# Race Analysis

Race Analysis lets you replay a race with multiple athletes side by side. After creating a session from a primary Strava activity and optionally adding comparison athletes (by Strava activity ID or GPX file), the dashboard shows gap trends, segment-by-segment rankings, and an automatically detected event timeline.

Navigate to **Race → Analysis** (`/race/sessions`) to view all sessions.

---

## Creating a Session

Sessions are created from the CLI — the analysis pipeline requires stream data that is not available through the browser:

```bash
# Create session from your activity (streams must be synced first)
fitops race session-create --activity <strava_id> --name "Berlin 2026" --course 1

# Add a comparison athlete from a public Strava activity
fitops race session-add-athlete 1 --label "Alex" --activity 98765432100

# Add a comparison athlete from a GPX file
fitops race session-add-athlete 1 --label "Sam" --gpx /path/to/sam.gpx
```

Once created, the session appears in the dashboard immediately.

---

## Sessions List (`/race/sessions`)

Displays all saved sessions in a table:

| Column | Description |
|--------|-------------|
| Name | Link to the session detail page |
| Primary Activity | Strava activity ID used as the primary athlete |
| Athletes | Total number of athletes in the session |
| Course | Linked course ID (if any) |
| Created | Session creation date |

---

## Session Detail (`/race/sessions/<id>`)

The session detail page has three panels:

### Gap Analysis

A time-series chart showing each athlete's gap to the leader (in seconds) over the course of the race. The leader at any given point is the athlete with the minimum elapsed time — their line is anchored at 0.

- Positive gap = behind the leader
- A rising line = falling further behind
- A falling line = closing the gap
- Lines crossing = position changes

The chart plots at 50 m resolution for the full course distance.

### Segment Breakdown

The course is divided into climbing, flat, and descending sections. The table shows per-athlete performance for each segment:

| Column | Description |
|--------|-------------|
| Segment | Label (e.g. "Climb 1", "Flat 2") |
| km range | Start and end kilometre markers |
| Grade | Average gradient % |
| Athlete cols | Time (MM:SS), pace (MM:SS/km), rank within segment |

Segments are derived from the linked course's km-segments (grade-based merging) when a course is linked, or from the primary athlete's altitude stream using a rolling-window fallback.

### Event Timeline

Automatically detected tactical events displayed in chronological order:

| Event Type | What it means |
|-----------|---------------|
| **Surge** | An athlete's pace jumped >15% above their 60 s rolling baseline and held for ≥20 s |
| **Fade** | An athlete's second-half average pace was <90% of their first-half average |
| **Final Sprint** | An athlete ran the last 400 m >10% faster than their race average |
| **Drop** | An athlete's gap to the leader grew by >10 s over a 500 m window |
| **Bridge** | An athlete closed the gap to the leader by >10 s over a 500 m window |
| **Separation** | The total field spread (fastest to slowest) exceeded 30 s |

---

## CLI Equivalents

| Dashboard view | CLI command |
|----------------|-------------|
| Create session | `fitops race session-create --activity <id> --name "..."` |
| Add athlete | `fitops race session-add-athlete <id> --label "..." --activity <id>` |
| List sessions | `fitops race sessions` |
| Session detail | `fitops race session <id>` |
| Gap series only | `fitops race session-gaps <id>` |
| Segment breakdown only | `fitops race session-segments <id>` |
| Events only | `fitops race session-events <id>` |
| Delete session | `fitops race session-delete <id>` |

See [`fitops race`](../commands/race.md) for full CLI reference.
