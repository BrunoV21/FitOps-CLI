from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fitops.db.models.note import Note
from fitops.notes.loader import NoteFile


async def get_all_notes(
    session: AsyncSession,
    tag: Optional[str] = None,
    activity_id: Optional[int] = None,
    q: Optional[str] = None,
) -> list[Note]:
    stmt = select(Note).order_by(Note.created_at.desc())
    result = await session.execute(stmt)
    notes = list(result.scalars().all())

    if tag:
        notes = [n for n in notes if tag.lower() in [t.lower() for t in n.tags_list()]]
    if activity_id:
        notes = [n for n in notes if n.activity_id == activity_id]
    if q:
        q_lower = q.lower()
        notes = [n for n in notes if q_lower in n.title.lower()]

    return notes


async def get_note_by_slug(session: AsyncSession, slug: str) -> Optional[Note]:
    result = await session.execute(select(Note).where(Note.slug == slug))
    return result.scalar_one_or_none()


async def get_all_tags(session: AsyncSession) -> list[dict]:
    """Return list of {tag, count} dicts sorted by count desc."""
    result = await session.execute(select(Note))
    notes = result.scalars().all()

    counts: dict[str, int] = {}
    for note in notes:
        for t in note.tags_list():
            counts[t] = counts.get(t, 0) + 1

    return sorted(
        [{"tag": t, "count": c} for t, c in counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )


async def upsert_note(session: AsyncSession, note: NoteFile) -> None:
    """Sync a NoteFile into the DB."""
    from datetime import timezone

    result = await session.execute(select(Note).where(Note.slug == note.slug))
    row = result.scalar_one_or_none()

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
