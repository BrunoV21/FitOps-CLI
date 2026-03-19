# FitOps Agent Guidelines

## Core Philosophy: One Dataset, Two Audiences

FitOps is built on a single principle: **your fitness data is yours**, and it should be equally accessible to you and to the AI agents working on your behalf.

There are two first-class consumers of FitOps data:

| Consumer | Interface | Interaction style |
|----------|-----------|-------------------|
| **You (human)** | Dashboard (browser) | Visual exploration, charts, filters |
| **AI Agent** | CLI + JSON | Programmatic querying, analysis, automation |

Both read from the same local SQLite database (`~/.fitops/fitops.db`). Neither has privileged access. The CLI and the dashboard are two views into the same truth.

---

## The Duality Rule

> **Any new functionality added to FitOps must be accessible in both surfaces.**

If you add a new analytics feature:
- The CLI must expose it as a command that outputs structured JSON an agent can consume.
- The dashboard must expose it as a visual route a human can navigate to.

If you add it to only one surface, it is incomplete. Both surfaces should reach parity before a feature is considered done.

### What this means in practice

- A new metric (e.g., Training Stress Score) → add a CLI command **and** a dashboard chart.
- A new data source (e.g., sleep, weight) → add CLI queries **and** dashboard visualization.
- A new filter or aggregation → expose it as a CLI flag **and** a dashboard UI control.
- A new computed column → make it queryable via CLI **and** surfaced in the dashboard.

---

## Agent Interface Contract

When writing CLI commands for agent consumption, follow these conventions:

### Output format
All commands output JSON with a `_meta` block:

```json
{
  "_meta": {
    "tool": "fitops-cli",
    "version": "...",
    "generated_at": "ISO-8601 timestamp",
    "total_count": N,
    "filters_applied": {}
  },
  "<data_key>": [...]
}
```

### Field naming
- Units are explicit: `_seconds`, `_km`, `_bpm`, `_watts`
- Human-readable companions alongside raw values: `"moving_time_seconds": 3720, "moving_time_formatted": "1:02:00"`
- IDs are resolved to names where possible (gear IDs → gear names)
- `data_availability` blocks tell agents what additional detail can be fetched

### Agent-friendliness checklist
- [ ] Can an agent call this command with no interactive prompts?
- [ ] Is the output deterministic given the same inputs?
- [ ] Are all units explicit and unambiguous?
- [ ] Does the `_meta` block describe what filters were applied?
- [ ] Can the agent discover what to fetch next from `data_availability` fields?

---

## Dashboard Interface Contract

When adding dashboard routes, follow these conventions:

### Route structure
Routes live in `fitops/dashboard/routes/`. Each feature area gets its own module mirroring the CLI command hierarchy:

```
CLI:        fitops analytics training-load
Dashboard:  /analytics/training-load
```

### Human-friendliness checklist
- [ ] Does the page show a chart or table, not raw JSON?
- [ ] Are units labeled in plain language ("beats per minute", not "bpm")?
- [ ] Does the page have a period filter (7d / 30d / 90d / 1y / all)?
- [ ] Are empty states handled gracefully with a helpful message?
- [ ] Does the nav include this page so a human can discover it?

---

## Shared Business Logic

CLI routes and dashboard routes must **not** duplicate logic. All computation lives in shared modules:

```
fitops/
├── analytics/          # Shared computation (training load, zones, VO2max, trends)
├── dashboard/
│   ├── queries/        # SQL queries used by dashboard routes
│   └── routes/         # Flask route handlers (thin — call analytics/ modules)
└── cli/                # Typer command handlers (thin — call analytics/ modules)
```

A CLI command and a dashboard route that show the same metric must call the same underlying function. If you find yourself copy-pasting logic between `cli/` and `dashboard/routes/`, extract it into `analytics/`.

---

## Adding a New Feature: Checklist

1. **Implement the logic** in `fitops/analytics/` (or extend an existing module).
2. **Add a CLI command** in `fitops/cli/` that calls the logic and outputs JSON.
3. **Add a dashboard route** in `fitops/dashboard/routes/` that calls the same logic and renders an HTML template.
4. **Add a dashboard query** in `fitops/dashboard/queries/` if the route needs a SQL query.
5. **Add a template** in `fitops/dashboard/templates/` for the new page.
6. **Wire navigation** in `fitops/dashboard/templates/base.html`.
7. **Test** that the CLI output is valid JSON and the dashboard route returns HTTP 200.

---

## Why This Matters

An AI agent working on your training plan needs the same data quality and depth that you see on your dashboard. If the dashboard shows a Training Readiness score and the CLI does not, the agent is flying blind. If the CLI exposes raw streams but the dashboard does not visualize them, you are flying blind.

FitOps is a tool for human-AI collaboration over personal fitness data. That collaboration only works when both sides see the same picture.
