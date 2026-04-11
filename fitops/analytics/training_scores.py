from __future__ import annotations

from fitops.analytics.athlete_settings import AthleteSettings
from fitops.db.models.activity import Activity

RUN_TYPES = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
RIDE_TYPES = {"Ride", "VirtualRide", "EBikeRide", "MountainBikeRide", "GravelRide"}


def _intensity_factor(activity: Activity, settings: AthleteSettings) -> float:
    """Compute intensity factor relative to threshold (1.0 = threshold effort)."""
    sport = activity.sport_type or ""

    # 1. Cycling + power + FTP
    if sport in RIDE_TYPES and activity.average_watts and settings.ftp:
        return min(activity.average_watts / settings.ftp, 2.0)

    # 2. Running + pace + threshold pace
    if (
        sport in RUN_TYPES
        and activity.average_speed_ms
        and activity.average_speed_ms > 0
    ):
        threshold_s = settings.threshold_pace_per_km_s
        if threshold_s and threshold_s > 0:
            avg_pace_s = 1000.0 / activity.average_speed_ms
            return min(threshold_s / avg_pace_s, 2.0)

    # 3. HR fallback: LTHR or 88% max_hr
    if activity.average_heartrate:
        avg_hr = activity.average_heartrate
        if settings.lthr:
            return min(avg_hr / settings.lthr, 2.0)
        if settings.max_hr:
            return min(avg_hr / (settings.max_hr * 0.88), 2.0)
        if settings.age:
            estimated_max = 220 - settings.age
            return min(avg_hr / (estimated_max * 0.88), 2.0)

    return 0.75  # assume light aerobic if no data


def compute_aerobic_score(activity: Activity, settings: AthleteSettings) -> float:
    """
    Aerobic training score (unbounded, typically 0–6+).

    Power-law model calibrated against Huawei watch reference values:
      score = 4.0 × IF^0.58 × duration_h^0.24

    Calibration data points:
      2.22h ride IF=0.812 → 4.3, 0.78h threshold run IF=1.002 → 3.8,
      0.96h easy run IF=0.684 → 3.2
    """
    duration_h = (activity.moving_time_s or 0) / 3600.0
    if duration_h <= 0:
        return 0.0

    intensity = _intensity_factor(activity, settings)
    if intensity <= 0:
        return 0.0

    return round(4.0 * (intensity**0.58) * (duration_h**0.24), 1)


def compute_anaerobic_score(activity: Activity, settings: AthleteSettings) -> float:
    """
    Anaerobic training score (unbounded, typically 0–6+).

    Sport-specific power-law models calibrated against Huawei watch reference values.

    Running: score = 4.77 × IF^1.59 × duration_h^0.24
      Calibration: 0.98h run IF=0.811 → 3.4, 0.78h threshold run IF=1.002 → 4.5

    Cycling: score = 4.7 × IF^5.8 × duration_h^0.24
      Calibration: 2.22h ride IF=0.812 → 1.7
      The steep IF exponent captures how cycling anaerobic stress ramps sharply
      above threshold.
    """
    duration_h = (activity.moving_time_s or 0) / 3600.0
    if duration_h <= 0:
        return 0.0

    intensity = _intensity_factor(activity, settings)
    if intensity <= 0:
        return 0.0

    sport = activity.sport_type or ""
    if sport in RUN_TYPES:
        return round(4.77 * (intensity**1.59) * (duration_h**0.24), 1)
    return round(4.7 * (intensity**5.8) * (duration_h**0.24), 1)


def aerobic_label(score: float) -> str:
    """Human-readable label for an aerobic training score."""
    if score >= 4.5:
        return "Exceptional aerobic session"
    if score >= 3.5:
        return "Strong aerobic stimulus"
    if score >= 2.5:
        return "Solid aerobic base work"
    if score >= 1.5:
        return "Moderate aerobic benefit"
    if score >= 0.5:
        return "Light aerobic stimulus"
    return "Minimal aerobic benefit"


def anaerobic_label(score: float) -> str:
    """Human-readable label for an anaerobic training score."""
    if score >= 4.5:
        return "Race-intensity effort"
    if score >= 3.5:
        return "Hard anaerobic session"
    if score >= 2.5:
        return "Significant threshold stress"
    if score >= 1.5:
        return "Moderate anaerobic load"
    if score >= 0.5:
        return "Light anaerobic stimulus"
    return "Minimal anaerobic stress"
