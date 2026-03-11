from __future__ import annotations

from typing import Optional


def compute_hr_drift(hr_stream: list[float], pace_stream: list[float]) -> Optional[dict]:
    """
    Cardiac decoupling: compare HR:pace efficiency ratio in first vs second half.
    Higher drift = aerobic system struggling to maintain pace at same HR.
    Decoupling % = (second_half_ratio - first_half_ratio) / first_half_ratio * 100
    <5% = well coupled (aerobic), 5-10% = moderate drift, >10% = significant decoupling
    """
    valid = [(h, p) for h, p in zip(hr_stream, pace_stream) if h and h > 0 and p and p > 0]
    if len(valid) < 20:
        return None

    mid = len(valid) // 2
    first = valid[:mid]
    second = valid[mid:]

    def _efficiency(pairs):
        # pace in m/s, HR in bpm — efficiency = speed / HR (higher = better)
        ratios = [p / h for h, p in pairs]
        return sum(ratios) / len(ratios)

    e1 = _efficiency(first)
    e2 = _efficiency(second)

    if e1 <= 0:
        return None

    drift_pct = round((e2 - e1) / e1 * 100, 1)

    if abs(drift_pct) < 5:
        label = "Well coupled — good aerobic efficiency"
    elif drift_pct < -5:
        label = "Positive drift — fading (HR rising relative to pace)"
    else:
        label = "Negative drift — warming up or downhill finish"

    return {
        "first_half_efficiency": round(e1, 6),
        "second_half_efficiency": round(e2, 6),
        "decoupling_pct": drift_pct,
        "label": label,
    }


def compute_pace_hr_ratio(avg_pace_s_per_km: Optional[float], avg_hr: Optional[float]) -> Optional[float]:
    """Efficiency ratio: pace (s/km) / HR. Lower = more efficient (faster at lower HR)."""
    if not avg_pace_s_per_km or not avg_hr or avg_hr <= 0:
        return None
    return round(avg_pace_s_per_km / avg_hr, 3)
