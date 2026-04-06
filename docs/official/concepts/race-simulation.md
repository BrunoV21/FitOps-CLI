# Race Simulation

FitOps generates per-kilometre pacing plans for a race course, adjusted for elevation gradient, temperature, humidity, and wind. You can simulate a target time with an even, negative, or positive split strategy — or model a pacer strategy where you break from the pacer at a specific kilometre.

---

## How It Works

### 1. Import a Course

A race course is a sequence of GPS points. FitOps segments it into 1km bins and computes the elevation delta and average gradient for each.

```bash
fitops race import berlin-marathon.gpx --name "Berlin Marathon 2026"
fitops race import course.tcx --name "Local 10K"
fitops race import --activity 12345678901 --name "My Race Course"  # from Strava activity
```

Courses are stored locally. Each gets an ID you use with the simulation commands.

### 2. The Grade-Adjusted Pace (GAP) Model

For each kilometre, FitOps computes a **grade factor** — how much the gradient affects your pace relative to flat:

- Uphills slow you down (higher pace factor)
- Downhills speed you up, but with diminishing returns beyond ~5% gradient (your quads can only absorb so much)
- The model uses empirically calibrated multipliers per gradient range

This is the same GAP model used in activity analysis. On a hilly course, the simulation will show slower target paces on climbs and faster paces on descents — same effort, different pace.

### 3. The Weather-Adjusted Pace (WAP) Model

For each kilometre, FitOps applies a **weather factor** accounting for:

- **Heat and humidity** — via WBGT (Wet Bulb Globe Temperature). A hot humid segment gets a penalty on top of the elevation adjustment.
- **Wind** — headwind vs tailwind per segment, based on the course bearing at that point and the wind direction. Headwinds cost more than tailwinds save (Pugh 1971 asymmetry).

Weather can be provided manually (`--temp`, `--humidity`, `--wind`) or auto-fetched from Open-Meteo using a date and race start hour.

See [Weather & Pace](./weather-pace.md) for the full WAP and GAP models.

### 4. Pacing Strategy

Given a target time (or target pace), FitOps distributes effort across all kilometres adjusted by their combined GAP+WAP factor.

**Even** (default): constant effort output — faster on downhills, slower on uphills, but equal power throughout. The most reliable strategy for most runners.

**Negative**: start slightly conservative, finish strong. FitOps reserves ~2% of energy for the second half. Useful when the second half of a course is easier than the first.

**Positive**: start faster, manage a slowdown in the back half. Useful when the course front-loads climbs — you can bank time early on the flat before the major climb.

### 5. Pacer Mode

If you plan to run with a pacing group before making your own move:

```bash
fitops race simulate 1 --target-time 3:05:00 --pacer-pace 4:40 --drop-at-km 35
```

FitOps runs the simulation in two phases:
1. **Pacer phase (km 1 to drop point):** locked to the pacer's pace, ignoring elevation/weather — you run exactly what the pacer runs
2. **Solo phase (drop point to finish):** FitOps calculates the exact pace required to hit your target finish time given the remaining distance and course profile

The output shows when the pace shift happens and what your required effort becomes after you drop the group.

---

## Course Profile

```bash
fitops race course 1
```

Shows the full per-km segment table: distance, elevation delta, gradient %, and cumulative distance. Useful for identifying where the major climbs and descents are and planning your pacing strategy accordingly.

---

## Weather Auto-Fetch

When `--date` is provided and the course has GPS coordinates, FitOps fetches weather from Open-Meteo automatically — no API key required:

- **Future date** (within 16 days): Open-Meteo forecast API
- **Past date**: Open-Meteo historical archive

Manual `--temp` + `--humidity` always override auto-fetched weather. If the fetch fails, FitOps uses neutral conditions (15°C, 40% RH, no wind) and prints a warning.

---

## Example Output

```
Berlin Marathon 2026  —  Simulation  target 3:15:00  strategy: even

  km   Elev    Grade    GAP×    WAP×    Target Pace   Split    Elapsed
 ──────────────────────────────────────────────────────────────────────
   1   +8 m    +0.8%    1.04    1.00    4:42/km       4:42     0:04:42
   2   -3 m    -0.3%    0.98    1.00    4:33/km       4:33     0:09:15
   3   +0 m     0.0%    1.00    1.02    4:38/km       4:38     0:13:53
  ...
  42   -12 m   -1.2%    0.96    1.00    4:28/km       4:28     3:14:55

  Predicted finish   3:14:55   avg pace 4:37/km
```

---

## Commands

```bash
fitops race import <file_or_activity> --name "Name"   # import course
fitops race courses                                    # list all courses
fitops race course <id>                                # course profile
fitops race splits <id> --target-time 3:15:00          # quick even-split table
fitops race simulate <id> --target-time 3:15:00        # full simulation
fitops race simulate <id> --target-time 3:05:00 --pacer-pace 4:40 --drop-at-km 35
fitops race simulate <id> --target-time 3:15:00 --date 2026-10-25 --hour 9
fitops race delete <id>                                # remove course
```

See [Commands → race](../commands/race.md) for the full option reference.

← [Concepts](./index.md)
