"""Hosted FitOps deploy API.

This app is intended to be deployed separately from user dashboards. It accepts
the same user-owned HF/GitHub credentials as the local CLI, keeps them in memory
only for a short-lived job, and calls the shared deploy service directly.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from fitops.cloud.deploy_hf import HfDeployRequest, deploy_hf_space, validate_repo_id

_TOKEN_RE = re.compile(r"\b(?:hf|gh[pousr])_[A-Za-z0-9_]{8,}\b")
_SENSITIVE_KEYS = {
    "dashboard_password",
    "github_token",
    "github_backup_token",
    "hf_token",
    "password",
    "pw_hash",
    "session_secret",
    "sync_token",
    "strava_client_secret",
    "totp_secret",
}


class HfDeployJobRequest(BaseModel):
    hf_token: str = Field(min_length=8)
    hf_repo: str | None = None
    github_token: str = Field(min_length=8)
    github_repo: str
    dashboard_password: str = Field(min_length=8, max_length=256)
    strava_client_id: str | None = None
    strava_client_secret: str | None = None


@dataclass
class DeployEvent:
    message: str
    level: str = "info"
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, str]:
        return {"message": self.message, "level": self.level, "at": self.at}


@dataclass
class DeployJob:
    id: str
    created_at: datetime
    expires_at: datetime
    status: str
    hf_token: str
    hf_repo: str | None
    github_token: str
    github_repo: str
    dashboard_password: str
    strava_client_id: str | None
    strava_client_secret: str | None
    totp_secret: str
    totp_uri: str
    events: list[DeployEvent] = field(default_factory=list)
    result: dict[str, str] | None = None
    error: str | None = None

    def clear_secrets(self) -> None:
        self.hf_token = ""
        self.github_token = ""
        self.dashboard_password = ""
        self.strava_client_secret = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "events": [event.to_dict() for event in self.events],
            "result": self.result,
            "error": self.error,
        }


class DeployJobManager:
    def __init__(
        self,
        *,
        ttl_seconds: int = 3600,
        max_concurrent_jobs: int = 2,
        timeout_seconds: int = 900,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_concurrent_jobs = max_concurrent_jobs
        self.timeout_seconds = timeout_seconds
        self.jobs: dict[str, DeployJob] = {}

    def create_job(self, payload: HfDeployJobRequest) -> DeployJob:
        self.cleanup_expired()
        running = sum(1 for job in self.jobs.values() if job.status == "running")
        if running >= self.max_concurrent_jobs:
            raise HTTPException(status_code=429, detail="Too many deploy jobs running.")

        hf_repo = payload.hf_repo.strip() if payload.hf_repo else None
        if hf_repo == "":
            hf_repo = None
        github_repo = payload.github_repo.strip()
        hf_token = payload.hf_token.strip()
        github_token = payload.github_token.strip()
        strava_client_id = (
            payload.strava_client_id.strip() if payload.strava_client_id else None
        )
        strava_client_secret = (
            payload.strava_client_secret.strip()
            if payload.strava_client_secret
            else None
        )
        if bool(strava_client_id) != bool(strava_client_secret):
            raise HTTPException(
                status_code=400,
                detail="Strava Client ID and Client Secret must be provided together.",
            )

        if hf_repo:
            validate_repo_id(hf_repo, label="HF Space repo")
        validate_repo_id(github_repo, label="GitHub backup repo")

        from fitops.auth.totp import generate_secret, provisioning_uri

        job_id = secrets.token_urlsafe(18)
        account = hf_repo or "fitops-dashboard"
        totp_secret = generate_secret()
        job = DeployJob(
            id=job_id,
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
            status="queued",
            hf_token=hf_token,
            hf_repo=hf_repo,
            github_token=github_token,
            github_repo=github_repo,
            dashboard_password=payload.dashboard_password,
            strava_client_id=strava_client_id,
            strava_client_secret=strava_client_secret,
            totp_secret=totp_secret,
            totp_uri=provisioning_uri(totp_secret, account=account),
        )
        job.events.append(DeployEvent("Deploy job queued."))
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> DeployJob:
        self.cleanup_expired()
        job = self.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Deploy job not found.")
        return job

    def cleanup_expired(self) -> None:
        now = datetime.now(UTC)
        expired = [job_id for job_id, job in self.jobs.items() if job.expires_at < now]
        for job_id in expired:
            self.jobs[job_id].clear_secrets()
            del self.jobs[job_id]

    async def run_job(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job.status = "running"
        job.events.append(DeployEvent("Deploy job started."))

        secret_values = [
            job.hf_token,
            job.github_token,
            job.dashboard_password,
            job.strava_client_secret or "",
            job.totp_secret,
        ]

        def add_event(message: str, level: str = "info") -> None:
            job.events.append(DeployEvent(redact_text(message, secret_values), level))

        def run_sync() -> dict[str, str]:
            import bcrypt

            pw_hash = bcrypt.hashpw(
                job.dashboard_password.encode(), bcrypt.gensalt()
            ).decode()
            request = HfDeployRequest(
                hf_token=job.hf_token,
                hf_repo=job.hf_repo,
                github_backup_token=job.github_token,
                github_backup_repo=job.github_repo,
                pw_hash=pw_hash,
                totp_secret=job.totp_secret,
                session_secret=secrets.token_hex(32),
                sync_token=secrets.token_hex(32),
                strava_client_id=job.strava_client_id,
                strava_client_secret=job.strava_client_secret,
            )
            result = deploy_hf_space(request, progress=add_event)
            return {
                "hf_repo": result.hf_repo,
                "space_url": result.space_url,
                "app_url": result.app_url_display,
                "webhook_url": result.webhook_url,
                "callback_domain": result.callback_domain,
            }

        try:
            job.result = await asyncio.wait_for(
                asyncio.to_thread(run_sync), timeout=self.timeout_seconds
            )
            job.status = "succeeded"
            add_event("Deploy job succeeded.")
        except TimeoutError:
            job.status = "failed"
            job.error = "Deploy job timed out."
            add_event(job.error, "error")
        except Exception as exc:
            job.status = "failed"
            job.error = redact_text(str(exc), secret_values) or "Deploy job failed."
            add_event(job.error, "error")
        finally:
            job.clear_secrets()


class RateLimiter:
    def __init__(self, *, limit: int, window_seconds: int = 3600) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            raise HTTPException(status_code=429, detail="Deploy rate limit exceeded.")
        hits.append(now)


def redact_text(text: str, secret_values: list[str] | tuple[str, ...] = ()) -> str:
    redacted = text
    for value in secret_values:
        if value and len(value) >= 4:
            redacted = redacted.replace(value, "[REDACTED]")
    redacted = _TOKEN_RE.sub("[REDACTED]", redacted)
    return redacted


def scrub_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key in _SENSITIVE_KEYS else scrub_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub_payload(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _allowed_origins_from_env() -> list[str]:
    raw = os.getenv("FITOPS_DEPLOY_ALLOWED_ORIGINS", "")
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


def create_app(
    *,
    allowed_origins: list[str] | None = None,
    manager: DeployJobManager | None = None,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    allowed = [
        origin.rstrip("/") for origin in (allowed_origins or _allowed_origins_from_env())
    ]
    app = FastAPI(title="FitOps Deploy API", version="0.1.0")
    app.state.allowed_origins = allowed
    app.state.manager = manager or DeployJobManager(
        ttl_seconds=_env_int("FITOPS_DEPLOY_JOB_TTL_SECONDS", 3600),
        max_concurrent_jobs=_env_int("FITOPS_DEPLOY_MAX_CONCURRENT_JOBS", 2),
        timeout_seconds=_env_int("FITOPS_DEPLOY_JOB_TIMEOUT_SECONDS", 900),
    )
    app.state.rate_limiter = rate_limiter or RateLimiter(
        limit=_env_int("FITOPS_DEPLOY_RATE_LIMIT_PER_HOUR", 5)
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def enforce_origin(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            origin = (request.headers.get("origin") or "").rstrip("/")
            if not allowed or origin not in allowed:
                return JSONResponse(
                    {"detail": "Origin is not allowed."}, status_code=403
                )
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/deploy/hf/jobs")
    async def create_hf_job(payload: HfDeployJobRequest, request: Request):
        client = request.client.host if request.client else "unknown"
        app.state.rate_limiter.check(client)
        job = app.state.manager.create_job(payload)
        asyncio.create_task(app.state.manager.run_job(job.id))
        return {
            "job_id": job.id,
            "status": job.status,
            "totp": {
                "manual_key": job.totp_secret,
                "provisioning_uri": job.totp_uri,
            },
        }

    @app.get("/api/deploy/hf/jobs/{job_id}")
    async def get_hf_job(job_id: str):
        return scrub_payload(app.state.manager.get_job(job_id).public_dict())

    @app.get("/api/deploy/hf/jobs/{job_id}/events")
    async def stream_hf_job(job_id: str):
        async def event_stream():
            offset = 0
            while True:
                job = app.state.manager.get_job(job_id)
                while offset < len(job.events):
                    payload = job.events[offset].to_dict()
                    offset += 1
                    yield f"data: {json.dumps(scrub_payload(payload))}\n\n"
                if job.status in {"succeeded", "failed"}:
                    terminal = {
                        "status": job.status,
                        "result": job.result,
                        "error": job.error,
                    }
                    yield f"data: {json.dumps(scrub_payload(terminal))}\n\n"
                    break
                await asyncio.sleep(0.5)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app


app = create_app()
