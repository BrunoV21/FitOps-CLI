"""Shared HuggingFace Space deployment helpers.

Both the local CLI and the hosted deploy API use this module. Keep all external
API calls here so wrappers only handle interaction style and security policy.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_GH_API = "https://api.github.com"
_GH_WORKFLOW_PATH = ".github/workflows/fitops.yml"
_REPO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")

ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class HfDeployRequest:
    hf_token: str
    hf_repo: str | None
    github_backup_token: str
    github_backup_repo: str
    pw_hash: str
    totp_secret: str
    session_secret: str
    sync_token: str
    strava_client_id: str | None = None
    strava_client_secret: str | None = None
    github_repo_prevalidated: bool = False


@dataclass(frozen=True)
class HfDeployResult:
    hf_repo: str
    space_url: str
    app_url: str
    webhook_url: str
    callback_domain: str

    @property
    def app_url_display(self) -> str:
        return f"{self.app_url}/"


def deploy_hf_space(
    request: HfDeployRequest,
    *,
    progress: ProgressCallback | None = None,
) -> HfDeployResult:
    """Create/update the FitOps HF Space and backup repo workflow."""

    def emit(message: str) -> None:
        if progress:
            progress(message)

    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError(
            "huggingface-hub is required. Install with: pip install 'fitops[server]'"
        ) from exc

    if not request.github_repo_prevalidated:
        emit("Checking GitHub backup repo...")
        validate_github_repo(request.github_backup_token, request.github_backup_repo)
        emit(f"GitHub backup repo is accessible: {request.github_backup_repo}")

    api = HfApi(token=request.hf_token)
    hf_repo = request.hf_repo
    if hf_repo is None:
        username = api.whoami()["name"]
        hf_repo = f"{username}/fitops-dashboard"
        emit(f"No HF Space repo provided; using {hf_repo}")
    else:
        validate_repo_id(hf_repo, label="HF Space repo")

    validate_repo_id(request.github_backup_repo, label="GitHub backup repo")

    emit("Creating HuggingFace Space...")
    api.create_repo(
        repo_id=hf_repo,
        repo_type="space",
        space_sdk="docker",
        exist_ok=True,
        private=True,
    )

    cloud_dir = Path(__file__).parent / "hf_space"
    for fname in ("Dockerfile", "startup.sh"):
        emit(f"Uploading {fname} to HuggingFace Space...")
        api.upload_file(
            path_or_fileobj=str(cloud_dir / fname),
            path_in_repo=fname,
            repo_id=hf_repo,
            repo_type="space",
        )

    owner, space_name = hf_repo.split("/", 1)
    app_url = f"https://{owner}-{space_name}.hf.space"
    webhook_url = f"{app_url}/api/strava/webhook"
    result = HfDeployResult(
        hf_repo=hf_repo,
        space_url=f"https://huggingface.co/spaces/{hf_repo}",
        app_url=app_url,
        webhook_url=webhook_url,
        callback_domain=f"{owner}-{space_name}.hf.space",
    )

    emit("Setting HuggingFace Space secrets...")
    space_secrets = build_hf_space_secrets(
        pw_hash=request.pw_hash,
        totp_secret=request.totp_secret,
        session_secret=request.session_secret,
        sync_token=request.sync_token,
        public_base_url=result.app_url,
        webhook_url=result.webhook_url,
        github_backup_token=request.github_backup_token,
        github_backup_repo=request.github_backup_repo,
        strava_client_id=request.strava_client_id,
        strava_client_secret=request.strava_client_secret,
    )
    for key, value in space_secrets.items():
        api.add_space_secret(repo_id=hf_repo, key=key, value=value)
        emit(f"Set Space secret {key}")

    emit("Configuring GitHub Actions keepalive workflow...")
    setup_github_actions(
        request.github_backup_token,
        request.github_backup_repo,
        result.app_url,
        request.sync_token,
        progress=emit,
    )
    emit("Deployment complete.")
    return result


def validate_repo_id(repo: str, *, label: str = "repo") -> None:
    if not _REPO_ID_RE.match(repo):
        raise ValueError(f"{label} must be in 'owner/name' format.")
    if ".." in repo or repo.startswith("/") or repo.endswith("/"):
        raise ValueError(f"{label} contains unsupported path characters.")


def build_hf_space_secrets(
    *,
    pw_hash: str,
    totp_secret: str,
    session_secret: str,
    sync_token: str,
    public_base_url: str,
    webhook_url: str,
    github_backup_token: str,
    github_backup_repo: str,
    strava_client_id: str | None = None,
    strava_client_secret: str | None = None,
) -> dict[str, str]:
    secrets = {
        "FITOPS_AUTH_ENABLED": "true",
        "FITOPS_PASSWORD_HASH": pw_hash,
        "FITOPS_TOTP_SECRET": totp_secret,
        "FITOPS_SESSION_SECRET": session_secret,
        "FITOPS_SYNC_TOKEN": sync_token,
        "FITOPS_PUBLIC_BASE_URL": public_base_url.rstrip("/"),
        "FITOPS_WEBHOOK_CALLBACK_URL": webhook_url,
        "FITOPS_DEFAULT_SYNC_MODE": "webhook",
        "FITOPS_INSTANCE_KIND": "hf-space",
        "FITOPS_INSTANCE_LABEL": webhook_url.split("/api/", 1)[0].replace(
            "https://", ""
        ),
        "FITOPS_INSTANCE_ROLE": "primary",
        "GITHUB_BACKUP_TOKEN": github_backup_token,
        "GITHUB_BACKUP_REPO": github_backup_repo,
    }
    if strava_client_id and strava_client_secret:
        secrets["FITOPS_STRAVA_CLIENT_ID"] = strava_client_id
        secrets["FITOPS_STRAVA_CLIENT_SECRET"] = strava_client_secret
    return secrets


def format_webhook_setup_message(owner: str, space_name: str, webhook_url: str) -> str:
    callback_domain = f"{owner}-{space_name}.hf.space"
    return (
        "\nStrava webhook sync:\n"
        f"  Configured webhook URL: {webhook_url}\n"
        "  FitOps saved this URL in the HuggingFace Space as "
        "FITOPS_WEBHOOK_CALLBACK_URL.\n\n"
        "  To make Strava accept it, add this Authorization Callback Domain "
        "in your Strava API app:\n"
        f"    {callback_domain}\n\n"
        "  Do not paste the full webhook URL into Strava's domain field. "
        "Use the domain only.\n"
        "  The webhook subscription will be registered automatically after "
        "Strava auth is restored or completed.\n\n"
        "  Then push your local data and Strava credentials to the backup:\n"
        "    fitops backup create --to github"
    )


def gh_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def validate_github_repo(token: str, repo: str) -> None:
    import requests

    validate_repo_id(repo, label="GitHub backup repo")
    try:
        resp = requests.get(
            f"{_GH_API}/repos/{repo}",
            headers=gh_headers(token),
            timeout=10,
        )
    except requests.ConnectionError as exc:
        raise RuntimeError("Could not reach GitHub API.") from exc

    if resp.status_code == 200:
        return
    if resp.status_code in (401, 403):
        raise RuntimeError(
            f"GitHub token was rejected for '{repo}' (HTTP {resp.status_code}). "
            "Ensure the PAT has the 'repo' scope."
        )
    if resp.status_code == 404:
        raise RuntimeError(
            f"GitHub repo '{repo}' not found. Check the name, or add the 'repo' "
            "scope to your PAT for private repos."
        )
    raise RuntimeError(f"GitHub API returned {resp.status_code}.")


def setup_github_actions(
    token: str,
    repo: str,
    app_url: str,
    sync_token: str,
    *,
    progress: ProgressCallback | None = None,
) -> None:
    import base64

    import requests

    def emit(message: str) -> None:
        if progress:
            progress(message)

    validate_repo_id(repo, label="GitHub backup repo")
    s = requests.Session()
    s.headers.update(gh_headers(token))

    workflow_content = build_gha_yaml(app_url)
    encoded = base64.b64encode(workflow_content.encode()).decode()

    sha: str | None = None
    check = s.get(f"{_GH_API}/repos/{repo}/contents/{_GH_WORKFLOW_PATH}", timeout=10)
    if check.status_code == 200:
        sha = check.json()["sha"]
    elif check.status_code != 404:
        check.raise_for_status()

    payload: dict[str, str] = {
        "message": "ci: add FitOps keepalive & sync workflow",
        "content": encoded,
    }
    if sha:
        payload["sha"] = sha
        payload["message"] = "ci: update FitOps keepalive & sync workflow"

    s.put(
        f"{_GH_API}/repos/{repo}/contents/{_GH_WORKFLOW_PATH}",
        json=payload,
        timeout=10,
    ).raise_for_status()
    emit(f"{'Updated' if sha else 'Created'} {_GH_WORKFLOW_PATH}")

    pk_resp = s.get(f"{_GH_API}/repos/{repo}/actions/secrets/public-key", timeout=10)
    pk_resp.raise_for_status()
    pk_data = pk_resp.json()

    encrypted = encrypt_github_secret(pk_data["key"], sync_token)
    s.put(
        f"{_GH_API}/repos/{repo}/actions/secrets/FITOPS_SYNC_TOKEN",
        json={"encrypted_value": encrypted, "key_id": pk_data["key_id"]},
        timeout=10,
    ).raise_for_status()
    emit("Set repo secret FITOPS_SYNC_TOKEN")


def encrypt_github_secret(public_key_b64: str, secret_value: str) -> str:
    from base64 import b64encode

    from nacl import encoding, public

    pk = public.PublicKey(public_key_b64.encode(), encoding.Base64Encoder)
    sealed = public.SealedBox(pk).encrypt(secret_value.encode())
    return b64encode(sealed).decode()


def build_gha_yaml(app_url: str) -> str:
    return f"""\
---
name: FitOps Keepalive

on:
  schedule:
    - cron: '*/20 * * * *'
  push:
    branches: [main]

jobs:
  keepalive:
    runs-on: ubuntu-latest
    steps:
      - name: Ping health endpoint
        run: curl -sf {app_url}/health || echo "Health check failed (Space may be cold-starting)"
"""
