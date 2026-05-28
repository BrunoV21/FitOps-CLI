from __future__ import annotations

import io
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest

from fitops.backup import archive as arc


def _write_db(path: Path, value: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS sample (value TEXT NOT NULL)")
    conn.execute("DELETE FROM sample")
    conn.execute("INSERT INTO sample (value) VALUES (?)", (value,))
    conn.commit()
    return conn


def _read_value(path: Path) -> str:
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT value FROM sample").fetchone()[0]


def test_create_archive_snapshots_live_wal_database(tmp_path: Path) -> None:
    fitops_dir = tmp_path / "fitops"
    fitops_dir.mkdir()
    db_path = fitops_dir / "fitops.db"
    backup_dir = tmp_path / "backups"

    conn = _write_db(db_path, "from-live-db")
    try:
        archive_path = arc.create_archive(fitops_dir, db_path, backup_dir)
    finally:
        conn.close()

    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extract("fitops.db", path=extract_dir, filter="data")

    assert _read_value(extract_dir / "fitops.db") == "from-live-db"


def test_restore_archive_replaces_db_and_removes_wal_sidecars(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_db = source_dir / "fitops.db"
    source_conn = _write_db(source_db, "restored")
    source_conn.close()
    archive_path = arc.create_archive(source_dir, source_db, tmp_path / "backups")

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target_db = target_dir / "fitops.db"
    target_conn = _write_db(target_db, "old")
    target_conn.close()
    Path(f"{target_db}-wal").write_bytes(b"stale wal")
    Path(f"{target_db}-shm").write_bytes(b"stale shm")

    restored = arc.restore_archive(archive_path, target_dir, target_db)

    assert "fitops.db" in restored
    assert not Path(f"{target_db}-wal").exists()
    assert not Path(f"{target_db}-shm").exists()
    assert _read_value(target_db) == "restored"


def test_restore_archive_rejects_malformed_database(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target_db = target_dir / "fitops.db"
    target_conn = _write_db(target_db, "keep-me")
    target_conn.close()

    archive_path = tmp_path / "bad-backup.tar.gz"
    manifest = {
        "created_at": "2026-05-28T00:00:00+00:00",
        "files": [{"arcname": "fitops.db", "source": "test"}],
    }
    with tarfile.open(archive_path, "w:gz") as tar:
        bad_db = b"not a sqlite database"
        db_info = tarfile.TarInfo("fitops.db")
        db_info.size = len(bad_db)
        tar.addfile(db_info, io.BytesIO(bad_db))

        manifest_bytes = json.dumps(manifest).encode()
        manifest_info = tarfile.TarInfo(arc.MANIFEST_NAME)
        manifest_info.size = len(manifest_bytes)
        tar.addfile(manifest_info, io.BytesIO(manifest_bytes))

    with pytest.raises(ValueError, match="valid SQLite database"):
        arc.restore_archive(archive_path, target_dir, target_db)

    assert _read_value(target_db) == "keep-me"
