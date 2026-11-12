from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class MobileActivityOrigin(Base):
    """Stable source identity for records transferred from FitOps Mobile."""

    __tablename__ = "mobile_activity_origins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    athlete_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_activity_id: Mapped[str] = mapped_column(Text, nullable=False)
    exported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint(
            "athlete_id",
            "provider",
            "provider_account_id",
            "provider_activity_id",
            name="uq_mobile_activity_source",
        ),
    )
