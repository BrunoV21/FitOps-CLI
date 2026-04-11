from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Wet Bulb Temperature (Stull 2011)
# ---------------------------------------------------------------------------


def wet_bulb_temp(temp_c: float, rh_pct: float) -> float:
    """Stull (2011), accurate ±0.35°C for 5–99% RH."""
    T, RH = temp_c, rh_pct
    return (
        T * math.atan(0.151977 * (RH + 8.313659) ** 0.5)
        + math.atan(T + RH)
        - math.atan(RH - 1.676331)
        + 0.00391838 * RH**1.5 * math.atan(0.023101 * RH)
        - 4.686035
    )


# ---------------------------------------------------------------------------
# WBGT approximation (shade, no solar radiation)
# ---------------------------------------------------------------------------


def wbgt_approx(temp_c: float, rh_pct: float) -> float:
    """WBGT ≈ 0.7*Tw + 0.3*Td (shade, no direct solar radiation)."""
    return 0.7 * wet_bulb_temp(temp_c, rh_pct) + 0.3 * temp_c


# ---------------------------------------------------------------------------
# Pace heat/humidity factor (Ely et al. 2007 / ACSM guidelines)
# ---------------------------------------------------------------------------


def pace_heat_factor(temp_c: float, rh_pct: float) -> float:
    """
    Pace multiplier due to heat/humidity. 1.0 = no penalty.
    Uses WBGT piecewise from Ely et al. (2007) / ACSM guidelines.
    """
    wbgt = wbgt_approx(temp_c, rh_pct)
    if wbgt < 10:
        return 1.0
    elif wbgt < 18:
        return 1.0 + 0.002 * (wbgt - 10)  # 0–1.6%
    elif wbgt < 23:
        return 1.016 + 0.006 * (wbgt - 18)  # 1.6–4.6%
    elif wbgt < 28:
        return 1.046 + 0.014 * (wbgt - 23)  # 4.6–11.6%
    else:
        return 1.116 + 0.020 * (wbgt - 28)  # steepest


# ---------------------------------------------------------------------------
# GPS bearing
# ---------------------------------------------------------------------------


