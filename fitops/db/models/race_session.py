from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class RaceSession(Base):
    __tablename__ = "race_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    primary_activity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    course_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Pre-computed replay timeline — JSON: list of
    # {t_s, athletes: [{lat, lon, dist_m, vel, hr, rank, gap_m}, ...]}
    # Athletes array preserves the order returned by get_session_athletes().
    replay_frames_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    replay_time_step_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    def get_replay_frames(self) -> list[dict]:
        """Deserialise replay_frames_json -> list[dict]."""
        if not self.replay_frames_json:
            return []
        return json.loads(self.replay_frames_json)

    def to_summary_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "primary_activity_id": self.primary_activity_id,
            "course_id": self.course_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RaceSessionAthlete(Base):
    __tablename__ = "race_session_athletes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # activity_id is None for GPX imports that aren't linked to a Strava activity
    activity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    athlete_label: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Interpolated, smoothed stream — JSON: {time, distance, latlng, altitude, heartrate,
    # cadence, velocity, gap_series, ...} aligned to 10m distance grid
    stream_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-athlete race metrics JSON: {total_time_s, avg_pace_s_per_km, avg_hr, cadence_std, ...}
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    def get_stream(self) -> dict:
        """Deserialise stream_json -> dict."""
        if not self.stream_json:
            return {}
        return json.loads(self.stream_json)

    def get_metrics(self) -> dict:
        """Deserialise metrics_json -> dict."""
        if not self.metrics_json:
            return {}
        return json.loads(self.metrics_json)

    def to_summary_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "activity_id": self.activity_id,
            "strava_url": f"https://www.strava.com/activities/{self.activity_id}" if self.activity_id else None,
            "athlete_label": self.athlete_label,
            "is_primary": self.is_primary,
            "metrics": self.get_metrics(),
            "added_at": self.added_at.isoformat() if self.added_at else None,
        }


class RaceSessionGap(Base):
    __tablename__ = "race_session_gaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    athlete_label: Mapped[str] = mapped_column(Text, nullable=False)
    # gap_series — JSON: list of {distance_km, time_s, gap_to_leader_s, gap_to_leader_m, position}
    gap_series_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # delta_series — JSON: list of {distance_km, delta_s_per_km} (derivative of gap)
    delta_series_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    def get_gap_series(self) -> list[dict]:
        if not self.gap_series_json:
            return []
        return json.loads(self.gap_series_json)

    def get_delta_series(self) -> list[dict]:
        if not self.delta_series_json:
            return []
        return json.loads(self.delta_series_json)


class RaceSessionEvent(Base):
    __tablename__ = "race_session_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # event_type: surge | drop | bridge | fade | final_sprint | separation
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    athlete_label: Mapped[str] = mapped_column(Text, nullable=False)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    elapsed_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Positive = gained time, negative = lost time
    impact_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "athlete_label": self.athlete_label,
            "distance_km": self.distance_km,
            "elapsed_s": self.elapsed_s,
            "impact_s": self.impact_s,
            "description": self.description,
        }


class RaceSessionSegment(Base):
    __tablename__ = "race_session_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    segment_label: Mapped[str] = mapped_column(Text, nullable=False)
    start_km: Mapped[float] = mapped_column(Float, nullable=False)
    end_km: Mapped[float] = mapped_column(Float, nullable=False)
    # gradient_type: climb | descent | flat
    gradient_type: Mapped[str] = mapped_column(Text, nullable=False, default="flat")
    avg_grade_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Per-athlete metrics — JSON: {athlete_label: {time_s, gap_s, avg_pace_s_per_km,
    #   avg_gap_s_per_km, rank, time_gained_vs_leader_s}}
    athlete_metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    def get_athlete_metrics(self) -> dict:
        if not self.athlete_metrics_json:
            return {}
        return json.loads(self.athlete_metrics_json)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "segment_label": self.segment_label,
            "start_km": self.start_km,
            "end_km": self.end_km,
            "gradient_type": self.gradient_type,
            "avg_grade_pct": self.avg_grade_pct,
            "athlete_metrics": self.get_athlete_metrics(),
        }
