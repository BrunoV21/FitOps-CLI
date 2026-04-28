from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class RacePlan(Base):
    """A saved race simulation / plan linked to a RaceCourse.

    One plan per simulation snapshot.  When an activity is auto-matched
    (by date + GPS proximity) its internal id is stored in ``activity_id``.
    Simulated splits are cached in ``splits_json`` as a JSON array so the
    detail page never needs to re-run the simulation.
    """

    __tablename__ = "race_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # Race date/time
    race_date: Mapped[str | None] = mapped_column(Text, nullable=True)  # YYYY-MM-DD
    race_hour: Mapped[int] = mapped_column(Integer, default=9)

    # Target
    target_time: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # display "H:MM:SS"
    target_time_s: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # canonical

    # Pacing strategy
    strategy: Mapped[str] = mapped_column(
        Text, default="even"
    )  # even|negative|positive
    pacer_pace: Mapped[str | None] = mapped_column(Text, nullable=True)  # "MM:SS"
    drop_at_km: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Weather at save time
    weather_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_wind_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_wind_dir_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_source: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cached simulated splits JSON: list[dict] from simulate_splits()
    splits_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Linked activity (set by auto-association in sync pipeline)
    activity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_splits(self) -> list[dict]:
        """Deserialise splits_json → list of split dicts.  Returns [] if unset."""
        if not self.splits_json:
            return []
        try:
            return json.loads(self.splits_json)
        except (json.JSONDecodeError, TypeError):
            return []

    def to_summary_dict(self) -> dict[str, Any]:
        """Lightweight dict for list views (no splits payload)."""
        return {
            "id": self.id,
            "course_id": self.course_id,
            "name": self.name,
            "race_date": self.race_date,
            "race_hour": self.race_hour,
            "target_time": self.target_time,
            "target_time_s": self.target_time_s,
            "strategy": self.strategy,
            "pacer_pace": self.pacer_pace,
            "drop_at_km": self.drop_at_km,
            "weather_temp_c": self.weather_temp_c,
            "weather_humidity_pct": self.weather_humidity_pct,
            "weather_wind_ms": self.weather_wind_ms,
            "weather_wind_dir_deg": self.weather_wind_dir_deg,
            "weather_source": self.weather_source,
            "activity_id": self.activity_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_detail_dict(self) -> dict[str, Any]:
        """Full dict including cached splits."""
        d = self.to_summary_dict()
        d["splits"] = self.get_splits()
        return d
