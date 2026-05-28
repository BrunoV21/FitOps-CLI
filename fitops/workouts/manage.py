from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fitops.workouts.json_parser import generate_markdown_body, parse_segments_from_json
from fitops.workouts.loader import workouts_dir


def slugify_workout_name(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug or "workout"


def build_structured_workout_markdown(
    workout_json: dict[str, Any],
    *,
    name: str,
    sport: str | None = None,
) -> dict[str, Any]:
    segments = parse_segments_from_json(workout_json)
    if not segments:
        raise ValueError("No segments found in workout JSON.")

    sport_value = sport or workout_json.get("sport") or "run"
    total_min = sum(s.duration_min for s in segments if s.duration_min)
    meta_line = json.dumps(workout_json)
    body = generate_markdown_body(workout_json, name)
    markdown = (
        f"---\n"
        f"name: {name}\n"
        f"sport: {sport_value}\n"
        f"target_duration_min: {round(total_min)}\n"
        f"tags: []\n"
        f"workout_meta: {meta_line}\n"
        f"---\n\n"
        f"{body}"
    )
    return {
        "markdown": markdown,
        "meta_line": meta_line,
        "sport": sport_value,
        "total_duration_min": round(total_min, 1),
        "segment_count": len(segments),
        "segments": segments,
    }


def workout_json_from_meta(raw_meta: str | None) -> dict[str, Any] | None:
    if not raw_meta:
        return None
    try:
        parsed = json.loads(raw_meta)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("workout_meta"), str):
        try:
            nested = json.loads(parsed["workout_meta"])
        except json.JSONDecodeError:
            nested = None
        if isinstance(nested, dict):
            return nested
    return parsed if isinstance(parsed, dict) else None


def safe_workout_file_path(file_name: str | None) -> Path | None:
    if not file_name:
        return None
    base = workouts_dir().resolve()
    candidate = (base / Path(file_name).name).resolve()
    if base not in candidate.parents:
        return None
    return candidate
