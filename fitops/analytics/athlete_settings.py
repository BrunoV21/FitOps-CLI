from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fitops.config.settings import get_settings


def _path() -> Path:
    return get_settings().fitops_dir / "athlete_settings.json"


def _load() -> dict:
    p = _path()
    return json.loads(p.read_text()) if p.exists() else {}


def _save(data: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


class AthleteSettings:
    def __init__(self) -> None:
        self._data = _load()

    def reload(self) -> None:
        self._data = _load()

    @property
    def weight_kg(self) -> Optional[float]:
        return self._data.get("weight_kg")

    @property
    def height_cm(self) -> Optional[float]:
        return self._data.get("height_cm")

    @property
    def max_hr(self) -> Optional[int]:
        return self._data.get("max_hr")

    @property
    def resting_hr(self) -> Optional[int]:
        return self._data.get("resting_hr")

    @property
    def lthr(self) -> Optional[int]:
        return self._data.get("lthr")

    @property
    def ftp(self) -> Optional[float]:
        return self._data.get("ftp")

    @property
    def threshold_pace_per_km_s(self) -> Optional[float]:
        return self._data.get("threshold_pace_per_km_s")

    @property
    def lt1_pace_s(self) -> Optional[float]:
        return self._data.get("lt1_pace_s")

    @property
    def vo2max_pace_s(self) -> Optional[float]:
        return self._data.get("vo2max_pace_s")

    @property
    def lt1_hr(self) -> Optional[int]:
        return self._data.get("lt1_hr")

    @property
    def lt2_hr(self) -> Optional[int]:
        return self._data.get("lt2_hr")

    @property
    def vo2max_override(self) -> Optional[float]:
        return self._data.get("vo2max_override")

    def set(self, **kwargs) -> None:
        self._data.update({k: v for k, v in kwargs.items() if v is not None})
        _save(self._data)
        self.reload()

    def clear(self, *keys: str) -> None:
        for k in keys:
            self._data.pop(k, None)
        _save(self._data)
        self.reload()

    def to_dict(self) -> dict:
        return dict(self._data)

    def best_zone_method(self) -> str:
        if self.lthr:
            return "lthr"
        elif self.max_hr and self.resting_hr:
            return "hrr"
        elif self.max_hr:
            return "max-hr"
        return "none"


_instance: Optional[AthleteSettings] = None


def get_athlete_settings() -> AthleteSettings:
    global _instance
    if _instance is None:
        _instance = AthleteSettings()
    return _instance
