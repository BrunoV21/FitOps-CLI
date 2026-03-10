from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class ActivityStream(Base):
    __tablename__ = "activity_streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    stream_type: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    data_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("activity_id", "stream_type", name="uq_stream_activity_type"),
    )

    @property
    def data(self) -> list:
        return json.loads(self.data_json)

    @classmethod
    def from_strava_stream(cls, activity_id: int, stream_type: str, data: list) -> "ActivityStream":
        return cls(
            activity_id=activity_id,
            stream_type=stream_type,
            data_json=json.dumps(data),
            data_length=len(data),
        )
