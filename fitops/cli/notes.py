from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import UTC

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
)
from fitops.output.formatter import make_meta
from fitops.output.text_formatter import (
    print_note_detail,
    print_note_tags,
    print_notes_list,
)

app = typer.Typer(no_args_is_help=True)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _upsert_note(note: NoteFile) -> None:
    """Insert or update a Note DB row from a NoteFile."""

    async with get_async_session() as session:
        res = await session.execute(select(Note).where(Note.slug == note.slug))
        row = res.scalar_one_or_none()

        preview = note.body[:200].strip() if note.body else None
        tags_json = json.dumps(note.tags)
        created_at = note.created.replace(tzinfo=UTC) if note.created else None

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
    tags: str | None = typer.Option(None, "--tags", help="Comma-separated tags."),
    body: str | None = typer.Option(None, "--body", help="Note body (markdown)."),
    activity: int | None = typer.Option(
        None, "--activity", "-a", help="Link to a Strava activity ID."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Create a new note and save it to ~/.fitops/notes/."""
    init_db()

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    note_body = body or ""

    note = create_note_file(
        title=title, tags=tag_list, body=note_body, activity_id=activity
    )
    asyncio.run(_upsert_note(note))

    out = {
        "_meta": make_meta(),
        "created": {
            "slug": note.slug,
            "title": note.title,
            "tags": note.tags,
            "activity_id": note.activity_id,
            "file_path": str(note.file_path),
            "created": note.created.isoformat() if note.created else None,
        },
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2))
    else:
        typer.echo(f"Created note: {note.title}  ({note.slug}.md)")
        if note.tags:
            typer.echo(f"  Tags: {', '.join(note.tags)}")
        typer.echo(f"  File: {note.file_path}")


@app.command("list")
def list_notes(
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag."),
    activity: int | None = typer.Option(
        None, "--activity", "-a", help="Filter by activity ID."
    ),
    limit: int = typer.Option(50, "--limit", help="Max results."),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
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

    notes_data = [
        {
            "slug": n.slug,
            "title": n.title,
            "tags": n.tags,
            "activity_id": n.activity_id,
            "created": n.created.isoformat() if n.created else None,
            "body_preview": n.body[:200].strip() if n.body else "",
        }
        for n in notes
    ]

    out = {
        "_meta": make_meta(total_count=len(notes), filters_applied=filters or None),
        "notes_dir": str(notes_dir()),
        "notes": notes_data,
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2))
    else:
        print_notes_list(out)


@app.command("get")
def get_note(
    slug: str = typer.Argument(..., help="Note slug (filename without .md)."),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Display a note's full content."""
    note = get_note_file(slug)
    if note is None:
        typer.echo(f"Note '{slug}' not found. Run `fitops notes list` to see available notes.", err=True)
        raise typer.Exit(1)

    out = {
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
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2))
    else:
        print_note_detail(out)


@app.command("edit")
def edit_note(
    slug: str = typer.Argument(..., help="Note slug to edit."),
) -> None:
    """Open a note in $EDITOR, then re-sync DB."""
    note = get_note_file(slug)
    if note is None:
        typer.echo(f"Note '{slug}' not found.", err=True)
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        typer.echo(f"Set $EDITOR to edit in your preferred editor.")
        typer.echo(f"  File: {note.file_path}")
        return

    subprocess.call([editor, str(note.file_path)])

    # Re-sync after edit
    init_db()
    reloaded = get_note_file(slug)
    if reloaded:
        asyncio.run(_upsert_note(reloaded))

    typer.echo(f"Saved: {slug}")


@app.command("delete")
def delete_note(
    slug: str = typer.Argument(..., help="Note slug to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a note file and remove it from the DB index."""
    note = get_note_file(slug)
    if note is None:
        typer.echo(f"Note '{slug}' not found.", err=True)
        raise typer.Exit(1)

    if not yes:
        typer.confirm(f"Delete note '{note.title}' ({slug}.md)?", abort=True)

    init_db()
    delete_note_file(slug)
    asyncio.run(_delete_note_db(slug))

    typer.echo(f"Deleted: {slug}")


@app.command("tags")
def list_tags(
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """List all tags with usage counts."""
    notes = list_note_files()

    counts: dict[str, int] = {}
    for n in notes:
        for t in n.tags:
            counts[t] = counts.get(t, 0) + 1

    sorted_tags = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    out = {
        "_meta": make_meta(total_count=len(sorted_tags)),
        "tags": [{"tag": t, "count": c} for t, c in sorted_tags],
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2))
    else:
        print_note_tags(out)


@app.command("sync")
def sync_notes() -> None:
    """Re-index all note files into the DB (runs automatically on `list`)."""
    init_db()
    count = asyncio.run(_sync_all())
    typer.echo(f"Synced {count} notes.")
