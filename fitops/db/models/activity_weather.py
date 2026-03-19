from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class ActivityWeather(Base):
    __tablename__ = "activity_weather"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)

    # Core fields (SI units: °C, %, m/s, mm, degrees)
    temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    apparent_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dew_point_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_speed_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)       # m/s
    wind_direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0=N, 90=E
    wind_gusts_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    precipitation_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weather_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)        # WMO code

    # Derived / computed on write
    wbgt_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)              # WBGT approx
    pace_heat_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)    # e.g. 1.06

    source: Mapped[str] = mapped_column(Text, default="open-meteo")  # "open-meteo" | "manual"
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "activity_id": self.activity_id,
            "temperature_c": self.temperature_c,
            "humidity_pct": self.humidity_pct,
            "apparent_temp_c": self.apparent_temp_c,
            "dew_point_c": self.dew_point_c,
            "wind_speed_ms": self.wind_speed_ms,
            "wind_direction_deg": self.wind_direction_deg,
            "wind_gusts_ms": self.wind_gusts_ms,
            "precipitation_mm": self.precipitation_mm,
            "weather_code": self.weather_code,
            "wbgt_c": self.wbgt_c,
            "pace_heat_factor": self.pace_heat_factor,
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }
