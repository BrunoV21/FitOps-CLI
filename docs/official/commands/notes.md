# fitops notes

Markdown-based training journal. Notes are plain `.md` files stored in `~/.fitops/notes/` and indexed in the local database for fast querying. They act as persistent memory across coaching sessions — yours and your agent's.

Commands print human-readable output by default. Add `--json` for raw JSON output.

## Commands

### `fitops notes create`

Create a new note and save it to `~/.fitops/notes/`.

```bash
fitops notes create --title "Post-race thoughts" [OPTIONS]
```

**Options:**

| Flag | Description |
|------|-------------|
| `--title TEXT` | Note title (required) |
| `--tags a,b,c` | Comma-separated tags |
| `--body TEXT` | Note body as inline markdown |
| `--activity ID` | Link this note to a Strava activity ID |

**Examples:**

```bash
# Quick note
fitops notes create --title "Legs heavy today" --tags fatigue,recovery

# Note linked to a specific activity
fitops notes create --title "Post-tempo debrief" --activity 12345678901 --tags threshold,quality

# Note with inline body
fitops notes create --title "Threshold session" --body "Felt strong. LT2 felt easy. Bump LTHR next week." --tags threshold
```

**Output:**

```
Created  post-race-thoughts
  File   /Users/you/.fitops/notes/post-race-thoughts.md
```

Note files are plain markdown with YAML frontmatter. You can also create them manually in any editor — run `fitops notes sync` to re-index.

---

### `fitops notes list`

List notes, newest first. Re-syncs the DB index from disk automatically.

```bash
fitops notes list [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--tag TAG` | — | Filter by a single tag |
| `--activity ID` | — | Show notes linked to a specific activity |
| `--query TEXT` / `-q` | — | Keyword search across title, body, and tags |
| `--limit N` | 50 | Max results to return |

Filters stack — you can combine `--tag`, `--query`, and `--activity` to narrow results simultaneously.

**Examples:**

```bash
fitops notes list
fitops notes list --tag fatigue
fitops notes list --activity 12345678901
fitops notes list --query "threshold"
fitops notes list --tag race --query "nutrition"
fitops notes list -q "tempo" --limit 10
```

---

### `fitops notes get <slug>`

Display the full content of a note.

```bash
fitops notes get post-race-thoughts
```

The slug is the filename without `.md` (shown in `fitops notes list` output).

**Output:**

```
Post-race thoughts  2026-03-14
  Tags     race, review
  Activity 12345678901

Felt strong in the second half...
```

---

### `fitops notes edit <slug>`

Open a note in `$EDITOR`, then re-sync the DB index.

```bash
fitops notes edit post-race-thoughts
```

If `$EDITOR` is not set, the file path is printed instead.

---

### `fitops notes delete <slug>`

Delete a note file and remove it from the DB index.

```bash
fitops notes delete post-race-thoughts

# Skip confirmation prompt
fitops notes delete post-race-thoughts --yes
```

---

### `fitops notes tags`

List all tags with usage counts.

```bash
fitops notes tags
```

**Output:**

```
  Tag         Count
 ──────────────────
  threshold      12
  fatigue         7
  race            3
```

---

### `fitops notes sync`

Re-index all note files into the DB. Runs automatically on `fitops notes list`.

```bash
fitops notes sync
```

Use this after manually creating or editing note files in `~/.fitops/notes/`.

---

## Note File Format

Notes are `.md` files with YAML frontmatter:

```markdown
---
title: Felt sluggish on intervals
tags: [fatigue, nutrition, threshold]
activity_id: 12345678       # optional — links note to a specific activity
created: 2026-03-14T08:30:00
---

Legs felt heavy from km 3 onward. Probably under-fueled — skipped
breakfast before the session. HR drifted +8 bpm above normal for Z4.
Next time eat at least 90 min before threshold work.
```

**Frontmatter fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `title` | Yes | Display name |
| `tags` | No | List of tags for filtering |
| `activity_id` | No | Strava activity ID to associate with |
| `created` | No | ISO 8601 timestamp (auto-set on creation) |

The body is freeform markdown. Files can be created and edited in any text editor — run `fitops notes sync` to re-index.

## See Also

- [`fitops activities get`](./activities.md) — activity details to reference in notes
- [Concepts → LLM Integration](../concepts/llm-integration.md) — using notes as agent memory

← [Commands Reference](./index.md)
