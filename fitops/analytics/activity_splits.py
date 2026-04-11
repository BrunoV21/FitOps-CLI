from __future__ import annotations

RUN_SPORT_TYPES = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}


def compute_km_splits(
    streams: dict, sport_type: str, true_pace: list[float] | None = None
) -> list[dict] | None:
    """Compute per-km splits from distance/velocity/heartrate/cadence/altitude streams.

    Returns None for non-running sports or when there is insufficient data.
    Each split dict: {km, label, partial, pace, pace_s, avg_hr, avg_cad, elev_gain,
                      elev_loss, avg_true_pace}
    """
    if sport_type not in RUN_SPORT_TYPES:
        return None

    dist = streams.get("distance", [])
    vel = streams.get("velocity_smooth", [])
    hr = streams.get("heartrate", [])
    cad = streams.get("cadence", [])
    alt = streams.get("altitude", [])
    tp = true_pace or []

    if len(dist) < 10 or len(vel) < 10 or (dist[-1] if dist else 0) < 1000:
        return None

    is_run = sport_type in {"Run", "TrailRun", "VirtualRun"}

    def _seg_stats(start: int, end: int) -> dict:
        seg_vel = vel[start : end + 1]
        valid_vels = [v for v in seg_vel if v and v > 0.1]
        if not valid_vels:
            return {}
        avg_vel = sum(valid_vels) / len(valid_vels)
        pace_s = round(1000.0 / avg_vel, 1)
        m, s_rem = divmod(int(pace_s), 60)

        avg_hr_val = None
        if hr and len(hr) > start:
            hr_slice = [h for h in hr[start : end + 1] if h and h > 0]
            if hr_slice:
                avg_hr_val = round(sum(hr_slice) / len(hr_slice))

        avg_cad = None
        if cad and len(cad) > start:
            cad_slice = [c for c in cad[start : end + 1] if c and c > 0]
            if cad_slice:
                raw = sum(cad_slice) / len(cad_slice)
                avg_cad = round(raw * 2 if is_run else raw)

        elev_gain = None
        elev_loss = None
        if alt and len(alt) > start:
            alt_slice = alt[start : end + 1]
            gain = 0.0
            loss = 0.0
            for j in range(1, len(alt_slice)):
                delta = alt_slice[j] - alt_slice[j - 1]
                if delta > 0:
                    gain += delta
                else:
                    loss += abs(delta)
            elev_gain = round(gain)
            elev_loss = round(loss)

        avg_true_pace = None
        if tp and len(tp) > start:
            tp_slice = [v for v in tp[start : end + 1] if v and v > 0]
            if tp_slice:
                avg_tp_s = sum(tp_slice) / len(tp_slice)
                tp_m, tp_s = divmod(int(avg_tp_s), 60)
                avg_true_pace = f"{tp_m}:{tp_s:02d}/km"

        return {
            "pace": f"{m}:{s_rem:02d}",
            "pace_s": pace_s,
            "avg_hr": avg_hr_val,
            "avg_cad": avg_cad,
            "elev_gain": elev_gain,
            "elev_loss": elev_loss,
            "avg_true_pace": avg_true_pace,
        }

    splits = []
    km_target = 1000.0
    seg_start = 0

    for i in range(1, len(dist)):
        if dist[i] < km_target:
            continue

        stats = _seg_stats(seg_start, i)
        if not stats:
            km_target += 1000.0
            continue

        splits.append(
            {
                "km": len(splits) + 1,
                "label": str(len(splits) + 1),
                "partial": False,
                **stats,
            }
        )

        seg_start = i
        km_target += 1000.0
        if len(splits) >= 100:
            break

    # Partial last km
    if seg_start < len(dist) - 1 and (dist[-1] - dist[seg_start]) >= 100:
        remaining = dist[-1] - dist[seg_start]
        stats = _seg_stats(seg_start, len(dist) - 1)
        if stats:
            splits.append(
                {
                    "km": len(splits) + 1,
                    "label": f"{len(splits) + 1} ({remaining / 1000:.2f}km)",
                    "partial": True,
                    **stats,
                }
            )

    return splits if splits else None


def compute_avg_gap(streams: dict, sport_type: str) -> str | None:
    """Compute average grade-adjusted pace from stream data (running only).

    Returns a formatted string like '4:52/km', or None.
    """
    if sport_type not in RUN_SPORT_TYPES:
        return None

    gas = streams.get("grade_adjusted_speed", [])
    if not gas:
        vel = streams.get("velocity_smooth", [])
        grade = streams.get("grade_smooth", [])
        if vel and grade:
            gas = [
                v * (1 + 0.033 * g) if v and v > 0.1 else 0.0
                for v, g in zip(vel, grade, strict=False)
            ]

    valid = [v for v in gas if v and v > 0.1]
    if not valid:
        return None

    avg_v = sum(valid) / len(valid)
    pace_s = 1000.0 / avg_v
    m, s = divmod(int(pace_s), 60)
    return f"{m}:{s:02d}/km"
