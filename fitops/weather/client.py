from __future__ import annotations

from datetime import datetime
from typing import Optional

import httpx

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "dew_point_2m",
    "weather_code",
]

# Map Open-Meteo field names → our model field names
_FIELD_MAP = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "humidity_pct",
    "apparent_temperature": "apparent_temp_c",
    "precipitation": "precipitation_mm",
    "wind_speed_10m": "wind_speed_ms",
    "wind_direction_10m": "wind_direction_deg",
    "wind_gusts_10m": "wind_gusts_ms",
    "dew_point_2m": "dew_point_c",
    "weather_code": "weather_code",
}


async def fetch_activity_weather(
    lat: float, lng: float, activity_start_utc: datetime
) -> Optional[dict]:
    """
    Fetch one hourly weather record from Open-Meteo archive API.
    Returns dict with normalized field names (matching ActivityWeather model), or None on failure.
    """
    date_str = activity_start_utc.strftime("%Y-%m-%d")
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lng, 4),
        "start_date": date_str,
        "end_date": date_str,
        "hourly": ",".join(HOURLY_FIELDS),
        "timezone": "UTC",
        "wind_speed_unit": "ms",  # m/s for physics formulas
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(BASE_URL, params=params)
            resp.raise_for_status()
        data = resp.json()
        hour_idx = activity_start_utc.hour
        hourly = data["hourly"]
        raw = {field: hourly[field][hour_idx] for field in HOURLY_FIELDS}
        # Remap to model field names
        return {_FIELD_MAP[k]: v for k, v in raw.items()}
    except Exception:
        return None


async def fetch_forecast_weather(
    lat: float, lng: float, date: str, hour: int
) -> Optional[dict]:
    """
    Fetch hourly forecast from Open-Meteo forecast API (up to 16 days ahead).
    date: 'YYYY-MM-DD', hour: 0-23 (local time at location).
    Returns dict with normalized field names, or None on failure.
    """
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lng, 4),
        "start_date": date,
        "end_date": date,
        "hourly": ",".join(HOURLY_FIELDS),
        "timezone": "auto",  # local time at the given lat/lng
        "wind_speed_unit": "ms",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(FORECAST_URL, params=params)
            resp.raise_for_status()
        data = resp.json()
        hourly = data["hourly"]
        raw = {field: hourly[field][hour] for field in HOURLY_FIELDS}
        result = {_FIELD_MAP[k]: v for k, v in raw.items()}
        result["_timezone"] = data.get("timezone", "UTC")
        return result
    except Exception:
        return None
