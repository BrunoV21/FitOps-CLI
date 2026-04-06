# Concepts

The training science and design decisions behind FitOps analytics.

FitOps isn't just a data viewer — it applies established sports science models to your Strava data locally. This section explains what those models are, how FitOps implements them, and why they matter for understanding your training.

## Topics

| Topic | What it covers |
|-------|-------------|
| [Training Load](./training-load.md) | CTL, ATL, TSB — the fitness/fatigue/form model and how to read it |
| [Zones](./zones.md) | Heart rate zone methods (LTHR, max HR, Karvonen) and how FitOps computes and infers them |
| [VO2max](./vo2max.md) | VO2max estimation from run performance — three-formula composite methodology |
| [Weather & Pace](./weather-pace.md) | GAP (grade-adjusted pace), WAP (weather-adjusted pace), and True Pace |
| [Workouts & Compliance](./workouts.md) | Markdown workout definitions, segment scoring, and simulation on a course |
| [Race Simulation](./race-simulation.md) | Per-km pacing plans adjusted for elevation, weather, and strategy |
| [Training Notes](./notes.md) | Markdown training journal, activity linking, tags, and agent memory |
| [AI Agent Integration](./llm-integration.md) | Using FitOps with AI assistants, scripting, and persistent agent memory |

## The Core Ideas

**Training load (CTL/ATL/TSB)** is the foundation of structured training. CTL is your long-term fitness — how much work your body has adapted to. ATL is your short-term fatigue. TSB (form) is the difference — positive means fresh, deeply negative means overreached. FitOps computes these from every synced activity and surfaces them in plain language at the terminal.

**Zones** are only as accurate as the thresholds behind them. FitOps supports three calculation methods (LTHR, max HR, Karvonen/HRR) and can automatically infer your LTHR and max HR from rolling-window HR analysis across all your cached stream data — no lab test required.

**Weather-adjusted pace** is unique to FitOps. Running the same route at 30°C and 80% humidity is a fundamentally different physiological effort than running it at 12°C. WAP applies a physics-based model (Pugh 1971 wind drag, WBGT heat stress) to normalise pace across conditions — making month-to-month comparisons and VO2max trending far more reliable.

**True Pace** combines both GAP and WAP adjustments into a single effort-normalised metric. This is what FitOps uses for LT2 inference and long-term performance trending.

**Workouts and compliance scoring** let you define structured sessions in plain Markdown and measure how well you executed them. Each `##` heading in a workout file becomes a scoreable segment mapped against your actual HR stream. The compliance formula weights time-in-zone and average deviation from target to give each segment a 0–1 score.

**Race simulation** applies the GAP and WAP models to a full course. Import a GPX file, set a target time, and FitOps produces a per-km split plan accounting for every climb, descent, headwind, and heat penalty along the route.

**Training notes** are plain Markdown files that serve as your coaching journal. Linked to activities, tagged for filtering, and queryable by CLI — they give both you and any AI assistant persistent, structured context that survives across sessions.

## Why Local?

All analytics run against your local `~/.fitops/fitops.db`. There's no cloud service computing your TSB — it's calculated on-device from your own data, using open formulas you can read in this documentation. You own the inputs and the outputs.

← [Back to Docs Home](../index.md)
