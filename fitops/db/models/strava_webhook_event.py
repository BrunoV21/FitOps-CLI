from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class StravaWebhookEvent(Base):
    __tablename__ = "strava_webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    object_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    object_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    aspect_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    event_time: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    updates_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            "object_type",
            "object_id",
            "aspect_type",
            "event_time",
            name="uq_strava_webhook_event",
        ),
    )

    @property
    def updates(self) -> dict:
        if not self.updates_json:
            return {}
        try:
            return json.loads(self.updates_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subscription_id": self.subscription_id,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "aspect_type": self.aspect_type,
            "owner_id": self.owner_id,
            "event_time": self.event_time,
            "updates": self.updates,
            "status": self.status,
            "error": self.error,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "processed_at": self.processed_at.isoformat()
            if self.processed_at
            else None,
        }
