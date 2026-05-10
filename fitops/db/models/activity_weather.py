from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class ActivityWeather(Base):
    __tablename__ = "activity_weather"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        Integer, nullable=False, unique=True, index=True
    )

    # Core fields (SI units: °C, %, m/s, mm, degrees)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    apparent_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    dew_point_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)  # m/s
    wind_direction_deg: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # 0=N, 90=E
    wind_gusts_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_code: Mapped[int | None] = mapped_column(Integer, nullable=True)  # WMO code

    # Derived / computed on write
    wbgt_c: Mapped[float | None] = mapped_column(Float, nullable=True)  # WBGT approx
    pace_heat_factor: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # e.g. 1.06

    # Persisted derived weather-pace values (populated during weather fetch or
    # lazy-computed on first read; NULL means "not yet computed").
    wap_factor: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # combined heat+wind factor e.g. 1.06
    course_bearing: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # degrees, 0=N clockwise
    hr_heat_pct: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # HR impact from heat (%)
    hr_heat_bpm: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # HR impact from heat (bpm)
    true_pace_s_per_km: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # distance-weighted mean true pace

    source: Mapped[str] = mapped_column(
        Text, default="open-meteo"
    )  # "open-meteo" | "manual"
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
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
            "wap_factor": self.wap_factor,
            "course_bearing": self.course_bearing,
            "hr_heat_pct": self.hr_heat_pct,
            "hr_heat_bpm": self.hr_heat_bpm,
            "true_pace_s_per_km": self.true_pace_s_per_km,
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }
