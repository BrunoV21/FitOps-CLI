from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fitops.backup.identity import resolve_origin
from fitops.backup.providers.base import RemoteBackup
from fitops.backup.retention import select_backups_to_delete
from fitops.backup.service import create_local_archive, record_local_archive
from fitops.backup.signature import dataset_signature
from fitops.backup.state import get_last_successful_backup, mark_dataset_changed


@pytest.fixture(autouse=True)
def reset_settings_cache():
    import fitops.config.settings as settings_module

    old = settings_module._settings
    settings_module._settings = None
    yield
    settings_module._settings = old


def _reset_settings(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    import fitops.config.settings as settings_module

    fitops_dir = tmp_path / ".fitops"
    fitops_dir.mkdir()
    db_path = tmp_path / "fitops.db"
    (fitops_dir / "config.json").write_text(
        json.dumps({"preferences": {"db_path": str(db_path)}})
    )
    monkeypatch.setenv("FITOPS_DIR", str(fitops_dir))
    settings_module._settings = None
    return fitops_dir, db_path


def _init_backup_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE backup_state (key TEXT PRIMARY KEY, value TEXT, updated_at DATETIME)"
        )
        conn.execute(
            """
            CREATE TABLE backup_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                remote_id TEXT,
                remote_name TEXT,
                provider TEXT NOT NULL DEFAULT 'github',
                origin_kind TEXT,
                origin_label TEXT,
                origin_role TEXT,
                trigger TEXT,
                dataset_signature TEXT,
                dataset_revision INTEGER,
                status TEXT NOT NULL DEFAULT 'success',
                detail TEXT,
                created_at DATETIME
            )
            """
        )
        conn.execute(
            "CREATE TABLE activities (id INTEGER PRIMARY KEY, updated_at DATETIME)"
        )
        conn.execute("INSERT INTO activities (id, updated_at) VALUES (1, '2026-05-28')")


def test_resolve_origin_uses_hf_env(monkeypatch, tmp_path):
    _reset_settings(monkeypatch, tmp_path)
    monkeypatch.setenv("FITOPS_INSTANCE_KIND", "hf-space")
    monkeypatch.setenv("FITOPS_INSTANCE_LABEL", "user/fitops-dashboard")
    monkeypatch.setenv("FITOPS_INSTANCE_ROLE", "primary")

    origin = resolve_origin()

    assert origin.kind == "hf-space"
    assert origin.label == "user/fitops-dashboard"
    assert origin.role == "primary"
    assert origin.instance_id


def test_dataset_signature_changes_for_db_and_file_changes(monkeypatch, tmp_path):
    fitops_dir, db_path = _reset_settings(monkeypatch, tmp_path)
    _init_backup_db(db_path)
    workouts = fitops_dir / "workouts"
    workouts.mkdir()
    (workouts / "a.md").write_text("one")

    first = dataset_signature(db_path=db_path, fitops_dir=fitops_dir)
    mark_dataset_changed("test")
    second = dataset_signature(db_path=db_path, fitops_dir=fitops_dir)
    (workouts / "a.md").write_text("two")
    third = dataset_signature(db_path=db_path, fitops_dir=fitops_dir)

    assert first != second
    assert second != third


def test_create_local_archive_skips_when_signature_unchanged(monkeypatch, tmp_path):
    _, db_path = _reset_settings(monkeypatch, tmp_path)
    _init_backup_db(db_path)

    archive_path, metadata, skip_reason = create_local_archive(trigger="manual")
    assert archive_path is not None
    assert skip_reason is None
    record_local_archive(archive_path, metadata)

    skipped_path, skipped_metadata, skipped_reason = create_local_archive(
        trigger="scheduled"
    )

    assert skipped_path is None
    assert skipped_reason
    assert skipped_metadata["dataset_signature"] == metadata["dataset_signature"]
    assert (
        get_last_successful_backup()["dataset_signature"]
        == metadata["dataset_signature"]
    )


def test_retention_keeps_recent_and_prunes_old_same_origin():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    backups = [
        RemoteBackup(
            id=str(idx),
            name=f"backup-{idx}.tar.gz",
            created_at=(start + timedelta(days=idx)).isoformat(),
            size_bytes=1,
            download_url="",
            metadata={
                "origin": {
                    "kind": "hf-space",
                    "label": "space",
                    "role": "primary",
                }
            },
        )
        for idx in range(35)
    ]

    deletions = select_backups_to_delete(backups)

    assert deletions
    assert "34" not in {backup.id for backup in deletions}
