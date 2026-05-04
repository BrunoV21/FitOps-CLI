"""fitops deploy — deploy FitOps dashboard to cloud providers."""

from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("hf")
def deploy_hf(
    hf_token: str = typer.Option(
        ...,
        "--hf-token",
        envvar="HF_TOKEN",
        help="HuggingFace write PAT.",
    ),
    hf_repo: str = typer.Option(
        ...,
        "--hf-repo",
        help="HF Space repo ID (e.g. myuser/fitops-dashboard).",
    ),
    github_backup_token: str = typer.Option(
        ...,
        "--github-token",
        envvar="GITHUB_BACKUP_TOKEN",
        help="GitHub PAT with read access to the backup repo.",
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

    # Generate TOTP secret and display QR code
    totp_secret = generate_secret()
    uri = provisioning_uri(totp_secret, account=hf_repo)
    typer.echo("Scan this QR code with your authenticator app:\n")
    print_qr(uri)
    typer.echo(f"\nManual entry key: {totp_secret}\n")
    typer.confirm("Have you saved the TOTP key in your authenticator?", abort=True)

    # Collect and hash password
    password = typer.prompt(
        "Set a dashboard password", hide_input=True, confirmation_prompt=True
    )
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    # Generate random secrets
    session_secret = _secrets.token_hex(32)
    sync_token = _secrets.token_hex(32)

    typer.echo("\nCreating HuggingFace Space…")

    api = HfApi(token=hf_token)

    api.create_repo(
        repo_id=hf_repo,
        repo_type="space",
        space_sdk="docker",
        exist_ok=True,
        private=True,
    )

    # Upload container files
    _cloud_dir = Path(__file__).parent.parent / "cloud" / "hf_space"
    for fname in ("Dockerfile", "startup.sh"):
        api.upload_file(
            path_or_fileobj=str(_cloud_dir / fname),
            path_in_repo=fname,
            repo_id=hf_repo,
            repo_type="space",
        )

    # Set Space secrets
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

    typer.echo(f"\n  Space:   {space_url}")
    typer.echo(f"  App URL: {app_url}")
    typer.echo(
        f"\n  Sync token (add as repo secret FITOPS_SYNC_TOKEN):\n  {sync_token}\n"
    )

    _print_gha_yaml(app_url=app_url)


def _print_gha_yaml(app_url: str) -> None:
    # Note: {{ and }} in f-strings produce literal { } in the output,
    # which is what GitHub Actions expects for ${{ secrets.X }}.
    yaml = f"""\
Add this workflow to your backup repo at .github/workflows/fitops.yml:

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
    typer.echo(yaml)
