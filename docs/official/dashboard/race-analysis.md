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

A time-series chart showing each athlete's gap to the leader (in seconds) over the course of the race — at every distance, the leader is the athlete with the minimum elapsed time and their line is anchored at 0. The y-axis is seconds; the same time-gap values feed event detection (drop / bridge / separation).

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

The Race Events section now has two layers:

- **Story cards** at the top summarise the headline move, decisive point, biggest gain, lead-change count, and notable finish kicks.
- **Narrative timeline** underneath lists each detected event with the athlete, rival, rank swing, segment context, and gap before/after the move.

The event engine still uses the gap chart as its base, but it now adds rival-aware context so the timeline can explain *who* a move happened against and *why* it mattered.

| Event Type | What it means |
|-----------|---------------|
| **Surge** | An athlete lifted speed >15% above their 60 s rolling baseline for a sustained window |
| **Fade** | An athlete's pace fell materially below their own first-half baseline; this is terrain-sensitive on back-loaded courses |
| **Final Sprint** | An athlete ran the last 400 m >10% faster than their race average |
| **Drop** | An athlete lost >10 s to the leader over a 500 m window |
| **Bridge** | An athlete gained >10 s on the leader over a 500 m window |
| **Separation** | An athlete first fell 30 s behind the leader |
| **Pass** | An athlete improved race position and overtook the runner ahead |
| **Caught** | An athlete closed a meaningful gap and made contact with the rival ahead |
| **Breakaway** | An athlete opened a sustained gap on the runner behind |
| **Pack Split** | A clear time gap opened between adjacent race positions, separating the field into groups |
| **Decisive Move** | The move where an eventual top finisher entered their final position and never gave it back |
| **Recovery** | An athlete regained lost time or position after a previous difficult patch |

Each event row also carries:

- `Rival`: the athlete directly involved when one can be inferred
- `Rank`: position change such as `P3 → P2`
- `Context`: segment label, move duration, and tags like `finish`, `climb`, or `decisive`
- `Gap`: the before/after gap values that explain the move quantitatively

### Replay

The session detail page animates each athlete along the course on a map alongside a live leaderboard and pace/HR charts.

On phones, the pace/HR comparison panel switches to a stacked layout: the chart selector buttons sit above the explanatory label, the chart height is reduced to fit the viewport better, and athlete labels move into compact chips above the chart so the plot area stays readable.

**Architecture: server-driven.** When a session is created or an athlete is added, the backend pre-computes a canonical replay timeline and persists it on the `race_sessions` row (`replay_frames_json`, `replay_time_step_s`). The frontend is a pure renderer — it reads the frames out of a JSON literal embedded in the template and indexes into them during animation, GIF export, and leaderboard updates. No interpolation happens in the browser, which guarantees that the map position, leaderboard rank, and gap always agree.

GIF export reuses that same timeline, but renders at the live map's viewport area and current `devicePixelRatio` instead of a fixed small canvas. Tile requests use retina variants on high-DPI screens, and the export expands the source timeline to a minimum 60 fps playback cadence so long sessions do not get frame-dropped down to a coarse animation. The leaderboard overlay also scales from the export viewport, with larger fonts and wider stat columns in portrait ratios such as `9:16`, so standings remain readable on phone-sized outputs.

Frame shape (one entry per `time_step_s`, default 5 s):

```json
{
  "t_s": 15.0,
  "athletes": [
    {"lat": 40.0, "lon": -8.01, "course_m": 52.4, "vel": 3.5, "hr": 158, "rank": 1, "gap_m": 0.0, "gap_geo_m": 0.0},
    {"lat": 40.0, "lon": -8.009, "course_m": 47.1, "vel": 3.3, "hr": 162, "rank": 2, "gap_m": 5.3, "gap_geo_m": 4.8}
  ]
}
```

`frame.athletes[i]` corresponds positionally to the athlete at index `i` returned by the server — athletes are ordered with the primary first, then by insertion time. Rank is assigned by `course_m` descending while the winner is still racing (leader = rank 1, `gap_m = 0`). `course_m` is each athlete's projected progress along the primary athlete's route, so leaderboard order matches map position even when athletes started recording at different moments on the course. `gap_m` is the along-route distance behind the leader; `gap_geo_m` is the straight-line haversine distance between the athlete's and leader's lat/lon at that instant — this is what the live leaderboard displays so it matches what's visible on the map. Once the winner finishes, the leaderboard switches to finish-time order and shows time behind the winner until each remaining athlete finishes, then freezes at the final gap.

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
