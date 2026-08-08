from __future__ import annotations

import json

import typer

from fitops.browser.config import resolve_browser_profile
from fitops.config.settings import get_settings
from fitops.output.formatter import make_meta
from fitops.utils.exceptions import BrowserPublicationError

app = typer.Typer(no_args_is_help=True)


@app.command("login-headless")
def login_headless(
    timeout_seconds: int = typer.Option(
        300,
        "--timeout-seconds",
        min=30,
        max=900,
        help="Seconds to wait for the interactive Strava login.",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Log a dedicated browser profile into Strava for headless jobs."""
    from fitops.browser.description import login_headless_profile

    if not json_output:
        typer.echo("Complete the Strava login in the Brave window that opens.")
    try:
        result = login_headless_profile(timeout_seconds=timeout_seconds)
    except BrowserPublicationError as exc:
        payload = {
            "_meta": make_meta(
                total_count=0,
                filters_applied={"timeout_seconds": timeout_seconds},
            ),
            "error": {"code": exc.code, "message": str(exc)},
        }
        if json_output:
            typer.echo(json.dumps(payload, indent=2), err=True)
        else:
            typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    payload = {
        "_meta": make_meta(
            total_count=1,
            filters_applied={"timeout_seconds": timeout_seconds},
        ),
        "headless_login": result.to_dict(),
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo("Strava login verified and saved for headless jobs.")


@app.command("append-description")
def append_description(
    activity_id: int = typer.Argument(..., help="Strava activity ID."),
    text: str = typer.Argument(..., help="Text to append to the description."),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Open and validate the activity without saving a change.",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--show-browser",
        help="Hide the browser when the Playwright backend is used.",
    ),
    backend: str = typer.Option(
        "auto",
        "--backend",
        help="auto, brave-live, brave-headless, or playwright.",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Append text to a Strava activity using your logged-in browser session."""
    from fitops.browser.description import append_activity_description

    filters = {
        "activity_id": activity_id,
        "dry_run": dry_run,
        "headless": headless,
        "backend": backend,
    }
    try:
        result = append_activity_description(
            activity_id,
            text,
            dry_run=dry_run,
            headless=headless,
            backend=backend,
        )
    except BrowserPublicationError as exc:
        payload = {
            "_meta": make_meta(total_count=0, filters_applied=filters),
            "error": {"code": exc.code, "message": str(exc)},
        }
        if json_output:
            typer.echo(json.dumps(payload, indent=2), err=True)
        else:
            typer.echo(str(exc), err=True)
        raise typer.Exit(1)

    payload = {
        "_meta": make_meta(total_count=1, filters_applied=filters),
        "description_update": result.to_dict(),
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    elif result.dry_run:
        typer.echo(
            f"Dry run passed for Strava activity {activity_id}; no change was saved."
        )
    else:
        typer.echo(f"Appended text to Strava activity {activity_id}.")


@app.command("configure")
def configure(
    browser_type: str = typer.Option(..., "--type", help="brave, chrome, or edge."),
    user_data_dir: str = typer.Option(..., "--user-data-dir"),
    profile: str = typer.Option("Default", "--profile"),
    executable: str | None = typer.Option(None, "--executable"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Select the already logged-in local browser profile used for Strava."""
    if browser_type.lower() not in {"brave", "chrome", "edge"}:
        typer.echo("--type must be brave, chrome, or edge", err=True)
        raise typer.Exit(2)
    settings = get_settings()
    settings.save_browser_preferences(
        browser_type=browser_type.lower(),
        user_data_dir=user_data_dir,
        profile=profile,
        executable=executable,
    )
    payload = {
        "_meta": make_meta(total_count=1),
        "browser": {
            "type": browser_type.lower(),
            "user_data_dir": user_data_dir,
            "profile": profile,
            "executable": executable,
        },
    }
    typer.echo(
        json.dumps(payload, indent=2) if json_output else "Browser profile saved."
    )


@app.command("status")
def status(json_output: bool = typer.Option(False, "--json")) -> None:
    """Validate browser discovery and report whether its profile is in use."""
    try:
        profile = resolve_browser_profile()
        browser = profile.to_dict()
        from fitops.browser.description import choose_description_backend

        browser["append_backend"] = choose_description_backend(profile, "auto")
        ok = True
    except BrowserPublicationError as exc:
        browser = {"configured": False, "error": str(exc), "code": exc.code}
        ok = False
    payload = {"_meta": make_meta(total_count=1 if ok else 0), "browser": browser}
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        if not ok:
            typer.echo(browser["error"], err=True)
            raise typer.Exit(1)
        state = "open (close it before publishing)" if browser["is_open"] else "ready"
        typer.echo(
            f"{browser['browser_type']} / {browser['profile']}: {state}; "
            f"append backend: {browser['append_backend']}"
        )
