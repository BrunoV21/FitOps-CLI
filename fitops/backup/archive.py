from __future__ import annotations

import json
import tarfile
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


def backup_filename() -> str:
    return f"fitops-backup-{_timestamp()}.tar.gz"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_archive(fitops_dir: Path, db_path: Path, dest: Path) -> Path:
    """Create a gzipped tar archive of the FitOps data directory.

    Args:
        fitops_dir: The ~/.fitops directory.
        db_path: Resolved path to the SQLite database file.
        dest: Directory where the archive will be written.

    Returns:
        Path to the created archive file.
    """
    dest.mkdir(parents=True, exist_ok=True)
    archive_path = dest / backup_filename()

    included: list[dict] = []

    with tarfile.open(archive_path, "w:gz") as tar:
        # Database — stored as "fitops.db" in the root of the archive regardless
        # of where the user has configured it on disk.
        if db_path.exists():
            tar.add(db_path, arcname="fitops.db")
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
            "files": included,
        }
        manifest_bytes = json.dumps(manifest, indent=2).encode()
        import io

        info = tarfile.TarInfo(name=MANIFEST_NAME)
        info.size = len(manifest_bytes)
        tar.addfile(info, io.BytesIO(manifest_bytes))

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

    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name == MANIFEST_NAME:
                continue

            if member.name == "fitops.db":
                # Extract DB to the configured db_path
                db_path.parent.mkdir(parents=True, exist_ok=True)
                f = tar.extractfile(member)
                if f is not None:
                    db_path.write_bytes(f.read())
                    restored.append(member.name)
            else:
                tar.extract(member, path=fitops_dir, filter="data")
                restored.append(member.name)

    return restored
