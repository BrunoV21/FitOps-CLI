from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fitops.config.settings import get_settings


def notes_dir() -> Path:
    """Return ~/.fitops/notes/, creating it if needed."""
    d = get_settings().fitops_dir / "notes"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Frontmatter parser (no PyYAML dependency)
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text

    rest = text[3:]
    match = re.search(r"\n---[ \t]*(\n|$)", rest)
    if not match:
        return {}, text

    fm_text = rest[: match.start()].strip()
    body = rest[match.end() :].strip()

    meta: dict[str, Any] = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, raw_val = line.partition(":")
        key = key.strip()
        val = raw_val.strip()

        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            items = [x.strip().strip("\"'") for x in inner.split(",") if x.strip()]
            meta[key] = items
        elif re.match(r"^-?\d+$", val):
            meta[key] = int(val)
        elif re.match(r"^-?\d+\.\d+$", val):
            meta[key] = float(val)
        elif val.lower() in ("true", "yes"):
            meta[key] = True
        elif val.lower() in ("false", "no"):
            meta[key] = False
        else:
            meta[key] = val

    return meta, body


def _title_to_slug(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug or "note"


def _parse_created(val: Any) -> datetime | None:
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# NoteFile dataclass
# ---------------------------------------------------------------------------


@dataclass
class NoteFile:
    """A note loaded from a .md file in ~/.fitops/notes/."""

    slug: str
    file_name: str
    file_path: Path
    title: str
    tags: list[str] = field(default_factory=list)
    activity_id: int | None = None
    created: datetime | None = None
    body: str = ""
    raw: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_note_file(path: Path) -> NoteFile:
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    slug = path.stem
    return NoteFile(
        slug=slug,
        file_name=path.name,
        file_path=path,
        title=meta.get("title") or slug.replace("-", " ").title(),
        tags=meta.get("tags", []),
        activity_id=meta.get("activity_id"),
        created=_parse_created(meta.get("created")),
        body=body,
        raw=raw,
    )


def list_note_files() -> list[NoteFile]:
    """Return all .md note files, newest first."""
    notes = [load_note_file(f) for f in notes_dir().glob("*.md")]
    notes.sort(key=lambda n: n.created or datetime.min, reverse=True)
    return notes


def get_note_file(slug: str) -> NoteFile | None:
    """Find a note by slug (filename stem)."""
    path = notes_dir() / f"{slug}.md"
    if path.exists():
        return load_note_file(path)
    return None


def create_note_file(
    title: str,
    tags: list[str],
    body: str,
    activity_id: int | None = None,
    slug: str | None = None,
) -> NoteFile:
    """Write a new note .md file and return the loaded NoteFile."""
    if not slug:
        slug = _title_to_slug(title)

    d = notes_dir()
    # Avoid collisions
    base_slug = slug
    counter = 1
    while (d / f"{slug}.md").exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    created_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    tags_str = "[" + ", ".join(tags) + "]" if tags else "[]"
    activity_line = f"activity_id: {activity_id}\n" if activity_id else ""

    markdown = (
        f"---\n"
        f"title: {title}\n"
        f"tags: {tags_str}\n"
        f"{activity_line}"
        f"created: {created_str}\n"
        f"---\n\n"
        f"{body}"
    )

    path = d / f"{slug}.md"
    path.write_text(markdown, encoding="utf-8")
    return load_note_file(path)


def update_note_file(
    slug: str,
    title: str,
    tags: list[str],
    body: str,
    activity_id: int | None = None,
) -> NoteFile | None:
    """Overwrite an existing note file preserving the original created timestamp."""
    existing = get_note_file(slug)
    if existing is None:
        return None

    created_str = (
        existing.created.strftime("%Y-%m-%dT%H:%M:%S")
        if existing.created
        else datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    )
    tags_str = "[" + ", ".join(tags) + "]" if tags else "[]"
    activity_line = f"activity_id: {activity_id}\n" if activity_id else ""

    markdown = (
        f"---\n"
        f"title: {title}\n"
        f"tags: {tags_str}\n"
        f"{activity_line}"
        f"created: {created_str}\n"
        f"---\n\n"
        f"{body}"
    )
    existing.file_path.write_text(markdown, encoding="utf-8")
    return load_note_file(existing.file_path)


def delete_note_file(slug: str) -> bool:
    """Delete a note file. Returns True if deleted, False if not found."""
    path = notes_dir() / f"{slug}.md"
    if path.exists():
        path.unlink()
        return True
    return False
