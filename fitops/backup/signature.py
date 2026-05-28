from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from fitops.backup.state import get_dataset_revision
from fitops.config.settings import get_settings

SIGNATURE_VERSION = 1

_TABLES: tuple[str, ...] = (
    "activities",
    "activity_streams",
    "activity_laps",
    "activity_weather",
    "analytics_snapshots",
    "athletes",
    "notes",
    "race_courses",
    "race_plans",
    "race_sessions",
    "workouts",
    "workout_activity_links",
    "workout_segments",
)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _scalar(conn: sqlite3.Connection, sql: str) -> Any:
    row = conn.execute(sql).fetchone()
    return row[0] if row else None


def _table_summary(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    if not _table_exists(conn, table):
        return {"exists": False}

    columns = _table_columns(conn, table)
    summary: dict[str, Any] = {
        "exists": True,
        "count": _scalar(conn, f"SELECT COUNT(*) FROM {table}"),
    }
    if "id" in columns:
        summary["max_id"] = _scalar(conn, f"SELECT MAX(id) FROM {table}")
    for col in ("updated_at", "created_at", "computed_at", "stamped_at"):
        if col in columns:
            summary[f"max_{col}"] = _scalar(conn, f"SELECT MAX({col}) FROM {table}")
    return summary


def _config_payload(fitops_dir: Path) -> dict:
    path = fitops_dir / "config.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"_unparseable_sha256": _hash_bytes(path.read_bytes())}

    backup = data.get("backup")
    if isinstance(backup, dict):
        backup = dict(backup)
        schedule = backup.get("schedule")
        if isinstance(schedule, dict):
            schedule = dict(schedule)
            schedule.pop("last_backup_at", None)
            schedule.pop("last_checked_at", None)
            backup["schedule"] = schedule
        data = dict(data)
        data["backup"] = backup
    return data


def _file_tree_summary(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        try:
            data = path.read_bytes()
        except OSError:
            continue
        rows.append({"path": rel, "size": len(data), "sha256": _hash_bytes(data)})
    return rows


def dataset_fingerprint(
    db_path: Path | None = None, fitops_dir: Path | None = None
) -> dict[str, Any]:
    settings = get_settings()
    db_path = db_path or settings.db_path
    fitops_dir = fitops_dir or settings.fitops_dir

    payload: dict[str, Any] = {
        "version": SIGNATURE_VERSION,
        "revision": get_dataset_revision(db_path),
        "tables": {},
        "files": {
            "notes": _file_tree_summary(fitops_dir / "notes"),
            "workouts": _file_tree_summary(fitops_dir / "workouts"),
        },
        "config": _config_payload(fitops_dir),
    }

    if db_path.exists():
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                for table in _TABLES:
                    payload["tables"][table] = _table_summary(conn, table)
        except sqlite3.Error as exc:
            payload["db_error"] = str(exc)

    return payload


def dataset_signature(
    db_path: Path | None = None, fitops_dir: Path | None = None
) -> str:
    payload = dataset_fingerprint(db_path=db_path, fitops_dir=fitops_dir)
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return f"sha256:{_hash_bytes(encoded)}"


def short_signature(signature: str) -> str:
    return signature.split(":", 1)[-1][:12]
