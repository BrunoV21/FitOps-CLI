"""fitops backup — create, restore and manage cloud backups."""

from __future__ import annotations

import tempfile
from pathlib import Path

import typer

from fitops.backup import archive as arc
from fitops.backup import config as bcfg
from fitops.config.settings import get_settings

app = typer.Typer(no_args_is_help=True)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _github_provider():
    """Return a configured GitHubProvider or abort with a helpful message."""
    from fitops.backup.providers.github import GitHubProvider

    cfg = bcfg.get_github_config()
    if not cfg:
        typer.echo(
            "GitHub backup is not configured. Run `fitops backup setup github` first.",
            err=True,
        )
        raise typer.Exit(1)
    return GitHubProvider(token=cfg["token"], repo=cfg["repo"])


def _resolve_provider(provider: str):
    if provider == "github":
        return _github_provider()
    typer.echo(f"Unknown provider '{provider}'.", err=True)
    raise typer.Exit(1)


def _default_backup_dir(settings) -> Path:
    return settings.fitops_dir / "backups"


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


@app.command("setup")
def setup(
    provider: str = typer.Argument(..., help="Provider to configure: github"),
) -> None:
    """Interactively configure a cloud backup provider."""
    if provider == "github":
        _setup_github()
    else:
        typer.echo(f"Unknown provider '{provider}'. Supported: github", err=True)
        raise typer.Exit(1)


def _setup_github() -> None:
    from fitops.backup.providers.github import validate_config

    typer.echo("Configure GitHub backup")
    typer.echo("  You need a private GitHub repository and a Personal Access Token")
    typer.echo("  with the 'repo' scope.\n")

    existing = bcfg.get_github_config()
    if existing:
        typer.echo(
            f"  Currently configured: {existing['repo']}  (token: ***{existing['token'][-4:]})"
        )
        if not typer.confirm("  Overwrite existing config?", default=False):
            raise typer.Exit(0)

    token = typer.prompt("  GitHub Personal Access Token", hide_input=True)
    repo = typer.prompt("  Repository (owner/name)")

    typer.echo("\n  Validating credentials…")
    try:
        full_name = validate_config(token, repo)
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"  Error: {exc}", err=True)
        raise typer.Exit(1)

    bcfg.save_github_config(token, repo)
    typer.echo(f"  Saved. Repo: {full_name}")
    typer.echo("\n  Run `fitops backup create --to github` to push your first backup.")


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@app.command("create")
def create(
    to: str | None = typer.Option(
        None, "--to", help="Push to a cloud provider after creating (e.g. github)."
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directory for the local archive. Defaults to ~/.fitops/backups/.",
    ),
    keep_local: bool = typer.Option(
        True,
        "--keep-local/--no-keep-local",
        help="Keep the local archive after uploading to the cloud.",
    ),
) -> None:
    """Create a backup archive of all FitOps data."""
    settings = get_settings()
    dest = output_dir or _default_backup_dir(settings)

    typer.echo("Creating backup archive…")
    archive_path = arc.create_archive(
        fitops_dir=settings.fitops_dir,
        db_path=settings.db_path,
        dest=dest,
    )
    size_mb = arc.archive_size_mb(archive_path)
    typer.echo(f"  Archive: {archive_path}  ({size_mb:.1f} MB)")

    if to:
        provider = _resolve_provider(to)
        typer.echo(f"  Uploading to {to}…")
        remote = provider.upload(archive_path)
        typer.echo(f"  Uploaded: {remote.name}")

        if not keep_local:
            archive_path.unlink()
            typer.echo("  Local archive removed.")

    typer.echo("Done.")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@app.command("list")
def list_backups(
    provider: str | None = typer.Option(
        None,
        "--provider",
        "-p",
        help="List backups from a cloud provider (e.g. github).",
    ),
    local: bool = typer.Option(
        False, "--local", "-l", help="List locally stored archives."
    ),
) -> None:
    """List available backups (local and/or cloud)."""
    settings = get_settings()

    if local or (provider is None):
        backup_dir = _default_backup_dir(settings)
        archives = sorted(backup_dir.glob("fitops-backup-*.tar.gz"), reverse=True)
        if archives:
            typer.echo(f"Local backups ({backup_dir}):")
            for p in archives:
                size_mb = arc.archive_size_mb(p)
                typer.echo(f"  {p.name}  ({size_mb:.1f} MB)")
        else:
            typer.echo(f"No local backups found in {backup_dir}.")

    if provider:
        prov = _resolve_provider(provider)
        typer.echo(f"\nCloud backups ({provider}):")
        backups = prov.list_backups()
        if not backups:
            typer.echo("  No backups found.")
        for b in backups:
            size_mb = b.size_bytes / (1024 * 1024)
            typer.echo(f"  {b.name}  ({size_mb:.1f} MB)  {b.created_at}")


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------


