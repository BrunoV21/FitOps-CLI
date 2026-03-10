from __future__ import annotations

import asyncio
import secrets
import webbrowser
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from fitops.config.settings import FitOpsSettings, get_settings
from fitops.utils.exceptions import StravaAuthError
from fitops.utils.logging import get_logger

logger = get_logger(__name__)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_DEAUTH_URL = "https://www.strava.com/oauth/deauthorize"

DEFAULT_SCOPES = ["read", "activity:read_all", "profile:read_all"]
CALLBACK_TIMEOUT_S = 120
CALLBACK_PORTS = [8080, 8081, 8082]


def validate_strava_token(access_token: Optional[str], expires_at: Optional[datetime]) -> bool:
    """Return True if the token is still valid (5-minute buffer)."""
    if not access_token or not expires_at:
        return False
    buffer = timedelta(minutes=5)
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return now < (expires_at - buffer)


class LocalCallbackServer:
    """Tiny asyncio HTTP server that captures a single OAuth callback."""

    def __init__(self) -> None:
        self.code: Optional[str] = None
        self.state: Optional[str] = None
        self.error: Optional[str] = None
        self._received = asyncio.Event()

    async def _handle_request(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            data = await asyncio.wait_for(reader.read(4096), timeout=10)
            request_line = data.decode("utf-8", errors="replace").split("\r\n")[0]
            method, path, *_ = request_line.split(" ")
            parsed = urlparse(path)
            params = parse_qs(parsed.query)

            self.code = params.get("code", [None])[0]
            self.state = params.get("state", [None])[0]
            self.error = params.get("error", [None])[0]

            body = b"<html><body><h2>FitOps: Authentication successful!</h2><p>You can close this tab.</p></body></html>"
            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/html\r\n"
                b"Connection: close\r\n\r\n" + body
            )
            writer.write(response)
            await writer.drain()
        finally:
            writer.close()
            self._received.set()

    async def wait_for_callback(self, port: int) -> None:
        server = await asyncio.start_server(self._handle_request, "127.0.0.1", port)
        async with server:
            try:
                await asyncio.wait_for(self._received.wait(), timeout=CALLBACK_TIMEOUT_S)
            except asyncio.TimeoutError:
                raise StravaAuthError(
                    f"OAuth callback timed out after {CALLBACK_TIMEOUT_S}s. Please try again."
                )


class StravaOAuth:
    """Handles Strava OAuth 2.0 flow."""

    def __init__(self, settings: Optional[FitOpsSettings] = None) -> None:
        self.settings = settings or get_settings()

    def get_authorization_url(
        self,
        scopes: Optional[list[str]] = None,
        state: Optional[str] = None,
        port: int = 8080,
    ) -> str:
        if scopes is None:
            scopes = DEFAULT_SCOPES
        if state is None:
            state = secrets.token_urlsafe(32)
        redirect_uri = f"http://localhost:{port}/callback"
        params = {
            "client_id": self.settings.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": ",".join(scopes),
            "state": state,
            "approval_prompt": "auto",
        }
        return f"{STRAVA_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str, port: int = 8080) -> dict:
        redirect_uri = f"http://localhost:{port}/callback"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": self.settings.client_id,
                    "client_secret": self.settings.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
        if response.status_code != 200:
            raise StravaAuthError(f"Token exchange failed: {response.text}")
        data = response.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": datetime.fromtimestamp(data["expires_at"], tz=timezone.utc),
            "athlete_id": data["athlete"]["id"],
            "scopes": data.get("scope", "").split(","),
        }

    async def refresh_access_token(self, refresh_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": self.settings.client_id,
                    "client_secret": self.settings.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        if response.status_code != 200:
            raise StravaAuthError(f"Token refresh failed: {response.text}")
        data = response.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": datetime.fromtimestamp(data["expires_at"], tz=timezone.utc),
        }

    async def fetch_detailed_athlete(self, access_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.strava.com/api/v3/athlete",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code != 200:
            raise StravaAuthError(f"Failed to fetch athlete profile: {response.text}")
        return response.json()

    async def revoke_access_token(self, access_token: str) -> bool:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                STRAVA_DEAUTH_URL,
                data={"access_token": access_token},
            )
        return response.status_code == 200

    async def run_login_flow(self, scopes: Optional[list[str]] = None) -> dict:
        """Full interactive login: open browser, capture callback, exchange token."""
        state = secrets.token_urlsafe(32)
        self.settings.save_pending_state(state)

        port = 8080
        auth_url = self.get_authorization_url(scopes=scopes, state=state, port=port)

        print(f"\nOpening Strava authorization in your browser...")
        print(f"If the browser doesn't open, visit:\n  {auth_url}\n")
        webbrowser.open(auth_url)

        callback = LocalCallbackServer()
        await callback.wait_for_callback(port=port)

        if callback.error:
            raise StravaAuthError(f"Strava denied authorization: {callback.error}")
        if not callback.code:
            raise StravaAuthError("No authorization code received.")

        expected_state = self.settings.pop_pending_state()
        if expected_state and callback.state != expected_state:
            raise StravaAuthError("OAuth state mismatch — possible CSRF attack.")

        token_data = await self.exchange_code_for_token(callback.code, port=port)
        athlete_data = await self.fetch_detailed_athlete(token_data["access_token"])

        self.settings.save_tokens(token_data)

        return {**token_data, "athlete": athlete_data}

    async def ensure_valid_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        self.settings.reload()
        if validate_strava_token(self.settings.access_token, self.settings.expires_at):
            return self.settings.access_token

        if not self.settings.refresh_token:
            raise StravaAuthError("No refresh token available. Please run `fitops auth login`.")

        token_data = await self.refresh_access_token(self.settings.refresh_token)
        self.settings.save_tokens(token_data)
        return token_data["access_token"]
