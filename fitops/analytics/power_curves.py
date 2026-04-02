from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select

from fitops.db.models.activity import Activity
from fitops.db.models.activity_stream import ActivityStream
from fitops.db.session import get_async_session

STANDARD_DURATIONS = [5, 10, 15, 20, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200]
RIDE_TYPES = {"Ride", "VirtualRide", "EBikeRide"}
RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
CP_ZONE_NAMES = {
    1: "Active Recovery",
    2: "Endurance",
    3: "Tempo",
    4: "Lactate Threshold",
    5: "VO2max",
    6: "Neuromuscular",
}


def _max_mean(data: list[float], window: int) -> float | None:
    if len(data) < window:
        return None
    total = sum(data[:window])
    best = total
    for i in range(1, len(data) - window + 1):
        total += data[i + window - 1] - data[i - 1]
        if total > best:
            best = total
    return best / window if best > 0 else None


def _fit_cp(
    durations: list[int], powers: list[float]
) -> tuple[float | None, float | None, float | None]:
    try:
        from scipy.optimize import curve_fit
    except ImportError:
        return None, None, None
    if len(durations) < 5:
        return None, None, None
    try:

        def model(t, cp, w_prime):
            return cp + w_prime / t

        popt, _ = curve_fit(
            model,
            durations,
            powers,
            p0=[powers[-1] * 0.9, powers[0] * durations[0] * 0.2],
            maxfev=5000,
            bounds=([0, 0], [600, 60000]),  # typical W' ≈ 15–40 kJ; cap at 60 kJ
        )
        cp, w_prime = popt
        y_pred = [model(t, cp, w_prime) for t in durations]
        ss_res = sum((y - yp) ** 2 for y, yp in zip(powers, y_pred, strict=False))
        mean_y = sum(powers) / len(powers)
        ss_tot = sum((y - mean_y) ** 2 for y in powers)
        r_sq = round(max(0.0, 1.0 - ss_res / ss_tot), 3) if ss_tot > 0 else 0.0
        return round(cp, 1), round(w_prime, 0), r_sq
    except Exception:
        return None, None, None


def _cp_zones(cp: float) -> list[dict]:
    limits = [
        (1, 0.0, 0.55),
        (2, 0.56, 0.75),
        (3, 0.76, 0.90),
        (4, 0.91, 1.05),
        (5, 1.06, 1.20),
        (6, 1.50, None),
    ]
    zones = []
    for zn, lo, hi in limits:
        zones.append(
            {
                "zone": zn,
                "name": CP_ZONE_NAMES[zn],
                "min_watts": round(cp * lo),
                "max_watts": round(cp * hi) if hi is not None else None,
            }
        )
    return zones


@dataclass
class PowerCurveResult:
    sport: str
    activity_count: int
    mean_maximal_power: dict  # duration_s (str key for JSON) -> watts/speed
    critical_power: float | None
    w_prime: float | None
    r_squared: float | None
    zones: list[dict]
    power_to_weight: dict | None


async def compute_power_curve(
    athlete_id: int,
    sport: str = "Ride",
    max_activities: int = 20,
) -> PowerCurveResult | None:
    is_cycling = sport.lower() in ("ride", "cycling") or sport in RIDE_TYPES
    sport_types = list(RIDE_TYPES) if is_cycling else list(RUN_TYPES)
    stream_type = "watts" if is_cycling else "velocity_smooth"

    lookback = datetime.now(UTC) - timedelta(days=365)

    async with get_async_session() as session:
        from fitops.db.models.athlete import Athlete

        ath = (
            await session.execute(
                select(Athlete).where(Athlete.strava_id == athlete_id)
            )
        ).scalar_one_or_none()
        weight_kg = ath.weight_kg if ath else None

        stmt = (
            select(Activity)
            .where(
                Activity.athlete_id == athlete_id,
                Activity.sport_type.in_(sport_types),
                Activity.start_date >= lookback,
                Activity.streams_fetched.is_(True),
            )
            .order_by(desc(Activity.start_date))
            .limit(max_activities)
        )
        activities = (await session.execute(stmt)).scalars().all()

        if not activities:
            return None

        dur_values: dict[int, list[float]] = {d: [] for d in STANDARD_DURATIONS}
        acts_with_data = 0

        for act in activities:
            s_res = await session.execute(
                select(ActivityStream).where(
                    ActivityStream.activity_id == act.id,
                    ActivityStream.stream_type == stream_type,
                )
            )
            stream = s_res.scalar_one_or_none()
            if stream is None:
                continue
            data = [float(v) for v in stream.data if v is not None and float(v) > 0]
            if not data:
                continue
            acts_with_data += 1
            for dur in STANDARD_DURATIONS:
                mmp = _max_mean(data, dur)
                if mmp is not None:
                    dur_values[dur].append(mmp)

    mmp_curve = {}
    for dur in STANDARD_DURATIONS:
        vals = dur_values[dur]
        mmp_curve[str(dur)] = (
            round(sum(vals) / len(vals), 1) if len(vals) >= 3 else None
        )

    cp = w_prime = r_sq = None
    zones: list[dict] = []
    ptw_info = None

    if is_cycling:
        valid = [
            (d, mmp_curve[str(d)])
            for d in STANDARD_DURATIONS
            if mmp_curve.get(str(d)) is not None
        ]
        if len(valid) >= 5:
            durs, pows = zip(*valid, strict=False)
            cp, w_prime, r_sq = _fit_cp(list(durs), list(pows))
        if cp and r_sq is not None and r_sq >= 0.7:
            zones = _cp_zones(cp)
            if weight_kg:
                ptw_info = {
                    "ftp_estimate_watts": cp,
                    "weight_kg": weight_kg,
                    "w_per_kg": round(cp / weight_kg, 2),
                }

    return PowerCurveResult(
        sport="Ride" if is_cycling else "Run",
        activity_count=acts_with_data,
        mean_maximal_power=mmp_curve,
        critical_power=cp,
        w_prime=w_prime,
        r_squared=r_sq,
        zones=zones,
        power_to_weight=ptw_info,
    )
