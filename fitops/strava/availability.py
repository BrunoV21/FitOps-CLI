from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass

from fitops.config.settings import get_settings
from fitops.strava.client import StravaClient
from fitops.utils.exceptions import StravaAPIError, StravaAuthError


@dataclass(frozen=True)
class StravaAvailability:
    available: bool
    status_code: int
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


_cached: tuple[float, StravaAvailability] | None = None
_lock = asyncio.Lock()
TTL_SECONDS = 60.0


def clear_availability_cache() -> None:
    global _cached
    _cached = None


def record_strava_failure(status_code: int, reason: str = "strava_api_error") -> None:
    """Update the shared cache after another Strava operation fails."""
    global _cached
    _cached = (
        time.monotonic(),
        StravaAvailability(False, status_code, reason),
    )


async def get_strava_availability(
    *, force: bool = False, client: StravaClient | None = None
) -> StravaAvailability:
    """Probe Strava once per TTL and preserve its meaningful HTTP status."""
    global _cached
    settings = get_settings()
    if not settings.is_authenticated:
        return StravaAvailability(False, 401, "not_authenticated")

    now = time.monotonic()
    if not force and _cached and now - _cached[0] < TTL_SECONDS:
        return _cached[1]

    async with _lock:
        now = time.monotonic()
        if not force and _cached and now - _cached[0] < TTL_SECONDS:
            return _cached[1]
        try:
            await asyncio.wait_for(
                (client or StravaClient()).get_authenticated_athlete(), timeout=3.0
            )
            status = StravaAvailability(True, 200, "ok")
        except StravaAPIError as exc:
            status = StravaAvailability(False, exc.status_code, "strava_api_error")
        except StravaAuthError:
            status = StravaAvailability(False, 401, "authentication_failed")
        except TimeoutError:
            status = StravaAvailability(False, 503, "timeout")
        except Exception:
            status = StravaAvailability(False, 503, "unreachable")
        _cached = (time.monotonic(), status)
        return status
