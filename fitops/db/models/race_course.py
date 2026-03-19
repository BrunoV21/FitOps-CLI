from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class RaceCourse(Base):
    __tablename__ = "race_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)        # "gpx" | "tcx" | "mapmyrun" | "strava"
    source_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # URL or activity_id string
    file_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # "gpx" | "tcx" | None

    total_distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    total_elevation_gain_m: Mapped[float] = mapped_column(Float, nullable=False)
    num_points: Mapped[int] = mapped_column(Integer, nullable=False)

    # Start point for weather fetch (first waypoint of the course)
    start_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Full waypoints — JSON: list of {lat, lon, elevation_m, distance_from_start_m}
    course_points_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Pre-built 1km segments — JSON: list of {km, distance_m, elevation_gain_m, grade, bearing}
    # Stored at import time; never recomputed on simulate calls.
    km_segments_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def get_course_points(self) -> list[dict]:
        """Deserialise course_points_json -> list of dicts."""
        return json.loads(self.course_points_json)

    def get_km_segments(self) -> list[dict]:
        """Deserialise km_segments_json -> list of dicts. Returns [] if not set."""
        if not self.km_segments_json:
            return []
        return json.loads(self.km_segments_json)

    def to_summary_dict(self) -> dict:
        """Lightweight dict for course list output (no waypoints)."""
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "source_ref": self.source_ref,
            "total_distance_km": round(self.total_distance_m / 1000, 2),
            "total_elevation_gain_m": round(self.total_elevation_gain_m, 1),
            "num_points": self.num_points,
            "start_lat": self.start_lat,
            "start_lon": self.start_lon,
            "imported_at": self.imported_at.isoformat() if self.imported_at else None,
        }
