from __future__ import annotations

import asyncio
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from fitops.strava import webhook_config as wcfg
from fitops.strava import webhook_subscription as subs
from fitops.strava import webhooks

router = APIRouter()


def register() -> APIRouter:
    @router.get("/api/strava/webhook")
    async def verify_webhook(request: Request):
        try:
            body = webhooks.verify_challenge(
                request.query_params.get("hub.verify_token"),
                request.query_params.get("hub.challenge"),
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=403)
        return JSONResponse(body)

    @router.post("/api/strava/webhook")
    async def receive_webhook(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        asyncio.create_task(webhooks.process_webhook_payload(payload))
        return JSONResponse({"ok": True, "status": "queued"})

    @router.get("/api/strava/webhook/status")
    async def webhook_status():
        cfg = wcfg.get_webhook_config()
        events = await webhooks.recent_events(limit=10)
        remote: list[dict] | None = None
        remote_error: str | None = None
        try:
            remote = await asyncio.get_event_loop().run_in_executor(
                None, subs.list_subscriptions
            )
        except Exception as exc:
            remote_error = str(exc)
        return JSONResponse(
            {
                "configured": bool(cfg),
                "enabled": bool((cfg or {}).get("enabled")),
                "callback_url": (cfg or {}).get("callback_url"),
                "subscription_id": (cfg or {}).get("subscription_id"),
                "sync_mode": wcfg.get_sync_mode(),
                "remote_subscriptions": remote,
                "remote_error": remote_error,
                "recent_events": events,
            }
        )

    @router.post("/api/strava/webhook/setup")
    async def setup_webhook(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        callback_url = (payload.get("callback_url") or "").strip()
        verify_token = (
            payload.get("verify_token") or ""
        ).strip() or secrets.token_urlsafe(24)
        if not callback_url:
            return JSONResponse({"error": "callback_url is required"}, status_code=400)
        if len(callback_url) > 255:
            return JSONResponse(
                {"error": "callback_url must be 255 characters or fewer"},
                status_code=400,
            )

        wcfg.save_webhook_config(
            callback_url=callback_url,
            verify_token=verify_token,
            enabled=True,
        )
        try:
            subscription_id = await asyncio.get_event_loop().run_in_executor(
                None, lambda: subs.create_subscription(callback_url, verify_token)
            )
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        wcfg.update_subscription_id(subscription_id)
        wcfg.save_sync_mode("webhook")
        return JSONResponse(
            {
                "ok": True,
                "callback_url": callback_url,
                "subscription_id": subscription_id,
                "sync_mode": "webhook",
            }
        )

    @router.delete("/api/strava/webhook/subscription")
    async def delete_webhook_subscription():
        cfg = wcfg.get_webhook_config()
        subscription_id = (cfg or {}).get("subscription_id")
        if subscription_id:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: subs.delete_subscription(int(subscription_id))
                )
            except Exception as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)
        wcfg.clear_webhook_config()
        return JSONResponse({"ok": True, "sync_mode": wcfg.get_sync_mode()})

    @router.post("/api/strava/webhook/sync-mode")
    async def save_sync_mode(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        mode = (payload.get("mode") or "").strip()
        try:
            wcfg.save_sync_mode(mode)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "sync_mode": mode})

    return router
