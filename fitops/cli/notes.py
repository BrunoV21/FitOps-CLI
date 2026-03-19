from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from typing import Optional

import typer
from sqlalchemy import delete, select

from fitops.db.migrations import init_db
from fitops.db.models.note import Note
from fitops.db.session import get_async_session
from fitops.notes.loader import (
    NoteFile,
    create_note_file,
    delete_note_file,
    get_note_file,
    list_note_files,
    notes_dir,
    update_note_file,
)
from fitops.output.formatter import make_meta

app = typer.Typer(no_args_is_help=True)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _upsert_note(note: NoteFile) -> None:
    """Insert or update a Note DB row from a NoteFile."""
    from datetime import timezone

    async with get_async_session() as session:
        res = await session.execute(select(Note).where(Note.slug == note.slug))
        row = res.scalar_one_or_none()

        preview = note.body[:200].strip() if note.body else None
        tags_json = json.dumps(note.tags)
        created_at = note.created.replace(tzinfo=timezone.utc) if note.created else None

        if row:
            row.title = note.title
            row.tags = tags_json
            row.activity_id = note.activity_id
            row.body_preview = preview
        else:
            row = Note(
                slug=note.slug,
                title=note.title,
                tags=tags_json,
                activity_id=note.activity_id,
                body_preview=preview,
                created_at=created_at,
            )
            session.add(row)


async def _delete_note_db(slug: str) -> None:
    async with get_async_session() as session:
        await session.execute(delete(Note).where(Note.slug == slug))


async def _sync_all() -> int:
    """Re-index all note files into DB. Returns count synced."""
    notes = list_note_files()
    slugs_on_disk = {n.slug for n in notes}

    for note in notes:
        await _upsert_note(note)

    # Remove DB rows with no corresponding file
    async with get_async_session() as session:
        res = await session.execute(select(Note))
        db_rows = res.scalars().all()
        for row in db_rows:
            if row.slug not in slugs_on_disk:
                await session.delete(row)

    return len(notes)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command("create")
def create_note(
    title: str = typer.Option(..., "--title", "-t", help="Note title."),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags."),
    body: Optional[str] = typer.Option(None, "--body", help="Note body (markdown)."),
    activity: Optional[int] = typer.Option(None, "--activity", "-a", help="Link to a Strava activity ID."),
) -> None:
    """Create a new note and save it to ~/.fitops/notes/."""
    init_db()

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    note_body = body or ""

    note = create_note_file(title=title, tags=tag_list, body=note_body, activity_id=activity)
    asyncio.run(_upsert_note(note))

    typer.echo(
        json.dumps(
            {
                "_meta": make_meta(),
                "created": {
                    "slug": note.slug,
                    "title": note.title,
                    "tags": note.tags,
                    "activity_id": note.activity_id,
                    "file_path": str(note.file_path),
                    "created": note.created.isoformat() if note.created else None,
                },
            },
            indent=2,
        )
    )


@app.command("list")
def list_notes(
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag."),
    activity: Optional[int] = typer.Option(None, "--activity", "-a", help="Filter by activity ID."),
    limit: int = typer.Option(50, "--limit", help="Max results."),
) -> None:
    """List notes, newest first. Re-syncs DB index from disk."""
    init_db()

    notes = list_note_files()

    # Re-sync DB in background
    asyncio.run(_sync_all())

    # Apply filters
    if tag:
        notes = [n for n in notes if tag.lower() in [t.lower() for t in n.tags]]
    if activity:
        notes = [n for n in notes if n.activity_id == activity]

    notes = notes[:limit]

    filters: dict = {}
    if tag:
        filters["tag"] = tag
    if activity:
        filters["activity_id"] = activity

    typer.echo(
        json.dumps(
            {
                "_meta": make_meta(total_count=len(notes), filters_applied=filters or None),
                "notes_dir": str(notes_dir()),
                "notes": [
                    {
                        "slug": n.slug,
                        "title": n.title,
                        "tags": n.tags,
                        "activity_id": n.activity_id,
                        "created": n.created.isoformat() if n.created else None,
                        "body_preview": n.body[:200].strip() if n.body else "",
                    }
                    for n in notes
                ],
            },
            indent=2,
        )
    )


@app.command("get")
def get_note(
    slug: str = typer.Argument(..., help="Note slug (filename without .md)."),
) -> None:
    """Display a note's full content."""
    note = get_note_file(slug)
    if note is None:
        typer.echo(
            json.dumps(
                {"error": f"Note '{slug}' not found.", "hint": "Run `fitops notes list` to see available notes."},
                indent=2,
            )
        )
        raise typer.Exit(1)

    typer.echo(
        json.dumps(
            {
                "_meta": make_meta(),
                "note": {
                    "slug": note.slug,
                    "title": note.title,
                    "tags": note.tags,
                    "activity_id": note.activity_id,
                    "created": note.created.isoformat() if note.created else None,
                    "body": note.body,
                    "file_path": str(note.file_path),
                },
            },
            indent=2,
        )
    )


@app.command("edit")
def edit_note(
    slug: str = typer.Argument(..., help="Note slug to edit."),
) -> None:
    """Open a note in $EDITOR, then re-sync DB."""
    note = get_note_file(slug)
    if note is None:
        typer.echo(json.dumps({"error": f"Note '{slug}' not found."}, indent=2))
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        typer.echo(
            json.dumps(
                {
                    "hint": f"Set $EDITOR env var to edit in your preferred editor.",
                    "file_path": str(note.file_path),
                },
                indent=2,
            )
        )
        return

    subprocess.call([editor, str(note.file_path)])

    # Re-sync after edit
    init_db()
    reloaded = get_note_file(slug)
    if reloaded:
        asyncio.run(_upsert_note(reloaded))

    typer.echo(json.dumps({"_meta": make_meta(), "edited": slug}, indent=2))


@app.command("delete")
def delete_note(
    slug: str = typer.Argument(..., help="Note slug to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a note file and remove it from the DB index."""
    note = get_note_file(slug)
    if note is None:
        typer.echo(json.dumps({"error": f"Note '{slug}' not found."}, indent=2))
        raise typer.Exit(1)

    if not yes:
        typer.confirm(f"Delete note '{note.title}' ({slug}.md)?", abort=True)

    init_db()
    delete_note_file(slug)
    asyncio.run(_delete_note_db(slug))

    typer.echo(json.dumps({"_meta": make_meta(), "deleted": slug}, indent=2))


@app.command("tags")
def list_tags() -> None:
    """List all tags with usage counts."""
    notes = list_note_files()

    counts: dict[str, int] = {}
    for n in notes:
        for t in n.tags:
            counts[t] = counts.get(t, 0) + 1

    sorted_tags = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    typer.echo(
        json.dumps(
            {
                "_meta": make_meta(total_count=len(sorted_tags)),
                "tags": [{"tag": t, "count": c} for t, c in sorted_tags],
            },
            indent=2,
        )
    )


@app.command("sync")
def sync_notes() -> None:
    """Re-index all note files into the DB (runs automatically on `list`)."""
    init_db()
    count = asyncio.run(_sync_all())
    typer.echo(json.dumps({"_meta": make_meta(), "synced": count}, indent=2))
