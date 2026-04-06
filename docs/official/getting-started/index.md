# Getting Started

## What is FitOps?

FitOps is a local-first training analytics tool for runners and cyclists who want to understand their data — not just log it.

Most fitness platforms give you a dashboard you scroll through. FitOps gives you a **CLI you can talk to**, a **local browser dashboard** you control, and the ability to connect an AI agent directly to your training history. Everything runs on your machine. No subscriptions. No cloud. Your data never leaves `~/.fitops/`.

```
You (human)  →  Dashboard (browser)  ─┐
                                       ├─  ~/.fitops/fitops.db
AI Agent     →  CLI (Rich + JSON)    ─┘
```

Sync your Strava activities once, then explore them however you like — visually in the browser or by asking questions at the terminal.

---

## The Problem FitOps Solves

Training platforms like TrainingPeaks and Intervals.icu are great web apps, but they have a shared set of limitations:

- **Your data lives in their cloud.** You can't query it programmatically, pipe it into a script, or let an AI agent read it without an expensive API.
- **Strava has sold user location data** to third parties and published private coaching notes without consent. The "free" version hides analytics behind a premium paywall.
- **No weather context.** A 4:50/km run on a 30°C humid day is a very different effort from the same pace on a 10°C morning. No platform adjusts for this except FitOps.
- **Race simulation is shallow.** Pace calculators exist, but nothing adjusts splits per-kilometre for actual elevation, headwind, and heat on race day.

FitOps is built around the principle that **your training data should be yours to query, in any way you want, locally.**

---

## What Makes FitOps Different

| | FitOps | TrainingPeaks | Intervals.icu | Strava |
|---|---|---|---|---|
| **Price** | Free | ~$135/yr | Free | ~$132/yr |
| **Open source** | ✅ | ❌ | ❌ | ❌ |
| **Local / offline** | ✅ | ❌ | ❌ | ❌ |
| **Data ownership** | ✅ Your machine | ❌ | ❌ | ❌ Sold to 3rd parties |
| **Open API / scripting** | ✅ Native CLI | ❌ | ✅ documented | ✅ rate-limited |
| **LLM / AI agent native** | ✅ Designed for it | ❌ | ⚡ via API | ❌ |
| **Training load (CTL/ATL/TSB)** | ✅ | ✅ | ✅ | ⚡ premium |
| **VO2max estimation** | ✅ 3-formula composite | ❌ | ✅ | ⚡ premium |
| **Workout compliance scoring** | ✅ per-segment | ✅ premium | ✅ | ❌ |
| **Race simulation (per-km splits)** | ✅ full engine | ⚡ pace calc | ❌ | ❌ |
| **Weather-adjusted pace (WAP)** | ✅ | ❌ | ❌ | ❌ |
| **Workout simulation on course** | ✅ | ❌ | ❌ | ❌ |

**Unique to FitOps:**

- **Weather-Adjusted Pace (WAP)** — per-activity historical weather from Open-Meteo (no API key), WBGT heat stress model, Pugh 1971 wind drag. Makes a hot run directly comparable to a cool one.
- **True Pace** — a single effort-normalised metric combining GAP (grade) and WAP (weather), enabling cross-season VO2max trending without noise.
- **Race simulation engine** — per-km split plan adjusted for actual elevation, temperature, humidity, and wind. Supports pacer strategy and forecast weather for race day.
- **Workout simulation on course** — simulate how a structured workout plays out on a GPX course with terrain and weather per segment.
- **AI-native design** — the dashboard and CLI are two views into the same SQLite database. An agent can query anything a human can see, and vice versa.

---

## Setup Steps

1. [Installation](./installation.md) — Install FitOps (pip or uvx)
2. [Authentication](./authentication.md) — Connect your Strava account
3. [First Sync](./first-sync.md) — Download your activities

---

## After Setup

Once you've synced, here's where to start:

```bash
fitops activities list                    # your recent activities as a table
fitops analytics training-load --today    # current CTL, ATL, TSB, form
fitops analytics zones --infer            # detect your HR zones from stream data
fitops dashboard serve                    # open the browser dashboard
```

- [`fitops activities list`](../commands/activities.md) — Browse and filter activities
- [`fitops analytics training-load`](../commands/analytics.md) — Fitness, fatigue, form
- [`fitops analytics zones`](../commands/analytics.md) — Configure your HR zones
- [`fitops athlete profile`](../commands/athlete.md) — Profile, gear, and stats

← [Back to Docs Home](../index.md)
