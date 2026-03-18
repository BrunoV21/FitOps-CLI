from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fitops.analytics.athlete_settings import get_athlete_settings

# (zone_num, name, faster_pct, slower_pct)
# faster_pct = min_s_per_km boundary (None = no lower bound = Z5 can go infinitely fast)
# slower_pct = max_s_per_km boundary (None = no upper bound = Z1 can go infinitely slow)
PACE_ZONE_DEFS = [
    (1, "Easy",       1.16, None),
    (2, "Aerobic",    1.08, 1.16),
    (3, "Tempo",      1.02, 1.08),
    (4, "Threshold",  0.96, 1.02),
    (5, "VO2max",     None, 0.96),
]


def _fmt_pace(s: Optional[int]) -> Optional[str]:
    if s is None:
        return None
    s = int(s)
    return f"{s // 60}:{s % 60:02d}"


def _parse_mm_ss(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid pace format: {value!r} (expected MM:SS)")
    return int(parts[0]) * 60 + int(parts[1])


@dataclass
class PaceZoneResult:
    threshold_pace_s: int
    threshold_pace_fmt: str
    source: str
    zones: list[dict]


def compute_pace_zones(threshold_pace_s: int, source: str = "manual") -> PaceZoneResult:
    zones = []
    for zone_num, name, faster_pct, slower_pct in PACE_ZONE_DEFS:
        min_s = int(round(threshold_pace_s * faster_pct)) if faster_pct is not None else None
        max_s = int(round(threshold_pace_s * slower_pct)) if slower_pct is not None else None
        zones.append({
            "zone": zone_num,
            "name": name,
            "min_s_per_km": min_s,
            "max_s_per_km": max_s,
            "min_pace_fmt": _fmt_pace(min_s),
            "max_pace_fmt": _fmt_pace(max_s),
        })
    return PaceZoneResult(
        threshold_pace_s=threshold_pace_s,
        threshold_pace_fmt=_fmt_pace(threshold_pace_s),
        source=source,
        zones=zones,
    )


def get_pace_zones() -> Optional[PaceZoneResult]:
    settings = get_athlete_settings()
    data = settings.to_dict()
    threshold_s = data.get("threshold_pace_per_km_s")
    if threshold_s is None:
        return None
    return compute_pace_zones(threshold_s, source=data.get("pace_zones_source", "manual"))


def set_threshold_pace(pace_str: str) -> PaceZoneResult:
    threshold_s = _parse_mm_ss(pace_str)
    settings = get_athlete_settings()
    settings.set(threshold_pace_per_km_s=threshold_s, pace_zones_source="manual")
    return compute_pace_zones(threshold_s)
