from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fitops.config.settings import get_settings

REVISION_KEY = "dataset_revision"
LAST_SUCCESS_KEY = "last_successful_backup"
LAST_SKIP_KEY = "last_backup_skip"


def _db_path() -> Path:
    return get_settings().db_path


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def _set_value(conn: sqlite3.Connection, key: str, value: Any) -> None:
    payload = json.dumps(value, sort_keys=True, default=str)
    conn.execute(
        """
        INSERT INTO backup_state (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, payload, _now()),
    )


def _get_value(conn: sqlite3.Connection, key: str) -> Any | None:
    row = conn.execute(
        "SELECT value FROM backup_state WHERE key = ?", (key,)
    ).fetchone()
    if row is None or row[0] is None:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return row[0]


def get_dataset_revision(db_path: Path | None = None) -> int:
    path = db_path or _db_path()
    if not path.exists():
        return 0
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            value = _get_value(conn, REVISION_KEY)
    except sqlite3.Error:
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def mark_dataset_changed(reason: str, scope: str = "data") -> int | None:
    try:
        with _connect() as conn:
            current = _get_value(conn, REVISION_KEY)
            try:
                revision = int(current or 0) + 1
            except (TypeError, ValueError):
                revision = 1
            _set_value(conn, REVISION_KEY, revision)
            _set_value(
                conn,
                "last_dataset_change",
                {
                    "reason": reason,
                    "scope": scope,
                    "revision": revision,
                    "changed_at": _now(),
                },
            )
            return revision
    except sqlite3.Error:
        return None


def get_last_successful_backup() -> dict | None:
    try:
        with sqlite3.connect(f"file:{_db_path()}?mode=ro", uri=True) as conn:
            value = _get_value(conn, LAST_SUCCESS_KEY)
    except sqlite3.Error:
        return None
    return value if isinstance(value, dict) else None


def get_last_backup_skip() -> dict | None:
    try:
        with sqlite3.connect(f"file:{_db_path()}?mode=ro", uri=True) as conn:
            value = _get_value(conn, LAST_SKIP_KEY)
    except sqlite3.Error:
        return None
    return value if isinstance(value, dict) else None


def record_backup_skip(reason: str, signature: str | None, trigger: str) -> None:
    try:
        with _connect() as conn:
            _set_value(
                conn,
                LAST_SKIP_KEY,
                {
                    "reason": reason,
                    "dataset_signature": signature,
                    "trigger": trigger,
                    "skipped_at": _now(),
                },
            )
            conn.execute(
                """
                INSERT INTO backup_history
                    (provider, trigger, dataset_signature, status, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("github", trigger, signature, "skipped", reason, _now()),
            )
    except sqlite3.Error:
        return


def record_successful_backup(
    *,
    provider: str,
    remote_id: str | None,
    remote_name: str | None,
    origin: dict,
    trigger: str,
    dataset_signature: str,
    dataset_revision: int,
) -> None:
    payload = {
        "provider": provider,
        "remote_id": remote_id,
        "remote_name": remote_name,
        "origin": origin,
        "trigger": trigger,
        "dataset_signature": dataset_signature,
        "dataset_revision": dataset_revision,
        "created_at": _now(),
    }
    try:
        with _connect() as conn:
            _set_value(conn, LAST_SUCCESS_KEY, payload)
            conn.execute(
                """
                INSERT INTO backup_history
                    (
                        remote_id, remote_name, provider, origin_kind, origin_label,
                        origin_role, trigger, dataset_signature, dataset_revision,
                        status, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    remote_id,
                    remote_name,
                    provider,
                    origin.get("kind"),
                    origin.get("label"),
                    origin.get("role"),
                    trigger,
                    dataset_signature,
                    dataset_revision,
                    "success",
                    _now(),
                ),
            )
    except sqlite3.Error:
        return


def record_retention_deletion(
    *,
    provider: str,
    remote_id: str,
    remote_name: str,
    origin: dict | None,
) -> None:
    origin = origin or {}
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO backup_history
                    (
                        remote_id, remote_name, provider, origin_kind, origin_label,
                        origin_role, status, detail, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    remote_id,
                    remote_name,
                    provider,
                    origin.get("kind"),
                    origin.get("label"),
                    origin.get("role"),
                    "deleted",
                    "retention",
                    _now(),
                ),
            )
    except sqlite3.Error:
        return


def should_skip_backup(signature: str, force: bool = False) -> tuple[bool, str | None]:
    if force:
        return False, None
    last = get_last_successful_backup()
    if last and last.get("dataset_signature") == signature:
        return True, "dataset unchanged since last successful backup"
    return False, None
