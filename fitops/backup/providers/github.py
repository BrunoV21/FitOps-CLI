"""GitHub Releases backup provider.

Each FitOps backup is stored as a GitHub Release on a user-supplied private
repository.  The release tag is derived from the archive filename so backups
are easy to identify directly on GitHub.

Authentication: a Personal Access Token (PAT) with the ``repo`` scope.
No extra dependencies — uses ``httpx`` which is already in the project.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from fitops.backup.providers.base import BackupProvider, RemoteBackup

_API = "https://api.github.com"
_UPLOAD = "https://uploads.github.com"


class GitHubProvider(BackupProvider):
    def __init__(self, token: str, repo: str) -> None:
        """
        Args:
            token: GitHub PAT with ``repo`` scope.
            repo:  Repository in ``owner/name`` format.
        """
        self._token = token
        self._repo = repo

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self, *, content_type: str = "application/json") -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": content_type,
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=60)

    @staticmethod
    def _to_remote(release: dict) -> RemoteBackup:
        assets = release.get("assets", [])
        # The first .tar.gz asset is our archive
        asset = next((a for a in assets if a["name"].endswith(".tar.gz")), None)
        return RemoteBackup(
            id=str(release["id"]),
            name=asset["name"] if asset else release["tag_name"],
            created_at=release["created_at"],
            size_bytes=asset["size"] if asset else 0,
            download_url=asset["url"] if asset else "",
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def upload(self, archive_path: Path) -> RemoteBackup:
        tag = archive_path.stem.replace(".tar", "")  # strip double extension
        # tarfile names end in .tar.gz — stem strips only the last suffix
        # so let's derive a clean tag from the filename
        name = archive_path.name
        tag = name.replace(".tar.gz", "")

        with self._client() as client:
            # 1. Create a release
            resp = client.post(
                f"{_API}/repos/{self._repo}/releases",
                headers=self._headers(),
                json={
                    "tag_name": tag,
                    "name": name,
                    "body": "FitOps automated backup",
                    "draft": False,
                    "prerelease": False,
                },
            )
            _raise(resp)
            release = resp.json()
            upload_url_template = release["upload_url"]
            # Template looks like: …/assets{?name,label}
            upload_url = upload_url_template.split("{")[0]

            # 2. Upload the archive as a release asset
            data = archive_path.read_bytes()
            resp = client.post(
                upload_url,
                headers=self._headers(content_type="application/gzip"),
                params={"name": name},
                content=data,
                timeout=300,
            )
            _raise(resp)

        return self._to_remote(release)

    def download(self, backup: RemoteBackup, dest: Path) -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        local_path = dest / backup.name

        with self._client() as client:
            # GitHub requires Accept: application/octet-stream to get the raw file
            resp = client.get(
                backup.download_url,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/octet-stream",
                },
                follow_redirects=True,
                timeout=300,
            )
            _raise(resp)
            local_path.write_bytes(resp.content)

        return local_path

    def list_backups(self) -> list[RemoteBackup]:
        results: list[RemoteBackup] = []
        page = 1

        with self._client() as client:
            while True:
                resp = client.get(
                    f"{_API}/repos/{self._repo}/releases",
                    headers=self._headers(),
                    params={"per_page": 100, "page": page},
                )
                _raise(resp)
                releases = resp.json()
                if not releases:
                    break
                for r in releases:
                    # Only include releases that have a backup asset
                    assets = r.get("assets", [])
                    if any(a["name"].endswith(".tar.gz") for a in assets):
                        results.append(self._to_remote(r))
                page += 1

        # Already newest-first from the API but be explicit
        results.sort(key=lambda b: b.created_at, reverse=True)
        return results

    def delete(self, backup: RemoteBackup) -> None:
        with self._client() as client:
            resp = client.delete(
                f"{_API}/repos/{self._repo}/releases/{backup.id}",
                headers=self._headers(),
            )
            _raise(resp)


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------


def validate_config(token: str, repo: str) -> str:
    """Check that the PAT can access the repo.  Returns the repo full name."""
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{_API}/repos/{repo}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if resp.status_code == 401:
            raise ValueError("GitHub token is invalid or expired.")
        if resp.status_code == 404:
            raise ValueError(
                f"Repository '{repo}' not found. "
                "Check the name and that your token has 'repo' scope."
            )
        _raise(resp)
        return resp.json()["full_name"]


def _raise(resp: httpx.Response) -> None:
    if resp.is_error:
        try:
            msg = resp.json().get("message", resp.text)
        except Exception:
            msg = resp.text
        raise RuntimeError(f"GitHub API error {resp.status_code}: {msg}")
