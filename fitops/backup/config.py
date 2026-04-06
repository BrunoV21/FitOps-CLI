"""Helpers for reading and writing backup provider config inside config.json."""

from __future__ import annotations

import json
from pathlib import Path


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


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


def get_github_config() -> dict | None:
    return _load().get("backup", {}).get("github")


def save_github_config(token: str, repo: str) -> None:
    data = _load()
    data.setdefault("backup", {})["github"] = {"token": token, "repo": repo}
    _save(data)


def clear_github_config() -> None:
    data = _load()
    data.get("backup", {}).pop("github", None)
    _save(data)


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------


def get_schedule_config() -> dict | None:
    """Return schedule config or None if not configured.

    Shape: { "enabled": bool, "interval_hours": int, "provider": str,
             "last_backup_at": str|None }
    """
    return _load().get("backup", {}).get("schedule")


def save_schedule_config(
    enabled: bool,
    interval_hours: int,
    provider: str,
    last_backup_at: str | None = None,
) -> None:
    data = _load()
    existing = data.setdefault("backup", {}).get("schedule", {})
    data["backup"]["schedule"] = {
        "enabled": enabled,
        "interval_hours": interval_hours,
        "provider": provider,
        "last_backup_at": last_backup_at or existing.get("last_backup_at"),
    }
    _save(data)


def update_last_backup_at(ts: str) -> None:
    data = _load()
    sched = data.get("backup", {}).get("schedule")
    if sched is not None:
        sched["last_backup_at"] = ts
        _save(data)
