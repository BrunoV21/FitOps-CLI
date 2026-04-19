from __future__ import annotations

from typing import Any

import httpx

from fitops.config.settings import get_settings
from fitops.strava.oauth import StravaOAuth
from fitops.utils.exceptions import StravaAuthError, SyncError
from fitops.utils.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.strava.com/api/v3"

STREAM_KEYS = [
    "time",
    "distance",
    "latlng",
    "altitude",
    "heartrate",
    "watts",
    "cadence",
    "temp",
    "moving",
    "grade_smooth",
    "velocity_smooth",
    "grade_adjusted_speed",
]


class StravaClient:
    """Async Strava API client using httpx."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._oauth = StravaOAuth(self._settings)

    async def _get_token(self) -> str:
        return await self._oauth.ensure_valid_token()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        data: dict | None = None,
    ) -> Any:
        token = await self._get_token()
        url = f"{BASE_URL}{endpoint}"
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method, url, headers=headers, params=params, data=data
            )
        if response.status_code == 401:
            raise StravaAuthError(
                "Unauthorized — token may be invalid. Try `fitops auth refresh`."
            )
        if response.status_code == 429:
            raise SyncError(
                "Strava API rate limit exceeded. Please wait and try again."
            )
        if response.status_code >= 400:
            raise SyncError(
                f"Strava API error {response.status_code} for {endpoint}: {response.text[:200]}"
            )
        return response.json()

    async def get_authenticated_athlete(self) -> dict:
        return await self._make_request("GET", "/athlete")

    async def get_athlete_stats(self, athlete_id: int) -> dict:
        return await self._make_request("GET", f"/athletes/{athlete_id}/stats")

    async def list_athlete_activities(
        self,
        before: int | None = None,
        after: int | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict]:
        params: dict = {"page": page, "per_page": per_page}
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        result = await self._make_request("GET", "/athlete/activities", params=params)
        return result if isinstance(result, list) else []

    async def get_activity(self, activity_id: int) -> dict:
        return await self._make_request(
            "GET", f"/activities/{activity_id}", params={"include_all_efforts": False}
        )

    async def get_activity_streams(
        self,
        activity_id: int,
        keys: list[str] | None = None,
    ) -> dict:
        if keys is None:
            keys = STREAM_KEYS
        return await self._make_request(
            "GET",
            f"/activities/{activity_id}/streams",
            params={"keys": ",".join(keys), "key_by_type": True},
        )

    async def get_activity_laps(self, activity_id: int) -> list[dict]:
        result = await self._make_request("GET", f"/activities/{activity_id}/laps")
        return result if isinstance(result, list) else []

    async def get_athlete_zones(self) -> dict:
        return await self._make_request("GET", "/athlete/zones")
