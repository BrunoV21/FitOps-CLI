from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_workouts() -> None:
    """List workouts. (Phase 3 — not yet implemented)"""
    typer.echo("Workouts coming in Phase 3. Stay tuned!")


@app.command("create")
def create_workout() -> None:
    """Create a workout template. (Phase 3 — not yet implemented)"""
    typer.echo("Workout creation coming in Phase 3. Stay tuned!")


@app.command("schedule")
def schedule_workout() -> None:
    """Schedule a workout. (Phase 3 — not yet implemented)"""
    typer.echo("Workout scheduling coming in Phase 3. Stay tuned!")


@app.command("link")
def link_workout() -> None:
    """Link a workout to an activity for compliance scoring. (Phase 3 — not yet implemented)"""
    typer.echo("Workout linking coming in Phase 3. Stay tuned!")
