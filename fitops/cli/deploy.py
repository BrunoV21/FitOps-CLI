"""fitops deploy — deploy FitOps dashboard to cloud providers."""

from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)

_GH_API = "https://api.github.com"
_GH_WORKFLOW_PATH = ".github/workflows/fitops.yml"


@app.command("hf")
def deploy_hf(
    hf_token: str = typer.Option(
        ...,
        "--hf-token",
        envvar="HF_TOKEN",
        help="HuggingFace write PAT.",
    ),
    hf_repo: str | None = typer.Option(
        None,
        "--hf-repo",
        help="HF Space repo ID (e.g. myuser/fitops-dashboard). Auto-generated from your HF username if omitted.",
    ),
    github_backup_token: str = typer.Option(
        ...,
        "--github-token",
        envvar="GITHUB_BACKUP_TOKEN",
        help="GitHub PAT with repo scope (read + secrets write) on the backup repo.",
    ),
    github_backup_repo: str = typer.Option(
        ...,
        "--github-repo",
        help="GitHub backup repo (e.g. myuser/fitops-backups).",
    ),
) -> None:
    """Deploy the FitOps dashboard to a HuggingFace Space with 2FA auth."""
    try:
        import bcrypt

        from fitops.auth.totp import generate_secret, print_qr, provisioning_uri
    except ImportError:
        typer.echo(
            "Error: fitops[server] is required. Run: pip install 'fitops[server]'",
            err=True,
        )
        raise typer.Exit(1)

    try:
        from huggingface_hub import HfApi
    except ImportError:
        typer.echo(
            "Error: huggingface-hub not installed. Run: pip install 'fitops[server]'",
            err=True,
        )
        raise typer.Exit(1)

    import secrets as _secrets
    from pathlib import Path

    typer.echo("=== FitOps HuggingFace Deploy ===\n")

    # ── Step 1: validate GitHub backup repo before any interactive prompts ──
    typer.echo("Checking GitHub backup repo…")
    _validate_github_repo(github_backup_token, github_backup_repo)
    typer.echo(f"  ✓ {github_backup_repo} is accessible\n")

    # ── Step 2: resolve HF repo name ────────────────────────────────────────
    api = HfApi(token=hf_token)

    if hf_repo is None:
        username = api.whoami()["name"]
        hf_repo = f"{username}/fitops-dashboard"
        typer.echo(f"No --hf-repo provided — using: {hf_repo}\n")

    # ── Step 3: TOTP setup ──────────────────────────────────────────────────
    totp_secret = generate_secret()
    uri = provisioning_uri(totp_secret, account=hf_repo)
    typer.echo("Scan this QR code with your authenticator app:\n")
    print_qr(uri)
    typer.echo(f"\nManual entry key: {totp_secret}\n")
    typer.confirm("Have you saved the TOTP key in your authenticator?", abort=True)

    # ── Step 4: password ────────────────────────────────────────────────────
    password = typer.prompt(
        "Set a dashboard password", hide_input=True, confirmation_prompt=True
    )
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    # ── Step 5: generate random secrets ────────────────────────────────────
    session_secret = _secrets.token_hex(32)
    sync_token = _secrets.token_hex(32)

    # ── Step 6: create HF Space ─────────────────────────────────────────────
    typer.echo("\nCreating HuggingFace Space…")

    api.create_repo(
        repo_id=hf_repo,
        repo_type="space",
        space_sdk="docker",
        exist_ok=True,
        private=True,
    )

    _cloud_dir = Path(__file__).parent.parent / "cloud" / "hf_space"
    for fname in ("Dockerfile", "startup.sh"):
        api.upload_file(
            path_or_fileobj=str(_cloud_dir / fname),
            path_in_repo=fname,
            repo_id=hf_repo,
            repo_type="space",
        )

    space_secrets = {
        "FITOPS_AUTH_ENABLED": "true",
        "FITOPS_PASSWORD_HASH": pw_hash,
        "FITOPS_TOTP_SECRET": totp_secret,
        "FITOPS_SESSION_SECRET": session_secret,
        "FITOPS_SYNC_TOKEN": sync_token,
        "GITHUB_BACKUP_TOKEN": github_backup_token,
        "GITHUB_BACKUP_REPO": github_backup_repo,
    }
    for key, value in space_secrets.items():
        api.add_space_secret(repo_id=hf_repo, key=key, value=value)

    owner, space_name = hf_repo.split("/", 1)
    space_url = f"https://huggingface.co/spaces/{hf_repo}"
    app_url = f"https://{owner}-{space_name}.hf.space"
    app_url_display = f"{app_url}/"
    webhook_url = f"{app_url}/api/strava/webhook"

    typer.echo(f"  Space:   {space_url}")
    typer.echo(f"  App URL: {app_url_display}")

    # ── Step 7: configure GitHub Actions automatically ──────────────────────
    typer.echo("\nConfiguring GitHub Actions on backup repo…")
    _setup_github_actions(github_backup_token, github_backup_repo, app_url, sync_token)

    typer.echo("\nDone! Your dashboard will be live in a few minutes.")
    typer.echo(f"\n  Dashboard → {app_url_display}")
    typer.echo("\nStrava webhook sync:")
    typer.echo(f"  Callback URL: {webhook_url}")
    typer.echo(f"  Strava app callback domain: {owner}-{space_name}.hf.space")
    typer.echo(
        "  After the Space is live, enable it with:\n"
        f"    fitops webhooks setup --callback-url {webhook_url}\n"
        "    fitops backup create --to github"
    )


