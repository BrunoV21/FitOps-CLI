# Strava API & Data Use

FitOps reads your activity data from Strava through Strava's public API. This page explains how FitOps's design lines up with Strava's [API Agreement](https://www.strava.com/legal/api) and the [November 2024 update](https://press.strava.com/articles/updates-to-stravas-api-agreement) — and why a personal, local-first tool sits squarely in what Strava explicitly continues to allow.

## TL;DR

FitOps is a **single-user, local-only** tool. You connect with your **own Strava API app** under your **own Strava account**, and your data flows from Strava → your machine. Nothing is published, nothing is shared, nothing is used to train models, nothing is sold. The exact pattern Strava's announcement called out as remaining allowed: *"coaching platforms focused on providing feedback to users and tools that help users understand their data and performance."*

## How FitOps Maps to the Agreement

| Strava requirement | How FitOps complies |
|---|---|
| **Display data only to the user it belongs to.** | FitOps runs entirely on your machine. Your activities are only ever shown to you, in your own terminal or your own browser at `localhost:8888`. There is no FitOps server, no shared feed, no public surface. |
| **No use of Strava data for AI / ML model training.** | FitOps does not train any model. When you use FitOps with an AI assistant (Claude Code, Cursor, etc.), the assistant **reads** your data through the CLI to give you feedback — that's inference, not training. You choose the assistant; FitOps never ships your data anywhere on its own. |
| **No public sharing or third-party redistribution of data.** | FitOps has no upload path, no telemetry, no analytics pipeline, no cloud sync (cloud backup, when enabled, writes to **your** Drive / OneDrive / GitHub repo — never to a FitOps service). |
| **Cross-user / aggregate analytics are prohibited.** | FitOps is single-user by design. There is no cross-athlete aggregation anywhere in the codebase. The "analytics" in the name refers to **your** training metrics — CTL/ATL/TSB, VO2max, zones — computed from **your** activities, displayed to **you**. |
| **Personal coaching insights are explicitly allowed.** | This is exactly what FitOps does: training-load tracking, zone analysis, weather-adjusted pace, race simulation — all classic personal coaching feedback, locally computed. |
| **You authenticate with your own API credentials.** | The setup flow asks you to create your own Strava API application. You are the API-app owner; Strava's developer terms apply to you directly. FitOps is the local tool you use to work with the data Strava has agreed to send you. |

## What "Local-First" Really Means Here

Every byte of activity data lives in `~/.fitops/` on your machine:

```
~/.fitops/
├── config.json      # your Strava credentials (client id, refresh token)
├── fitops.db        # SQLite — all activities, streams, analytics
├── workouts/        # your workout markdown
└── notes/           # your training notes
```

There is no FitOps account. There are no FitOps servers. The project ships a CLI and a local web UI; both bind to `localhost`. If you delete `~/.fitops/`, FitOps no longer has any of your data, instantly.

## AI Agent Integration — Why It's Not "AI Training"

Strava's prohibition is on **using Strava data to train artificial intelligence or machine learning models**. FitOps's agent integration does the opposite:

- The agent (Claude, Cursor, etc.) is a pre-trained model the user already chose.
- The agent calls `fitops` CLI commands and receives JSON.
- The agent **reads** that JSON to answer the user's questions about their own training.
- Nothing is sent back upstream to train anything.

This is exactly the same shape as a coach reading a TrainingPeaks dashboard and giving you feedback — the model is the coach, your data is the input it considers in this one conversation, and Strava's announcement explicitly preserves this pattern.

## What You Should Know

A few practical points so there are no surprises:

- **You bring your own Strava API app.** Each FitOps user creates one through `strava.com/settings/api`. Strava's "Single Player Mode" defaults to a 1-athlete cap, which is exactly what FitOps needs.
- **Rate limits are Strava's, not ours.** 200 requests / 15 min and 2,000 / day. The sync engine batches and respects these.
- **You control retention.** Activities are stored locally for as long as you keep them. Removing the local database removes all of it.
- **Your LLM choice is yours.** If you point an agent at FitOps, the data leaving your machine is whatever you choose to put in your prompts — a decision that lives between you and your LLM provider, not FitOps.

## References

- [Strava API Agreement](https://www.strava.com/legal/api)
- [Updates to Strava's API Agreement (Nov 2024)](https://press.strava.com/articles/updates-to-stravas-api-agreement)
- [API Agreement Update — Strava Support](https://support.strava.com/hc/en-us/articles/31798729397773-API-Agreement-Update-How-Data-Appears-on-3rd-Party-Apps)
- [Strava API Rate Limits](https://developers.strava.com/docs/rate-limits/)

---

← [Back to Concepts](./index.md)
