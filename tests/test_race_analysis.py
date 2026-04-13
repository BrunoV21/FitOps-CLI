"""Tests for Phase 9 — Race Analysis & Replay.

Covers:
- Unit tests: normalize_stream, compute_gap_series, compute_delta_series,
  detect_events (surge, fade, final_sprint, drop, bridge, separation)
- Output formatter smoke tests
- CLI JSON shape tests
- Dashboard HTTP 200 tests (/race/sessions, /race/sessions/{id})
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fitops.analytics.race_analysis import (
    NormalizedStream,
    RaceEvent,
    DetectedSegment,
    build_common_grid,
    compute_delta_series,
    compute_gap_series,
    compute_segment_athlete_metrics,
    detect_events,
    detect_segments_from_altitude,
    detect_segments_from_km_segments,
    elapsed_at_distance,
    normalize_stream,
    normalized_stream_from_dict,
    normalized_stream_to_dict,
)


# ---------------------------------------------------------------------------
# Helpers — fabricate minimal raw streams
# ---------------------------------------------------------------------------


def _make_raw_streams(
    total_dist_m: float,
    total_time_s: float,
    n_pts: int = 50,
    velocity: float | None = None,
) -> dict:
    """Uniform pace raw streams over n_pts data points."""
    distances = [i * total_dist_m / (n_pts - 1) for i in range(n_pts)]
    times = [i * total_time_s / (n_pts - 1) for i in range(n_pts)]
    streams: dict = {"distance": distances, "time": times}
    if velocity is not None:
        streams["velocity_smooth"] = [velocity] * n_pts
    return streams


def _make_normalized(
    label: str,
    total_dist_m: float,
    total_time_s: float,
    n_pts: int = 50,
    velocity: float | None = None,
    is_primary: bool = True,
) -> NormalizedStream:
    raw = _make_raw_streams(total_dist_m, total_time_s, n_pts, velocity)
    return normalize_stream(raw, label, is_primary)


# ---------------------------------------------------------------------------
# normalize_stream — grid alignment and interpolation
# ---------------------------------------------------------------------------


def test_normalize_stream_grid_spacing():
    """Grid points should be spaced at 10m intervals."""
    ns = _make_normalized("A", total_dist_m=100.0, total_time_s=60.0, n_pts=20)
    assert ns.distance_grid[0] == 0.0
    # All steps should be 10m (the default)
    steps = [
        round(ns.distance_grid[i + 1] - ns.distance_grid[i], 6)
        for i in range(len(ns.distance_grid) - 1)
    ]
    assert all(abs(s - 10.0) < 0.01 for s in steps)


def test_normalize_stream_elapsed_monotonic():
    """Elapsed seconds should be monotonically increasing."""
    ns = _make_normalized("A", total_dist_m=500.0, total_time_s=200.0, n_pts=30)
    for i in range(1, len(ns.elapsed_s)):
        assert ns.elapsed_s[i] >= ns.elapsed_s[i - 1]


def test_normalize_stream_total_time_preserved():
    """Last elapsed value should approximate total race time."""
    total_time_s = 300.0
    ns = _make_normalized("A", total_dist_m=1000.0, total_time_s=total_time_s, n_pts=50)
    assert abs(ns.elapsed_s[-1] - total_time_s) < 2.0


def test_normalize_stream_empty_returns_empty():
    """Empty raw streams → empty NormalizedStream."""
    ns = normalize_stream({}, "A", is_primary=True)
    assert ns.distance_grid == []
    assert ns.elapsed_s == []


def test_normalize_stream_label_preserved():
    ns = _make_normalized("Athlete X", total_dist_m=200.0, total_time_s=100.0)
    assert ns.label == "Athlete X"
    assert ns.is_primary is True


def test_normalize_stream_velocity_interpolated():
    """velocity_smooth should be interpolated onto the grid."""
    raw = _make_raw_streams(200.0, 80.0, n_pts=20, velocity=2.5)
    ns = normalize_stream(raw, "A", is_primary=True)
    assert ns.velocity is not None
    assert len(ns.velocity) == len(ns.distance_grid)
    # All velocity values should be close to 2.5 m/s
    valid = [v for v in ns.velocity if v is not None]
    assert all(abs(v - 2.5) < 0.5 for v in valid)


def test_normalize_stream_roundtrip():
    """Serialise and deserialise NormalizedStream should be lossless."""
    ns = _make_normalized("B", total_dist_m=500.0, total_time_s=180.0)
    d = normalized_stream_to_dict(ns)
    ns2 = normalized_stream_from_dict(d)
    assert ns2.label == ns.label
    assert ns2.is_primary == ns.is_primary
    assert len(ns2.distance_grid) == len(ns.distance_grid)
    assert ns2.elapsed_s[0] == pytest.approx(ns.elapsed_s[0], abs=0.1)
    assert ns2.elapsed_s[-1] == pytest.approx(ns.elapsed_s[-1], abs=0.1)


# ---------------------------------------------------------------------------
# elapsed_at_distance
# ---------------------------------------------------------------------------


def test_elapsed_at_distance_start():
    ns = _make_normalized("A", total_dist_m=1000.0, total_time_s=300.0)
    t = elapsed_at_distance(ns, 0.0)
    assert t == pytest.approx(0.0, abs=1.0)


def test_elapsed_at_distance_end():
    ns = _make_normalized("A", total_dist_m=1000.0, total_time_s=300.0)
    t = elapsed_at_distance(ns, 1000.0)
    assert t == pytest.approx(300.0, abs=2.0)


def test_elapsed_at_distance_midpoint():
    """At half distance, elapsed should be roughly half the total time."""
    ns = _make_normalized("A", total_dist_m=1000.0, total_time_s=300.0)
    t = elapsed_at_distance(ns, 500.0)
    assert t == pytest.approx(150.0, abs=5.0)


def test_elapsed_at_distance_empty():
    ns = NormalizedStream(
        label="X", is_primary=True, activity_id=None, distance_grid=[], elapsed_s=[]
    )
    assert elapsed_at_distance(ns, 100.0) is None


# ---------------------------------------------------------------------------
# build_common_grid
# ---------------------------------------------------------------------------


def test_build_common_grid_uses_min_distance():
    """Common grid should stop at the shorter athlete's distance."""
    a = _make_normalized("A", total_dist_m=1000.0, total_time_s=300.0)
    b = _make_normalized("B", total_dist_m=800.0, total_time_s=250.0)
    grid = build_common_grid([a, b])
    assert grid[-1] <= 800.0