def compute_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing (degrees, 0=N clockwise) from (lat1,lon1) to (lat2,lon2)."""
    dlng = math.radians(lon2 - lon1)
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    x = math.sin(dlng) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(
        lat2_r
    ) * math.cos(dlng)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# ---------------------------------------------------------------------------
# Headwind component
# ---------------------------------------------------------------------------


def headwind_ms(
    wind_speed_ms: float, wind_dir_deg: float, course_bearing_deg: float
) -> float:
    """
    Headwind component in m/s (positive = into runner's face).
    wind_dir_deg: meteorological FROM direction.
    course_bearing_deg: direction athlete runs TOWARD.
    """
    wind_toward = (wind_dir_deg + 180) % 360
    wu = wind_speed_ms * math.sin(math.radians(wind_toward))
    wv = wind_speed_ms * math.cos(math.radians(wind_toward))
    ru = math.sin(math.radians(course_bearing_deg))
    rv = math.cos(math.radians(course_bearing_deg))
    return -(wu * ru + wv * rv)  # negative dot → headwind positive


# ---------------------------------------------------------------------------
# Wind pace factor (Pugh 1971)
# ---------------------------------------------------------------------------


def pace_wind_factor(headwind_ms_val: float) -> float:
    """
    Pace multiplier from wind. Headwind > 0 = slower, tailwind < 0 = faster.
    Calibrated to Pugh (1971) empirical data:
      6.4 km/h (1.78 m/s) headwind → ~4% penalty
      12.9 km/h (3.58 m/s) headwind → ~8% penalty
      19.3 km/h (5.36 m/s) headwind → ~16% penalty
    Tailwind benefit is ~55% of headwind cost (aerodynamic asymmetry, Pugh 1971).
    """
    if headwind_ms_val >= 0:
        penalty = 0.006 * headwind_ms_val**2
    else:
        penalty = -0.0033 * abs(headwind_ms_val) ** 2  # 55% of headwind cost
    return max(0.85, min(1.25, 1.0 + penalty))


# ---------------------------------------------------------------------------
# VO2max heat factor (Sawka / Kenefick)
# ---------------------------------------------------------------------------


def vo2max_heat_factor(temp_c: float, rh_pct: float) -> float:
    """VO2max multiplier. 1.0 = full capacity, 0.90 = 10% reduced."""
    if temp_c <= 10:
        return 1.0
    wbgt = wbgt_approx(temp_c, rh_pct)
    reduction = min(0.25, max(0.0, 0.010 * (wbgt - 10)))
    return 1.0 - reduction


# ---------------------------------------------------------------------------
# Combined WAP factor
# ---------------------------------------------------------------------------


def compute_wap_factor(
    temp_c: float,
    rh_pct: float,
    wind_speed_ms_val: float,
    wind_dir_deg: float,
    course_bearing: float | None,
) -> float:
    """
    Combined weather adjustment factor for pace.
    WAP = actual_pace_s_per_km / wap_factor
    wap_factor > 1 means conditions were hard (adjusted pace is faster).
    """
    heat = pace_heat_factor(temp_c, rh_pct)
    wind = 1.0
    if course_bearing is not None:
        hw = headwind_ms(wind_speed_ms_val, wind_dir_deg, course_bearing)
        wind = pace_wind_factor(hw)
    return heat * wind


# ---------------------------------------------------------------------------
# Wind direction — degrees → compass label
# ---------------------------------------------------------------------------

_COMPASS_16 = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
]


def deg_to_compass(deg: float) -> str:
    """Convert meteorological wind-from direction (degrees) to 16-point compass label."""
    idx = round(deg / 22.5) % 16
    return _COMPASS_16[idx]


# ---------------------------------------------------------------------------
# WMO weather code labels
# ---------------------------------------------------------------------------

_WMO_LABELS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light showers",
    81: "Showers",
    82: "Heavy showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm w/ hail",
    99: "Thunderstorm w/ heavy hail",
}


def weather_condition_label(weather_code: int) -> str:
    """Map WMO weather interpretation code to human-readable label."""
    return _WMO_LABELS.get(weather_code, f"Code {weather_code}")


# ---------------------------------------------------------------------------
# WBGT flag (heat stress category)
# ---------------------------------------------------------------------------


def wbgt_flag(wbgt: float) -> str:
    """Return WBGT heat stress flag color."""
    if wbgt < 10:
        return "green"
    elif wbgt < 23:
        return "yellow"
    elif wbgt < 28:
        return "red"
    else:
        return "black"


def weather_row_to_dict(w) -> dict:
    """Convert an ActivityWeather ORM row to a plain dict for CLI/dashboard use."""
    wbgt = w.wbgt_c
    wcode = w.weather_code
    return {
        "temperature_c": w.temperature_c,
        "apparent_temp_c": w.apparent_temp_c,
        "humidity_pct": w.humidity_pct,
        "wind_speed_ms": w.wind_speed_ms,
        "wind_speed_kmh": round(w.wind_speed_ms * 3.6, 1)
        if w.wind_speed_ms is not None
        else None,
        "wind_direction_deg": w.wind_direction_deg,
        "wind_dir_compass": deg_to_compass(w.wind_direction_deg)
        if w.wind_direction_deg is not None
        else None,
        "precipitation_mm": w.precipitation_mm,
        "wbgt_c": wbgt,
        "wbgt_flag": wbgt_flag(wbgt) if wbgt is not None else "green",
        "pace_heat_factor": w.pace_heat_factor,
        "source": w.source,
        "condition": weather_condition_label(wcode) if wcode is not None else None,
        "temp_fmt": f"{round(w.temperature_c)}°C"
        if w.temperature_c is not None
        else None,
    }
