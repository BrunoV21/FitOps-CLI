from __future__ import annotations

import typer

from fitops.docs_urls import CLI_DOCS

app = typer.Typer(
    name="fitops",
    help=(
        "FitOps-CLI — local Strava analytics with LLM-friendly output.\n\n"
        f"Docs: {CLI_DOCS['main']}"
    ),
    no_args_is_help=True,
    add_completion=False,
)


def _register_subapps() -> None:
    from fitops.cli.activities import app as activities_app
    from fitops.cli.analytics import app as analytics_app
    from fitops.cli.athlete import app as athlete_app
    from fitops.cli.auth import app as auth_app
    from fitops.cli.backup import app as backup_app
    from fitops.cli.dashboard import app as dashboard_app
    from fitops.cli.notes import app as notes_app
    from fitops.cli.race import app as race_app
    from fitops.cli.sync import app as sync_app
    from fitops.cli.weather import app as weather_app
    from fitops.cli.workouts import app as workouts_app

    app.add_typer(
        auth_app,
        name="auth",
        help=f"Manage Strava authentication.\n\nDocs: {CLI_DOCS['auth']}",
    )
    app.add_typer(
        sync_app,
        name="sync",
        help=f"Sync activities from Strava.\n\nDocs: {CLI_DOCS['sync']}",
    )
    app.add_typer(
        activities_app,
        name="activities",
        help=f"View synced activities.\n\nDocs: {CLI_DOCS['activities']}",
    )
    app.add_typer(
        athlete_app,
        name="athlete",
        help=f"View athlete profile and stats.\n\nDocs: {CLI_DOCS['athlete']}",
    )
    app.add_typer(
        analytics_app,
        name="analytics",
        help=f"Training analytics (CTL, ATL, VO2max, zones).\n\nDocs: {CLI_DOCS['analytics']}",
    )
    app.add_typer(
        workouts_app,
        name="workouts",
        help=f"Markdown workout definitions and activity linking.\n\nDocs: {CLI_DOCS['workouts']}",
    )
    app.add_typer(
        notes_app,
        name="notes",
        help=f"Create and manage training notes.\n\nDocs: {CLI_DOCS['notes']}",
    )
    app.add_typer(
        weather_app,
        name="weather",
        help=f"Fetch and manage activity weather data.\n\nDocs: {CLI_DOCS['weather']}",
    )
    app.add_typer(
        race_app,
        name="race",
        help=f"Race course management and simulation.\n\nDocs: {CLI_DOCS['race']}",
    )
    app.add_typer(
        dashboard_app,
        name="dashboard",
        help=f"Launch local training dashboards.\n\nDocs: {CLI_DOCS['dashboard']}",
    )
    app.add_typer(
        backup_app,
        name="backup",
        help=f"Backup and restore FitOps data.\n\nDocs: {CLI_DOCS['backup']}",
    )


_register_subapps()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context, version: bool = typer.Option(False, "--version", "-v")
) -> None:
    if version:
        typer.echo("fitops-cli 0.1.0")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()
