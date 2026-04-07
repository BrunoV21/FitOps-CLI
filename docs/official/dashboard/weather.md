# Dashboard — Weather

The Weather page (`/weather`) answers the question: *"What's the weather on race day, and how should I adjust my pace?"*

## What the Page Shows

Enter a location (or let FitOps default to your most recent GPS activity's coordinates) and a date and hour, and the page returns:

| Data | Description |
|------|-------------|
| Temperature | Air temperature (°C) |
| Apparent temperature | Feels-like temperature accounting for wind and humidity |
| Humidity | Relative humidity (%) |
| Precipitation | Expected rainfall (mm) |
| Wind speed & direction | km/h, with compass direction |
| Condition | Plain-language label (Clear, Cloudy, Rain, Storm, …) |
| WBGT | Wet Bulb Globe Temperature — a composite heat stress index |
| Heat flag | Green / Yellow / Orange / Red based on WBGT thresholds |
| Pace heat factor | A multiplier showing how much to add to your target pace in these conditions |

## Using the Pace Heat Factor

The pace heat factor tells you by how much to slow your target pace to maintain the same physiological effort. For example, a factor of `1.04` means your easy-day 5:00/km becomes a 5:12/km effort.

The same factor is used in [Race simulations](./race.md) when a future race date is entered — so your pacing plan automatically accounts for forecast conditions.

## Where the Data Comes From

Weather is sourced from the Open-Meteo API (no API key required). Historical weather uses the archive endpoint; forecasts use the regular forecast endpoint. FitOps caches results locally so repeated queries for the same location and date don't hit the network.

## See Also

- [Overview](./overview.md) — today's weather widget uses the same data
- [Race](./race.md) — weather is factored into race pacing plans
- [Concepts → Weather & Pace](../concepts/weather-pace.md)
- [`fitops weather`](../commands/weather.md) — CLI reference

← [Dashboard Overview](./index.md)
