# Dashboard

The FitOps Dashboard is a local web interface that makes your training data visual and interactive. Everything the CLI can tell you — your activity history, fitness metrics, race plans, workouts, journal, and backups — is available here in a browser, served entirely from your own machine.

## Starting the Dashboard

```bash
fitops dashboard serve
```

Your browser opens automatically at `http://localhost:8888`. The dashboard is ready to use as soon as it's running — no login, no account, no cloud.

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--port PORT` | `8888` | Change the port if 8888 is taken |
| `--host HOST` | `127.0.0.1` | Bind to a different interface (e.g. `0.0.0.0` to access from other devices on your network) |
| `--no-open` | false | Start the server without opening a browser tab |

## Installation

The dashboard needs one extra install step:

```bash
pip install 'fitops-cli[dashboard]'
```

After that, `fitops dashboard serve` will work.

## First Use

If you haven't connected Strava yet, the dashboard opens a **Setup** screen where you can paste your Strava API credentials and authorise access. Once connected, a sync kicks off automatically and you land on your Overview.

If you've already authenticated via the CLI, the dashboard picks up your credentials and opens directly on your training summary.

## What's Available

| Page | What you do there |
|------|------------------|
| [Overview](./overview.md) | See your week/month/year at a glance — stats, recent activities, fitness state, and today's weather |
| [Activities](./activities.md) | Browse, filter, and search your full activity history |
| [Analytics](./analytics.md) | Explore your training load over time and detailed performance metrics |
| [Workouts](./workouts.md) | Build structured workouts, simulate them on a course, and review past sessions |
| [Race](./race.md) | Import a GPX course, generate a pacing plan, and run a race simulation |
| [Notes](./notes.md) | Write and browse your training journal entries |
| [Weather](./weather.md) | Check race-day weather and see how it should adjust your target pace |
| [Profile](./profile.md) | Set your physiology (LTHR, max HR, VO2max, pace zones) and view your zone breakdowns |
| [Backup](./backup.md) | Back up your data to GitHub, restore a previous backup, or set a schedule |

← [Back to Docs Home](../index.md)
