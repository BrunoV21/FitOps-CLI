"""fitops deploy — deploy FitOps dashboard to cloud providers."""

from __future__ import annotations

import secrets as _secrets

import typer

from fitops.cloud import deploy_hf as _hf
from fitops.cloud.deploy_hf import HfDeployRequest, deploy_hf_space

app = typer.Typer(no_args_is_help=True, add_completion=False)

_build_gha_yaml = _hf.build_gha_yaml
_build_hf_space_secrets = _hf.build_hf_space_secrets
_encrypt_github_secret = _hf.encrypt_github_secret
_format_webhook_setup_message = _hf.format_webhook_setup_message
_gh_headers = _hf.gh_headers
_setup_github_actions = _hf.setup_github_actions
_validate_github_repo = _hf.validate_github_repo


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
    strava_client_id: str | None = typer.Option(
        None,
        "--strava-client-id",
        help="Optional Strava app Client ID to prefill deployed setup.",
    ),
    strava_client_secret: str | None = typer.Option(
        None,
        "--strava-client-secret",
        help="Optional Strava app Client Secret to prefill deployed setup.",
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
        import huggingface_hub  # noqa: F401
    except ImportError:
        typer.echo(
            "Error: huggingface-hub not installed. Run: pip install 'fitops[server]'",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo("=== FitOps HuggingFace Deploy ===\n")

    if bool(strava_client_id) != bool(strava_client_secret):
        typer.echo(
            "Error: --strava-client-id and --strava-client-secret must be provided together.",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo("Checking GitHub backup repo...")
    try:
        _validate_github_repo(github_backup_token, github_backup_repo)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"  ✓ {github_backup_repo} is accessible\n")

    totp_secret = generate_secret()
    account = hf_repo or "fitops-dashboard"
    uri = provisioning_uri(totp_secret, account=account)
    typer.echo("Scan this QR code with your authenticator app:\n")
    print_qr(uri)
    typer.echo(f"\nManual entry key: {totp_secret}\n")
    typer.confirm("Have you saved the TOTP key in your authenticator?", abort=True)

    password = typer.prompt(
        "Set a dashboard password", hide_input=True, confirmation_prompt=True
    )
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    request = HfDeployRequest(
        hf_token=hf_token,
        hf_repo=hf_repo,
        github_backup_token=github_backup_token,
        github_backup_repo=github_backup_repo,
        pw_hash=pw_hash,
        totp_secret=totp_secret,
        session_secret=_secrets.token_hex(32),
        sync_token=_secrets.token_hex(32),
        strava_client_id=strava_client_id,
        strava_client_secret=strava_client_secret,
        github_repo_prevalidated=True,
    )

    try:
        result = deploy_hf_space(
            request,
            progress=lambda message: typer.echo(f"  {message}"),
        )
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n  Space:   {result.space_url}")
    typer.echo(f"  App URL: {result.app_url_display}")
    typer.echo("\nDone! Your dashboard will be live in a few minutes.")
    typer.echo(f"\n  Dashboard → {result.app_url_display}")
    owner, space_name = result.hf_repo.split("/", 1)
    typer.echo(_format_webhook_setup_message(owner, space_name, result.webhook_url))
