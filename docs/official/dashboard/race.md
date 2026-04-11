# Dashboard — Race

The Race page (`/race`) is your race planning hub. Import a course, generate a pacing plan, and simulate different race-day scenarios — all without touching the CLI.

## Course Library

The main race view lists every course you've imported. Each entry shows the course name, total distance, and elevation gain. Click a course to open its detail page.

To add a new course, click **Import Course** and upload a GPX or TCX file. FitOps reads the GPS track and elevation profile and stores it locally.

## Course Detail

Once a course is imported, its detail page shows:

- **Route map** — an interactive map of the GPS track
- **Elevation profile** — distance vs. elevation across the full course
- **Key stats** — total distance, total climb, total descent

From here you can generate a pacing plan or run a full simulation.

## Pacing Plan

Click **Generate Pacing Plan** to get a per-kilometre breakdown of your race. You'll enter:

- **Target finish time** — e.g. `3:15:00`
- **Race date & hour** — used to fetch forecast weather
- **Pacer strategy** — even splits, negative split, or a custom effort distribution

The plan output shows each kilometre with:

- Adjusted target pace (accounting for gradient and wind)
- Cumulative projected time
- Expected HR zone
- Weather adjustment factor for that section

This is the same plan `fitops race simulate` produces in the CLI.

## Race Simulation

![Race Simulation Results](../assets/dashboard-race-simulate-results.png)

The **Simulate** option lets you model different race-day scenarios. Change the target time, weather conditions, or pacer strategy and immediately see how the plan shifts. Useful for stress-testing your pacing before race day.

## See Also

- [Concepts → Race Simulation](../concepts/race-simulation.md)
- [Concepts → Weather & Pace](../concepts/weather-pace.md)
- [`fitops race`](../commands/race.md) — CLI reference

← [Dashboard Overview](./index.md)