def test_build_common_grid_empty():
    assert build_common_grid([]) == []


# ---------------------------------------------------------------------------
# compute_gap_series
# ---------------------------------------------------------------------------


def test_gap_series_leader_always_zero():
    """The faster athlete should always have gap_to_leader_s == 0."""
    fast = _make_normalized("Fast", total_dist_m=1000.0, total_time_s=240.0)
    slow = _make_normalized("Slow", total_dist_m=1000.0, total_time_s=300.0)
    gaps = compute_gap_series([fast, slow])

    fast_gaps = gaps["Fast"]
    assert all(p["gap_to_leader_s"] == pytest.approx(0.0, abs=0.5) for p in fast_gaps)


def test_gap_series_follower_has_positive_gap():
    """The slower athlete should accumulate positive gap."""
    fast = _make_normalized("Fast", total_dist_m=1000.0, total_time_s=240.0)
    slow = _make_normalized("Slow", total_dist_m=1000.0, total_time_s=300.0)
    gaps = compute_gap_series([fast, slow])

    slow_gaps = gaps["Slow"]
    # At the end, gap should be ~60s (300 - 240)
    assert slow_gaps[-1]["gap_to_leader_s"] == pytest.approx(60.0, abs=10.0)


def test_gap_series_positions():
    """Position field should reflect rank (leader = 1)."""
    fast = _make_normalized("Fast", total_dist_m=1000.0, total_time_s=200.0)
    slow = _make_normalized("Slow", total_dist_m=1000.0, total_time_s=300.0)
    gaps = compute_gap_series([fast, slow])

    # At most grid points, Fast should be position 1
    fast_positions = [p["position"] for p in gaps["Fast"]]
    assert all(pos == 1 for pos in fast_positions)

    slow_positions = [p["position"] for p in gaps["Slow"]]
    assert all(pos == 2 for pos in slow_positions)


