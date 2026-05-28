from __future__ import annotations

import os
import platform
import uuid
from dataclasses import asdict, dataclass

from fitops.config.settings import get_settings


@dataclass(frozen=True)
class BackupOrigin:
    kind: str
    label: str
    role: str
    instance_id: str
    hostname: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _instance_id() -> str:
    settings = get_settings()
    path = settings.fitops_dir / "instance_id"
    if path.exists():
        value = path.read_text().strip()
        if value:
            return value

    value = uuid.uuid4().hex
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n")
    return value


def resolve_origin() -> BackupOrigin:
    hostname = platform.node() or "unknown"
    kind = (os.environ.get("FITOPS_INSTANCE_KIND") or "local").strip() or "local"
    role = (
        os.environ.get("FITOPS_INSTANCE_ROLE") or "secondary"
    ).strip() or "secondary"
    label = (os.environ.get("FITOPS_INSTANCE_LABEL") or hostname).strip() or hostname
    return BackupOrigin(
        kind=kind,
        label=label,
        role=role,
        instance_id=_instance_id(),
        hostname=hostname,
    )


def origin_slug(origin: BackupOrigin | None = None) -> str:
    origin = origin or resolve_origin()
    raw = f"{origin.kind}-{origin.label}"
    chars = []
    for ch in raw.lower():
        chars.append(ch if ch.isalnum() else "-")
    slug = "-".join(part for part in "".join(chars).split("-") if part)
    return slug[:80] or "unknown"
