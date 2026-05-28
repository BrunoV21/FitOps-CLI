from __future__ import annotations

import sys
from pathlib import Path

from fitops.backup import archive as arc
from fitops.backup.identity import origin_slug, resolve_origin
from fitops.backup.retention import apply_retention
from fitops.backup.signature import dataset_signature, short_signature
from fitops.backup.state import (
    get_dataset_revision,
    record_backup_skip,
    record_successful_backup,
    should_skip_backup,
)
from fitops.config.settings import get_settings


def build_backup_metadata(trigger: str, signature: str | None = None) -> dict:
    settings = get_settings()
    origin = resolve_origin()
    signature = signature or dataset_signature(
        db_path=settings.db_path, fitops_dir=settings.fitops_dir
    )
    return {
        "origin": origin.to_dict(),
        "origin_slug": origin_slug(origin),
        "instance_id_short": origin.instance_id[:12],
        "trigger": trigger,
        "dataset_revision": get_dataset_revision(settings.db_path),
        "dataset_signature": signature,
        "dataset_signature_short": short_signature(signature),
        "python_version": sys.version.split()[0],
    }


def create_local_archive(
    *,
    trigger: str,
    output_dir: Path | None = None,
    force: bool = False,
) -> tuple[Path | None, dict, str | None]:
    settings = get_settings()
    signature = dataset_signature(
        db_path=settings.db_path, fitops_dir=settings.fitops_dir
    )
    skip, reason = should_skip_backup(signature, force=force)
    metadata = build_backup_metadata(trigger=trigger, signature=signature)
    if skip:
        record_backup_skip(reason or "dataset unchanged", signature, trigger)
        return None, metadata, reason

    archive_path = arc.create_archive(
        fitops_dir=settings.fitops_dir,
        db_path=settings.db_path,
        dest=output_dir or settings.fitops_dir / "backups",
        metadata=metadata,
    )
    return archive_path, metadata, None


def upload_archive(
    archive_path: Path,
    *,
    provider_name: str,
    provider,
    metadata: dict,
    apply_smart_retention: bool = True,
):
    remote = provider.upload(archive_path, metadata=metadata)
    record_successful_backup(
        provider=provider_name,
        remote_id=remote.id,
        remote_name=remote.name,
        origin=metadata.get("origin") or {},
        trigger=metadata.get("trigger") or "manual",
        dataset_signature=metadata["dataset_signature"],
        dataset_revision=int(metadata.get("dataset_revision") or 0),
    )
    if apply_smart_retention:
        try:
            apply_retention(provider)
        except Exception:
            pass
    return remote


def record_local_archive(archive_path: Path, metadata: dict) -> None:
    record_successful_backup(
        provider="local",
        remote_id=None,
        remote_name=archive_path.name,
        origin=metadata.get("origin") or {},
        trigger=metadata.get("trigger") or "manual",
        dataset_signature=metadata["dataset_signature"],
        dataset_revision=int(metadata.get("dataset_revision") or 0),
    )
