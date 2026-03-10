from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, Float, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class AnalyticsSnapshot(Base):
    """Phase 2 stub — table created but no business logic yet."""

    __tablename__ = "analytics_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    sport_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ctl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    atl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tsb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vo2max_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lt1_hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lt2_hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("athlete_id", "snapshot_date", "sport_type", name="uq_snapshot"),
    )
