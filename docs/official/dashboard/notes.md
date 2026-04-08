# Dashboard — Notes

The Notes page (`/notes`) is your training journal. Write Markdown entries, tag them, link them to activities, and browse your log over time — all from the browser.

## Notes List

The main view shows all your journal entries, newest first. Each note card displays:

- **Title** — the note heading
- **Date** — when it was written
- **Tags** — labels you added (e.g. `race-week`, `injury`, `long-run`)
- **Preview** — the first few lines of the note body

Use the search bar or tag filter to find specific entries.

## Writing a Note

Click **New Note** to open the editor. Fill in:

- **Title** — a short label for the entry
- **Tags** — comma-separated, for later filtering
- **Body** — written in Markdown; `fenced_code` blocks and line breaks are rendered

Notes are saved as `.md` files in `~/.fitops/notes/` on your filesystem, so they're plain text and portable. The dashboard keeps an index of them in the local database for fast search and filtering.

## Editing & Deleting

Open any note from the list to read it in rendered Markdown. Use the **Edit** button to update the title, tags, or body. Use **Delete** to remove the note (this also deletes the file from disk).

## Linking Notes to Activities

Notes can be linked to Strava activities via the CLI:

```bash
fitops notes link <slug> <activity_id>
```

Linked activities appear in the note detail view. This is useful for capturing post-run reflections attached to a specific session.

## See Also

- [Concepts → Training Notes](../concepts/notes.md)
- [`fitops notes`](../commands/notes.md) — CLI reference

← [Dashboard Overview](./index.md)
