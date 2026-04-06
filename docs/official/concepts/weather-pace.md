# Weather & Pace Adjustment

FitOps normalises your running pace for environmental conditions — heat, humidity, and wind — to make your efforts comparable across different days and courses.

---

## WBGT — Wet Bulb Globe Temperature

**WBGT** (Wet Bulb Globe Temperature) is the standard physiological heat stress index used in athletics and military settings. It captures the combined effect of temperature and humidity better than either alone.

FitOps uses the **Stull (2011)** approximation for shade conditions (no direct solar radiation):

```
WBGT ≈ 0.7 × Tw + 0.3 × Td
```

Where:
- `Td` = dry-bulb temperature (°C) — what a regular thermometer reads
- `Tw` = wet-bulb temperature (°C) — computed via the Stull (2011) empirical formula, accurate to ±0.35°C for 5–99% relative humidity

### Heat stress categories (WBGT flags)

| Flag | WBGT range | Meaning |
|------|-----------|---------|
| `green` | < 10°C | No heat stress |
| `yellow` | 10–22°C | Moderate — pace will be slightly affected |
| `red` | 23–27°C | High — significant pace penalty |
| `black` | ≥ 28°C | Extreme — race cancellation threshold in many events |

---

## Pace Heat Factor

The pace heat factor quantifies how much slower you run due to heat and humidity. A factor of `1.10` means conditions were hard enough that your actual pace was ~10% slower than it would have been in neutral weather.

FitOps uses a **piecewise WBGT model** calibrated from Ely et al. (2007) and ACSM guidelines:

| WBGT range | Penalty model | Max penalty at upper bound |
|-----------|---------------|--------------------------|
| < 10°C | None (factor = 1.0) | 0% |
| 10–18°C | 0.2% per °C above 10 | 1.6% |
| 18–23°C | 0.6% per °C above 18 | 4.6% |
| 23–28°C | 1.4% per °C above 23 | 11.6% |
| > 28°C | 2.0% per °C above 28 | Steepest |

**Example:** WBGT 28°C → pace_heat_factor ≈ 1.116 → approximately 10% pace penalty.

---

## VO2max Heat Factor

Heat also reduces your aerobic capacity, not just your pace. The **VO2max heat factor** estimates this capacity reduction using the Sawka/Kenefick model:

```
reduction = min(25%, max(0%, 1% × (WBGT − 10)))
vo2max_heat_factor = 1.0 − reduction
```

- At WBGT 10°C or below: no reduction (factor = 1.0)
- At WBGT 35°C: ~25% capacity reduction (factor = 0.75)

This factor appears in the `fitops weather show` and `fitops weather forecast` outputs. It is also used when computing VO2max estimates to adjust for conditions during the effort.

---

## Wind Physics

FitOps models wind using **Pugh (1971)** empirical running data, which found that headwind and tailwind effects are asymmetric: **headwind costs more energy than tailwind saves**.

### Headwind component

Wind direction in weather data is reported as the direction the wind comes **from** (meteorological convention). FitOps resolves the component of wind that the runner faces given a course bearing:

- A southerly wind (from 180°) is a headwind if you're running north (bearing 0°)
- The same wind is a tailwind if you're running south (bearing 180°)
- Cross-winds have a partial headwind component

### Pace wind factor

| Condition | Penalty model |
|-----------|---------------|
| Headwind (> 0 m/s) | `0.006 × headwind²` (steeper at higher speeds) |
| Tailwind (< 0 m/s) | `0.0033 × tailwind²` (55% of headwind cost) |

The asymmetry reflects aerodynamic reality: a 5 m/s headwind (~18 km/h) costs roughly 15% in pace, while the same tailwind saves only ~8%. The factor is clamped to [0.85, 1.25].

**Wind compass:** FitOps uses a 16-point compass (N, NNE, NE, ENE, E, ESE, SE, SSE, S, SSW, SW, WSW, W, WNW, NW, NNW), each covering 22.5° of arc.

---

## WAP — Weather-Adjusted Pace

**WAP** (Weather-Adjusted Pace) removes the combined effect of heat, humidity, and wind from your actual pace:

```
wap_factor = pace_heat_factor × pace_wind_factor
WAP = actual_pace_s_per_km / wap_factor
```

A `wap_factor` greater than 1.0 means conditions were harder than neutral — WAP will be faster than your actual pace.

**Example:** You ran 5:12/km in 28°C heat with a headwind. `wap_factor = 1.12`. WAP = 5:12 / 1.12 ≈ 4:39/km. That's your equivalent effort in neutral conditions.

WAP appears in `fitops weather show` output. If course bearing is not recorded (point-to-point GPS not available), wind correction is omitted and only heat/humidity are factored in.

---

## True Pace

**True Pace** normalises for both **gradient** (via GAP — Grade-Adjusted Pace) and **weather** (via WAP):

```
True Pace = GAP adjusted for weather
```

In practice, True Pace is computed from the activity stream by:

1. Computing GAP per GPS point (removes uphill/downhill effort)
2. Applying the WAP factor for the activity conditions (removes heat and wind)

The result is a pace metric that reflects your physiological effort independent of terrain and weather — making pace zones, LT2 inference, and cross-activity comparisons more accurate.

### Pace preference hierarchy

When FitOps computes pace zones or infers LT2, it uses the best available pace signal:

1. **True Pace** — if activity streams and weather data are available *(most accurate)*
2. **GAP** — if streams are available but weather is missing
3. **Raw pace** — fallback if neither streams nor weather are available

For hilly or windy courses, using raw pace can significantly distort zone assignments and LT2 estimates. Fetching streams and weather unlocks the full accuracy of the model.

---

## Where it appears

| Feature | Uses weather adjustment |
|---------|------------------------|
| `fitops weather show <id>` | WAP, actual pace, WAP factor, VO2max heat factor |
| `fitops weather forecast` | Forecast pace heat factor, WAP factor, headwind, VO2max heat factor |
| Activity detail stream chart | True Pace series overlaid on the HR/pace chart |
| `fitops analytics pace-zones` | True Pace preferred over GAP preferred over raw |
| LT2 inference | Uses True Pace from streams if available |
| Dashboard | Today's weather and WAP factor on the overview card |

---

## References

- Stull R. (2011). Wet-Bulb Temperature from Relative Humidity and Air Temperature. *Journal of Applied Meteorology and Climatology.*
- Ely M.R. et al. (2007). Impact of weather on marathon-running performance. *Medicine & Science in Sports & Exercise.*
- Sawka M.N., Kenefick R.W. (2012). Physiological adaptations to heat and humidity. *Journal of Experimental Biology.*
- Pugh L.G.C.E. (1971). The influence of wind resistance in running. *Journal of Physiology.*

← [Concepts](./README.md)
