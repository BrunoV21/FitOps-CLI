"""Tests for Phase 3.1 — Markdown workout definitions."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from fitops.workouts.loader import (
    WorkoutFile,
    _parse_frontmatter,
    _stem_to_name,
    load_workout_file,
)


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

FULL_FM = """\
---
name: Threshold Tuesday
sport: Run
target_duration_min: 60
tags: [threshold, quality, run]
active: true
threshold_pace: 5.5
---

## Warmup
10 min easy (Z1-Z2)

## Main Set
4 × 8 min @ Z4
"""

NO_FM = """\
## Just a body

No frontmatter here.
"""

EMPTY_FM = """\
---
---
## Body only
"""


def test_parse_frontmatter_full():
    meta, body = _parse_frontmatter(FULL_FM)
    assert meta["name"] == "Threshold Tuesday"
    assert meta["sport"] == "Run"
    assert meta["target_duration_min"] == 60
    assert meta["tags"] == ["threshold", "quality", "run"]
    assert meta["active"] is True
    assert meta["threshold_pace"] == 5.5
    assert "## Warmup" in body
    assert "## Main Set" in body


def test_parse_frontmatter_no_frontmatter():
    meta, body = _parse_frontmatter(NO_FM)
    assert meta == {}
    assert "Just a body" in body


def test_parse_frontmatter_empty_block():
    meta, body = _parse_frontmatter(EMPTY_FM)
    assert meta == {}
    assert "## Body only" in body


def test_parse_frontmatter_integer_coercion():
    text = "---\nduration: 45\n---\nbody"
    meta, _ = _parse_frontmatter(text)
    assert meta["duration"] == 45
    assert isinstance(meta["duration"], int)


def test_parse_frontmatter_float_coercion():
    text = "---\npace: 5.75\n---\nbody"
    meta, _ = _parse_frontmatter(text)
    assert meta["pace"] == 5.75
    assert isinstance(meta["pace"], float)


def test_parse_frontmatter_boolean_true():
    for val in ("true", "True", "TRUE", "yes", "Yes"):
        text = f"---\nflag: {val}\n---\nbody"
        meta, _ = _parse_frontmatter(text)
        assert meta["flag"] is True, f"Expected True for '{val}'"


def test_parse_frontmatter_boolean_false():
    for val in ("false", "False", "no", "No"):
        text = f"---\nflag: {val}\n---\nbody"
        meta, _ = _parse_frontmatter(text)
        assert meta["flag"] is False, f"Expected False for '{val}'"


def test_parse_frontmatter_list_single_item():
    text = "---\ntags: [only]\n---\nbody"
    meta, _ = _parse_frontmatter(text)
    assert meta["tags"] == ["only"]


def test_parse_frontmatter_list_empty():
    text = "---\ntags: []\n---\nbody"
    meta, _ = _parse_frontmatter(text)
    assert meta["tags"] == []


def test_parse_frontmatter_body_stripped():
    """Body should not include the closing --- line."""
    meta, body = _parse_frontmatter(FULL_FM)
    assert not body.startswith("---")
    assert "---" not in body.split("\n")[0]


# ---------------------------------------------------------------------------
# Stem-to-name helper
# ---------------------------------------------------------------------------

def test_stem_to_name_hyphens():
    assert _stem_to_name("threshold-tuesday") == "Threshold Tuesday"


def test_stem_to_name_underscores():
    assert _stem_to_name("long_run_sunday") == "Long Run Sunday"


def test_stem_to_name_mixed():
    assert _stem_to_name("z4-intervals_hard") == "Z4 Intervals Hard"


# ---------------------------------------------------------------------------
# load_workout_file
# ---------------------------------------------------------------------------

def _write_tmp_workout(content: str) -> Path:
    """Write content to a temporary .md file and return the path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return Path(f.name)


def test_load_workout_file_with_frontmatter():
    p = _write_tmp_workout(FULL_FM)
    try:
        w = load_workout_file(p)
        assert w.name == "Threshold Tuesday"
        assert w.sport == "Run"
        assert w.target_duration_min == 60
        assert "threshold" in w.tags
        assert "## Warmup" in w.body
        assert w.raw == FULL_FM
    finally:
        os.unlink(p)


def test_load_workout_file_no_frontmatter():
    p = _write_tmp_workout(NO_FM)
    try:
        w = load_workout_file(p)
        # Name should be derived from filename stem
        assert w.name == _stem_to_name(p.stem)
        assert w.sport is None
        assert w.target_duration_min is None
        assert w.tags == []
        assert "Just a body" in w.body
    finally:
        os.unlink(p)


def test_load_workout_file_fields():
    p = _write_tmp_workout(FULL_FM)
    try:
        w = load_workout_file(p)
        assert w.file_name == p.name
        assert w.file_path == p
        assert isinstance(w.meta, dict)
    finally:
        os.unlink(p)


# ---------------------------------------------------------------------------
# WorkoutFile dataclass
# ---------------------------------------------------------------------------

def test_workout_file_is_dataclass():
    w = WorkoutFile(
        file_name="test.md",
        file_path=Path("/tmp/test.md"),
        name="Test Workout",
        sport="Ride",
        target_duration_min=45,
        tags=["endurance"],
        meta={"sport": "Ride"},
        body="## Main\nSteady Z2 ride.",
        raw="---\nsport: Ride\n---\n## Main\nSteady Z2 ride.",
    )
    assert w.name == "Test Workout"
    assert w.sport == "Ride"
    assert w.tags == ["endurance"]


# ---------------------------------------------------------------------------
# Workout DB model helpers
# ---------------------------------------------------------------------------

def test_workout_model_get_meta_empty():
    from fitops.db.models.workout import Workout
    w = Workout(name="x", sport_type="Run")
    assert w.get_workout_meta() == {}


def test_workout_model_get_meta_valid_json():
    from fitops.db.models.workout import Workout
    w = Workout(name="x", sport_type="Run")
    w.workout_meta = json.dumps({"sport": "Run", "tags": ["z4"]})
    assert w.get_workout_meta()["sport"] == "Run"
    assert w.get_workout_meta()["tags"] == ["z4"]


def test_workout_model_get_meta_invalid_json():
    from fitops.db.models.workout import Workout
    w = Workout(name="x", sport_type="Run")
    w.workout_meta = "not-json{{"
    assert w.get_workout_meta() == {}


def test_workout_model_get_physiology_snapshot():
    from fitops.db.models.workout import Workout
    snap = {"ctl": 72.4, "atl": 68.1, "tsb": 4.3, "vo2max": 52.8}
    w = Workout(name="x", sport_type="Run")
    w.physiology_snapshot = json.dumps(snap)
    result = w.get_physiology_snapshot()
    assert result["ctl"] == 72.4
    assert result["tsb"] == 4.3


def test_workout_model_to_summary_dict():
    from fitops.db.models.workout import Workout
    w = Workout(name="Threshold Tuesday", sport_type="Run", status="completed")
    d = w.to_summary_dict()
    assert d["name"] == "Threshold Tuesday"
    assert d["sport_type"] == "Run"
    assert d["status"] == "completed"
    assert "activity_id" in d
    assert "linked_at" in d
