from __future__ import annotations

import json
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

MANIFEST_NAME = "manifest.json"

# Files and directories (relative to fitops_dir) that are included in a backup.
# The DB path is resolved separately since it can be customised via config.
_RELATIVE_ITEMS = [
    "config.json",
    "sync_state.json",
    "athlete_settings.json",
    "notes",
    "workouts",
]


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")


def backup_filename(
    origin_slug: str | None = None,
    instance_id_short: str | None = None,
    signature_short: str | None = None,
) -> str:
    parts = ["fitops-backup"]
    if origin_slug:
        parts.append(origin_slug)
    if instance_id_short:
        parts.extend(["iid", instance_id_short])
    parts.append(_timestamp())
    if signature_short:
        parts.append(signature_short)
    return f"{'-'.join(parts)}.tar.gz"


def _sqlite_sidecars(db_path: Path) -> list[Path]:
    return [Path(f"{db_path}-wal"), Path(f"{db_path}-shm")]


def _remove_sqlite_sidecars(db_path: Path) -> None:
    for sidecar in _sqlite_sidecars(db_path):
        sidecar.unlink(missing_ok=True)


def _validate_sqlite_db(db_path: Path) -> None:
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError(
            f"Restored database is not a valid SQLite database: {exc}"
        ) from exc

    if row is None or row[0] != "ok":
        detail = row[0] if row else "no quick_check result"
        raise ValueError(f"Restored database failed SQLite quick_check: {detail}")


def _snapshot_sqlite_db(db_path: Path, dest: Path) -> Path:
    """Create a consistent SQLite snapshot suitable for archiving."""
    dest.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        prefix=f"{db_path.stem}-",
        suffix=".db",
        dir=dest,
        delete=False,
    )
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as source:
            with sqlite3.connect(tmp_path) as target:
                source.backup(target)
        _validate_sqlite_db(tmp_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return tmp_path


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_archive(
    fitops_dir: Path,
    db_path: Path,
    dest: Path,
    *,
    metadata: dict | None = None,
) -> Path:
    """Create a gzipped tar archive of the FitOps data directory.

    Args:
        fitops_dir: The ~/.fitops directory.
        db_path: Resolved path to the SQLite database file.
        dest: Directory where the archive will be written.

    Returns:
        Path to the created archive file.
    """
    dest.mkdir(parents=True, exist_ok=True)
    metadata = metadata or {}
    archive_path = dest / backup_filename(
        metadata.get("origin_slug"),
        metadata.get("instance_id_short"),
        metadata.get("dataset_signature_short"),
    )

    included: list[dict] = []

    db_snapshot: Path | None = None
    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            # Database — stored as "fitops.db" in the root of the archive
            # regardless of where the user has configured it on disk. Use the
            # SQLite backup API so WAL pages and concurrent writes cannot leave
            # a partial copy in the archive.
            if db_path.exists():
                db_snapshot = _snapshot_sqlite_db(db_path, dest)
                tar.add(db_snapshot, arcname="fitops.db")
                included.append({"arcname": "fitops.db", "source": str(db_path)})

            # Config files and directories from fitops_dir
            for name in _RELATIVE_ITEMS:
                item = fitops_dir / name
                if item.exists():
                    tar.add(item, arcname=name)
                    included.append({"arcname": name, "source": str(item)})

            # Write manifest last
            manifest = {
                "created_at": datetime.now(UTC).isoformat(),
                "fitops_version": "0.1.0",
                "backup_format_version": 2,
                "files": included,
            }
            manifest.update(metadata)
            manifest_bytes = json.dumps(manifest, indent=2).encode()
            import io

            info = tarfile.TarInfo(name=MANIFEST_NAME)
            info.size = len(manifest_bytes)
            tar.addfile(info, io.BytesIO(manifest_bytes))
    finally:
        if db_snapshot is not None:
            db_snapshot.unlink(missing_ok=True)

    return archive_path


# ---------------------------------------------------------------------------
# Inspect
# ---------------------------------------------------------------------------


def read_manifest(archive_path: Path) -> dict:
    """Return the manifest dict from an archive without fully extracting it."""
    with tarfile.open(archive_path, "r:gz") as tar:
        member = tar.getmember(MANIFEST_NAME)
        f = tar.extractfile(member)
        if f is None:
            raise ValueError("Manifest member is not a regular file.")
        return json.loads(f.read())


def archive_size_mb(archive_path: Path) -> float:
    return archive_path.stat().st_size / (1024 * 1024)


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


def restore_archive(archive_path: Path, fitops_dir: Path, db_path: Path) -> list[str]:
    """Extract an archive into the FitOps data directory.

    The database member ("fitops.db") is extracted to ``db_path``.
    Everything else lands in ``fitops_dir``.

    Returns:
        List of items restored (arcnames).
    """
    fitops_dir.mkdir(parents=True, exist_ok=True)

    restored: list[str] = []
    tmp_db_path: Path | None = None

    with tarfile.open(archive_path, "r:gz") as tar:
        db_member = next(
            (member for member in tar.getmembers() if member.name == "fitops.db"),
            None,
        )
        if db_member is not None:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = tempfile.NamedTemporaryFile(
                prefix=f".{db_path.name}.restore-",
                suffix=".tmp",
                dir=db_path.parent,
                delete=False,
            )
            tmp_db_path = Path(tmp.name)
            try:
                with tmp:
                    f = tar.extractfile(db_member)
                    if f is None:
                        raise ValueError(
                            "Backup database member is not a regular file."
                        )
                    shutil.copyfileobj(f, tmp)
                _validate_sqlite_db(tmp_db_path)
            except Exception:
                tmp_db_path.unlink(missing_ok=True)
                raise

        for member in tar.getmembers():
            if member.name == MANIFEST_NAME:
                continue

            if member.name == "fitops.db":
                continue
            else:
                tar.extract(member, path=fitops_dir, filter="data")
                restored.append(member.name)

    if tmp_db_path is not None:
        try:
            _remove_sqlite_sidecars(db_path)
            tmp_db_path.replace(db_path)
            _remove_sqlite_sidecars(db_path)
            restored.insert(0, "fitops.db")
        finally:
            tmp_db_path.unlink(missing_ok=True)

    return restored
