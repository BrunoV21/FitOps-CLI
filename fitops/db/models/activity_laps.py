from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class ActivityLap(Base):
    __tablename__ = "activity_laps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    strava_lap_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lap_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    elapsed_time_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    moving_time_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    distance_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    average_speed_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    average_heartrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_heartrate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    average_watts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def from_strava_data(cls, activity_id: int, data: dict) -> "ActivityLap":
        return cls(
            activity_id=activity_id,
            strava_lap_id=data.get("id"),
            lap_index=data.get("lap_index"),
            name=data.get("name"),
            elapsed_time_s=data.get("elapsed_time"),
            moving_time_s=data.get("moving_time"),
            distance_m=data.get("distance"),
            average_speed_ms=data.get("average_speed"),
            average_heartrate=data.get("average_heartrate"),
            max_heartrate=data.get("max_heartrate"),
            average_watts=data.get("average_watts"),
        )
