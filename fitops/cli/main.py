from __future__ import annotations

import typer

app = typer.Typer(
    name="fitops",
    help="FitOps-CLI — local Strava analytics with LLM-friendly output.",
    no_args_is_help=True,
    add_completion=False,
)


def _register_subapps() -> None:
    from fitops.cli.auth import app as auth_app
    from fitops.cli.sync import app as sync_app
    from fitops.cli.activities import app as activities_app
    from fitops.cli.athlete import app as athlete_app
    from fitops.cli.workouts import app as workouts_app

    app.add_typer(auth_app, name="auth", help="Manage Strava authentication.")
    app.add_typer(sync_app, name="sync", help="Sync activities from Strava.")
    app.add_typer(activities_app, name="activities", help="View synced activities.")
    app.add_typer(athlete_app, name="athlete", help="View athlete profile and stats.")
    app.add_typer(workouts_app, name="workouts", help="Manage workouts (Phase 3).")


_register_subapps()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context, version: bool = typer.Option(False, "--version", "-v")) -> None:
    if version:
        typer.echo("fitops-cli 0.1.0")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()
