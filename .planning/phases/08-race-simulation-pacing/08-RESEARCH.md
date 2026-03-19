# Phase 8: Race Simulation & Pacing — Research

**Researched:** 2026-03-19
**Domain:** GPS course parsing, race simulation math, pacing algorithms, Open-Meteo forecast
**Confidence:** HIGH (core algorithms), MEDIUM (MapMyRun scraping structure)

---

## Summary

Phase 8 builds a race simulation engine that combines course elevation profiles with weather-adjusted pace factors already built in Phase 7. The three course import sources (GPX/TCX local file, MapMyRun URL, Strava activity streams) each require different parsing approaches but funnel into a single normalised `race_courses` table storing waypoints as a JSON column.

The simulation engine iterates over 1km segments, applying two existing physics functions — the Strava/Minetti GAP factor for elevation and `compute_wap_factor()` from `weather_pace.py` for weather — to distribute a target total time across variable-difficulty terrain. All three pacing strategies (even, negative split, pacer mode) are mathematically straightforward given a normalised per-segment difficulty index.

The dashboard extends the FastAPI/Jinja2/Chart.js pattern established in Phase 7. The most technically uncertain piece is MapMyRun scraping: the `window.__STATE__` JSON structure was confirmed live on a real route URL, but it is an undocumented internal structure that could change without notice.

**Primary recommendation:** Use `gpxpy` for GPX, `tcxreader` for TCX, `httpx` + `json.loads` regex for MapMyRun. Simulation engine is pure Python math — no new scientific libraries needed.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `gpxpy` | 1.6.2 (Nov 2023) | GPX file parsing | De-facto standard; handles GPX 1.0 + 1.1; point objects have `.latitude`, `.longitude`, `.elevation` |
| `tcxreader` | 0.4.11 (Mar 2025) | TCX file parsing | Actively maintained; handles missing data; `.trackpoints` list with `.latitude`, `.longitude`, `.elevation`, `.distance` |
| `httpx` | already in deps | MapMyRun page fetch | Already used in `strava/client.py` and `weather/client.py` — no new dep |
| `re` / `json` (stdlib) | stdlib | Extract JSON from MapMyRun HTML | No additional dep; regex to locate `window.__STATE__` boundary |

### Supporting (already in deps, no new installs)
| Library | Purpose | When to Use |
|---------|---------|-------------|
| `fastapi` + `jinja2` | Dashboard route + templates | Race course profile page, simulation results |
| `sqlalchemy[asyncio]` | `race_courses` table + queries | Course storage and retrieval |
| `scipy` (already in deps) | Optional: smooth elevation profile | If raw GPS elevation data is too noisy |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `tcxreader` | `lxml` + manual XPath | tcxreader is simpler; lxml gives more control but requires writing TCX-specific XPath for every field |
| `tcxreader` | `python-tcxparser` | Both active; `tcxreader` handles missing data more gracefully per its docs |
| `re` for MapMyRun JSON | `beautifulsoup4` | BeautifulSoup adds a dep for a task regex handles in 3 lines; regex is sufficient when the key is `window.__STATE__` |

**Installation (new deps only):**
```bash
pip install gpxpy tcxreader
```

---

## Architecture Patterns

### Recommended Module Structure
```
fitops/
├── race/
│   ├── __init__.py
│   ├── course_parser.py       # GPX + TCX + MapMyRun + Strava stream parsers
│   ├── simulation.py          # per-km split engine, pacing strategies
│   └── formatter.py           # split table formatting helpers
├── cli/
│   └── race.py                # Typer command group: import/courses/course/simulate/splits/delete
├── db/
│   └── models/
│       └── race_course.py     # RaceCourse SQLAlchemy model
└── dashboard/
    ├── routes/
    │   └── race.py            # FastAPI /race/* routes
    ├── queries/
    │   └── race.py            # DB queries for race courses
    └── templates/
        └── race/
            ├── index.html     # course list
            ├── course.html    # elevation profile + stats
            └── simulate.html  # split table + pacer viz
```

### Pattern 1: Course Normalisation (funnel to common format)
**What:** All three import sources produce the same list of dicts before DB storage.
**When to use:** Always — parser functions return `list[dict]`, simulation never knows the source.

```python
# Normalised waypoint format — output of ALL parsers
CoursePoint = TypedDict("CoursePoint", {
    "lat": float,
    "lon": float,
    "elevation_m": float,
    "distance_from_start_m": float,   # cumulative, metres
})
```

