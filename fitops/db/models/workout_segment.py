from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fitops.workouts.compliance import SegmentCompliance

from sqlalchemy import Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class WorkoutSegment(Base):
    """Per-segment compliance analytics when a workout is linked to an activity.

    Phase 3.2 — table created now; compliance scoring logic added in Phase 3.2.
    Each row represents one named segment from the workout definition scored
    against the matching slice of the activity's HR/power streams.
    """

    __tablename__ = "workout_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workout_id: Mapped[int] = mapped_column(Integer, nullable=False)  # FK → workouts.id
    activity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Segment identity
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_type: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # warmup | interval | recovery | cooldown

    # Stream boundaries (indices into activity stream arrays)
    start_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Segment duration and distance actuals
    duration_actual_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_actual_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Target
    target_focus_type: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # hr_zone | pace_zone | power_zone | rpe
    target_zone: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Pace / speed actuals
    avg_pace_per_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    pace_consistency_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # 0.0–1.0

    # HR actuals
    avg_heartrate: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_zone_distribution: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON: {"z1": 0.05, "z2": 0.60, ...}

    # Pace / speed actuals (extended)
    avg_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_cadence: Mapped[float | None] = mapped_column(Float, nullable=True)  # spm
    avg_gap_per_km: Mapped[float | None] = mapped_column(Float, nullable=True)  # s/km

    # Target bounds for hr_range / pace_range segments
    target_hr_min_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_hr_max_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_pace_min_s_per_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_pace_max_s_per_km: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Power actuals
    avg_watts: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_power: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Compliance
    target_achieved: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # 1/0 bool stored as int (SQLite)
    deviation_pct: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # positive = above target
    time_in_target_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_above_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_below_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    compliance_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # 0.0–1.0

    # Data quality
    has_heartrate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_power: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_gps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_completeness: Mapped[float | None] = mapped_column(Float, nullable=True)

    def get_hr_zone_distribution(self) -> dict[str, Any]:
        if not self.hr_zone_distribution:
            return {}
        try:
            return json.loads(self.hr_zone_distribution)
        except (json.JSONDecodeError, TypeError):
            return {}

    @classmethod
    def from_compliance_result(
        cls,
        workout_id: int,
        activity_id: int,
        result: SegmentCompliance,  # fitops.workouts.compliance.SegmentCompliance
    ) -> WorkoutSegment:
        seg = result.segment
        scored = result.has_heartrate or result.has_pace
        return cls(
            workout_id=workout_id,
            activity_id=activity_id,
            segment_index=seg.index,
            segment_name=seg.name,
            step_type=seg.step_type,
            start_index=result.start_index,
            end_index=result.end_index,
            duration_actual_s=result.duration_actual_s
            if result.duration_actual_s
            else None,
            distance_actual_m=result.distance_actual_m,
            target_focus_type=seg.target_focus_type
            if seg.target_focus_type != "hr_zone" or seg.target_zone
            else None,
            target_zone=seg.target_zone,
            # Target bounds
            target_hr_min_bpm=seg.target_hr_min_bpm,
            target_hr_max_bpm=seg.target_hr_max_bpm,
            target_pace_min_s_per_km=seg.target_pace_min_s_per_km,
            target_pace_max_s_per_km=seg.target_pace_max_s_per_km,
            # HR actuals
            avg_heartrate=result.avg_heartrate,
            hr_zone_distribution=json.dumps(result.hr_zone_distribution)
            if result.hr_zone_distribution
            else None,
            # Pace / speed actuals
            avg_pace_per_km=result.avg_pace_per_km,
            avg_speed_ms=result.avg_speed_ms,
            avg_cadence=result.avg_cadence,
            avg_gap_per_km=result.avg_gap_per_km,
            # Compliance
            target_achieved=int(result.target_achieved) if scored else None,
            deviation_pct=result.deviation_pct if scored else None,
            time_in_target_pct=result.time_in_target_pct if scored else None,
            time_above_pct=result.time_above_pct if scored else None,
            time_below_pct=result.time_below_pct if scored else None,
            compliance_score=result.compliance_score if scored else None,
            has_heartrate=int(result.has_heartrate),
            has_power=0,
            has_gps=0,
            data_completeness=result.data_completeness,
        )

    def _fmt_pace(self, pace_s: float | None) -> str | None:
        if pace_s is None:
            return None
        m, s = divmod(int(pace_s), 60)
        return f"{m}:{s:02d}"

    def _fmt_duration(self, secs: int | None) -> str | None:
        if secs is None or secs <= 0:
            return None
        m, s = divmod(secs, 60)
        return f"{m}:{s:02d}"

    def _fmt_distance(self, meters: float | None) -> str | None:
        if meters is None or meters <= 0:
            return None
        if meters >= 1000:
            return f"{meters / 1000:.2f} km"
        return f"{meters:.0f} m"

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_index": self.segment_index,
            "segment_name": self.segment_name,
            "step_type": self.step_type,
            "target_focus_type": self.target_focus_type,
            "target_zone": self.target_zone,
            "target_hr_range": (
                {"min_bpm": self.target_hr_min_bpm, "max_bpm": self.target_hr_max_bpm}
                if self.target_hr_min_bpm is not None
                or self.target_hr_max_bpm is not None
                else None
            ),
            "target_pace_range": (
                {
                    "min_s_per_km": self.target_pace_min_s_per_km,
                    "max_s_per_km": self.target_pace_max_s_per_km,
                    "min_formatted": self._fmt_pace(self.target_pace_min_s_per_km),
                    "max_formatted": self._fmt_pace(self.target_pace_max_s_per_km),
                }
                if self.target_pace_min_s_per_km is not None
                or self.target_pace_max_s_per_km is not None
                else None
            ),
            "stream_slice": {
                "start_index": self.start_index,
                "end_index": self.end_index,
            },
            "actuals": {
                "duration_actual_s": self.duration_actual_s,
                "duration_formatted": self._fmt_duration(self.duration_actual_s),
                "distance_actual_m": self.distance_actual_m,
                "distance_formatted": self._fmt_distance(self.distance_actual_m),
                "avg_heartrate_bpm": self.avg_heartrate,
                "avg_pace_per_km": self.avg_pace_per_km,
                "avg_pace_formatted": self._fmt_pace(self.avg_pace_per_km),
                "avg_speed_ms": self.avg_speed_ms,
                "avg_speed_kmh": round(self.avg_speed_ms * 3.6, 2)
                if self.avg_speed_ms
                else None,
                "avg_cadence": self.avg_cadence,
                "avg_gap_per_km": self.avg_gap_per_km,
                "avg_gap_formatted": self._fmt_pace(self.avg_gap_per_km),
                "hr_zone_distribution": self.get_hr_zone_distribution(),
            },
            "compliance": {
                "target_achieved": bool(self.target_achieved)
                if self.target_achieved is not None
                else None,
                "compliance_score": self.compliance_score,
                "deviation_pct": self.deviation_pct,
                "time_in_target_pct": self.time_in_target_pct,
                "time_above_pct": self.time_above_pct,
                "time_below_pct": self.time_below_pct,
            },
            "data_quality": {
                "has_heartrate": bool(self.has_heartrate),
                "has_power": bool(self.has_power),
                "data_completeness": self.data_completeness,
            },
        }
