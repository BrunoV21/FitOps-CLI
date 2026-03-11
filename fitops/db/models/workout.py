from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class Workout(Base):
    """A workout definition linked to a Strava activity."""

    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Identity ---
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sport_type: Mapped[str] = mapped_column(Text, nullable=False)

    # --- Markdown-file source (Phase 3) ---
    athlete_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    workout_file_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workout_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workout_meta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # --- Activity link ---
    activity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    linked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Physiology snapshot at link time ---
    physiology_snapshot: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON: {ctl, atl, tsb, vo2max, lt1_hr, lt2_hr, zones_method, zones}

    # --- Legacy / Phase 3.2 ---
    course_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="planned")
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    compliance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # --- Helpers ---

    def get_workout_meta(self) -> dict[str, Any]:
        if not self.workout_meta:
            return {}
        try:
            return json.loads(self.workout_meta)
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_physiology_snapshot(self) -> dict[str, Any]:
        if not self.physiology_snapshot:
            return {}
        try:
            return json.loads(self.physiology_snapshot)
        except (json.JSONDecodeError, TypeError):
            return {}

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "sport_type": self.sport_type,
            "workout_file": self.workout_file_name,
            "activity_id": self.activity_id,
            "linked_at": str(self.linked_at) if self.linked_at else None,
            "compliance_score": self.compliance_score,
            "status": self.status,
        }