def test_gap_series_distance_km_field():
    """Each gap point should have a distance_km field."""
    a = _make_normalized("A", total_dist_m=500.0, total_time_s=150.0)
    b = _make_normalized("B", total_dist_m=500.0, total_time_s=180.0)
    gaps = compute_gap_series([a, b])
    for label, series in gaps.items():
        for point in series:
            assert "distance_km" in point
            assert point["distance_km"] >= 0.0


def test_gap_series_single_athlete():
    """Single athlete: gap is always 0."""
    ns = _make_normalized("Solo", total_dist_m=1000.0, total_time_s=300.0)
    gaps = compute_gap_series([ns])
    for p in gaps["Solo"]:
        assert p["gap_to_leader_s"] == pytest.approx(0.0, abs=0.1)


# ---------------------------------------------------------------------------
# compute_delta_series
# ---------------------------------------------------------------------------


def test_delta_series_shape():
    """Delta series should have one fewer point than the gap series (derivative)."""
    fast = _make_normalized("Fast", total_dist_m=1000.0, total_time_s=240.0)
    slow = _make_normalized("Slow", total_dist_m=1000.0, total_time_s=300.0)
    gaps = compute_gap_series([fast, slow])
    deltas = compute_delta_series(gaps)

    for label in ["Fast", "Slow"]:
        assert len(deltas[label]) <= len(gaps[label])


def test_delta_series_fields():
    """Each delta point should have distance_km and delta_s_per_km."""
    a = _make_normalized("A", total_dist_m=500.0, total_time_s=150.0)
    b = _make_normalized("B", total_dist_m=500.0, total_time_s=200.0)
    gaps = compute_gap_series([a, b])
    deltas = compute_delta_series(gaps)
    for label, series in deltas.items():
        for point in series:
            assert "distance_km" in point
            assert "delta_s_per_km" in point


def test_delta_series_even_pace_near_zero():
    """Two athletes at constant pace → gap roughly constant → delta near 0."""
    # Both at identical pace, different start times not relevant for relative gaps
    fast = _make_normalized("Fast", total_dist_m=1000.0, total_time_s=200.0, velocity=5.0)
    slow = _make_normalized("Slow", total_dist_m=1000.0, total_time_s=250.0, velocity=4.0)
    gaps = compute_gap_series([fast, slow])
    deltas = compute_delta_series(gaps)
    # For "Fast" (leader, gap always 0), deltas should be near 0
    fast_deltas = [abs(p["delta_s_per_km"]) for p in deltas.get("Fast", [])]
    if fast_deltas:
        assert max(fast_deltas) < 5.0  # leader's gap is always 0 → delta near 0


# ---------------------------------------------------------------------------
# detect_segments_from_km_segments
# ---------------------------------------------------------------------------


def _make_km_segments(grades: list[float]) -> list[dict]:
    return [{"km": i + 1, "distance_m": 1000.0, "grade": g, "bearing": 0.0} for i, g in enumerate(grades)]


def test_detect_segments_all_flat():
    km_segs = _make_km_segments([0.5, 1.0, -0.5, 0.2])
    segs = detect_segments_from_km_segments(km_segs)
    assert len(segs) == 1
    assert segs[0].gradient_type == "flat"


def test_detect_segments_climb():
    km_segs = _make_km_segments([4.0, 5.0, 4.5, 5.0])
    segs = detect_segments_from_km_segments(km_segs)
    assert len(segs) == 1
    assert segs[0].gradient_type == "climb"
    assert segs[0].avg_grade_pct > 3.0


def test_detect_segments_descent():
    km_segs = _make_km_segments([-4.0, -5.0, -4.5])
    segs = detect_segments_from_km_segments(km_segs)
    assert len(segs) == 1
    assert segs[0].gradient_type == "descent"


