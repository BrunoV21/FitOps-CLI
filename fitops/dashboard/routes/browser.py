from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from fitops.browser.description import append_activity_description
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

    return router
