"""Config helpers for Strava webhook sync."""

from __future__ import annotations

import json
from pathlib import Path

VALID_SYNC_MODES = {"webhook", "polling", "manual"}


def _config_path() -> Path:
    import os

    env = os.environ.get("FITOPS_DIR")
    base = Path(env).expanduser() if env else Path.home() / ".fitops"
    return base / "config.json"


def _load() -> dict:
    path = _config_path()
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _save(data: dict) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get_webhook_config() -> dict | None:
    return _load().get("strava", {}).get("webhook")


def save_webhook_config(
    *,
    callback_url: str,
    verify_token: str,
    subscription_id: int | None = None,
    enabled: bool = True,
    signing_secret: str | None = None,
) -> dict:
    data = _load()
    existing = data.setdefault("strava", {}).get("webhook", {})
    config = {
        "callback_url": callback_url,
        "verify_token": verify_token,
        "subscription_id": subscription_id
        if subscription_id is not None
        else existing.get("subscription_id"),
        "enabled": enabled,
    }
    if signing_secret or existing.get("signing_secret"):
        config["signing_secret"] = signing_secret or existing.get("signing_secret")
    data["strava"]["webhook"] = config
    _save(data)
    return config


def update_subscription_id(subscription_id: int | None) -> None:
    data = _load()
    webhook = data.setdefault("strava", {}).setdefault("webhook", {})
    webhook["subscription_id"] = subscription_id
    _save(data)


def clear_webhook_config() -> None:
    data = _load()
    data.get("strava", {}).pop("webhook", None)
    if get_sync_mode_from_data(data) == "webhook":
        data.setdefault("sync", {})["mode"] = "polling"
    _save(data)


def get_sync_mode_from_data(data: dict) -> str:
    mode = data.get("sync", {}).get("mode")
    if mode in VALID_SYNC_MODES:
        return mode
    webhook = data.get("strava", {}).get("webhook")
    if webhook and webhook.get("enabled"):
        return "webhook"
    return "polling"


def get_sync_mode() -> str:
    return get_sync_mode_from_data(_load())


def save_sync_mode(mode: str) -> None:
    if mode not in VALID_SYNC_MODES:
        raise ValueError(
            f"sync mode must be one of: {', '.join(sorted(VALID_SYNC_MODES))}"
        )
    data = _load()
    data.setdefault("sync", {})["mode"] = mode
    _save(data)
