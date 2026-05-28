from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class BackupState(Base):
    __tablename__ = "backup_state"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class BackupHistory(Base):
    __tablename__ = "backup_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    remote_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="github")
    origin_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="success")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
