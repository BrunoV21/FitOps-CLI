from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fitops.backup.providers.base import BackupProvider, RemoteBackup


def _parse_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def _origin_key(backup: RemoteBackup) -> str:
    origin = backup.metadata.get("origin") if backup.metadata else None
    if not isinstance(origin, dict):
        return "unknown"
    return "|".join(
        [
            str(origin.get("kind") or "unknown"),
            str(origin.get("label") or "unknown"),
            str(origin.get("role") or "unknown"),
        ]
    )


def select_backups_to_delete(backups: list[RemoteBackup]) -> list[RemoteBackup]:
    if len(backups) <= 1:
        return []

    sorted_backups = sorted(
        backups, key=lambda b: _parse_dt(b.created_at), reverse=True
    )
    keep_ids: set[str] = {sorted_backups[0].id}
    by_origin: dict[str, list[RemoteBackup]] = defaultdict(list)
    for backup in sorted_backups:
        by_origin[_origin_key(backup)].append(backup)

    for origin_backups in by_origin.values():
        keep_ids.add(origin_backups[0].id)
        keep_ids.update(backup.id for backup in origin_backups[:14])

        daily: set[str] = set()
        weekly: set[tuple[int, int]] = set()
        monthly: set[str] = set()
        for backup in origin_backups:
            created = _parse_dt(backup.created_at)
            day_key = created.date().isoformat()
            week_key = created.isocalendar()[:2]
            month_key = f"{created.year:04d}-{created.month:02d}"
            if len(daily) < 30 and day_key not in daily:
                daily.add(day_key)
                keep_ids.add(backup.id)
            if len(weekly) < 12 and week_key not in weekly:
                weekly.add(week_key)
                keep_ids.add(backup.id)
            if len(monthly) < 12 and month_key not in monthly:
                monthly.add(month_key)
                keep_ids.add(backup.id)

    return [backup for backup in sorted_backups if backup.id not in keep_ids]


def apply_retention(provider: BackupProvider) -> list[RemoteBackup]:
    backups = provider.list_backups()
    deletions = select_backups_to_delete(backups)
    for backup in deletions:
        provider.delete(backup)
        try:
            from fitops.backup.state import record_retention_deletion

            origin = backup.metadata.get("origin") if backup.metadata else None
            record_retention_deletion(
                provider="github",
                remote_id=backup.id,
                remote_name=backup.name,
                origin=origin if isinstance(origin, dict) else None,
            )
        except Exception:
            pass
    return deletions
