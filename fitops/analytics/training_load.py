from __future__ import annotations

import statistics as _stats
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

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
    sport_filter: str | None = None

    @property
    def current(self) -> DailyLoad | None:
        return self.history[-1] if self.history else None

    @property
    def ramp_rate_pct(self) -> float | None:
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
        return round(duration_h * (intensity_factor**2) * 100, 2)

    # --- Running with pace + threshold pace from settings ---
    if (
        sport in RUN_TYPES
        and activity.average_speed_ms
        and activity.average_speed_ms > 0
    ):
        threshold_pace_s = settings.threshold_pace_per_km_s  # seconds per km
        if threshold_pace_s and threshold_pace_s > 0:
            avg_pace_s = 1000 / activity.average_speed_ms  # seconds per km
            intensity_factor = min(threshold_pace_s / avg_pace_s, 2.0)
            return round(duration_h * (intensity_factor**2) * 100, 2)
        else:
            intensity_factor = min(1.1, 2.0)
            return round(duration_h * (intensity_factor**2) * 100, 2)

    # --- HR fallback ---
    if activity.average_heartrate:
        lthr = settings.lthr
        max_hr = settings.max_hr
        avg_hr = activity.average_heartrate

        if lthr:
            hr_ratio = avg_hr / lthr
        elif max_hr:
            hr_ratio = avg_hr / (max_hr * 0.88)  # LTHR ≈ 88% max HR (Karvonen standard)
        else:
            age = settings.age
            estimated_max_hr = (220 - age) if age else 185
            hr_ratio = avg_hr / estimated_max_hr

        intensity_factor = min(hr_ratio, 2.0)
        return round(duration_h * (intensity_factor**2) * 100, 2)

    return round(duration_h * 50, 2)


async def compute_training_load(
    athlete_id: int,
    days: int = 90,
    sport_filter: str | None = None,
    sport_types: frozenset | None = None,
) -> TrainingLoadResult:
    end_date = date.today()
    warmup_days = CTL_DAYS * 2
    total_days = days + warmup_days
    start_date = end_date - timedelta(days=total_days)

    async with get_async_session() as session:
        stmt = select(Activity).where(
            Activity.athlete_id == athlete_id,
            Activity.start_date
            >= datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC),
        )
        if sport_filter:
            stmt = stmt.where(Activity.sport_type == sport_filter)
        elif sport_types:
            stmt = stmt.where(Activity.sport_type.in_(list(sport_types)))
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
                DailyLoad(
                    date=current,
                    daily_tss=round(tss, 2),
                    ctl=round(ctl, 2),
                    atl=round(atl, 2),
                    tsb=round(tsb, 2),
                )
            )
        current += timedelta(days=1)

    return result_obj


async def persist_training_load_snapshot(athlete_id: int) -> None:
    """Compute today's CTL/ATL/TSB and upsert into analytics_snapshots.

    Called once at the end of every sync so that dashboard page loads can
    read a single pre-computed row instead of re-running the full 84-day
    EWMA warmup on every request.
    """
    from datetime import datetime, timezone

    from sqlalchemy import text

    from fitops.db.session import get_async_session

    result = await compute_training_load(athlete_id=athlete_id, days=1)
    if not result.current:
        return

    c = result.current
    today = c.date.isoformat()
    now = datetime.now(timezone.utc).isoformat()

    async with get_async_session() as session:
        # sport_type IS NULL makes standard ON CONFLICT unreliable in SQLite;
        # use a manual SELECT + INSERT/UPDATE instead.
        existing = await session.execute(
            text(
                "SELECT id FROM analytics_snapshots "
                "WHERE athlete_id = :aid AND snapshot_date = :dt AND sport_type IS NULL"
            ),
            {"aid": athlete_id, "dt": today},
        )
        row = existing.scalar_one_or_none()
        if row is None:
            await session.execute(
                text(
                    "INSERT INTO analytics_snapshots "
                    "(athlete_id, snapshot_date, sport_type, ctl, atl, tsb, computed_at) "
                    "VALUES (:aid, :dt, NULL, :ctl, :atl, :tsb, :now)"
                ),
                {
                    "aid": athlete_id,
                    "dt": today,
                    "ctl": round(c.ctl, 2),
                    "atl": round(c.atl, 2),
                    "tsb": round(c.tsb, 2),
                    "now": now,
                },
            )
        else:
            await session.execute(
                text(
                    "UPDATE analytics_snapshots "
                    "SET ctl = :ctl, atl = :atl, tsb = :tsb, computed_at = :now "
                    "WHERE id = :id"
                ),
                {
                    "ctl": round(c.ctl, 2),
                    "atl": round(c.atl, 2),
                    "tsb": round(c.tsb, 2),
                    "now": now,
                    "id": row,
                },
            )


def _compute_overtraining_indicators(history: list) -> dict:
    """Compute ACWR, training monotony, and training strain from DailyLoad history."""
    if not history:
        return {}

    current = history[-1]

    # Require 21+ days of history before ACWR is meaningful (CTL takes ~42 days to converge)
    if len(history) < 21:
        acwr = None
        acwr_label = "Insufficient history"
    else:
        acwr = round(current.atl / current.ctl, 2) if current.ctl > 0 else None
        if acwr is None:
            acwr_label = "Unknown"
        elif acwr < 0.8:
            acwr_label = "Detraining"
        elif acwr <= 1.3:
            acwr_label = "Optimal"
        elif acwr <= 1.5:
            acwr_label = "Caution — elevated injury risk"
        else:
            acwr_label = "Danger — high injury risk"

    # Training monotony from last 7 days of TSS
    recent_tss = [d.daily_tss for d in history[-7:]]
    monotony = None
    strain = None
    if len(recent_tss) >= 5:  # require 5 data points to avoid meaningless monotony
        mean_tss = sum(recent_tss) / len(recent_tss)
        if mean_tss > 0:
            try:
                stdev = _stats.stdev(recent_tss)
                monotony = round(mean_tss / stdev, 2) if stdev > 0 else None
            except Exception:
                monotony = None

    if monotony is not None:
        strain = round(monotony * sum(recent_tss), 1)

    if monotony is None:
        monotony_label = "Unknown"
    elif monotony < 1.5:
        monotony_label = "Varied — good training diversity"
    elif monotony < 2.0:
        monotony_label = "Monotonous — consider varying intensity"
    else:
        monotony_label = "High risk — vary training immediately"

    return {
        "acwr": acwr,
        "acwr_label": acwr_label,
        "training_monotony": monotony,
        "monotony_label": monotony_label,
        "training_strain": strain,
    }
