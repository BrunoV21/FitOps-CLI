from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fitops.config.settings import get_settings


def workouts_dir() -> Path:
    """Return ~/.fitops/workouts/, creating it if needed."""
    d = get_settings().fitops_dir / "workouts"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Frontmatter parser (no PyYAML dependency — handles str/int/float/bool/list)
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML-like frontmatter block from markdown text.

    Returns (meta_dict, body_text). If no frontmatter is found, returns
    ({}, original_text).

    Supported value types:
      - Strings:  name: Threshold Tuesday
      - Integers: target_duration_min: 60
      - Floats:   threshold_pace: 5.5
      - Booleans: active: true
      - Lists:    tags: [threshold, quality, run]
    """
    if not text.startswith("---"):
        return {}, text

    rest = text[3:]
    # closing --- must be on its own line
    match = re.search(r"\n---[ \t]*(\n|$)", rest)
    if not match:
        return {}, text

    fm_text = rest[: match.start()].strip()
    body = rest[match.end() :].strip()

    meta: dict[str, Any] = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, raw_val = line.partition(":")
        key = key.strip()
        val = raw_val.strip()

        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            items = [x.strip().strip("\"'") for x in inner.split(",") if x.strip()]
            meta[key] = items
        elif re.match(r"^-?\d+$", val):
            meta[key] = int(val)
        elif re.match(r"^-?\d+\.\d+$", val):
            meta[key] = float(val)
        elif val.lower() in ("true", "yes"):
            meta[key] = True
        elif val.lower() in ("false", "no"):
            meta[key] = False
        else:
            meta[key] = val

    return meta, body


def _stem_to_name(stem: str) -> str:
    return stem.replace("-", " ").replace("_", " ").title()


# ---------------------------------------------------------------------------
# WorkoutFile dataclass
# ---------------------------------------------------------------------------

@dataclass
class WorkoutFile:
    """A workout definition loaded from a .md file in ~/.fitops/workouts/."""

    file_name: str              # e.g. "threshold-tuesday.md"
    file_path: Path
    name: str                   # from frontmatter["name"] or derived from filename
    sport: Optional[str]        # e.g. "Run", "Ride"
    target_duration_min: Optional[int]
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)   # all frontmatter fields
    body: str = ""              # markdown body (content after frontmatter)
    raw: str = ""               # complete file content


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_workout_file(path: Path) -> WorkoutFile:
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    return WorkoutFile(
        file_name=path.name,
        file_path=path,
        name=meta.get("name") or _stem_to_name(path.stem),
        sport=meta.get("sport"),
        target_duration_min=meta.get("target_duration_min"),
        tags=meta.get("tags", []),
        meta=meta,
        body=body,
        raw=raw,
    )


def list_workout_files() -> list[WorkoutFile]:
    """Return all .md workout files sorted by filename."""
    return [load_workout_file(f) for f in sorted(workouts_dir().glob("*.md"))]


def get_workout_file(name_or_filename: str) -> Optional[WorkoutFile]:
    """Find a workout by filename (with or without .md) or display name.

    Matching order:
      1. Exact filename (adds .md if extension missing)
      2. Case-insensitive stem match after normalising spaces → hyphens
    """
    d = workouts_dir()

    # Exact filename
    candidate = Path(name_or_filename)
    if not candidate.suffix:
        candidate = candidate.with_suffix(".md")
    full = d / candidate.name
    if full.exists():
        return load_workout_file(full)

    # Normalised stem match
    target = name_or_filename.lower().replace(" ", "-").replace("_", "-")
    for f in sorted(d.glob("*.md")):
        if f.stem.lower() == target or f.name.lower() == name_or_filename.lower():
            return load_workout_file(f)

    return None
