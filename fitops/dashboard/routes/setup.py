from __future__ import annotations

import secrets

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from fitops.config.settings import get_settings
from fitops.strava.oauth import STRAVA_AUTH_URL, DEFAULT_SCOPES, StravaOAuth
from urllib.parse import urlencode

router = APIRouter()


async def _initial_sync() -> None:
    """Run a full sync after first-time login."""
    try:
        from fitops.strava.sync_engine import SyncEngine
        engine = SyncEngine()
        await engine.run(full=True)
    except Exception:
        pass


def register(templates: Jinja2Templates) -> APIRouter:
    @router.get("/setup", response_class=HTMLResponse)
    async def setup_page(request: Request, connected: str = ""):
        settings = get_settings()
        if settings.is_authenticated and not connected:
            return RedirectResponse("/")
        return templates.TemplateResponse(
            request,
            "setup.html",
            {
                "request": request,
                "has_credentials": bool(settings.client_id and settings.client_secret),
                "connected": connected == "1",
            },
        )

    @router.post("/api/setup/credentials")
    async def save_credentials(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        client_id = (payload.get("client_id") or "").strip()
        client_secret = (payload.get("client_secret") or "").strip()
        if not client_id or not client_secret:
            return JSONResponse({"error": "client_id and client_secret are required"}, status_code=400)

        settings = get_settings()
        settings.save_credentials(client_id, client_secret)
        settings.reload()

        port = getattr(request.app.state, "dashboard_port", 8888)
        state = secrets.token_urlsafe(32)
        settings.save_pending_state(state)

        redirect_uri = f"http://localhost:{port}/callback"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": ",".join(DEFAULT_SCOPES),
            "state": state,
            "approval_prompt": "auto",
        }
        auth_url = f"{STRAVA_AUTH_URL}?{urlencode(params)}"
        return JSONResponse({"auth_url": auth_url})

    @router.get("/callback")
    async def oauth_callback(request: Request, background_tasks: BackgroundTasks, code: str = "", state: str = "", error: str = ""):
        if error:
            return RedirectResponse(f"/setup?error={error}")

        if not code:
            return RedirectResponse("/setup?error=no_code")

        settings = get_settings()
        expected_state = settings.pop_pending_state()
        if expected_state and state != expected_state:
            return RedirectResponse("/setup?error=state_mismatch")

        port = getattr(request.app.state, "dashboard_port", 8888)
        try:
            oauth = StravaOAuth(settings)
            token_data = await oauth.exchange_code_for_token(code, port=port)
            settings.save_tokens(token_data)
            background_tasks.add_task(_initial_sync)
        except Exception as e:
            return RedirectResponse(f"/setup?error=token_exchange")

        return RedirectResponse("/setup?connected=1")

    @router.get("/api/setup/status")
    async def setup_status():
        settings = get_settings()
        if not settings.is_authenticated:
            return JSONResponse({"authenticated": False, "has_activities": False})

        from sqlalchemy import func, select
        from fitops.db.models.activity import Activity
        from fitops.db.session import get_async_session

        async with get_async_session() as session:
            count = (await session.execute(
                select(func.count()).select_from(Activity).where(Activity.athlete_id == settings.athlete_id)
            )).scalar_one()

        return JSONResponse({"authenticated": True, "has_activities": count > 0, "activity_count": count})

    return router