@app.command("restore")
def restore(
    archive: Path | None = typer.Argument(
        None,
        help="Path to a local .tar.gz archive. If omitted, fetch from --from.",
    ),
    from_provider: str | None = typer.Option(
        None,
        "--from",
        help="Cloud provider to restore from (e.g. github).",
    ),
    backup_name: str | None = typer.Option(
        None,
        "--backup",
        "-b",
        help="Specific backup name to restore (from cloud list). "
        "If omitted, the most recent one is used.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Restore FitOps data from a backup archive.

    \b
    Examples:
      # Restore latest backup from GitHub
      fitops backup restore --from github

      # Restore a specific backup from GitHub
      fitops backup restore --from github --backup fitops-backup-2026-04-05-120000

      # Restore from a local file
      fitops backup restore ./fitops-backup-2026-04-05-120000.tar.gz
    """
    settings = get_settings()

    # ------------------------------------------------------------------
    # Resolve the archive to restore from
    # ------------------------------------------------------------------
    tmp_dir = None

    if archive is None and from_provider is None:
        typer.echo(
            "Provide either a local archive path or --from <provider>.", err=True
        )
        raise typer.Exit(1)

    if from_provider:
        prov = _resolve_provider(from_provider)
        backups = prov.list_backups()
        if not backups:
            typer.echo(f"No backups found on {from_provider}.", err=True)
            raise typer.Exit(1)

        if backup_name:
            match = next((b for b in backups if backup_name in b.name), None)
            if match is None:
                typer.echo(
                    f"Backup '{backup_name}' not found. "
                    "Run `fitops backup list --provider {from_provider}` to see available backups.",
                    err=True,
                )
                raise typer.Exit(1)
            chosen = match
        else:
            # Use the most recent
            chosen = backups[0]

        typer.echo(f"Downloading {chosen.name} from {from_provider}…")
        tmp_dir_obj = tempfile.TemporaryDirectory()
        tmp_dir = tmp_dir_obj  # keep alive until we're done extracting
        archive = prov.download(chosen, dest=Path(tmp_dir_obj.name))

    if archive is None or not archive.exists():
        typer.echo(f"Archive not found: {archive}", err=True)
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # Show manifest and confirm
    # ------------------------------------------------------------------
    try:
        manifest = arc.read_manifest(archive)
    except Exception:
        manifest = {}

    created_at = manifest.get("created_at", "unknown")
    files = manifest.get("files", [])

    typer.echo(f"\nRestoring from: {archive.name}")
    typer.echo(f"  Backup created: {created_at}")
    typer.echo(f"  Items: {len(files)}")
    typer.echo(
        "\n  WARNING: This will overwrite your current FitOps data, including "
        "fitops.db, config.json, notes and workouts."
    )

    if not yes:
        typer.confirm("\nProceed with restore?", abort=True)

    # ------------------------------------------------------------------
    # Extract
    # ------------------------------------------------------------------
    typer.echo("\nRestoring…")
    restored = arc.restore_archive(
        archive_path=archive,
        fitops_dir=settings.fitops_dir,
        db_path=settings.db_path,
    )
    for item in restored:
        typer.echo(f"  Restored: {item}")

    # Clean up temp dir if we downloaded from cloud
    if tmp_dir is not None:
        tmp_dir.cleanup()

    typer.echo("\nDone. Restart fitops to use the restored data.")


# ---------------------------------------------------------------------------
# schedule
# ---------------------------------------------------------------------------


@app.command("schedule")
def schedule(
    enable: bool | None = typer.Option(
        None, "--enable/--disable", help="Turn scheduled backups on or off."
    ),
    interval: int | None = typer.Option(
        None,
        "--interval",
        "-i",
        help="Interval in hours between backups (e.g. 6, 12, 24).",
    ),
    provider: str = typer.Option(
        "github", "--provider", "-p", help="Cloud provider to push to."
    ),
    status: bool = typer.Option(
        False, "--status", "-s", help="Print current schedule and exit."
    ),
) -> None:
    """Configure or view the automatic backup schedule.

    \b
    Examples:
      fitops backup schedule --status
      fitops backup schedule --enable --interval 24 --provider github
      fitops backup schedule --disable
    """
    current = bcfg.get_schedule_config()

    if status or (enable is None and interval is None):
        if not current:
            typer.echo(
                "No schedule configured. Use --enable --interval <hours> to set one up."
            )
        else:
            state = "ENABLED" if current["enabled"] else "DISABLED"
            typer.echo(f"Schedule: {state}")
            typer.echo(f"  Interval : every {current['interval_hours']}h")
            typer.echo(f"  Provider : {current['provider']}")
            typer.echo(f"  Last run : {current.get('last_backup_at') or 'never'}")
        return

    # Merge with existing config
    if current:
        resolved_enabled = enable if enable is not None else current["enabled"]
        resolved_interval = (
            interval if interval is not None else current["interval_hours"]
        )
        resolved_provider = provider or current["provider"]
    else:
        resolved_enabled = enable if enable is not None else True
        resolved_interval = interval or 24
        resolved_provider = provider

    if resolved_interval < 1:
        typer.echo("Interval must be at least 1 hour.", err=True)
        raise typer.Exit(1)

    bcfg.save_schedule_config(
        enabled=resolved_enabled,
        interval_hours=resolved_interval,
        provider=resolved_provider,
    )

    state = "enabled" if resolved_enabled else "disabled"
    typer.echo(f"Schedule {state}: every {resolved_interval}h → {resolved_provider}")
