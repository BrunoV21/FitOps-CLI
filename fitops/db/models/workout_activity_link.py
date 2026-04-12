from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class WorkoutActivityLink(Base):
    """Join table: one workout can be assigned to many activities.

    Stores the per-link metadata that previously lived on the Workout row
    (compliance_score, linked_at, physiology_snapshot, status).
    """

    __tablename__ = "workout_activity_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workout_id: Mapped[int] = mapped_column(Integer, nullable=False)
    activity_id: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # internal Activity.id

    linked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    physiology_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    compliance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="completed")

    def get_physiology_snapshot(self) -> dict[str, Any]:
        if not self.physiology_snapshot:
            return {}
        try:
            return json.loads(self.physiology_snapshot)
        except (json.JSONDecodeError, TypeError):
            return {}