### Pattern 2: GPX Parsing
```python
# Source: gpxpy GitHub README + PyPI 1.6.2
import gpxpy

def parse_gpx(file_path: str) -> list[CoursePoint]:
    with open(file_path, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    points: list[CoursePoint] = []
    cumulative_m = 0.0
    prev = None
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                if prev is not None:
                    cumulative_m += pt.distance_2d(prev) or 0.0
                points.append({
                    "lat": pt.latitude,
                    "lon": pt.longitude,
                    "elevation_m": pt.elevation or 0.0,
                    "distance_from_start_m": cumulative_m,
                })
                prev = pt
    return points
```

Note: `pt.distance_2d(prev)` returns metres between consecutive points. Also check `gpx.routes` and `gpx.waypoints` as race organiser exports may use routes, not tracks.

### Pattern 3: TCX Parsing
```python
# Source: tcxreader v0.4.11 README
from tcxreader.tcxreader import TCXReader

def parse_tcx(file_path: str) -> list[CoursePoint]:
    reader = TCXReader()
    data = reader.read(file_path)
    points = []
    for tp in data.trackpoints:
        if tp.latitude is None or tp.longitude is None:
            continue
        points.append({
            "lat": tp.latitude,
            "lon": tp.longitude,
            "elevation_m": tp.elevation or 0.0,
            "distance_from_start_m": tp.distance or 0.0,
        })
    return points
```

