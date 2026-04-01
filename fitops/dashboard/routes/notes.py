from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete as sa_delete, select

from fitops.db.migrations import create_all_tables
from fitops.db.models.note import Note
from fitops.db.session import get_async_session
from fitops.dashboard.queries.notes import get_all_notes, get_all_tags, upsert_note
from fitops.notes.loader import (
    create_note_file,
    delete_note_file,
    get_note_file,
    list_note_files,
    update_note_file,
)

router = APIRouter()


async def _sync_db_from_disk() -> None:
    """Re-index all note files into the DB, removing orphan rows."""
    notes = list_note_files()
    slugs_on_disk = {n.slug for n in notes}

    async with get_async_session() as session:
        for note in notes:
            await upsert_note(session, note)
        result = await session.execute(select(Note))
        for row in result.scalars().all():
            if row.slug not in slugs_on_disk:
                await session.delete(row)


def register(templates: Jinja2Templates) -> APIRouter:

    @router.get("/notes", response_class=HTMLResponse)
    async def notes_list(
        request: Request,
        tag: str = "",
        activity_id: str = "",
        q: str = "",
    ):
        await create_all_tables()
        await _sync_db_from_disk()

        act_id = int(activity_id) if activity_id.strip().isdigit() else None

        async with get_async_session() as session:
            notes = await get_all_notes(
                session,
                tag=tag or None,
                activity_id=act_id,
                q=q or None,
            )
            all_tags = await get_all_tags(session)

        rows = [
            {
                "slug": n.slug,
                "title": n.title,
                "tags": n.tags_list(),
                "activity_id": n.activity_id,
                "body_preview": n.body_preview or "",
                "created_at": n.created_at.strftime("%d %b %Y") if n.created_at else "—",
            }
            for n in notes
        ]

        return templates.TemplateResponse(
            request,
            "notes/list.html",
            {
                "request": request,
                "notes": rows,
                "all_tags": all_tags,
                "active_tag": tag,
                "active_q": q,
                "active_page": "notes",
            },
        )

    @router.get("/notes/create", response_class=HTMLResponse)
    async def notes_create_form(request: Request):
        return templates.TemplateResponse(
            request,
            "notes/create.html",
            {"request": request, "note": None, "active_page": "notes"},
        )

    @router.post("/notes/create")
    async def notes_create_submit(
        request: Request,
        title: str = Form(...),
        tags: str = Form(""),
        body: str = Form(""),
        activity_id: str = Form(""),
    ):
        await create_all_tables()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        act_id = int(activity_id) if activity_id.strip().isdigit() else None

        note = create_note_file(title=title, tags=tag_list, body=body, activity_id=act_id)

        async with get_async_session() as session:
            await upsert_note(session, note)

        return RedirectResponse(url=f"/notes/{note.slug}", status_code=303)

    @router.get("/notes/{slug}/edit", response_class=HTMLResponse)
    async def notes_edit_form(request: Request, slug: str):
        note = get_note_file(slug)
        if note is None:
            return templates.TemplateResponse(
                request,
                "notes/detail.html",
                {"request": request, "note": None, "active_page": "notes"},
                status_code=404,
            )

        return templates.TemplateResponse(
            request,
            "notes/create.html",
            {
                "request": request,
                "note": {
                    "slug": note.slug,
                    "title": note.title,
                    "tags": ", ".join(note.tags),
                    "body": note.body,
                    "activity_id": note.activity_id or "",
                },
                "active_page": "notes",
            },
        )

    @router.post("/notes/{slug}/edit")
    async def notes_edit_submit(
        request: Request,
        slug: str,
        title: str = Form(...),
        tags: str = Form(""),
        body: str = Form(""),
        activity_id: str = Form(""),
    ):
        await create_all_tables()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        act_id = int(activity_id) if activity_id.strip().isdigit() else None

        note = update_note_file(slug=slug, title=title, tags=tag_list, body=body, activity_id=act_id)
        if note is None:
            return RedirectResponse(url="/notes", status_code=303)

        async with get_async_session() as session:
            await upsert_note(session, note)

        return RedirectResponse(url=f"/notes/{slug}", status_code=303)

    @router.post("/notes/{slug}/delete")
    async def notes_delete(request: Request, slug: str):
        await create_all_tables()
        delete_note_file(slug)

        async with get_async_session() as session:
            await session.execute(sa_delete(Note).where(Note.slug == slug))

        return RedirectResponse(url="/notes", status_code=303)

    @router.get("/notes/{slug}", response_class=HTMLResponse)
    async def notes_detail(request: Request, slug: str):
        note = get_note_file(slug)
        if note is None:
            return templates.TemplateResponse(
                request,
                "notes/detail.html",
                {"request": request, "note": None, "active_page": "notes"},
                status_code=404,
            )

        linked_activity = None
        if note.activity_id:
            from fitops.db.models.activity import Activity
            async with get_async_session() as session:
                res = await session.execute(
                    select(Activity).where(Activity.strava_id == note.activity_id)
                )
                act = res.scalar_one_or_none()
                if act:
                    linked_activity = {
                        "strava_id": act.strava_id,
                        "name": act.name,
                        "date": act.start_date_local.strftime("%d %b %Y") if act.start_date_local else "—",
                        "sport_type": act.sport_type,
                        "distance_km": round(act.distance_m / 1000, 2) if act.distance_m else None,
                    }

        return templates.TemplateResponse(
            request,
            "notes/detail.html",
            {
                "request": request,
                "note": {
                    "slug": note.slug,
                    "title": note.title,
                    "tags": note.tags,
                    "activity_id": note.activity_id,
                    "created": note.created.strftime("%d %b %Y, %H:%M") if note.created else "—",
                    "body": note.body,
                },
                "linked_activity": linked_activity,
                "active_page": "notes",
            },
        )

    return router
