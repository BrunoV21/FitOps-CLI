"""Automatic Strava webhook setup for deployed dashboards."""

from __future__ import annotations

import asyncio
import os
import secrets

from fitops.config.settings import get_settings
from fitops.strava import webhook_config as wcfg
from fitops.strava import webhook_subscription as subs
from fitops.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_CALLBACK_ENV = "FITOPS_WEBHOOK_CALLBACK_URL"
DEFAULT_SYNC_MODE_ENV = "FITOPS_DEFAULT_SYNC_MODE"


def get_default_callback_url() -> str | None:
    """Return the deployed webhook callback URL from the environment."""
    callback_url = (os.environ.get(DEFAULT_CALLBACK_ENV) or "").strip()
    return callback_url or None


def _webhook_mode_enabled() -> bool:
    mode = (os.environ.get(DEFAULT_SYNC_MODE_ENV) or "webhook").strip().lower()
    return mode == "webhook"


def _validate_callback_url(callback_url: str) -> None:
    if not callback_url.startswith("https://"):
        raise ValueError("FITOPS_WEBHOOK_CALLBACK_URL must be a public HTTPS URL.")
    if not callback_url.endswith("/api/strava/webhook"):
        raise ValueError(
            "FITOPS_WEBHOOK_CALLBACK_URL must end with /api/strava/webhook."
        )


async def ensure_default_webhook(*, delay_seconds: float = 0.0) -> dict:
    """Create or repair the default webhook subscription for deployed dashboards.

    This is a no-op unless FITOPS_WEBHOOK_CALLBACK_URL is set. It is safe to call
    during startup and after OAuth; Strava subscription calls run off the event
    loop because they use the synchronous helper API.
    """
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)

    callback_url = get_default_callback_url()
    if not callback_url:
        return {"status": "skipped", "reason": "no_default_callback_url"}
    if not _webhook_mode_enabled():
        return {"status": "skipped", "reason": "default_sync_mode_not_webhook"}

    _validate_callback_url(callback_url)

    settings = get_settings()
    settings.reload()
    if not settings.client_id or not settings.client_secret:
        return {"status": "skipped", "reason": "missing_strava_app_credentials"}

    saved_sync_mode = wcfg.get_saved_sync_mode()
    if saved_sync_mode and saved_sync_mode != "webhook":
        return {
            "status": "skipped",
            "reason": "saved_sync_mode_not_webhook",
            "sync_mode": saved_sync_mode,
        }

    cfg = wcfg.get_webhook_config() or {}
    previous_sync_mode = wcfg.get_sync_mode()
    token = cfg.get("verify_token") or secrets.token_urlsafe(24)
    existing_subscription_id = cfg.get("subscription_id")
    if (
        cfg.get("enabled")
        and cfg.get("callback_url") == callback_url
        and existing_subscription_id
        and wcfg.get_sync_mode() == "webhook"
    ):
        return {
            "status": "configured",
            "action": "already_configured",
            "callback_url": callback_url,
            "subscription_id": existing_subscription_id,
            "sync_mode": "webhook",
        }

    try:
        wcfg.save_webhook_config(
            callback_url=callback_url,
            verify_token=token,
            subscription_id=(
                int(existing_subscription_id) if existing_subscription_id else None
            ),
            enabled=True,
        )

        loop = asyncio.get_running_loop()
        remote = await loop.run_in_executor(None, subs.list_subscriptions)
        matching = next(
            (
                item
                for item in remote
                if str(item.get("callback_url") or "").rstrip("/")
                == callback_url.rstrip("/")
            ),
            None,
        )

        action = "created"
        if matching and matching.get("id") is not None:
            subscription_id = int(matching["id"])
            action = "reused_remote"
        else:
            for item in remote:
                subscription_id_raw = item.get("id")
                if subscription_id_raw is None:
                    continue
                await loop.run_in_executor(
                    None,
                    lambda sid=int(subscription_id_raw): subs.delete_subscription(sid),
                )
            subscription_id = await loop.run_in_executor(
                None, lambda: subs.create_subscription(callback_url, token)
            )
    except Exception:
        if cfg:
            wcfg.save_webhook_config(
                callback_url=cfg.get("callback_url") or callback_url,
                verify_token=cfg.get("verify_token") or token,
                subscription_id=cfg.get("subscription_id"),
                enabled=bool(cfg.get("enabled")),
                signing_secret=cfg.get("signing_secret"),
            )
            wcfg.save_sync_mode(previous_sync_mode)
        else:
            wcfg.clear_webhook_config()
            if saved_sync_mode is None:
                wcfg.clear_sync_mode()
        raise

    wcfg.update_subscription_id(subscription_id)
    wcfg.save_sync_mode("webhook")
    logger.info("webhook: default subscription %s for %s", action, callback_url)
    return {
        "status": "configured",
        "action": action,
        "callback_url": callback_url,
        "subscription_id": subscription_id,
        "sync_mode": "webhook",
    }


async def ensure_default_webhook_logged(*, delay_seconds: float = 0.0) -> dict:
    """Run default webhook setup and log failures without crashing callers."""
    try:
        return await ensure_default_webhook(delay_seconds=delay_seconds)
    except Exception as exc:
        logger.warning("webhook: default setup failed: %s", exc)
        return {"status": "failed", "error": str(exc)}
