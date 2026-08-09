from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from fitops.browser.description import append_activity_description
from fitops.importers.activity_files import MAX_ACTIVITY_FILE_BYTES
from fitops.output.formatter import make_meta
from fitops.utils.exceptions import BrowserPublicationError

router = APIRouter()


class DescriptionAppendRequest(BaseModel):
    activity_id: int
    text: str
    dry_run: bool = False
    headless: bool = True


def register() -> APIRouter:
    @router.post("/api/browser/append-description")
    async def append_description(payload: DescriptionAppendRequest):
        filters = {
            "activity_id": payload.activity_id,
            "dry_run": payload.dry_run,
            "headless": payload.headless,
            "backend": "auto",
        }
        try:
            result = await asyncio.to_thread(
                append_activity_description,
                payload.activity_id,
                payload.text,
                dry_run=payload.dry_run,
                headless=payload.headless,
                backend="auto",
            )
        except BrowserPublicationError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "_meta": make_meta(total_count=0, filters_applied=filters),
                    "error": {"code": exc.code, "message": str(exc)},
                },
            )
        return {
            "_meta": make_meta(total_count=1, filters_applied=filters),
            "description_update": result.to_dict(),
        }

    @router.post("/api/browser/upload-activity")
    async def upload_activity(
        file: UploadFile = File(...),
        title: str = Form(...),
        description: str = Form(""),
        sport_type: str = Form(...),
        gear: str = Form(""),
    ):
        from fitops.browser.upload import upload_activity_file

        file_name = Path(file.filename or "activity").name
        filters = {
            "file_name": file_name,
            "sport_type": sport_type,
            "gear": gear or None,
            "headless": True,
            "backend": "auto",
        }
        data = await file.read(MAX_ACTIVITY_FILE_BYTES + 1)
        if len(data) > MAX_ACTIVITY_FILE_BYTES:
            exc = BrowserPublicationError(
                f"Activity files must be no larger than "
                f"{MAX_ACTIVITY_FILE_BYTES // (1024 * 1024)} MiB.",
                code="upload_file_too_large",
                status_code=413,
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "_meta": make_meta(total_count=0, filters_applied=filters),
                    "error": {"code": exc.code, "message": str(exc)},
                },
            )

        try:
            with tempfile.TemporaryDirectory(prefix="fitops-browser-upload-") as temp:
                source = Path(temp) / file_name
                await asyncio.to_thread(source.write_bytes, data)
                result = await asyncio.to_thread(
                    upload_activity_file,
                    source,
                    title=title,
                    description=description,
                    sport_type=sport_type,
                    gear=gear or None,
                    headless=True,
                    backend="auto",
                )
        except BrowserPublicationError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "_meta": make_meta(total_count=0, filters_applied=filters),
                    "error": {"code": exc.code, "message": str(exc)},
                },
            )
        return {
            "_meta": make_meta(total_count=1, filters_applied=filters),
            "activity_upload": result.to_dict(),
        }

    return router
