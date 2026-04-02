from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Zone:
    zone: int
    name: str
    min_bpm: int
    max_bpm: int
    description: str


@dataclass
class ZoneResult:
    method: str
    lthr_bpm: int | None
    max_hr_bpm: int | None
    resting_hr_bpm: int | None
    zones: list[Zone]
    lt1_bpm: int | None
    lt2_bpm: int | None

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "lthr_bpm": self.lthr_bpm,
            "max_hr_bpm": self.max_hr_bpm,
            "resting_hr_bpm": self.resting_hr_bpm,
            "heart_rate_zones": [
                {
                    "zone": z.zone,
                    "name": z.name,
                    "min_bpm": z.min_bpm,
                    "max_bpm": z.max_bpm,
                    "description": z.description,
                }
                for z in self.zones
            ],
            "thresholds": {
                "lt1_bpm": self.lt1_bpm,
                "lt2_bpm": self.lt2_bpm,
                "lt1_label": f"Top of Zone 2 (92% LTHR = {self.lt1_bpm} bpm)"
                if self.lt1_bpm
                else None,
                "lt2_label": f"LTHR (100% LTHR = {self.lt2_bpm} bpm)"
                if self.lt2_bpm
                else None,
            },
        }


def compute_lthr_zones(
    lthr: int,
    resting_hr: int | None = None,
    max_hr: int | None = None,
) -> ZoneResult:
    # LT1 (Z2/Z3 boundary): use HRR-corrected formula at 72% HRR when resting HR is
    # known, because the fixed 92%-LTHR ratio over-shoots LT1 for athletes with large
    # cardiac reserves (HRR > ~100 bpm). Falls back to 92% LTHR when resting HR is absent.
    if resting_hr is not None and max_hr is not None:
        z2_max = int(resting_hr + 0.72 * (max_hr - resting_hr))
    else:
        z2_max = int(lthr * 0.92)
    z1_max = int(lthr * 0.85)
    z3_max = lthr
    z4_max = int(lthr * 1.06)
    zones = [
        Zone(1, "Recovery", 0, z1_max, "Below LT1 — active recovery and warm-up"),
        Zone(2, "Aerobic", z1_max, z2_max, "LT1 region — aerobic base building"),
        Zone(3, "Tempo", z2_max, z3_max, "Comfortably hard — aerobic threshold"),
        Zone(4, "Threshold", z3_max, z4_max, "LT2 — lactate threshold work"),
        Zone(5, "VO2max", z4_max, 999, "Above threshold — high intensity intervals"),
    ]
    return ZoneResult(
        method="lthr",
        lthr_bpm=lthr,
        max_hr_bpm=max_hr,
        resting_hr_bpm=resting_hr,
        zones=zones,
        lt1_bpm=z2_max,
        lt2_bpm=lthr,
    )


def compute_max_hr_zones(max_hr: int) -> ZoneResult:
    zones = [
        Zone(
            1,
            "Recovery",
            int(max_hr * 0.50),
            int(max_hr * 0.60),
            "50–60% max HR — recovery",
        ),
        Zone(
            2,
            "Aerobic",
            int(max_hr * 0.60),
            int(max_hr * 0.70),
            "60–70% max HR — aerobic base",
        ),
        Zone(
            3,
            "Tempo",
            int(max_hr * 0.70),
            int(max_hr * 0.80),
            "70–80% max HR — aerobic threshold",
        ),
        Zone(
            4,
            "Threshold",
            int(max_hr * 0.80),
            int(max_hr * 0.90),
            "80–90% max HR — lactate threshold",
        ),
        Zone(5, "VO2max", int(max_hr * 0.90), 999, "90–100% max HR — high intensity"),
    ]
    return ZoneResult(
        method="max-hr",
        lthr_bpm=None,
        max_hr_bpm=max_hr,
        resting_hr_bpm=None,
        zones=zones,
        lt1_bpm=int(max_hr * 0.70),
        lt2_bpm=int(max_hr * 0.85),
    )


def compute_hrr_zones(max_hr: int, resting_hr: int) -> ZoneResult:
    hrr = max_hr - resting_hr

    def t(pct: float) -> int:
        return int(resting_hr + pct * hrr)

    zones = [
        Zone(1, "Recovery", t(0.50), t(0.60), "50–60% HRR — recovery"),
        Zone(2, "Aerobic", t(0.60), t(0.70), "60–70% HRR — aerobic base"),
        Zone(3, "Tempo", t(0.70), t(0.80), "70–80% HRR — aerobic threshold"),
        Zone(4, "Threshold", t(0.80), t(0.90), "80–90% HRR — lactate threshold"),
        Zone(5, "VO2max", t(0.90), 999, "90–100% HRR — high intensity"),
    ]
    return ZoneResult(
        method="hrr",
        lthr_bpm=None,
        max_hr_bpm=max_hr,
        resting_hr_bpm=resting_hr,
        zones=zones,
        lt1_bpm=t(0.70),
        lt2_bpm=t(0.85),
    )


def compute_zones(
    method: str,
    lthr: int | None = None,
    max_hr: int | None = None,
    resting_hr: int | None = None,
) -> ZoneResult | None:
    if method == "lthr":
        return (
            compute_lthr_zones(lthr, resting_hr=resting_hr, max_hr=max_hr)
            if lthr
            else None
        )
    elif method == "max-hr":
        return compute_max_hr_zones(max_hr) if max_hr else None
    elif method == "hrr":
        return compute_hrr_zones(max_hr, resting_hr) if max_hr and resting_hr else None
    return None