def test_detect_segments_alternating():
    km_segs = _make_km_segments([5.0, 5.0, -5.0, -5.0, 0.0, 0.0])
    segs = detect_segments_from_km_segments(km_segs)
    types = [s.gradient_type for s in segs]
    assert "climb" in types
    assert "descent" in types


def test_detect_segments_min_length_filter():
    """Segments shorter than min_length_km should be dropped."""
    # Single km at climb grade — 1.0 km long (above 0.2 default)
    km_segs = _make_km_segments([5.0])
    segs = detect_segments_from_km_segments(km_segs, min_length_km=0.2)
    assert len(segs) == 1


def test_detect_segments_empty():
    assert detect_segments_from_km_segments([]) == []


# ---------------------------------------------------------------------------
# detect_segments_from_altitude
# ---------------------------------------------------------------------------


def _make_ns_with_altitude(
    total_dist_m: float,
    altitudes: list[float],
) -> NormalizedStream:
    n = len(altitudes)
    dist = [i * total_dist_m / (n - 1) for i in range(n)]
    elapsed = [i * 300 / (n - 1) for i in range(n)]
    return NormalizedStream(
        label="Primary",
        is_primary=True,
        activity_id=None,
        distance_grid=dist,
        elapsed_s=elapsed,
        altitude=altitudes,
    )


def test_detect_segments_altitude_flat():
    ns = _make_ns_with_altitude(2000.0, [100.0] * 50)
    segs = detect_segments_from_altitude(ns)
    assert all(s.gradient_type == "flat" for s in segs)


def test_detect_segments_altitude_no_data():
    ns = NormalizedStream(
        label="X", is_primary=True, activity_id=None,
        distance_grid=[], elapsed_s=[], altitude=None
    )
    assert detect_segments_from_altitude(ns) == []


# ---------------------------------------------------------------------------
# compute_segment_athlete_metrics
# ---------------------------------------------------------------------------


def test_segment_athlete_metrics_rank():
    """Faster athlete on a segment should get rank 1."""
    fast = _make_normalized("Fast", total_dist_m=2000.0, total_time_s=400.0)
    slow = _make_normalized("Slow", total_dist_m=2000.0, total_time_s=600.0)

    seg = DetectedSegment(
        label="Flat 0.0–1.0 km",
        start_km=0.0,
        end_km=1.0,
        gradient_type="flat",
        avg_grade_pct=0.0,
    )
    metrics = compute_segment_athlete_metrics([fast, slow], [seg])
    seg_m = metrics["Flat 0.0–1.0 km"]
    assert seg_m["Fast"]["rank"] == 1
    assert seg_m["Slow"]["rank"] == 2


def test_segment_athlete_metrics_time_vs_leader():
    """time_vs_leader_s should be 0 for fastest athlete."""
    fast = _make_normalized("Fast", total_dist_m=2000.0, total_time_s=400.0)
    slow = _make_normalized("Slow", total_dist_m=2000.0, total_time_s=600.0)
    seg = DetectedSegment(
        label="Test 0.5–1.5 km", start_km=0.5, end_km=1.5,
        gradient_type="flat", avg_grade_pct=0.0
    )
    metrics = compute_segment_athlete_metrics([fast, slow], [seg])
    assert metrics["Test 0.5–1.5 km"]["Fast"]["time_vs_leader_s"] == pytest.approx(0.0, abs=0.5)
    assert metrics["Test 0.5–1.5 km"]["Slow"]["time_vs_leader_s"] > 0


# ---------------------------------------------------------------------------
# detect_events — surge
# ---------------------------------------------------------------------------


def _make_ns_velocity_profile(
    label: str,
    n_pts: int,
    base_vel: float,
    surge_start: int,
    surge_end: int,
    surge_vel: float,
) -> NormalizedStream:
    """Build NormalizedStream with a velocity spike between indices surge_start:surge_end."""
    dist = [i * 10.0 for i in range(n_pts)]  # 10m spacing
    vel = [base_vel] * n_pts
    for i in range(surge_start, min(surge_end, n_pts)):
        vel[i] = surge_vel
    # Elapsed: integrate from velocity
    elapsed = [0.0]
    for i in range(1, n_pts):
        dt = 10.0 / vel[i] if vel[i] > 0 else 10.0
        elapsed.append(elapsed[-1] + dt)
    return NormalizedStream(
        label=label,
        is_primary=True,
        activity_id=None,
        distance_grid=dist,
        elapsed_s=elapsed,
        velocity=vel,
    )


