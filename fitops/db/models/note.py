from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)         # JSON list
    activity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    body_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # first 200 chars
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def tags_list(self) -> list[str]:
        return json.loads(self.tags or "[]")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "tags": self.tags_list(),
            "activity_id": self.activity_id,
            "body_preview": self.body_preview,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
