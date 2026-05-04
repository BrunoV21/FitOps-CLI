from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class ActivityCalibration(Base):
    __tablename__ = "activity_calibrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    streams_json: Mapped[str] = mapped_column(Text, nullable=False)
    race_result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("activity_id", name="uq_activity_calibrations_activity_id"),
    )

    @property
    def summary(self) -> dict:
        return json.loads(self.summary_json)

    @property
    def streams(self) -> dict:
        return json.loads(self.streams_json)

    @property
    def race_result(self) -> dict:
        return json.loads(self.race_result_json)
