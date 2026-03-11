from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from fitops.db.models.activity import Activity
from fitops.db.session import get_async_session

CTL_DAYS = 42
ATL_DAYS = 7
ALPHA_CTL = 2.0 / (CTL_DAYS + 1)
ALPHA_ATL = 2.0 / (ATL_DAYS + 1)

RUN_TYPES = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}
RIDE_TYPES = {"Ride", "VirtualRide", "EBikeRide", "MountainBikeRide", "GravelRide"}
HR_ZONE_TSS = {"z1": 20, "z2": 40, "z3": 60, "z4": 80, "z5": 100}


@dataclass
class DailyLoad:
    date: date
    daily_tss: float
    ctl: float
    atl: float
    tsb: float


@dataclass
class TrainingLoadResult:
    history: list[DailyLoad] = field(default_factory=list)
    sport_filter: Optional[str] = None

    @property
    def current(self) -> Optional[DailyLoad]:
        return self.history[-1] if self.history else None

    @property
    def ramp_rate_pct(self) -> Optional[float]:
        if len(self.history) < 8:
            return None
        ctl_now = self.history[-1].ctl
        ctl_7ago = self.history[-8].ctl
        if ctl_7ago == 0:
            return None
        return ((ctl_now - ctl_7ago) / ctl_7ago) * 100

    def form_label(self, tsb: float) -> str:
        if tsb >= 15:
            return "Very fresh — possibly detrained"
        elif tsb >= 0:
            return "Fresh — optimal race readiness window"
        elif tsb >= -10:
            return "Productive — slight fatigue, good adaptation zone"
        elif tsb >= -20:
            return "Overreaching — high adaptation, monitor recovery"
        else:
            return "Overtraining risk — reduce load"

    def ramp_label(self, ramp: float) -> str:
        if ramp < 5:
            return "Conservative — below 5% weekly CTL increase"
        elif ramp < 10:
            return "Safe — under 10% weekly CTL increase"
        elif ramp < 15:
            return "Aggressive — above 10%, monitor fatigue"
        else:
            return "High risk — reduce load to prevent injury"


def _estimate_tss(activity: Activity) -> float:
    from fitops.analytics.athlete_settings import get_athlete_settings

    settings = get_athlete_settings()
    duration_h = (activity.moving_time_s or 0) / 3600.0
    if duration_h <= 0:
        return 0.0

    sport = activity.sport_type or ""

    # --- Cycling with power ---
    if sport in RIDE_TYPES and activity.average_watts:
        ftp = settings.ftp if settings.ftp else (activity.average_watts / 0.75)
        intensity_factor = min(activity.average_watts / ftp, 1.5)
        return round(duration_h * (intensity_factor ** 2) * 100, 2)

    # --- Running with pace + threshold pace from settings ---
    if sport in RUN_TYPES and activity.average_speed_ms and activity.average_speed_ms > 0:
        threshold_pace_s = settings.threshold_pace_per_km_s  # seconds per km
        if threshold_pace_s and threshold_pace_s > 0:
            avg_pace_s = 1000 / activity.average_speed_ms  # seconds per km
            intensity_factor = min(threshold_pace_s / avg_pace_s, 2.0)
            return round(duration_h * (intensity_factor ** 2) * 100, 2)
        else:
            intensity_factor = min(1.1, 2.0)
            return round(duration_h * (intensity_factor ** 2) * 100, 2)

    # --- HR fallback ---
    if activity.average_heartrate:
        lthr = settings.lthr
        max_hr = settings.max_hr
        avg_hr = activity.average_heartrate

        if lthr:
            hr_ratio = avg_hr / lthr
        elif max_hr:
            hr_ratio = avg_hr / (max_hr * 0.88)
        else:
            hr_ratio = avg_hr / 185.0

        intensity_factor = min(hr_ratio, 2.0)
        return round(duration_h * (intensity_factor ** 2) * 100, 2)

    return round(duration_h * 50, 2)


async def compute_training_load(
    athlete_id: int,
    days: int = 90,
    sport_filter: Optional[str] = None,
) -> TrainingLoadResult:
    end_date = date.today()
    warmup_days = CTL_DAYS * 2
    total_days = days + warmup_days
    start_date = end_date - timedelta(days=total_days)

    async with get_async_session() as session:
        stmt = select(Activity).where(
            Activity.athlete_id == athlete_id,
            Activity.start_date >= datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc),
        )
        if sport_filter:
            stmt = stmt.where(Activity.sport_type == sport_filter)
        result = await session.execute(stmt)
        activities = result.scalars().all()

    daily_tss: dict[date, float] = {}
    for activity in activities:
        if activity.start_date is None:
            continue
        act_date = activity.start_date.date()
        tss = _estimate_tss(activity)
        daily_tss[act_date] = daily_tss.get(act_date, 0.0) + tss

    result_obj = TrainingLoadResult(sport_filter=sport_filter)
    ctl = 0.0
    atl = 0.0
    current = start_date

    while current <= end_date:
        tss = daily_tss.get(current, 0.0)
        ctl = tss * ALPHA_CTL + ctl * (1 - ALPHA_CTL)
        atl = tss * ALPHA_ATL + atl * (1 - ALPHA_ATL)
        tsb = ctl - atl
        if current >= (end_date - timedelta(days=days)):
            result_obj.history.append(
                DailyLoad(date=current, daily_tss=round(tss, 2), ctl=round(ctl, 2), atl=round(atl, 2), tsb=round(tsb, 2))
            )
        current += timedelta(days=1)

    return result_obj