# ── GitHub helpers ───────────────────────────────────────────────────────────


def _gh_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _validate_github_repo(token: str, repo: str) -> None:
    import requests

    if "/" not in repo:
        typer.echo(
            f"Error: --github-repo must be in 'owner/repo' format, got '{repo}'.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        resp = requests.get(
            f"{_GH_API}/repos/{repo}",
            headers=_gh_headers(token),
            timeout=10,
        )
    except requests.ConnectionError:
        typer.echo("Error: Could not reach GitHub API.", err=True)
        raise typer.Exit(1)

    if resp.status_code == 200:
        return
    if resp.status_code in (401, 403):
        typer.echo(
            f"Error: GitHub token was rejected for '{repo}' (HTTP {resp.status_code}). "
            "Ensure the PAT has the 'repo' scope.",
            err=True,
        )
        raise typer.Exit(1)
    if resp.status_code == 404:
        typer.echo(
            f"Error: GitHub repo '{repo}' not found. "
            "Check the name, or add the 'repo' scope to your PAT for private repos.",
            err=True,
        )
        raise typer.Exit(1)
    typer.echo(f"Error: GitHub API returned {resp.status_code}.", err=True)
    raise typer.Exit(1)


def _setup_github_actions(
    token: str,
    repo: str,
    app_url: str,
    sync_token: str,
) -> None:
    import base64

    import requests

    s = requests.Session()
    s.headers.update(_gh_headers(token))

    workflow_content = _build_gha_yaml(app_url)
    encoded = base64.b64encode(workflow_content.encode()).decode()

    # Check if workflow file already exists (need sha to update)
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
    typer.echo(f"  {'Updated' if sha else 'Created'} {_GH_WORKFLOW_PATH}")

    # Set FITOPS_SYNC_TOKEN repo secret
    pk_resp = s.get(f"{_GH_API}/repos/{repo}/actions/secrets/public-key", timeout=10)
    pk_resp.raise_for_status()
    pk_data = pk_resp.json()

    encrypted = _encrypt_github_secret(pk_data["key"], sync_token)
    s.put(
        f"{_GH_API}/repos/{repo}/actions/secrets/FITOPS_SYNC_TOKEN",
        json={"encrypted_value": encrypted, "key_id": pk_data["key_id"]},
        timeout=10,
    ).raise_for_status()
    typer.echo("  Set repo secret FITOPS_SYNC_TOKEN")


def _encrypt_github_secret(public_key_b64: str, secret_value: str) -> str:
    from base64 import b64encode

    from nacl import encoding, public

    pk = public.PublicKey(public_key_b64.encode(), encoding.Base64Encoder)
    sealed = public.SealedBox(pk).encrypt(secret_value.encode())
    return b64encode(sealed).decode()


def _build_gha_yaml(app_url: str) -> str:
    # {{ and }} in f-strings produce literal { } — what GitHub Actions expects.
    return f"""\
---
name: FitOps Keepalive & Sync

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

  sync:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - name: Trigger dashboard sync
        run: |
          curl -sf -X POST {app_url}/api/internal/sync \\
            -H "X-Sync-Token: ${{{{ secrets.FITOPS_SYNC_TOKEN }}}}" \\
            || echo "Sync trigger failed"
"""