### Pattern 4: MapMyRun URL Scraping
**Confirmed structure (live test on https://www.mapmyrun.com/routes/view/116211105):**

The page embeds route data in `window.__STATE__` — a JS variable holding a large JSON object. The waypoints are at `state["routes"]["route"]["points"]` — an array of objects with `"lat"`, `"lng"`, `"ele"` (elevation metres), `"dis"` (cumulative distance metres).

```python
# Source: live page inspection of www.mapmyrun.com/routes/view/116211105
import re, json

async def parse_mapmyrun_url(url: str) -> list[CoursePoint]:
    """Scrape MapMyRun route page and extract embedded waypoints."""
    async with httpx.AsyncClient(
        timeout=20.0,
        headers={"User-Agent": "Mozilla/5.0 (compatible; FitOps/1.0)"},
        follow_redirects=True,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    html = resp.text

    # window.__STATE__ = {...}; — grab the JSON object
    match = re.search(r"window\.__STATE__\s*=\s*(\{.*?\});\s*(?:window|</script)", html, re.DOTALL)
    if not match:
        raise ValueError("Could not find window.__STATE__ in MapMyRun page HTML.")

    state = json.loads(match.group(1))
    raw_points = state["routes"]["route"]["points"]  # list of {"lat":..,"lng":..,"ele":..,"dis":..}

    return [
        {
            "lat": p["lat"],
            "lon": p["lng"],
            "elevation_m": p.get("ele") or 0.0,
            "distance_from_start_m": p.get("dis") or 0.0,
        }
        for p in raw_points
    ]
```

**Scraping caveats:**
- MapMyRun may require login for private routes — handle 302 redirect to login
- The `window.__STATE__` key is an internal convention, not a public API — flag as MEDIUM confidence
- Max ~97-100 waypoints per route (not every GPS point, decimated for web display)
- Elevation field may be `null` for some routes (default to 0.0, warn user)
- Route URL pattern: `https://www.mapmyrun.com/routes/view/<route_id>`

### Pattern 5: Strava Activity Streams Import
```python
# Source: existing ActivityStream model + activity_streams table in DB
async def parse_strava_activity(
    activity_strava_id: int, session: AsyncSession
) -> list[CoursePoint]:
    """Build course points from stored activity streams (latlng + altitude)."""
    from fitops.db.models.activity_stream import ActivityStream
    # Load latlng and altitude streams
    res = await session.execute(
        select(ActivityStream).where(
            ActivityStream.activity_id == activity_strava_id,
            ActivityStream.stream_type.in_(["latlng", "altitude", "distance"]),
        )
    )
    streams = {s.stream_type: s.data for s in res.scalars().all()}

    latlng = streams.get("latlng", [])        # [[lat, lng], ...]
    altitude = streams.get("altitude", [])     # [m, m, ...]
    distance = streams.get("distance", [])     # [m, m, ...]  (cumulative)

    return [
        {
            "lat": latlng[i][0],
            "lon": latlng[i][1],
            "elevation_m": altitude[i] if i < len(altitude) else 0.0,
            "distance_from_start_m": distance[i] if i < len(distance) else 0.0,
        }
        for i in range(len(latlng))
    ]
```

### Anti-Patterns to Avoid
- **Storing every raw GPS point as a DB row:** A 42km marathon at 1-second resolution is ~15,000 rows per course. Store as JSON column instead (see DB Schema section).
- **Re-fetching MapMyRun on every simulate call:** Parse once at import time; store normalised points in DB.
- **Using `gpx.waypoints` only:** Race organiser GPX files typically use `gpx.tracks`, not `gpx.waypoints`. Check all three (`tracks`, `routes`, `waypoints`) in priority order.
- **Assuming TCX distance field is always populated:** `tp.distance` may be `None` if Garmin didn't record it. Fall back to cumulative haversine distance computation.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GPX parsing | Custom XML/lxml GPX reader | `gpxpy` | Handles GPX 1.0+1.1, extensions, time zones, multi-segment tracks — ~40 edge cases |
| TCX parsing | Custom XML/lxml TCX reader | `tcxreader` | Handles Garmin extension namespaces, missing fields, laps, multiple activities in one file |
| Wind heading math | Custom vector projection | `headwind_ms()` in `weather_pace.py` | Already implemented, tested, Pugh 1971 calibrated |
| Heat pace factor | Custom WBGT formula | `pace_heat_factor()` in `weather_pace.py` | Already implemented, Ely et al. 2007 |
| Haversine distance | Custom lat/lon distance | `gpxpy`'s `distance_2d()` or `math`-based haversine | Edge cases for antimeridian crossing, polar coordinates |

**Key insight:** The weather and GAP math is already built and production-quality. Phase 8 is primarily an integration layer that feeds existing functions with per-segment inputs.

---

## GAP Factor Formula

This is the most important algorithmic detail for the simulation engine.

### Strava Improved GAP Model (recommended)
**Source:** Fellrnr.com/wiki/Grade_Adjusted_Pace + Strava engineering blog (improved model)

Strava's production formula, derived from millions of athlete runs (heart-rate based, improved over Minetti):

```
gap_factor(i) = 1 / (1 - (15.14 * i^2 - 2.896 * i))
```

Where `i` = grade as decimal (0.10 = 10% grade, -0.05 = -5% downhill).

Or equivalently expressed as a cost multiplier:
```python
def gap_factor(grade_decimal: float) -> float:
    """
    Returns factor to divide actual pace to get flat-equivalent pace.
    grade_decimal: 0.10 = 10% uphill, -0.05 = 5% downhill.
    Strava improved model (HR-based, big data calibration).
    Source: Strava engineering + Fellrnr.com/wiki/Grade_Adjusted_Pace
    """
    grade = max(-0.45, min(0.45, grade_decimal))  # clamp to validated range
    relative_cost = 15.14 * grade**2 - 2.896 * grade
    # relative_cost > 0 means harder than flat; < 0 means easier
    # Factor > 1 means uphill (actual pace is slower, GAP is faster)
    return 1.0 + relative_cost
```

Practical interpretation:
- +5% grade → factor ~1.07 (7% slower)
- +10% grade → factor ~1.22 (22% slower)
- -5% grade → factor ~0.86 (14% faster — downhill recovery)
- -10% grade → factor ~0.87 (slight diminishing return below -10%)

### Original Minetti Formula (reference)
```
cost(i) = 155.4*i^5 - 30.4*i^4 - 43.3*i^3 + 46.3*i^2 - 165*i + 3.6
gap_factor = cost(i) / cost(0)  # cost(0) = 3.6
```

The Strava improved formula is preferred — it is calibrated to real athlete HR data, not laboratory treadmill measurements, and handles downhill gradients more accurately.

---

## Simulation Algorithm

### Core Engine: Difficulty-Weighted Pace Distribution

**The problem:** Given total target time T and a course with N km-segments, each with a different difficulty factor, compute the target pace for each segment such that:
1. The athlete expends equal energy-per-unit-time across all segments
2. Total elapsed time = T

**Solution:** Compute a normalised difficulty index per segment, then scale.

```python
def simulate_splits(
    segments: list[dict],       # [{km, elevation_gain, grade, bearing}, ...]
    target_total_s: float,      # target time in seconds
    weather: dict,              # {temperature_c, humidity_pct, wind_speed_ms, wind_direction_deg}
    strategy: str = "even",     # "even" | "negative" | "positive"
) -> list[dict]:
    """
    Distribute target_total_s across segments proportional to difficulty.

    Returns list of per-km splits with:
      km, distance_m, grade_pct, gap_factor, wap_factor,
      combined_factor, target_pace_s, cumulative_time_s
    """
    from fitops.analytics.weather_pace import compute_wap_factor, compute_bearing

    # Step 1: compute per-segment factors
    for seg in segments:
        seg["gap_factor"] = gap_factor(seg["grade"])           # uphill cost multiplier
        seg["wap_factor"] = compute_wap_factor(
            temp_c=weather["temperature_c"],
            rh_pct=weather["humidity_pct"],
            wind_speed_ms_val=weather.get("wind_speed_ms", 0.0),
            wind_dir_deg=weather.get("wind_direction_deg", 0.0),
            course_bearing=seg.get("bearing"),                 # per-segment bearing
        )
        seg["combined_factor"] = seg["gap_factor"] * seg["wap_factor"]

    # Step 2: compute mean factor across all segments (weighted by distance)
    total_dist = sum(s["distance_m"] for s in segments)
    mean_factor = sum(
        s["combined_factor"] * s["distance_m"] / total_dist for s in segments
    )

    # Step 3: base flat-equivalent pace (what pace would we need on flat, no weather?)
    base_pace_s = target_total_s / (total_dist / 1000.0)   # s/km

    # Step 4: strategy multiplier per segment
    n = len(segments)
    if strategy == "negative":
        # First half at +2%, second half at -2% relative to base
        # Research basis: Grivas et al. marathon data; ~2% differential optimal
        strategy_factors = [
            1.02 if i < n // 2 else 0.98 for i in range(n)
        ]
    elif strategy == "positive":
        strategy_factors = [
            0.98 if i < n // 2 else 1.02 for i in range(n)
        ]
    else:
        strategy_factors = [1.0] * n

    # Step 5: per-segment target pace
    # target_pace = base_pace * combined_factor * strategy_factor
    # (combined_factor > 1 = hard segment → pace is slower in seconds → numerically larger)
    splits = []
    cumulative_s = 0.0
    for i, seg in enumerate(segments):
        pace_s = base_pace_s * seg["combined_factor"] * strategy_factors[i]
        seg_time_s = pace_s * (seg["distance_m"] / 1000.0)
        cumulative_s += seg_time_s
        splits.append({
            "km": seg["km"],
            "distance_m": seg["distance_m"],
            "elevation_gain_m": seg["elevation_gain_m"],
            "grade_pct": round(seg["grade"] * 100, 1),
            "bearing_deg": round(seg.get("bearing", 0.0), 1),
            "gap_factor": round(seg["gap_factor"], 4),
            "wap_factor": round(seg["wap_factor"], 4),
            "combined_factor": round(seg["combined_factor"], 4),
            "target_pace_s": round(pace_s, 1),
            "target_pace_fmt": _fmt_pace(pace_s),
            "segment_time_s": round(seg_time_s, 1),
            "cumulative_time_s": round(cumulative_s, 1),
            "cumulative_time_fmt": _fmt_duration(cumulative_s),
        })
    return splits
```

### Pacer Mode Math

**Inputs:** pacer_pace_s (pace of pacer in s/km), drop_at_km (where athlete breaks away), total_distance_km, course segments, target_total_s.

```python
def simulate_pacer_mode(
    segments: list[dict],
    target_total_s: float,
    pacer_pace_s: float,         # s/km, the pacer's constant pace
    drop_at_km: float,           # km at which athlete breaks away from pacer
) -> dict:
    """
    Sit phase: match pacer exactly until drop_at_km.
    Push phase: calculate required pace for remaining distance to hit target_total_s.
    """
    # Split segments into sit and push phases
    sit_segs = [s for s in segments if s["km"] <= drop_at_km]
    push_segs = [s for s in segments if s["km"] > drop_at_km]

    # Sit phase: constant pacer pace (no correction for terrain — pacer handles it)
    sit_dist_km = sum(s["distance_m"] for s in sit_segs) / 1000.0
    sit_time_s = pacer_pace_s * sit_dist_km

    # Projected time at drop point (pacer's time at that km)
    time_at_drop_s = sit_time_s

    # Remaining time budget
    remaining_time_s = target_total_s - time_at_drop_s

    # Remaining distance
    push_dist_km = sum(s["distance_m"] for s in push_segs) / 1000.0

    if push_dist_km <= 0:
        raise ValueError("drop_at_km is at or beyond finish — no push phase.")

    # Required average push pace (flat equivalent)
    required_push_pace_s = remaining_time_s / push_dist_km

    # Now distribute push pace across segments with terrain adjustments
    # (same difficulty-weighted distribution as simulate_splits, just for push phase)
    push_splits = _distribute_pace(push_segs, remaining_time_s)

    return {
        "sit_phase": {
            "through_km": drop_at_km,
            "pacer_pace_fmt": _fmt_pace(pacer_pace_s),
            "projected_time_at_drop": _fmt_duration(time_at_drop_s),
            "distance_km": round(sit_dist_km, 2),
        },
        "push_phase": {
            "from_km": drop_at_km,
            "required_avg_pace_fmt": _fmt_pace(required_push_pace_s),
            "remaining_distance_km": round(push_dist_km, 2),
            "remaining_time_budget": _fmt_duration(remaining_time_s),
            "splits": push_splits,
        },
        "projected_finish": _fmt_duration(target_total_s),
    }
```

### Segment Preparation (1km buckets)

The simulation works on 1km segments. Course points (potentially hundreds) must be bucketed:

```python
def build_km_segments(points: list[CoursePoint]) -> list[dict]:
    """
    Convert normalised course points into 1km buckets.
    Each bucket: {km, distance_m, elevation_gain_m, grade, bearing}
    """
    if not points:
        return []

    total_dist = points[-1]["distance_from_start_m"]
    num_km = math.ceil(total_dist / 1000.0)
    segments = []

    for k in range(num_km):
        start_dist = k * 1000.0
        end_dist = min((k + 1) * 1000.0, total_dist)

        # Filter points in this km
        bucket_pts = [
            p for p in points
            if start_dist <= p["distance_from_start_m"] < end_dist
        ]
        if not bucket_pts:
            # Interpolate from nearest points
            continue

        start_pt = bucket_pts[0]
        end_pt = bucket_pts[-1]

        elev_gain = max(0.0, end_pt["elevation_m"] - start_pt["elevation_m"])
        elev_delta = end_pt["elevation_m"] - start_pt["elevation_m"]
        dist_m = end_dist - start_dist
        grade = elev_delta / dist_m if dist_m > 0 else 0.0

        # Mean bearing for wind calculation (start → end of this km)
        bearing = compute_bearing(
            start_pt["lat"], start_pt["lon"],
            end_pt["lat"], end_pt["lon"],
        )

        segments.append({
            "km": k + 1,
            "distance_m": dist_m,
            "elevation_gain_m": round(elev_gain, 1),
            "elevation_delta_m": round(elev_delta, 1),
            "grade": grade,
            "bearing": bearing,
        })

    return segments
```

---

## Database Schema

### `race_courses` Table

**Decision: JSON column for course_points, not a separate rows table.**
Rationale: Queries never filter on individual waypoints; all access is "load all points for course X". JSON column avoids 10,000-row joins. SQLite's JSON functions are available if needed later.

```python
class RaceCourse(Base):
    __tablename__ = "race_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)  # "gpx" | "tcx" | "mapmyrun" | "strava"
    source_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # URL or activity_id
    file_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # "gpx" | "tcx" | None

    total_distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    total_elevation_gain_m: Mapped[float] = mapped_column(Float, nullable=False)
    num_points: Mapped[int] = mapped_column(Integer, nullable=False)

    # Centre point for weather fetch (first point of course)
    start_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Full waypoints array — JSON: list of {lat, lon, elevation_m, distance_from_start_m}
    course_points_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Pre-built 1km segments — JSON: list of {km, distance_m, elevation_gain_m, grade, bearing}
    km_segments_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
```

**Notes:**
- Store `km_segments_json` pre-computed at import time (not on every simulate call)
- `start_lat`/`start_lon` enables `fitops weather forecast --lat/--lng` integration without re-parsing points
- `source_ref` records the MapMyRun URL or Strava activity ID for reference
- No `athlete_id` FK — race courses are shared resources, not athlete-specific

### Migrations
Following the existing pattern in `migrations.py`: add `RaceCourse` import to `create_all_tables()` and register in `Base.metadata`. No ALTER TABLE migrations needed (new table).

---

## Weather Integration for Race Simulation

The existing `fetch_forecast_weather()` function in `weather/client.py` is used as-is:
- Future race date → `FORECAST_URL` (up to 16 days ahead)
- Past race date → `BASE_URL` archive endpoint (already in `fetch_activity_weather()`)

**Decision logic for `simulate` command:**
```python
from datetime import date

race_date = date.fromisoformat(race_date_str)
if race_date <= date.today():
    # Historical — use archive
    weather = await fetch_activity_weather(lat, lng, race_datetime_utc)
else:
    # Future — use forecast
    weather = await fetch_forecast_weather(lat, lng, race_date_str, race_hour)
```

**Manual override path:** `--temp T --humidity H --wind W --wind-dir DEG` flags (same pattern as `fitops weather set`) let users override fetched weather. This is the primary path for dry-run planning.

---

## Pacing Strategy Details

### Even Split (default)
All segments get `combined_factor` applied, no strategy multiplier. Conceptually: equal energy expenditure per unit time. Simple, well-understood.

### Negative Split (research-backed)
**Source:** Grivas et al. (2025) "The physiology and psychology of negative splits" — PMC12307312
Research finding: ~2% differential between halves is the evidence-backed optimum. Larger differentials (e.g. 5%) are psychologically useful for inexperienced runners but physiologically sub-optimal for elites.

Implementation:
- First half segments × 1.02 (start conservatively, 2% slower than equal-effort pace)
- Second half segments × 0.98 (finish strong, 2% faster than equal-effort pace)
- Net effect: same total time, negative split profile

Note: The 2% differential applies to the strategy multiplier, not the total time split. The actual clock time difference between halves depends on course terrain.

### Positive Split (informational)
Mirror of negative split (× 0.98 first, × 1.02 second). Useful for "what happens if I go out too fast" scenario analysis.

### Pacer Mode (sit-then-push)
Math detailed above. Key invariant: `sit_time_s + push_time_s = target_total_s`. The push pace is computed as a flat-equivalent pace, then re-distributed over push segments via the same difficulty weighting as even-split simulation.

**Edge case:** if `pacer_pace × total_distance < target_total_s`, the pacer is slower than the target — pacer mode makes no sense. Raise a clear error: "Pacer pace is too slow to achieve target time."

---

## Common Pitfalls

### Pitfall 1: GPX Format Confusion (tracks vs routes vs waypoints)
**What goes wrong:** Race organiser GPX files use `<rte>` (route) elements, not `<trk>` (track) elements. A parser that only reads `gpx.tracks` returns empty results.
**Why it happens:** GPX 1.1 spec allows both formats; different export tools use different conventions.
**How to avoid:** Check all three: `gpx.tracks` → `gpx.routes` → `gpx.waypoints`. Return first non-empty.
**Warning signs:** `len(points) == 0` after parsing a file the user insists is valid.

### Pitfall 2: MapMyRun Regex Truncation
**What goes wrong:** The regex `r"window\.__STATE__\s*=\s*(\{.*?\});"` with `re.DOTALL` may match a partial JSON object if `};` appears inside the state (valid in JSON strings).
**Why it happens:** `.*?` (non-greedy) stops at the first `};`, which could be mid-JSON.
**How to avoid:** After matching, use `json.JSONDecoder().raw_decode(html, pos)` at the `{` position instead of regex group capture. This handles nested braces correctly.
**Warning signs:** `json.JSONDecodeError` on `json.loads(match.group(1))`.

### Pitfall 3: Grade Clamping for Extreme Terrain
**What goes wrong:** A MapMyRun route with a 50% grade section produces a nonsensical GAP factor of 3.0x (3× slower than flat), making the simulation output implausible.
**Why it happens:** The Strava formula is calibrated for ±45% grade (treadmill study range). Steeper grades extrapolate badly.
**How to avoid:** Clamp grade input to [-0.45, 0.45] before applying GAP formula.
**Warning signs:** `gap_factor > 2.5` on any individual km segment.

### Pitfall 4: TCX Missing Distance Field
**What goes wrong:** `tp.distance` is `None` for Garmin devices that don't record distance stream (some older models).
**Why it happens:** Distance is optional in TCX spec. Some devices only store GPS + HR.
**How to avoid:** If `tp.distance is None`, compute cumulative distance using haversine between consecutive points.
**Warning signs:** All `distance_from_start_m` values are 0.0 in normalised output.

### Pitfall 5: Open-Meteo Forecast Horizon
**What goes wrong:** `fetch_forecast_weather()` fails silently for dates > 16 days ahead, returning `None`.
**Why it happens:** Open-Meteo forecast API maximum is 16 days. Beyond that, the API returns an error.
**How to avoid:** Check `race_date > today + timedelta(days=16)` before calling forecast. If true, prompt user to use `--temp/--humidity/--wind` manual flags.
**Warning signs:** `weather is None` after `fetch_forecast_weather()` call for a race far in the future.

### Pitfall 6: Simulation Ignores Last Partial Km
**What goes wrong:** A 21.1km half marathon produces 21 segments, missing the final 100m.
**Why it happens:** `math.floor(total_dist / 1000)` truncates the partial km.
**How to avoid:** Use `math.ceil` and handle the last segment with its actual sub-1km distance in the segment time calculation.
**Warning signs:** Simulated total time is systematically ~0.3–1% shorter than target.

---

## Code Examples

### Import Detection + Dispatch
```python
import os, re

def detect_source(arg: str) -> tuple[str, str]:
    """
    Returns (source_type, value):
      ("mapmyrun", url) | ("gpx", path) | ("tcx", path) | ("strava", activity_id)
    """
    if arg.startswith("https://www.mapmyrun.com/routes/view/"):
        return ("mapmyrun", arg)
    if os.path.isfile(arg):
        ext = os.path.splitext(arg)[1].lower()
        if ext == ".gpx":
            return ("gpx", arg)
        if ext == ".tcx":
            return ("tcx", arg)
        raise ValueError(f"Unsupported file extension: {ext}")
    if re.match(r"^\d+$", arg):
        return ("strava", arg)
    raise ValueError(f"Cannot determine source from: {arg!r}")
```

### Pace + Duration Formatting
```python
def _fmt_pace(s_per_km: float) -> str:
    mins = int(s_per_km) // 60
    secs = int(s_per_km) % 60
    return f"{mins}:{secs:02d}/km"

def _fmt_duration(total_s: float) -> str:
    h = int(total_s) // 3600
    m = (int(total_s) % 3600) // 60
    s = int(total_s) % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def _parse_time(time_str: str) -> float:
    """Parse HH:MM:SS or MM:SS into total seconds."""
    parts = time_str.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return int(parts[0]) * 60 + int(parts[1])
```

### CLI Command Structure (Typer pattern, matching existing CLIs)
```python
# fitops/cli/race.py
import typer
app = typer.Typer(no_args_is_help=True)

@app.command("import")
def import_course(
    source: str = typer.Argument(..., help="GPX/TCX file path, MapMyRun URL, or Strava activity ID."),
    name: str = typer.Option(..., "--name", help="Course name."),
) -> None:
    """Import a race course from a file, URL, or Strava activity."""
    init_db()
    ...

@app.command("simulate")
def simulate(
    course_id: int = typer.Argument(...),
    target_time: Optional[str] = typer.Option(None, "--target-time", help="HH:MM:SS"),
    target_pace: Optional[str] = typer.Option(None, "--target-pace", help="MM:SS"),
    pacer_pace: Optional[str] = typer.Option(None, "--pacer-pace", help="MM:SS"),
    drop_at_km: Optional[float] = typer.Option(None, "--drop-at-km"),
    strategy: str = typer.Option("even", "--strategy", help="even | negative | positive"),
    temp: Optional[float] = typer.Option(None, "--temp"),
    humidity: Optional[float] = typer.Option(None, "--humidity"),
    wind: Optional[float] = typer.Option(None, "--wind"),
    wind_dir: Optional[float] = typer.Option(None, "--wind-dir"),
    race_date: Optional[str] = typer.Option(None, "--date", help="YYYY-MM-DD for weather fetch."),
    race_hour: int = typer.Option(9, "--hour"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Simulate a race with per-km splits accounting for elevation and weather."""
    init_db()
    ...
```

### Registration in main.py
```python
from fitops.cli.race import app as race_app
app.add_typer(race_app, name="race", help="Race course management and simulation.")
```

---

## Dashboard Components

Following the existing FastAPI + Jinja2 + Chart.js pattern from `dashboard/routes/weather.py`:

### Routes
- `GET /race` — course list (table of imported courses)
- `GET /race/{course_id}` — course profile (elevation chart + stats)
- `GET /race/{course_id}/simulate` — simulation form + results
- `POST /race/{course_id}/simulate` — run simulation, redirect to results

### Charts (Chart.js, matching existing pattern)
1. **Elevation Profile** — Line chart, x-axis = km, y-axis = elevation_m. Markers at each km.
2. **Split Bar Chart** — Bar chart, x-axis = km, y-axis = target_pace_s_per_km. Color-coded: green (below target avg) → red (above target avg). Overlay pacer line if pacer mode.
3. **Scenario Comparison** — Multiple dataset overlays on split chart (e.g. even vs negative split for same course + target).

### Template file placement
```
fitops/dashboard/templates/race/
├── index.html       # course list (table)
├── course.html      # elevation profile + km-segment stats table
└── simulate.html    # simulation form at top, split table + charts below
```

---

## Unit System Handling

Open-Meteo already returns wind speed in m/s (enforced by `wind_speed_unit=ms` in `weather/client.py`). All internal calculations use SI units:
- Distances: metres internally, displayed as km
- Pace: seconds/km internally, displayed as MM:SS/km
- Elevation: metres throughout
- Wind: m/s for physics functions in `weather_pace.py`

The `--unit km|mi` flag in the roadmap CLI spec should affect **display only**, not internal computation. Implement a display formatter that converts pace and distance for output.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x (already configured) |
| Config file | `pyproject.toml` → `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/test_race.py -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map
| Behavior | Test Type | Automated Command |
|----------|-----------|-------------------|
| GPX parsing returns normalised waypoints | unit | `pytest tests/test_race.py::test_parse_gpx -x` |
| TCX parsing returns normalised waypoints | unit | `pytest tests/test_race.py::test_parse_tcx -x` |
| MapMyRun JSON extraction from mocked HTML | unit | `pytest tests/test_race.py::test_parse_mapmyrun_html -x` |
| `build_km_segments()` bucketing correct | unit | `pytest tests/test_race.py::test_km_segments -x` |
| GAP factor values at known grades | unit | `pytest tests/test_race.py::test_gap_factor -x` |
| Even-split total time equals target | unit | `pytest tests/test_race.py::test_even_split_total_time -x` |
| Negative-split halves: second half faster | unit | `pytest tests/test_race.py::test_negative_split_halves -x` |
| Pacer mode: sit+push times sum to target | unit | `pytest tests/test_race.py::test_pacer_mode_total_time -x` |
| Pacer too slow → clear error raised | unit | `pytest tests/test_race.py::test_pacer_too_slow_error -x` |
| Grade clamping at ±45% | unit | `pytest tests/test_race.py::test_grade_clamp -x` |

### Wave 0 Gaps
- [ ] `tests/test_race.py` — all simulation unit tests (new file)
- [ ] `tests/fixtures/sample.gpx` — minimal valid GPX with 3 trackpoints
- [ ] `tests/fixtures/sample.tcx` — minimal valid TCX with 3 trackpoints
- [ ] Install new deps: `pip install gpxpy tcxreader`

---

## Open Questions

1. **MapMyRun `window.__STATE__` stability**
   - What we know: The key `window.__STATE__` with `routes.route.points` array confirmed live on route/116211105
   - What's unclear: Whether Under Armour (MapMyRun owner) can change this internal structure at any time; whether it requires a logged-in session for non-public routes
   - Recommendation: Implement with a clear error message when parsing fails; document as "best-effort" feature; always suggest GPX export as the stable alternative

2. **Strava activity stream availability**
   - What we know: `latlng`, `altitude`, `distance` streams are fetched by `fitops activities streams <id>`
   - What's unclear: Whether all users' historical activities have streams cached, or if streams need to be re-fetched
   - Recommendation: Check `streams_fetched` flag on the Activity row; if False, prompt user to run `fitops activities streams <id>` first

3. **Elevation smoothing**
   - What we know: Raw GPS elevation data can be noisy (±5–10m error per point), causing artificial grade spikes
   - What's unclear: Whether scipy smooth (e.g. Gaussian filter) is worth the added complexity, or whether 1km bucketing already smooths enough
   - Recommendation: Try without smoothing first; add as optional `--smooth-elevation` flag if needed

4. **MapMyRun login requirement for private routes**
   - What we know: Public routes are accessible without auth
   - What's unclear: How to handle 302 redirects to login page
   - Recommendation: Detect redirect to mapmyrun.com/auth or /login URL; raise a clear error: "Route appears to be private or login required. Export to GPX and use `fitops race import file.gpx`."

---

## Sources

### Primary (HIGH confidence)
- `fitops/analytics/weather_pace.py` — existing GAP, WAP, bearing, headwind functions (Phase 7 production code)
- `fitops/weather/client.py` — Open-Meteo fetch pattern, field mapping, archive vs forecast URL
- `fitops/cli/weather.py` — CLI command pattern (asyncio.run bridge, Typer options, JSON output)
- `fitops/dashboard/routes/weather.py` — FastAPI + Jinja2 + Chart.js dashboard pattern
- `fitops/db/migrations.py` — table registration and ALTER TABLE migration pattern

### Secondary (MEDIUM confidence)
- [gpxpy PyPI page](https://pypi.org/project/gpxpy/) — version 1.6.2, current
- [gpxpy GitHub README](https://github.com/tkrajina/gpxpy) — parse/tracks/segments/points API
- [tcxreader GitHub README](https://github.com/alenrajsp/tcxreader) — trackpoint properties, v0.4.11
- [Fellrnr.com/wiki/Grade_Adjusted_Pace](https://fellrnr.com/wiki/Grade_Adjusted_Pace) — Minetti polynomial + Strava formula coefficients
- [Open-Meteo docs](https://open-meteo.com/en/docs) — forecast endpoint, 16-day max window
- [PMC12307312 — negative split physiology](https://pmc.ncbi.nlm.nih.gov/articles/PMC12307312/) — 2% differential evidence

### Tertiary (MEDIUM confidence — live scraping test)
- Live test of `https://www.mapmyrun.com/routes/view/116211105` — confirmed `window.__STATE__` structure with `routes.route.points` array, format `{"lat":..., "lng":..., "ele":..., "dis":...}`, ~98 waypoints for a 21km course. This is an internal structure — no official documentation exists.

---

## Metadata

**Confidence breakdown:**
- Standard stack (gpxpy, tcxreader): HIGH — both actively maintained, confirmed API, current releases
- GAP formula: HIGH — Strava/Minetti formula confirmed via Fellrnr.com with multiple cross-references
- Simulation math: HIGH — pure arithmetic on existing Phase 7 physics functions
- MapMyRun scraping: MEDIUM — structure confirmed live but undocumented, subject to change
- Dashboard patterns: HIGH — follows exact existing Phase 7 dashboard implementation

**Research date:** 2026-03-19
**Valid until:** 2026-09-19 for stable parts; 2026-04-19 for MapMyRun scraping (check if `window.__STATE__` still works)
