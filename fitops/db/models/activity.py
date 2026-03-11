from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base

RUN_SPORT_TYPES = {"Run", "TrailRun", "Walk", "Hike", "VirtualRun"}


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strava_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    athlete_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sport_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    workout_type: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    start_date_local: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    distance_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    moving_time_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    elapsed_time_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_elevation_gain_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    average_speed_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_speed_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    average_heartrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_heartrate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    average_cadence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    average_watts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_watts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    weighted_average_watts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    training_stress_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    calories: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    suffer_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    device_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    trainer: Mapped[bool] = mapped_column(Boolean, default=False)
    commute: Mapped[bool] = mapped_column(Boolean, default=False)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    private: Mapped[bool] = mapped_column(Boolean, default=False)

    kudos_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)

    start_latlng: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    end_latlng: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    map_summary_polyline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    gear_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)

    upload_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    detail_fetched: Mapped[bool] = mapped_column(Boolean, default=False)
    streams_fetched: Mapped[bool] = mapped_column(Boolean, default=False)
    laps_fetched: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_activities_athlete_start", "athlete_id", "start_date"),
        Index("ix_activities_sport_start", "sport_type", "start_date"),
    )

    @property
    def is_race(self) -> bool:
        return self.workout_type == 1

    @staticmethod
    def get_adjusted_cadence(raw_cadence: Optional[float], sport_type: str) -> Optional[float]:
        if raw_cadence is None:
            return None
        if sport_type in RUN_SPORT_TYPES:
            return raw_cadence * 2
        return raw_cadence

    @classmethod
    def from_strava_data(cls, data: dict, athlete_id: int) -> "Activity":
        sport_type = data.get("sport_type") or data.get("type", "")
        raw_cadence = data.get("average_cadence")
        adjusted_cadence = cls.get_adjusted_cadence(raw_cadence, sport_type)

        start_latlng = data.get("start_latlng")
        end_latlng = data.get("end_latlng")
        map_data = data.get("map", {}) or {}

        def parse_date(val: Any) -> Optional[datetime]:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            try:
                return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except ValueError:
                return None

        return cls(
            strava_id=data["id"],
            athlete_id=athlete_id,
            name=data.get("name", ""),
            sport_type=sport_type,
            workout_type=data.get("workout_type"),
            start_date=parse_date(data.get("start_date")),
            start_date_local=parse_date(data.get("start_date_local")),
            timezone=data.get("timezone"),
            distance_m=data.get("distance"),
            moving_time_s=data.get("moving_time"),
            elapsed_time_s=data.get("elapsed_time"),
            total_elevation_gain_m=data.get("total_elevation_gain"),
            average_speed_ms=data.get("average_speed"),
            max_speed_ms=data.get("max_speed"),
            average_heartrate=data.get("average_heartrate"),
            max_heartrate=data.get("max_heartrate"),
            average_cadence=adjusted_cadence,
            average_watts=data.get("average_watts"),
            max_watts=data.get("max_watts"),
            weighted_average_watts=data.get("weighted_average_watts"),
            description=data.get("description"),
            calories=data.get("calories"),
            suffer_score=data.get("suffer_score"),
            device_name=data.get("device_name"),
            trainer=bool(data.get("trainer", False)),
            commute=bool(data.get("commute", False)),
            manual=bool(data.get("manual", False)),
            private=bool(data.get("private", False)),
            kudos_count=data.get("kudos_count", 0) or 0,
            comment_count=data.get("comment_count", 0) or 0,
            start_latlng=json.dumps(start_latlng) if start_latlng else None,
            end_latlng=json.dumps(end_latlng) if end_latlng else None,
            map_summary_polyline=map_data.get("summary_polyline"),
            gear_id=data.get("gear_id"),
            upload_id=data.get("upload_id"),
            external_id=data.get("external_id"),
        )

    def update_from_strava_data(self, data: dict) -> None:
        sport_type = data.get("sport_type") or data.get("type", self.sport_type)
        raw_cadence = data.get("average_cadence")
        adjusted_cadence = self.get_adjusted_cadence(raw_cadence, sport_type)

        self.name = data.get("name", self.name)
        self.sport_type = sport_type
        self.workout_type = data.get("workout_type", self.workout_type)
        self.distance_m = data.get("distance", self.distance_m)
        self.moving_time_s = data.get("moving_time", self.moving_time_s)
        self.elapsed_time_s = data.get("elapsed_time", self.elapsed_time_s)
        self.total_elevation_gain_m = data.get("total_elevation_gain", self.total_elevation_gain_m)
        self.average_speed_ms = data.get("average_speed", self.average_speed_ms)
        self.max_speed_ms = data.get("max_speed", self.max_speed_ms)
        self.average_heartrate = data.get("average_heartrate", self.average_heartrate)
        self.max_heartrate = data.get("max_heartrate", self.max_heartrate)
        self.average_cadence = adjusted_cadence if adjusted_cadence is not None else self.average_cadence
        self.average_watts = data.get("average_watts", self.average_watts)
        self.max_watts = data.get("max_watts", self.max_watts)
        self.weighted_average_watts = data.get("weighted_average_watts", self.weighted_average_watts)
        self.description = data.get("description", self.description)
        self.calories = data.get("calories", self.calories)
        self.suffer_score = data.get("suffer_score", self.suffer_score)
        self.kudos_count = data.get("kudos_count", self.kudos_count) or 0
        self.comment_count = data.get("comment_count", self.comment_count) or 0
        self.gear_id = data.get("gear_id", self.gear_id)
        self.updated_at = datetime.now(timezone.utc)
