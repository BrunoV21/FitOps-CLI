"""
fitops/race/course_parser.py

Course import parsers and segment builder for race simulation.
Supports GPX, TCX, MapMyRun HTML/URL, and Strava activity streams.
All parsers return a list of CoursePoint dicts in the same normalised format.
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import TypedDict

import gpxpy
from tcxreader.tcxreader import TCXReader
import httpx

from fitops.analytics.weather_pace import compute_bearing


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

class CoursePoint(TypedDict):
    lat: float
    lon: float
    elevation_m: float
    distance_from_start_m: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two lat/lon points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Source detection
# ---------------------------------------------------------------------------

def detect_source(arg: str) -> tuple[str, str]:
    """
    Classify *arg* and return (source_type, value).

    - Strava URL    → ("strava_url", url)
    - MapMyRun URL  → ("mapmyrun", url)
    - .gpx file     → ("gpx", path)
    - .tcx file     → ("tcx", path)
    - numeric ID    → ("strava", id_str)   # legacy: fetch from local DB streams
    """
    if "strava.com/activities/" in arg:
        return ("strava_url", arg)
    if arg.startswith("https://www.mapmyrun.com"):
        return ("mapmyrun", arg)
    if os.path.isfile(arg):
        ext = os.path.splitext(arg)[1].lower()
        if ext == ".gpx":
            return ("gpx", arg)
        if ext == ".tcx":
            return ("tcx", arg)
        raise ValueError(f"Unsupported file extension: {ext!r}. Expected .gpx or .tcx")
    if re.match(r"^\d+$", arg):
        return ("strava", arg)
    raise ValueError(
        f"Cannot determine source for {arg!r}. "
        "Provide a Strava URL, MapMyRun URL, .gpx/.tcx file path, or numeric Strava activity ID."
    )


# ---------------------------------------------------------------------------
# GPX parser
# ---------------------------------------------------------------------------

def parse_gpx(file_path: str) -> list[CoursePoint]:
    """
    Parse a GPX file into a list of CoursePoints.

    Priority order: tracks → routes → waypoints (returns first non-empty list).
    Cumulative distance is computed via gpxpy's distance_2d between consecutive points.
    """
    with open(file_path, "r", encoding="utf-8") as fh:
        gpx = gpxpy.parse(fh)

    def _from_raw(raw_pts: list) -> list[CoursePoint]:
        result: list[CoursePoint] = []
        cumulative = 0.0
        prev = None
        for pt in raw_pts:
            if pt.latitude is None or pt.longitude is None:
                continue
            if prev is not None:
                d = pt.distance_2d(prev)
                cumulative += d if d is not None else 0.0
            result.append({
                "lat": pt.latitude,
                "lon": pt.longitude,
                "elevation_m": pt.elevation or 0.0,
                "distance_from_start_m": cumulative,
            })
            prev = pt
        return result

    # tracks
    track_pts: list = []
    for track in gpx.tracks:
        for segment in track.segments:
            track_pts.extend(segment.points)
    if track_pts:
        return _from_raw(track_pts)

    # routes
    route_pts: list = []
    for route in gpx.routes:
        route_pts.extend(route.points)
    if route_pts:
        return _from_raw(route_pts)

    # waypoints
    if gpx.waypoints:
        return _from_raw(gpx.waypoints)

    return []


# ---------------------------------------------------------------------------
# TCX parser
# ---------------------------------------------------------------------------

def parse_tcx(file_path: str) -> list[CoursePoint]:
    """
    Parse a TCX file into a list of CoursePoints.

    If any trackpoint is missing a cumulative distance value, the entire file
    falls back to haversine-derived cumulative distances.
    """
    reader = TCXReader()
    data = reader.read(file_path)

    valid_tps = [tp for tp in data.trackpoints if tp.latitude is not None and tp.longitude is not None]

    # Determine whether we can use native distance values
    use_native = all(tp.distance is not None for tp in valid_tps)

    result: list[CoursePoint] = []
    cumulative = 0.0
    prev_lat: float | None = None
    prev_lon: float | None = None

    for tp in valid_tps:
        if use_native:
            dist = float(tp.distance)  # type: ignore[arg-type]
        else:
            if prev_lat is not None and prev_lon is not None:
                cumulative += _haversine_m(prev_lat, prev_lon, tp.latitude, tp.longitude)
            dist = cumulative

        result.append({
            "lat": float(tp.latitude),
            "lon": float(tp.longitude),
            "elevation_m": float(tp.elevation) if tp.elevation is not None else 0.0,
            "distance_from_start_m": dist,
        })
        prev_lat = tp.latitude
        prev_lon = tp.longitude

    return result


# ---------------------------------------------------------------------------
# MapMyRun HTML parser
# ---------------------------------------------------------------------------

def parse_mapmyrun_html(html_str: str) -> list[CoursePoint]:
    """
    Extract course points from a MapMyRun page HTML string.

    Locates ``window.__STATE__`` and uses JSONDecoder.raw_decode() at the
    opening ``{`` position to avoid truncation caused by regex group capture.
    """
    match = re.search(r"window\.__STATE__\s*=\s*", html_str)
    if match is None:
        raise ValueError("Could not find window.__STATE__ in the provided HTML")

    # Position of the opening brace of the JSON object
    brace_pos = match.end()
    # Advance to the first '{' in case there is whitespace
    while brace_pos < len(html_str) and html_str[brace_pos] != "{":
        brace_pos += 1

    try:
        state, _ = json.JSONDecoder().raw_decode(html_str, brace_pos)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse window.__STATE__ JSON: {exc}") from exc

    try:
        raw_points = state["routes"]["route"]["points"]
    except (KeyError, TypeError) as exc:
        raise ValueError("MapMyRun page may require login or has unexpected structure") from exc

    return [
        {
            "lat": float(p["lat"]),
            "lon": float(p["lng"]),
            "elevation_m": float(p.get("ele") or 0.0),
            "distance_from_start_m": float(p.get("dis") or 0.0),
        }
        for p in raw_points
    ]


# ---------------------------------------------------------------------------
# MapMyRun URL fetcher (async)
# ---------------------------------------------------------------------------

async def parse_mapmyrun_url(url: str) -> list[CoursePoint]:
    """
    Fetch a MapMyRun route page and parse course points from it.

    Raises ValueError if the route requires login or cannot be fetched.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
        resp = await client.get(url)

    final_url = str(resp.url)
    if "/auth" in final_url or "/login" in final_url:
        raise ValueError("Route requires login — redirected to auth page")

    return parse_mapmyrun_html(resp.text)


# ---------------------------------------------------------------------------
# Strava URL importer (async) — for dashboard use
# ---------------------------------------------------------------------------

_STRAVA_ACTIVITY_RE = re.compile(r"strava\.com/activities/(\d+)")


async def parse_strava_url(url: str) -> list[CoursePoint]:
    """
    Import a course from a Strava activity URL.

    Strategy:
      1. Extract activity ID from URL.
      2. Try downloading GPX via /export_gpx with the stored Bearer token.
      3. On failure, fall back to Strava API streams (latlng + altitude + distance).

    Raises ValueError if authentication is missing or data cannot be retrieved.
    """
    m = _STRAVA_ACTIVITY_RE.search(url)
    if not m:
        raise ValueError(f"Cannot extract a Strava activity ID from URL: {url!r}")
    activity_id = int(m.group(1))

    # Get access token from stored settings
    from fitops.strava.oauth import StravaOAuth
    from fitops.config.settings import get_settings
    settings = get_settings()
    if not settings.access_token:
        raise ValueError("No Strava access token found. Run `fitops auth login` first.")
    oauth = StravaOAuth(settings)
    token = await oauth.ensure_valid_token()

    # 1. Try GPX export
    try:
        gpx_url = f"https://www.strava.com/activities/{activity_id}/export_gpx"
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=False,
            timeout=30.0,
        ) as client:
            resp = await client.get(gpx_url)

        if resp.status_code == 200 and resp.content:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".gpx", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name
            try:
                points = parse_gpx(tmp_path)
            finally:
                os.unlink(tmp_path)
            if points:
                return points
    except Exception:
        pass  # fall through to API streams

    # 2. Fall back to Strava API streams
    api_url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:
        resp = await client.get(api_url, params={
            "keys": "latlng,altitude,distance",
            "key_by_type": "true",
        })

    if resp.status_code == 401:
        raise ValueError("Strava token expired — run `fitops auth refresh`.")
    if resp.status_code == 403:
        raise ValueError(
            f"Activity {activity_id} is private or you don't have access to it."
        )
    if resp.status_code == 404:
        raise ValueError(f"Activity {activity_id} not found on Strava.")
    if resp.status_code >= 400:
        raise ValueError(f"Strava API error {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    latlng    = data.get("latlng",    {}).get("data", [])
    altitudes = data.get("altitude",  {}).get("data", [])
    distances = data.get("distance",  {}).get("data", [])

    if not latlng:
        raise ValueError(
            f"Activity {activity_id} has no GPS data (latlng stream empty)."
        )

    points: list[CoursePoint] = []
    for i, (lat, lon) in enumerate(latlng):
        points.append({
            "lat": float(lat),
            "lon": float(lon),
            "elevation_m": float(altitudes[i]) if i < len(altitudes) else 0.0,
            "distance_from_start_m": float(distances[i]) if i < len(distances) else 0.0,
        })
    return points


# ---------------------------------------------------------------------------
# Strava activity stream extractor (async)
# ---------------------------------------------------------------------------

async def parse_strava_activity(activity_strava_id: int, session) -> list[CoursePoint]:
    """
    Build CoursePoints from Strava activity streams.

    Looks up the activity in the local DB by Strava ID, then queries its
    cached streams.  If streams have not been fetched yet, they are
    downloaded from the Strava API automatically.
    """
    from fitops.db.models.activity import Activity
    from fitops.db.models.activity_stream import ActivityStream  # local import to avoid circular
    from sqlalchemy import select

    # Resolve the DB primary key (activity_streams.activity_id is the PK, not the Strava ID)
    activity_result = await session.execute(
        select(Activity).where(Activity.strava_id == activity_strava_id)
    )
    activity = activity_result.scalar_one_or_none()
    if activity is None:
        raise ValueError(
            f"Activity {activity_strava_id} not found locally. "
            f"Run: fitops sync run"
        )

    # Auto-fetch streams if not yet cached
    if not activity.streams_fetched:
        from fitops.strava.client import StravaClient
        client = StravaClient()
        stream_data = await client.get_activity_streams(activity_strava_id)
        for stream_type, stream_obj in stream_data.items():
            data_list = stream_obj.get("data", []) if isinstance(stream_obj, dict) else stream_obj
            existing = await session.execute(
                select(ActivityStream).where(
                    ActivityStream.activity_id == activity.id,
                    ActivityStream.stream_type == stream_type,
                )
            )
            if existing.scalar_one_or_none() is None:
                session.add(ActivityStream.from_strava_stream(activity.id, stream_type, data_list))
        activity.streams_fetched = True
        await session.commit()

    stmt = select(ActivityStream).where(
        ActivityStream.activity_id == activity.id,
        ActivityStream.stream_type.in_(("latlng", "altitude", "distance")),
    )
    rows = (await session.execute(stmt)).scalars().all()

    streams: dict[str, list] = {}
    for row in rows:
        streams[row.stream_type] = json.loads(row.data)

    latlng = streams.get("latlng", [])
    if not latlng:
        raise ValueError(
            f"Activity {activity_strava_id} has no GPS data (latlng stream is empty). "
            f"This activity may be an indoor workout with no route."
        )

    altitudes = streams.get("altitude", [])
    distances = streams.get("distance", [])

    points: list[CoursePoint] = []
    for i, (lat, lon) in enumerate(latlng):
        points.append({
            "lat": float(lat),
            "lon": float(lon),
            "elevation_m": float(altitudes[i]) if i < len(altitudes) else 0.0,
            "distance_from_start_m": float(distances[i]) if i < len(distances) else 0.0,
        })

    return points


# ---------------------------------------------------------------------------
# Segment builder
# ---------------------------------------------------------------------------

_GRADE_MIN = -0.45
_GRADE_MAX = 0.45


def build_km_segments(points: list[CoursePoint]) -> list[dict]:
    """
    Bucket a list of CoursePoints into 1-km segments.

    The final segment may be shorter than 1 km (partial last km handled via
    math.ceil). Grade is clamped to [-0.45, 0.45].
    """
    if not points:
        return []

    total_dist = points[-1]["distance_from_start_m"]
    num_km = math.ceil(total_dist / 1000.0)

    segments: list[dict] = []
    for k in range(num_km):
        start_dist = k * 1000.0
        end_dist = min((k + 1) * 1000.0, total_dist)

        bucket_pts = [
            p for p in points if start_dist <= p["distance_from_start_m"] < end_dist
        ]
        # Include the very last point in the final km
        if k == num_km - 1:
            bucket_pts = [
                p for p in points if start_dist <= p["distance_from_start_m"] <= end_dist
            ]

        if not bucket_pts:
            continue  # sparse GPS — skip

        start_pt = bucket_pts[0]
        end_pt = bucket_pts[-1]

        elev_delta = end_pt["elevation_m"] - start_pt["elevation_m"]
        elev_gain = max(0.0, elev_delta)
        dist_m = end_dist - start_dist
        raw_grade = elev_delta / dist_m if dist_m > 0 else 0.0
        grade = max(_GRADE_MIN, min(_GRADE_MAX, raw_grade))

        bearing = compute_bearing(
            start_pt["lat"], start_pt["lon"],
            end_pt["lat"], end_pt["lon"],
        )

        segments.append({
            "km": k + 1,
            "distance_m": round(dist_m, 1),
            "elevation_gain_m": round(elev_gain, 1),
            "elevation_delta_m": round(elev_delta, 1),
            "grade": grade,
            "bearing": bearing,
        })

    return segments


# ---------------------------------------------------------------------------
# Formatter helpers
# ---------------------------------------------------------------------------

def _fmt_pace(s_per_km: float) -> str:
    """Format seconds/km as MM:SS/km string."""
    mins = int(s_per_km) // 60
    secs = int(s_per_km) % 60
    return f"{mins}:{secs:02d}/km"


def _fmt_duration(total_s: float) -> str:
    """Format seconds as H:MM:SS or M:SS string."""
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


def compute_total_elevation_gain(points: list[CoursePoint]) -> float:
    """Sum all positive elevation deltas across course points."""
    total = 0.0
    for i in range(1, len(points)):
        delta = points[i]["elevation_m"] - points[i - 1]["elevation_m"]
        if delta > 0:
            total += delta
    return round(total, 1)
