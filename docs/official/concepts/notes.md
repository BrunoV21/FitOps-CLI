# Training Notes

FitOps includes a Markdown-based training journal. Notes are plain `.md` files on your local machine — queryable via the CLI, browsable in the dashboard, and designed to serve as persistent memory across coaching sessions.

---

## What Notes Are For

A training log captures what the data can't. CTL and TSB tell you how loaded you are — they don't tell you that your left calf felt tight on km 3, that you under-fuelled before the threshold session, or that the race felt harder than the numbers suggest because of travel stress the night before.

Notes are where that context lives. Because they're linked to specific activities, tagged, and indexed locally, you (or an AI assistant) can query them later:

```bash
fitops notes list --tag fatigue         # all notes tagged fatigue
fitops notes list --activity 12345678901  # notes linked to a specific run
```

---

## Note File Format

Notes are `.md` files in `~/.fitops/notes/` with YAML frontmatter:

```markdown
---
title: Felt sluggish on intervals
tags: [fatigue, nutrition, threshold]
activity_id: 12345678901
created: 2026-03-14T08:30:00
---

Legs felt heavy from km 3 onward. Probably under-fuelled — skipped
breakfast before the session. HR drifted +8 bpm above normal for Z4.
Next time eat at least 90 min before threshold work.
```

| Field | Required | Description |
|-------|----------|-------------|
| `title` | Yes | Display name |
| `tags` | No | List of tags for filtering |
| `activity_id` | No | Strava activity ID — links this note to a specific activity |
| `created` | No | ISO 8601 timestamp (auto-set on creation) |

The body is freeform Markdown. You can write notes in any editor and run `fitops notes sync` to re-index them into the local database.

---

## Creating Notes

```bash
# Quick note
fitops notes create --title "Legs heavy today" --tags fatigue,recovery

# Note linked to a specific activity
fitops notes create --title "Post-tempo debrief" --activity 12345678901 --tags threshold,quality

# Note with inline body
fitops notes create --title "Threshold session" \
  --body "Felt strong. LT2 felt easy. Bump LTHR next week." \
  --tags threshold
```

Notes can also be created manually as `.md` files in `~/.fitops/notes/` — run `fitops notes sync` to pick them up.

---

## Querying Notes

```bash
fitops notes list                    # all notes, newest first
fitops notes list --tag threshold    # filter by tag
fitops notes list --activity <id>    # linked to a specific activity
fitops notes get post-tempo-debrief  # full content of one note
fitops notes tags                    # all tags with usage counts
```

Tags give you a lightweight taxonomy for your journal. Common patterns:
- `fatigue`, `recovery` — flag load management observations
- `threshold`, `vo2max`, `easy` — label session type
- `race`, `review` — mark race-day and post-event reflections
- `nutrition`, `sleep`, `illness` — track lifestyle factors affecting training

---

## Notes as Agent Memory

Because notes are plain files with a queryable index, an AI assistant running FitOps commands can use them as **persistent memory across sessions**:

- After analysing your training, the agent writes an observation as a note
- In a future session, the agent reads recent notes before making recommendations
- Patterns spotted across weeks (e.g. HR drift worsening under fatigue, recurring tightness before threshold sessions) survive across conversations

```bash
# Agent writes an observation
fitops notes create --title "HR drift pattern — March 2026" \
  --body "Decoupling consistently >10% when TSB < -15. Likely aerobic ceiling." \
  --tags pattern,aerobic,hr-drift

# Future session — agent recalls context before advising
fitops notes list --tag pattern
fitops notes get hr-drift-pattern-march-2026
```

This is fundamentally different from an AI assistant relying on its own context window — the notes exist on your machine, survive indefinitely, and are readable by any tool or agent that has access to `fitops notes`.

---

## Commands

```bash
fitops notes create --title "..." [--tags a,b] [--body "..."] [--activity ID]
fitops notes list [--tag TAG] [--activity ID] [--limit N]
fitops notes get <slug>
fitops notes edit <slug>          # open in $EDITOR, then re-sync DB
fitops notes delete <slug>
fitops notes tags
fitops notes sync                 # re-index files into DB after manual edits
```

See [Commands → notes](../commands/notes.md) for the full reference.

← [Concepts](./index.md)
