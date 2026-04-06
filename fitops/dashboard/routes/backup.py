from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from fitops.backup import archive as arc
from fitops.backup import config as bcfg
from fitops.config.settings import get_settings

router = APIRouter()


def register(templates: Jinja2Templates) -> APIRouter:

    @router.get("/backup", response_class=HTMLResponse)
    async def backup_page(request: Request):
        gh = bcfg.get_github_config()
        schedule = bcfg.get_schedule_config()
        return templates.TemplateResponse(
            request,
            "backup.html",
            {
                "request": request,
                "active_page": "backup",
                "github_configured": bool(gh),
                "github_repo": gh["repo"] if gh else "",
                "schedule": schedule,
            },
        )

    # ------------------------------------------------------------------
    # Provider setup
    # ------------------------------------------------------------------

    @router.post("/api/backup/setup/github")
    async def setup_github(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        token = (payload.get("token") or "").strip()
        repo = (payload.get("repo") or "").strip()
        if not token or not repo:
            return JSONResponse(
                {"error": "token and repo are required"}, status_code=400
            )

        try:
            from fitops.backup.providers.github import validate_config

            full_name = validate_config(token, repo)
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        bcfg.save_github_config(token, repo)
        return JSONResponse({"ok": True, "repo": full_name})

    @router.delete("/api/backup/setup/github")
    async def remove_github():
        bcfg.clear_github_config()
        return JSONResponse({"ok": True})

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @router.post("/api/backup/create")
    async def create_backup(request: Request):
        try:
            payload = await request.json()
        except Exception:
            payload = {}

        provider_name = (payload.get("provider") or "").strip() or None

        settings = get_settings()
        dest = settings.fitops_dir / "backups"

        try:
            archive_path = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: arc.create_archive(
                    fitops_dir=settings.fitops_dir,
                    db_path=settings.db_path,
                    dest=dest,
                ),
            )
        except Exception as exc:
            return JSONResponse(
                {"error": f"Archive creation failed: {exc}"}, status_code=500
            )

        size_mb = arc.archive_size_mb(archive_path)
        result: dict = {
            "name": archive_path.name,
            "size_mb": round(size_mb, 1),
            "local_path": str(archive_path),
        }

        if provider_name:
            try:
                provider = _get_provider(provider_name)
                remote = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: provider.upload(archive_path)
                )
                result["uploaded"] = True
                result["remote_name"] = remote.name
                result["created_at"] = remote.created_at
                # Record last_backup_at in schedule if configured
                bcfg.update_last_backup_at(datetime.now(UTC).isoformat())
            except Exception as exc:
                result["uploaded"] = False
                result["upload_error"] = str(exc)

        return JSONResponse(result)

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    @router.get("/api/backup/list")
    async def list_backups(provider: str = "github"):
        try:
            prov = _get_provider(provider)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        try:
            backups = await asyncio.get_event_loop().run_in_executor(
                None, prov.list_backups
            )
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

        return JSONResponse(
            {
                "provider": provider,
                "backups": [
                    {
                        "id": b.id,
                        "name": b.name,
                        "created_at": b.created_at,
                        "size_mb": round(b.size_bytes / (1024 * 1024), 1),
                        "download_url": b.download_url,
                    }
                    for b in backups
                ],
            }
        )

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    @router.post("/api/backup/restore")
    async def restore_backup(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        provider_name = (payload.get("provider") or "").strip()
        backup_id = (payload.get("backup_id") or "").strip()

        if not provider_name or not backup_id:
            return JSONResponse(
                {"error": "provider and backup_id are required"}, status_code=400
            )

        try:
            prov = _get_provider(provider_name)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        # Find the backup in the remote list
        try:
            backups = await asyncio.get_event_loop().run_in_executor(
                None, prov.list_backups
            )
        except Exception as exc:
            return JSONResponse(
                {"error": f"Could not list backups: {exc}"}, status_code=500
            )

        chosen = next((b for b in backups if b.id == backup_id), None)
        if chosen is None:
            return JSONResponse(
                {"error": f"Backup '{backup_id}' not found."}, status_code=404
            )

        settings = get_settings()

        try:
            with tempfile.TemporaryDirectory() as tmp:
                archive_path = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: prov.download(chosen, Path(tmp))
                )
                manifest = arc.read_manifest(archive_path)
                restored = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: arc.restore_archive(
                        archive_path=archive_path,
                        fitops_dir=settings.fitops_dir,
                        db_path=settings.db_path,
                    ),
                )
        except Exception as exc:
            return JSONResponse({"error": f"Restore failed: {exc}"}, status_code=500)

        # Reload settings so the in-process singleton picks up any config changes
        settings.reload()

        return JSONResponse(
            {
                "ok": True,
                "restored_items": restored,
                "backup_created_at": manifest.get("created_at", "unknown"),
            }
        )

    # ------------------------------------------------------------------
    # Schedule
    # ------------------------------------------------------------------

    @router.get("/api/backup/schedule")
    async def get_schedule():
        sched = bcfg.get_schedule_config()
        return JSONResponse(sched or {})

    @router.post("/api/backup/schedule")
    async def save_schedule(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        enabled = bool(payload.get("enabled", True))
        try:
            interval_hours = int(payload.get("interval_hours", 24))
        except (TypeError, ValueError):
            return JSONResponse(
                {"error": "interval_hours must be an integer"}, status_code=400
            )

        if interval_hours < 1:
            return JSONResponse(
                {"error": "interval_hours must be >= 1"}, status_code=400
            )

        provider = (payload.get("provider") or "github").strip()

        bcfg.save_schedule_config(
            enabled=enabled,
            interval_hours=interval_hours,
            provider=provider,
        )
        return JSONResponse(
            {
                "ok": True,
                "enabled": enabled,
                "interval_hours": interval_hours,
                "provider": provider,
            }
        )

    return router


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_provider(name: str):
    if name == "github":
        cfg = bcfg.get_github_config()
        if not cfg:
            raise ValueError("GitHub backup is not configured.")
        from fitops.backup.providers.github import GitHubProvider

        return GitHubProvider(token=cfg["token"], repo=cfg["repo"])
    raise ValueError(f"Unknown provider '{name}'.")


# ---------------------------------------------------------------------------
# Background scheduler
# ---------------------------------------------------------------------------


async def run_scheduler() -> None:
    """Long-running asyncio task started by the FastAPI lifespan.

    Wakes every 60 s, checks whether a scheduled backup is due, and runs it
    if so.  Gracefully exits on cancellation.
    """
    while True:
        try:
            await asyncio.sleep(60)
            _maybe_run_scheduled_backup()
        except asyncio.CancelledError:
            break
        except Exception:
            pass  # never crash the server over a backup failure


def _maybe_run_scheduled_backup() -> None:
    sched = bcfg.get_schedule_config()
    if not sched or not sched.get("enabled"):
        return

    interval_s = sched["interval_hours"] * 3600
    last_str = sched.get("last_backup_at")

    if last_str:
        try:
            last_dt = datetime.fromisoformat(last_str)
            elapsed = (datetime.now(UTC) - last_dt).total_seconds()
            if elapsed < interval_s:
                return
        except Exception:
            pass

    provider_name = sched.get("provider", "github")
    settings = get_settings()
    dest = settings.fitops_dir / "backups"

    try:
        archive_path = arc.create_archive(
            fitops_dir=settings.fitops_dir,
            db_path=settings.db_path,
            dest=dest,
        )
        provider = _get_provider(provider_name)
        provider.upload(archive_path)
        bcfg.update_last_backup_at(datetime.now(UTC).isoformat())
    except Exception:
        pass
