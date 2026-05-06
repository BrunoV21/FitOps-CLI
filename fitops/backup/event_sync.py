"""Event-triggered remote sync.

After important local write actions (Strava sync, workout create, notes, etc.),
call trigger_cli() or trigger_async() to push a backup to the configured
provider so a deployed remote instance stays in sync.

Guards:
- Only fires if get_github_config() returns non-None ("deployed" check).
- 30-second cooldown collapses rapid consecutive triggers into one upload.
- All exceptions are swallowed — the user's action must never fail due to sync.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time

_COOLDOWN_S: float = 30.0

# CLI path state
_cli_lock = threading.Lock()
_cli_last_triggered: float = 0.0

# Dashboard path state (single asyncio thread — no lock needed)
_dashboard_last_triggered: float = 0.0


def trigger_cli() -> None:
    """Spawn a detached backup subprocess. Safe to call from sync CLI commands."""
    global _cli_last_triggered
    try:
        from fitops.backup.config import get_github_config

        if not get_github_config():
            return
        now = time.monotonic()
        with _cli_lock:
            if now - _cli_last_triggered < _COOLDOWN_S:
                return
            _cli_last_triggered = now
        subprocess.Popen(
            [sys.executable, "-m", "fitops", "backup", "create", "--to", "github"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except Exception:
        pass


async def trigger_async() -> None:
    """Schedule a backup asyncio task. Safe to await from FastAPI route handlers."""
    global _dashboard_last_triggered
    try:
        from fitops.backup.config import get_github_config

        if not get_github_config():
            return
        now = time.monotonic()
        if now - _dashboard_last_triggered < _COOLDOWN_S:
            return
        _dashboard_last_triggered = now
        import asyncio

        asyncio.create_task(_run_backup_async())
    except Exception:
        pass


async def _run_backup_async() -> None:
    """Run backup create + upload in a thread-pool executor (non-blocking)."""
    import asyncio
    from datetime import UTC, datetime

    try:
        from fitops.backup import archive as arc
        from fitops.backup.config import get_github_config, update_last_backup_at
        from fitops.backup.providers.github import GitHubProvider
        from fitops.config.settings import get_settings

        cfg = get_github_config()
        if not cfg:
            return

        settings = get_settings()
        dest = settings.fitops_dir / "backups"
        loop = asyncio.get_event_loop()

        archive_path = await loop.run_in_executor(
            None,
            lambda: arc.create_archive(
                fitops_dir=settings.fitops_dir,
                db_path=settings.db_path,
                dest=dest,
            ),
        )

        provider = GitHubProvider(token=cfg["token"], repo=cfg["repo"])
        await loop.run_in_executor(None, lambda: provider.upload(archive_path))
        update_last_backup_at(datetime.now(UTC).isoformat())
    except Exception:
        pass