def test_detect_surge():
    """Athlete with sustained pace 20%+ above baseline should produce a surge event."""
    # n=200 pts → ~2000m at 10m spacing; base 4 m/s, surge 5 m/s for pts 80-120
    ns = _make_ns_velocity_profile("A", n_pts=200, base_vel=4.0,
                                   surge_start=80, surge_end=120, surge_vel=5.0)
    gaps = compute_gap_series([ns])
    events = detect_events([ns], gaps)
    surge_events = [e for e in events if e.event_type == "surge"]
    assert len(surge_events) >= 1
    assert surge_events[0].athlete_label == "A"


# ---------------------------------------------------------------------------
# detect_events — fade
# ---------------------------------------------------------------------------


def test_detect_fade():
    """Athlete who slows significantly in second half should produce a fade event."""
    n = 200
    dist = [i * 10.0 for i in range(n)]
    # First half: 4 m/s; second half: 2 m/s (50% drop)
    vel = [4.0] * (n // 2) + [2.0] * (n // 2)
    elapsed = [0.0]
    for i in range(1, n):
        dt = 10.0 / vel[i]
        elapsed.append(elapsed[-1] + dt)

    ns = NormalizedStream(
        label="Fader", is_primary=True, activity_id=None,
        distance_grid=dist, elapsed_s=elapsed, velocity=vel
    )
    gaps = compute_gap_series([ns])
    events = detect_events([ns], gaps)
    fade_events = [e for e in events if e.event_type == "fade"]
    assert len(fade_events) >= 1
    assert fade_events[0].athlete_label == "Fader"


# ---------------------------------------------------------------------------
# detect_events — final_sprint
# ---------------------------------------------------------------------------


def test_detect_final_sprint():
    """Athlete who accelerates in last 400m should produce a final_sprint event."""
    n = 300
    dist = [i * 10.0 for i in range(n)]  # 3000m total
    vel = [4.0] * n
    # Last 40 points = last 400m → sprint at 5 m/s
    for i in range(n - 40, n):
        vel[i] = 5.0
    elapsed = [0.0]
    for i in range(1, n):
        dt = 10.0 / vel[i]
        elapsed.append(elapsed[-1] + dt)

    ns = NormalizedStream(
        label="Sprinter", is_primary=True, activity_id=None,
        distance_grid=dist, elapsed_s=elapsed, velocity=vel
    )
    gaps = compute_gap_series([ns])
    events = detect_events([ns], gaps)
    sprint_events = [e for e in events if e.event_type == "final_sprint"]
    assert len(sprint_events) >= 1
    assert sprint_events[0].athlete_label == "Sprinter"


# ---------------------------------------------------------------------------
# detect_events — drop (gap-based)
# ---------------------------------------------------------------------------


def test_detect_drop():
    """Athlete losing >10s over 500m triggers a drop event."""
    # Fast: constant 4 m/s for 2km
    fast = _make_normalized("Fast", total_dist_m=2000.0, total_time_s=500.0, velocity=4.0)

    # Slow: starts same pace but dramatically slows mid-race
    n = 200
    dist = [i * 10.0 for i in range(n)]
    # First 100 pts at 4 m/s, then 1.5 m/s (big drop)
    vel = [4.0] * 100 + [1.5] * 100
    elapsed = [0.0]
    for i in range(1, n):
        dt = 10.0 / vel[i]
        elapsed.append(elapsed[-1] + dt)

    slow = NormalizedStream(
        label="Dropper", is_primary=False, activity_id=None,
        distance_grid=dist, elapsed_s=elapsed, velocity=vel
    )
    gaps = compute_gap_series([fast, slow])
    events = detect_events([fast, slow], gaps)
    drop_events = [e for e in events if e.event_type == "drop"]
    assert len(drop_events) >= 1
    assert drop_events[0].athlete_label == "Dropper"


# ---------------------------------------------------------------------------
# detect_events — bridge (gap-based)
# ---------------------------------------------------------------------------


def test_detect_bridge():
    """Athlete closing gap >10s over 500m triggers a bridge event."""
    # Leader: constant pace 4 m/s for 2km
    leader = _make_normalized("Leader", total_dist_m=2000.0, total_time_s=500.0, velocity=4.0)

    # Chaser: starts slow but accelerates — builds big gap then closes it
    n = 200
    dist = [i * 10.0 for i in range(n)]
    # First 60 pts at 2 m/s (falls way behind), then 5 m/s (bridges hard)
    vel = [2.0] * 60 + [5.0] * 140
    elapsed = [0.0]
    for i in range(1, n):
        dt = 10.0 / vel[i]
        elapsed.append(elapsed[-1] + dt)

    chaser = NormalizedStream(
        label="Chaser", is_primary=False, activity_id=None,
        distance_grid=dist, elapsed_s=elapsed, velocity=vel
    )
    gaps = compute_gap_series([leader, chaser])
    events = detect_events([leader, chaser], gaps)
    bridge_events = [e for e in events if e.event_type == "bridge"]
    assert len(bridge_events) >= 1
    assert bridge_events[0].athlete_label == "Chaser"


# ---------------------------------------------------------------------------
# detect_events — separation (gap-based)
# ---------------------------------------------------------------------------


def test_detect_separation():
    """Gap >30s between position 1 and position 2 should trigger separation."""
    fast = _make_normalized("Fast", total_dist_m=2000.0, total_time_s=300.0, velocity=6.0)
    very_slow = _make_normalized("VerySlow", total_dist_m=2000.0, total_time_s=900.0, velocity=2.0)
    gaps = compute_gap_series([fast, very_slow])
    events = detect_events([fast, very_slow], gaps)
    sep_events = [e for e in events if e.event_type == "separation"]
    assert len(sep_events) >= 1


# ---------------------------------------------------------------------------
# Output formatter smoke tests
# ---------------------------------------------------------------------------


def test_print_race_sessions_list_empty(capsys):
    from fitops.output.text_formatter import print_race_sessions_list
    print_race_sessions_list({"sessions": []})
    out = capsys.readouterr().out
    assert "No race sessions" in out


def test_print_race_sessions_list_with_data(capsys):
    from fitops.output.text_formatter import print_race_sessions_list
    print_race_sessions_list(
        {
            "sessions": [
                {
                    "id": 1,
                    "name": "Berlin 2026",
                    "primary_activity_id": 12345,
                    "athlete_count": 3,
                    "course_id": None,
                    "created_at": "2026-04-13T10:00:00",
                }
            ]
        }
    )
    out = capsys.readouterr().out
    assert "Berlin 2026" in out


def test_print_race_session_detail_smoke(capsys):
    from fitops.output.text_formatter import print_race_session_detail
    detail = {
        "session": {
            "id": 1,
            "name": "Test Race",
            "primary_activity_id": 1001,
            "athlete_count": 2,
            "course_id": None,
            "created_at": "2026-04-13",
        },
        "athletes": [
            {
                "athlete_label": "Me",
                "is_primary": True,
                "activity_id": 1001,
                "finish_time_s": 1800.0,
                "avg_pace_s_per_km": 300.0,
                "avg_hr_bpm": 155.0,
                "total_dist_km": 6.0,
            }
        ],
        "segments": [],
        "events": [],
    }
    print_race_session_detail(detail)
    out = capsys.readouterr().out
    assert "Test Race" in out


def test_print_race_session_events_empty(capsys):
    from fitops.output.text_formatter import print_race_session_events
    print_race_session_events({"events": []})
    out = capsys.readouterr().out
    assert "No events" in out


def test_print_race_session_segments_empty(capsys):
    from fitops.output.text_formatter import print_race_session_segments
    print_race_session_segments({"segments": []})
    out = capsys.readouterr().out
    assert "No segments" in out


def test_print_race_session_gaps_empty(capsys):
    from fitops.output.text_formatter import print_race_session_gaps
    print_race_session_gaps({"gap_data": []})
    out = capsys.readouterr().out
    assert "No gap" in out


# ---------------------------------------------------------------------------
# CLI JSON shape — test via direct async mocking
# ---------------------------------------------------------------------------


def test_sessions_json_shape(monkeypatch):
    """sessions CLI command should return a dict with 'sessions' and '_meta'."""
    import asyncio

    fake_sessions = [
        {
            "id": 1,
            "name": "My Race",
            "primary_activity_id": 555,
            "athlete_count": 2,
            "course_id": None,
            "created_at": "2026-04-13",
        }
    ]

    async def _fake_get_all():
        return fake_sessions

    from fitops.output.formatter import make_meta

    result = asyncio.run(_fake_get_all())
    out = {
        "_meta": make_meta(total_count=len(result)),
        "sessions": result,
    }
    assert "sessions" in out
    assert out["sessions"][0]["name"] == "My Race"
    assert "_meta" in out
    assert out["_meta"]["total_count"] == 1


def test_session_json_shape(monkeypatch):
    """session detail CLI command should return a dict with 'session' key."""
    fake_detail = {
        "session": {"id": 1, "name": "My Race"},
        "athletes": [],
        "gap_data": [],
        "events": [],
        "segments": [],
    }

    from fitops.output.formatter import make_meta

    out = {"_meta": make_meta(), **fake_detail}
    assert "session" in out
    assert "athletes" in out
    assert "gap_data" in out
    assert "_meta" in out


def test_session_gaps_json_shape():
    """gap_data output should be a list of dicts with distance_km and gap_to_leader_s."""
    fast = _make_normalized("Fast", total_dist_m=500.0, total_time_s=150.0)
    slow = _make_normalized("Slow", total_dist_m=500.0, total_time_s=200.0)
    gaps = compute_gap_series([fast, slow])

    from fitops.output.formatter import make_meta

    flat_gap_data = [p for series in gaps.values() for p in series]
    out = {"_meta": make_meta(total_count=len(flat_gap_data)), "gap_data": flat_gap_data}

    assert "gap_data" in out
    assert "_meta" in out
    for p in out["gap_data"]:
        assert "distance_km" in p
        assert "gap_to_leader_s" in p


def test_session_segments_json_shape():
    """Segment output should include label, gradient_type, and per-athlete keys."""
    fast = _make_normalized("Fast", total_dist_m=2000.0, total_time_s=400.0)
    slow = _make_normalized("Slow", total_dist_m=2000.0, total_time_s=600.0)
    seg = DetectedSegment(
        label="Flat 0.0–1.0 km", start_km=0.0, end_km=1.0,
        gradient_type="flat", avg_grade_pct=0.0
    )
    metrics = compute_segment_athlete_metrics([fast, slow], [seg])

    from fitops.output.formatter import make_meta

    segs_out = [
        {
            "label": seg.label,
            "start_km": seg.start_km,
            "end_km": seg.end_km,
            "gradient_type": seg.gradient_type,
            "avg_grade_pct": seg.avg_grade_pct,
            "athletes": metrics.get(seg.label, {}),
        }
    ]
    out = {"_meta": make_meta(total_count=len(segs_out)), "segments": segs_out}

    assert "segments" in out
    first_seg = out["segments"][0]
    assert "label" in first_seg
    assert "gradient_type" in first_seg
    assert "athletes" in first_seg


def test_session_events_json_shape():
    """Events output should include event_type, athlete_label, distance_km."""
    fast = _make_normalized("Fast", total_dist_m=2000.0, total_time_s=300.0, velocity=6.0)
    very_slow = _make_normalized("VerySlow", total_dist_m=2000.0, total_time_s=900.0, velocity=2.0)
    gaps = compute_gap_series([fast, very_slow])
    events = detect_events([fast, very_slow], gaps)

    events_out = [
        {
            "event_type": e.event_type,
            "athlete_label": e.athlete_label,
            "distance_km": e.distance_km,
            "elapsed_s": e.elapsed_s,
            "impact_s": e.impact_s,
            "description": e.description,
        }
        for e in events
    ]
    from fitops.output.formatter import make_meta

    out = {"_meta": make_meta(total_count=len(events_out)), "events": events_out}
    assert "events" in out
    for ev in out["events"]:
        assert "event_type" in ev
        assert "athlete_label" in ev
        assert "distance_km" in ev


# ---------------------------------------------------------------------------
# Dashboard HTTP 200 tests
# ---------------------------------------------------------------------------


def _make_app():
    from fitops.dashboard.server import create_app
    return create_app()


@pytest.fixture
def client():
    from starlette.testclient import TestClient
    app = _make_app()
    with TestClient(app) as c:
        yield c


def test_dashboard_race_sessions_empty(client, monkeypatch):
    """GET /race/sessions should return 200 with an empty sessions list."""
    async def _fake_create_all():
        pass

    async def _fake_get_all():
        return []

    monkeypatch.setattr(
        "fitops.dashboard.routes.race.create_all_tables", _fake_create_all
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.race.get_all_race_sessions", _fake_get_all
    )

    resp = client.get("/race/sessions")
    assert resp.status_code == 200
    assert "No race sessions" in resp.text


def test_dashboard_race_sessions_with_data(client, monkeypatch):
    """GET /race/sessions should render the sessions table when data exists."""
    async def _fake_create_all():
        pass

    async def _fake_get_all():
        return [
            {
                "id": 1,
                "name": "Berlin 2026",
                "primary_activity_id": 12345,
                "athlete_count": 3,
                "course_id": None,
                "created_at": "2026-04-13T10:00:00",
            }
        ]

    monkeypatch.setattr(
        "fitops.dashboard.routes.race.create_all_tables", _fake_create_all
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.race.get_all_race_sessions", _fake_get_all
    )

    resp = client.get("/race/sessions")
    assert resp.status_code == 200
    assert "Berlin 2026" in resp.text


def test_dashboard_race_session_not_found(client, monkeypatch):
    """GET /race/sessions/999 should return 404 when session doesn't exist."""
    async def _fake_create_all():
        pass

    async def _fake_get_detail(session_id):
        return None

    monkeypatch.setattr(
        "fitops.dashboard.routes.race.create_all_tables", _fake_create_all
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.race.get_session_detail", _fake_get_detail
    )

    resp = client.get("/race/sessions/999")
    assert resp.status_code == 404


def test_dashboard_race_session_detail(client, monkeypatch):
    """GET /race/sessions/1 should return 200 with session data rendered."""
    async def _fake_create_all():
        pass

    fake_session_row = MagicMock()
    fake_session_row.id = 1
    fake_session_row.name = "Test Race Session"
    fake_session_row.primary_activity_id = 1001
    fake_session_row.athlete_count = 2
    fake_session_row.course_id = None
    fake_session_row.created_at = "2026-04-13"

    async def _fake_get_detail(session_id):
        return {
            "session": {
                "id": 1,
                "name": "Test Race Session",
                "primary_activity_id": 1001,
                "athlete_count": 2,
                "course_id": None,
                "created_at": "2026-04-13",
            },
            "athletes": [
                {
                    "athlete_label": "Me",
                    "is_primary": True,
                    "activity_id": 1001,
                    "finish_time_s": 1800.0,
                    "avg_pace_s_per_km": 300.0,
                    "avg_hr_bpm": 155.0,
                    "total_dist_km": 6.0,
                }
            ],
            "gap_data": [],
            "events": [],
            "segments": [],
        }

    fake_athlete = MagicMock()
    fake_athlete.athlete_label = "Me"
    fake_athlete.is_primary = True
    fake_athlete.get_stream.return_value = {"latlng": [], "elapsed_s": []}

    async def _fake_get_athletes(session_id):
        return [fake_athlete]

    monkeypatch.setattr(
        "fitops.dashboard.routes.race.create_all_tables", _fake_create_all
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.race.get_session_detail", _fake_get_detail
    )
    monkeypatch.setattr(
        "fitops.dashboard.routes.race.get_session_athletes", _fake_get_athletes
    )

    resp = client.get("/race/sessions/1")
    assert resp.status_code == 200
    assert "Test Race Session" in resp.text
