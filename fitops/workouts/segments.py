from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class WorkoutSegmentDef:
    """A segment definition parsed from a workout markdown body or JSON structure."""

    index: int
    name: str
    step_type: str  # warmup | interval | recovery | cooldown | main
    target_zone: int | None  # 1–5, derived from "Z4" / "Zone 4" in text
    duration_min: float | None

    # Extended target fields (set by JSON parser; None for markdown-based segments)
    target_hr_min_bpm: float | None = None
    target_hr_max_bpm: float | None = None
    target_pace_min_s_per_km: float | None = None
    target_pace_max_s_per_km: float | None = None
    target_focus_type: str = "hr_zone"  # hr_zone | hr_range | pace_range | none


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------


def _infer_step_type(heading: str) -> str:
    h = heading.lower()
    if any(w in h for w in ("warm",)):
        return "warmup"
    if any(w in h for w in ("cool",)):
        return "cooldown"
    if any(w in h for w in ("recovery", "rest", "jog", "walk")):
        return "recovery"
    if any(
        w in h
        for w in ("interval", "rep", "set", "effort", "hard", "threshold", "main")
    ):
        return "interval"
    return "main"


def _extract_target_zone(text: str) -> int | None:
    """Extract the highest target zone number mentioned in a text block.

    Matches: Z4, Zone 4, z4, zone4, Z4-Z5, Z3–Z4 (takes upper bound).
    """
    # Range like Z3-Z4 / Z3–Z4 / Z3—Z4 — take the upper value
    m = re.search(r"[Zz](?:one)?\s*([1-5])\s*[-–—]\s*[Zz]?(?:one)?\s*([1-5])", text)
    if m:
        return int(m.group(2))
    # Single zone: Z4, Zone 4, z4
    m = re.search(r"[Zz](?:one)?\s*([1-5])", text)
    if m:
        return int(m.group(1))
    return None


def _extract_duration_min(text: str) -> float | None:
    """Extract total effective duration in minutes from a text block.

    Handles:
      "10 min"          → 10.0
      "4 × 8 min"       → 32.0
      "4x8 min"         → 32.0
      "90 minutes"      → 90.0
    """
    # Multiplied: N × D min
    m = re.search(r"(\d+)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*min", text, re.IGNORECASE)
    if m:
        return int(m.group(1)) * float(m.group(2))
    # Simple: D min
    m = re.search(r"(\d+(?:\.\d+)?)\s*min(?:utes?)?", text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_segments_from_body(body: str) -> list[WorkoutSegmentDef]:
    """Parse workout segments from markdown body using ## headings.

    Each ## heading becomes a segment. Duration and target zone are extracted
    from the text block that follows the heading.

    Returns an empty list if no ## headings are found.
    """
    # Split on ## headings; result alternates [preamble, heading, content, ...]
    parts = re.split(r"^#{2}\s+(.+)$", body, flags=re.MULTILINE)

    segments: list[WorkoutSegmentDef] = []
    idx = 0
    i = 1  # skip preamble

    while i < len(parts) - 1:
        heading = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        full_text = f"{heading} {content}"

        segments.append(
            WorkoutSegmentDef(
                index=idx,
                name=heading,
                step_type=_infer_step_type(heading),
                target_zone=_extract_target_zone(full_text),
                duration_min=_extract_duration_min(full_text),
            )
        )
        idx += 1
        i += 2

    return segments
