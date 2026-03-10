from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fitops.config.settings import get_settings


def _state_path() -> Path:
    return get_settings().fitops_dir / "sync_state.json"


def _load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _save_state(data: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


class SyncState:
    """Reads and writes ~/.fitops/sync_state.json."""

    def __init__(self) -> None:
        self._data = _load_state()

    def reload(self) -> None:
        self._data = _load_state()

    @property
    def last_sync_at(self) -> Optional[datetime]:
        val = self._data.get("last_sync_at")
        if val is None:
            return None
        return datetime.fromisoformat(str(val))

    @property
    def last_sync_epoch(self) -> Optional[int]:
        dt = self.last_sync_at
        return int(dt.timestamp()) if dt else None

    @property
    def activities_synced_total(self) -> int:
        return self._data.get("activities_synced_total", 0)

    @property
    def sync_history(self) -> list[dict]:
        return self._data.get("sync_history", [])

    def update_after_sync(
        self,
        *,
        sync_type: str,
        activities_created: int,
        activities_updated: int,
        duration_s: float,
    ) -> None:
        now = datetime.now(timezone.utc)
        self._data["last_sync_at"] = now.isoformat()
        self._data["last_sync_type"] = sync_type
        self._data["activities_synced_total"] = (
            self.activities_synced_total + activities_created
        )
        history_entry = {
            "synced_at": now.isoformat(),
            "type": sync_type,
            "activities_created": activities_created,
            "activities_updated": activities_updated,
            "duration_s": round(duration_s, 2),
        }
        history = self._data.get("sync_history", [])
        history.insert(0, history_entry)
        self._data["sync_history"] = history[:50]  # keep last 50
        _save_state(self._data)
        self.reload()


def get_sync_state() -> SyncState:
    return SyncState()
