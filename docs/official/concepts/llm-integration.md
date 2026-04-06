# LLM Integration Guide

FitOps-CLI is designed as a data source for AI-assisted training analysis. Every command outputs structured JSON with explicit units, human-readable labels, and a `_meta` block that gives the AI context.

## The Design Philosophy

An AI model can't interpret `"distance": 10234` without knowing the unit. FitOps solves this by being explicit:

```json
"distance": {
  "meters": 10234.0,
  "km": 10.23,
  "miles": 6.35
}
```

The same principle applies to pace, time, heart rate, and analytics values — every number carries its unit and, where relevant, a human-readable label.

## Feeding FitOps Output to an AI

Pipe output directly into your prompt context:

```bash
fitops activities list --sport Run --limit 5 | pbcopy
```

Or combine multiple commands:

```bash
echo "=== Training Load ===" && fitops analytics training-load --today
echo "=== VO2max ===" && fitops analytics vo2max
echo "=== Recent runs ===" && fitops activities list --sport Run --limit 10
```

Paste the combined output into your AI assistant with a prompt like:

> "Based on this training data, am I ready to race this weekend? What does my CTL trend suggest about fitness?"

## Structured Questions FitOps Enables

Because the data is consistent and labeled, an AI can answer:

- "What was my average pace on long runs last month?"
- "Is my ramp rate too high — am I at injury risk?"
- "How does my VO2max trend over the last 6 months compare to peak season?"
- "Which shoes have the most mileage?"
- "Show me my HR zone distribution for all rides this year."

## `_meta` Block

Every response includes a `_meta` object so an AI knows when the data was generated and what filters were applied:

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "total_count": 10,
    "filters_applied": {
      "sport_type": "Run",
      "limit": 10
    }
  }
}
```

## Form Labels and Ramp Labels

Training load and zone outputs include text labels alongside numbers:

```json
"form_label": "Productive — slight fatigue, good adaptation zone"
"ramp_label": "Moderate build"
```

These labels make it easy for an AI to reason about training state without needing to implement its own thresholds.

## Automation

For AI agents that poll your training state:

```bash
# Daily snapshot — saves to DB for trending
fitops analytics snapshot

# Query current state
fitops analytics training-load --today
fitops analytics vo2max
fitops analytics zones
```

The `snapshot` command is idempotent per day — safe to run multiple times.

← [Concepts](./README.md)
