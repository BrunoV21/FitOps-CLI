"""Strava push subscription API helpers."""

from __future__ import annotations

import httpx

from fitops.config.settings import get_settings

PUSH_SUBSCRIPTIONS_URL = "https://www.strava.com/api/v3/push_subscriptions"


def _credentials() -> tuple[str, str]:
    settings = get_settings()
    if not settings.client_id or not settings.client_secret:
        raise ValueError("Strava client_id and client_secret are required.")
    return str(settings.client_id), str(settings.client_secret)


def create_subscription(callback_url: str, verify_token: str) -> int:
    client_id, client_secret = _credentials()
    with httpx.Client(timeout=3.0) as client:
        response = client.post(
            PUSH_SUBSCRIPTIONS_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "callback_url": callback_url,
                "verify_token": verify_token,
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Strava subscription create failed: {response.text[:300]}")
    payload = response.json()
    try:
        return int(payload["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Strava subscription response missing id: {payload}") from exc


def list_subscriptions() -> list[dict]:
    client_id, client_secret = _credentials()
    with httpx.Client(timeout=3.0) as client:
        response = client.get(
            PUSH_SUBSCRIPTIONS_URL,
            params={"client_id": client_id, "client_secret": client_secret},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Strava subscription list failed: {response.text[:300]}")
    payload = response.json()
    return payload if isinstance(payload, list) else []


def delete_subscription(subscription_id: int) -> None:
    client_id, client_secret = _credentials()
    with httpx.Client(timeout=3.0) as client:
        response = client.delete(
            f"{PUSH_SUBSCRIPTIONS_URL}/{subscription_id}",
            params={"client_id": client_id, "client_secret": client_secret},
        )
    if response.status_code not in (200, 202, 204):
        raise RuntimeError(f"Strava subscription delete failed: {response.text[:300]}")
