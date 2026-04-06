from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RemoteBackup:
    """Metadata for a single backup stored on a remote provider."""

    id: str  # Provider-specific identifier (release id, file id, …)
    name: str  # Human-readable filename
    created_at: str  # ISO-8601 string
    size_bytes: int
    download_url: str


class BackupProvider(ABC):
    """Abstract interface that every cloud backup provider must implement."""

    @abstractmethod
    def upload(self, archive_path: Path) -> RemoteBackup:
        """Upload *archive_path* and return metadata for the stored backup."""

    @abstractmethod
    def download(self, backup: RemoteBackup, dest: Path) -> Path:
        """Download *backup* into directory *dest*.  Returns the local file path."""

    @abstractmethod
    def list_backups(self) -> list[RemoteBackup]:
        """Return all available remote backups, newest first."""

    @abstractmethod
    def delete(self, backup: RemoteBackup) -> None:
        """Permanently delete a remote backup."""
