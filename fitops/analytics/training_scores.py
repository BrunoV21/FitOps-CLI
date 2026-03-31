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
    if sport in RUN_TYPES and activity.average_speed_ms and activity.average_speed_ms > 0:
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
    Aerobic training score 0.0–5.0.

    Measures how much aerobic base stimulus the activity provided.
    Zone 2 training is the sweet spot; longer duration at moderate intensity = higher score.

    Calibration: 1h40min at Z2 intensity = 5.0, 1h Z2 = 3.0, 30min Z2 = 1.5.
    """
    duration_h = (activity.moving_time_s or 0) / 3600.0
    if duration_h <= 0:
        return 0.0

    intensity = _intensity_factor(activity, settings)

    # Aerobic efficiency per zone — Z2 is optimal; high intensity shifts energy to anaerobic
    if intensity < 0.50:
        eff = 0.2       # very easy / rest
    elif intensity < 0.75:
        eff = 0.5       # recovery / Z1
    elif intensity < 0.88:
        eff = 1.0       # Z2 aerobic sweet spot
    elif intensity < 1.00:
        eff = 0.85      # Z3 tempo — still aerobic-dominant
    elif intensity < 1.06:
        eff = 0.55      # Z4 threshold — split energy systems
    else:
        eff = 0.30      # Z5 VO2max+ — anaerobic dominant

    # Normalizer: 5/3 hours at Z2 = 5.0
    return min(5.0, round(duration_h * eff * 3.0, 1))


def compute_anaerobic_score(activity: Activity, settings: AthleteSettings) -> float:
    """
    Anaerobic training score 0.0–5.0.

    Measures high-intensity / threshold stress above LT2.
    Ramps sharply above threshold; minimal for easy aerobic work.

    Calibration: 45min race effort at Z4/Z5 ≈ 4.5, 40min threshold session = 4.0.
    """
    duration_h = (activity.moving_time_s or 0) / 3600.0
    if duration_h <= 0:
        return 0.0

    intensity = _intensity_factor(activity, settings)

    if intensity < 0.88:
        # Below tempo: negligible anaerobic contribution
        raw = duration_h * 0.05
    elif intensity < 1.00:
        # Tempo zone: linear ramp from minimal to moderate anaerobic
        raw = duration_h * 0.3 * (intensity - 0.88) / 0.12
    elif intensity < 1.06:
        # Threshold zone: meaningful anaerobic stress
        raw = duration_h * 1.5
    else:
        # VO2max+: sharp ramp — supramaximal efforts are highly anaerobic
        raw = duration_h * (1.5 + (intensity - 1.0) * 8.0)

    # Normalizer: 40min at threshold (IF=1.02) ≈ 4.0
    return min(5.0, round(raw * 4.0, 1))
