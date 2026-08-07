from __future__ import annotations

import json

import typer

from fitops.browser.config import resolve_browser_profile
from fitops.config.settings import get_settings
from fitops.output.formatter import make_meta
from fitops.utils.exceptions import BrowserPublicationError

app = typer.Typer(no_args_is_help=True)


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
        typer.echo(f"{browser['browser_type']} / {browser['profile']}: {state}")
