# Output Examples — Notes

All examples show default output. Add `--json` to any command for raw JSON.

---

## `fitops notes list`

```bash
fitops notes list
```

```
  Slug                          Title                        Tags                   Date
 ───────────────────────────────────────────────────────────────────────────────────────
  hr-drift-march-2026           HR drift pattern March       pattern, aerobic        2026-03-28
  post-race-berlin              Post-race thoughts           race, review            2026-03-22
  threshold-fatigue-note        Threshold fatigue pattern    fatigue, threshold      2026-03-14
  long-run-nutrition            Long run fuelling notes      nutrition, aerobic      2026-03-01
```

With tag filter:

```bash
fitops notes list --tag fatigue
```

```
  Slug                          Title                        Tags                   Date
 ───────────────────────────────────────────────────────────────────────────────────────
  threshold-fatigue-note        Threshold fatigue pattern    fatigue, threshold      2026-03-14
```

---

## `fitops notes get <slug>`

```bash
fitops notes get threshold-fatigue-note
```

```
Threshold fatigue pattern  2026-03-14
  Tags      fatigue, threshold
  Activity  17972016511

Legs felt heavy from km 3 onward. Probably under-fueled — skipped
breakfast before the session. HR drifted +8 bpm above normal for Z4.

Next time: eat at least 90 min before threshold work.
```

---

## `fitops notes tags`

```bash
fitops notes tags
```

```
  Tag           Count
 ─────────────────────
  threshold        12
  fatigue           7
  aerobic           6
  race              3
  pattern           3
  nutrition         2
  recovery          2
```

---

## `fitops notes create`

```bash
fitops notes create --title "Hard day — legs very heavy" --tags fatigue,recovery
```

```
Created  hard-day-legs-very-heavy
  File   ~/.fitops/notes/hard-day-legs-very-heavy.md
```

With `--body` for inline content:

```bash
fitops notes create \
  --title "Post-long-run debrief" \
  --body "Ran 32 km. Felt good until km 25. Need more sodium next time." \
  --tags aerobic,nutrition \
  --activity 17985851162
```

```
Created  post-long-run-debrief
  File   ~/.fitops/notes/post-long-run-debrief.md
```

---

## JSON output (`--json`)

```bash
fitops notes list --json
```

```json
{
  "_meta": {
    "generated_at": "2026-04-06T09:15:00+00:00",
    "total_count": 4
  },
  "notes": [
    {
      "slug": "hr-drift-march-2026",
      "title": "HR drift pattern March",
      "tags": ["pattern", "aerobic"],
      "activity_id": null,
      "created_at": "2026-03-28T07:30:00"
    },
    {
      "slug": "post-race-berlin",
      "title": "Post-race thoughts",
      "tags": ["race", "review"],
      "activity_id": 17930412200,
      "created_at": "2026-03-22T18:00:00"
    }
  ]
}
```

```bash
fitops notes get threshold-fatigue-note --json
```

```json
{
  "_meta": { "generated_at": "2026-04-06T09:15:00+00:00" },
  "note": {
    "slug": "threshold-fatigue-note",
    "title": "Threshold fatigue pattern",
    "tags": ["fatigue", "threshold"],
    "activity_id": 17972016511,
    "created_at": "2026-03-14T08:30:00",
    "body": "Legs felt heavy from km 3 onward. Probably under-fueled — skipped\nbreakfast before the session. HR drifted +8 bpm above normal for Z4.\n\nNext time: eat at least 90 min before threshold work."
  }
}
```

← [Output Examples](./index.md)
