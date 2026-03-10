from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fitops.utils.exceptions import ConfigError


def _fitops_dir() -> Path:
    env = os.environ.get("FITOPS_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".fitops"


def _config_path() -> Path:
    return _fitops_dir() / "config.json"


def _load_config() -> dict:
    path = _config_path()
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _save_config(data: dict) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


class FitOpsSettings:
    """Reads and writes ~/.fitops/config.json."""

    def __init__(self) -> None:
        self._data = _load_config()

    def reload(self) -> None:
        self._data = _load_config()

    # ------------------------------------------------------------------
    # Strava credentials
    # ------------------------------------------------------------------

    @property
    def client_id(self) -> Optional[str]:
        return self._data.get("strava", {}).get("client_id")

    @property
    def client_secret(self) -> Optional[str]:
        return self._data.get("strava", {}).get("client_secret")

    @property
    def redirect_uri(self) -> str:
        return self._data.get("strava", {}).get(
            "redirect_uri", "http://localhost:8080/callback"
        )

    @property
    def access_token(self) -> Optional[str]:
        return self._data.get("strava", {}).get("access_token")

    @property
    def refresh_token(self) -> Optional[str]:
        return self._data.get("strava", {}).get("refresh_token")

    @property
    def expires_at(self) -> Optional[datetime]:
        val = self._data.get("strava", {}).get("expires_at")
        if val is None:
            return None
        if isinstance(val, datetime):
            return val
        return datetime.fromisoformat(str(val))

    @property
    def athlete_id(self) -> Optional[int]:
        return self._data.get("strava", {}).get("athlete_id")

    @property
    def scopes(self) -> list[str]:
        return self._data.get("strava", {}).get(
            "scopes", ["read", "activity:read_all", "profile:read_all"]
        )

    @property
    def is_authenticated(self) -> bool:
        return bool(self.access_token and self.refresh_token)

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    @property
    def db_path(self) -> Path:
        raw = self._data.get("preferences", {}).get("db_path", "~/.fitops/fitops.db")
        return Path(raw).expanduser()

    @property
    def fitops_dir(self) -> Path:
        return _fitops_dir()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def save_credentials(self, client_id: str, client_secret: str) -> None:
        self._data.setdefault("strava", {})
        self._data["strava"]["client_id"] = client_id
        self._data["strava"]["client_secret"] = client_secret
        _save_config(self._data)
        self.reload()

    def save_tokens(self, token_data: dict) -> None:
        self._data.setdefault("strava", {})
        s = self._data["strava"]
        s["access_token"] = token_data.get("access_token")
        s["refresh_token"] = token_data.get("refresh_token")
        expires_at = token_data.get("expires_at")
        s["expires_at"] = expires_at.isoformat() if isinstance(expires_at, datetime) else expires_at
        if "athlete_id" in token_data:
            s["athlete_id"] = token_data["athlete_id"]
        if "scopes" in token_data:
            s["scopes"] = token_data["scopes"]
        _save_config(self._data)
        self.reload()

    def save_pending_state(self, state: str) -> None:
        self._data.setdefault("strava", {})
        self._data["strava"]["pending_state"] = state
        _save_config(self._data)
        self.reload()

    def pop_pending_state(self) -> Optional[str]:
        state = self._data.get("strava", {}).pop("pending_state", None)
        _save_config(self._data)
        return state

    def clear_tokens(self) -> None:
        s = self._data.get("strava", {})
        for key in ("access_token", "refresh_token", "expires_at", "pending_state"):
            s.pop(key, None)
        _save_config(self._data)
        self.reload()

    def require_auth(self) -> None:
        from fitops.utils.exceptions import NotAuthenticatedError
        if not self.is_authenticated:
            raise NotAuthenticatedError(
                "Not authenticated. Run `fitops auth login` first."
            )


_settings: Optional[FitOpsSettings] = None


def get_settings() -> FitOpsSettings:
    global _settings
    if _settings is None:
        _settings = FitOpsSettings()
    return _settings
