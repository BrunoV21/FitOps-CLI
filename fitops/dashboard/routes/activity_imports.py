from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from fitops.backup.event_sync import trigger_async
from fitops.config.settings import get_settings
from fitops.importers.activity_files import (
    MAX_ACTIVITY_FILE_BYTES,
    ActivityFileError,
    import_activity_bytes,
    suggest_activity_from_filename,
)
from fitops.output.formatter import format_activity_row
from fitops.utils.exceptions import BrowserPublicationError

router = APIRouter()


def register(templates: Jinja2Templates) -> APIRouter:
    @router.get("/activities/import", response_class=HTMLResponse)
    async def activity_import_page(request: Request):
        return templates.TemplateResponse(
            request,
            "activities/import.html",
            {
                "request": request,
                "active_page": "activities",
                "has_athlete": bool(get_settings().athlete_id),
            },
        )

    @router.get("/api/activities/import/suggestion")
    async def activity_import_suggestion(filename: str):
        return JSONResponse(suggest_activity_from_filename(filename[:512]))

    @router.post("/api/activities/import")
    async def activity_import_api(
        file: UploadFile = File(...),
        sport: str = Form("auto"),
        name: str = Form(""),
        description: str = Form(""),
        post_to_strava: bool = Form(True),
    ):
        if not get_settings().athlete_id:
            return JSONResponse(
                {
                    "error": "Create a local athlete profile before importing.",
                    "code": "athlete_required",
                },
                status_code=409,
            )
        try:
            data = await file.read(MAX_ACTIVITY_FILE_BYTES + 1)
            result = await import_activity_bytes(
                data,
                file.filename or "activity",
                sport_type=sport,
                name=name or None,
                description=description or None,
            )
        except ActivityFileError as exc:
            status_code = 413 if exc.code == "file_too_large" else 422
            return JSONResponse(
                {"error": str(exc), "code": exc.code}, status_code=status_code
            )

        activity = result.activity
        publication_payload: dict[str, object] = {
            "requested": post_to_strava,
            "status": "not_requested",
            "strava_id": activity.strava_id,
        }
        if post_to_strava and activity.strava_id is not None:
            publication_payload.update(
                {
                    "status": "already_linked",
                    "strava_id": activity.strava_id,
                }
            )
        elif post_to_strava:
            from fitops.browser.publisher import publish_activity_bytes

            try:
                publication = await publish_activity_bytes(
                    activity.id,
                    data,
                    file.filename or "activity",
                )
            except BrowserPublicationError as exc:
                publication_payload.update(
                    {
                        "status": "failed",
                        "error": str(exc),
                        "code": exc.code,
                    }
                )
            else:
                activity.strava_id = publication.strava_id
                publication_payload.update(
                    {
                        "id": publication.id,
                        "action": publication.action,
                        "status": publication.status,
                        "strava_id": publication.strava_id,
                    }
                )

        await trigger_async()
        return JSONResponse(
            {
                "activity": format_activity_row(
                    {
                        column.name: getattr(activity, column.name)
                        for column in activity.__table__.columns
                    }
                ),
                "import": {
                    "created": result.created,
                    "match_type": result.match_type,
                    "file_format": result.import_record.file_format,
                    "original_filename": result.import_record.original_filename,
                    "sha256": result.import_record.sha256,
                    "sport_inference_source": result.sport_inference_source,
                    "sport_inference_confidence": result.sport_inference_confidence,
                },
                "weather": {
                    "status": result.weather_status,
                    "data": result.weather,
                },
                "publication": publication_payload,
            },
            status_code=201 if result.created else 200,
        )

    @router.post("/api/activities/{activity_id}/sync-strava")
    @router.post("/api/activities/{activity_id}/publish", include_in_schema=False)
    async def activity_sync_strava_api(activity_id: int, strava_id: int | None = None):
        from fitops.browser.publisher import publish_activity

        if strava_id is None:
            return JSONResponse(
                {
                    "error": "Enter the existing Strava activity ID to sync.",
                    "code": "strava_id_required",
                },
                status_code=422,
            )
        try:
            result = await publish_activity(activity_id, strava_id=strava_id)
        except BrowserPublicationError as exc:
            return JSONResponse(
                {"error": str(exc), "code": exc.code}, status_code=exc.status_code
            )
        return JSONResponse(
            {
                "publication": {
                    "id": result.id,
                    "activity_id": result.activity_id,
                    "action": result.action,
                    "status": result.status,
                    "strava_id": result.strava_id,
                }
            }
        )

    return router
