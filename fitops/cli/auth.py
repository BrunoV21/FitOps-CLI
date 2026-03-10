from __future__ import annotations

import asyncio
import json

import typer

from fitops.config.settings import get_settings
from fitops.strava.oauth import StravaOAuth, validate_strava_token
from fitops.utils.cache import clear_all_caches
from fitops.utils.exceptions import FitOpsError

app = typer.Typer(no_args_is_help=True)


@app.command("login")
def login() -> None:
    """Authenticate with Strava via OAuth."""
    settings = get_settings()

    if not settings.client_id:
        typer.echo("Strava client_id not configured.")
        client_id = typer.prompt("Enter your Strava Client ID")
        client_secret = typer.prompt("Enter your Strava Client Secret", hide_input=True)
        settings.save_credentials(client_id, client_secret)
        settings.reload()

    oauth = StravaOAuth(settings)
    try:
        result = asyncio.run(oauth.run_login_flow())
        athlete = result.get("athlete", {})
        name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
        typer.echo(f"\nAuthenticated as: {name} (ID: {result.get('athlete_id')})")
        typer.echo("Tokens saved. Run `fitops sync run` to fetch your activities.")
    except FitOpsError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("logout")
def logout() -> None:
    """Revoke Strava access and clear stored tokens."""
    settings = get_settings()
    if not settings.is_authenticated:
        typer.echo("Not currently authenticated.")
        return

    oauth = StravaOAuth(settings)
    try:
        asyncio.run(oauth.revoke_access_token(settings.access_token))
    except Exception:
        pass

    settings.clear_tokens()
    clear_all_caches()
    typer.echo("Logged out. Tokens cleared.")


@app.command("status")
def status() -> None:
    """Show current authentication status."""
    settings = get_settings()
    if not settings.is_authenticated:
        typer.echo("Status: NOT authenticated. Run `fitops auth login`.")
        return

    valid = validate_strava_token(settings.access_token, settings.expires_at)
    typer.echo(f"Status: {'Valid' if valid else 'EXPIRED (will auto-refresh)'}")
    typer.echo(f"Athlete ID: {settings.athlete_id}")
    typer.echo(f"Expires at: {settings.expires_at}")
    typer.echo(f"Scopes: {', '.join(settings.scopes)}")


@app.command("refresh")
def refresh() -> None:
    """Force refresh the Strava access token."""
    settings = get_settings()
    if not settings.refresh_token:
        typer.echo("No refresh token. Run `fitops auth login` first.", err=True)
        raise typer.Exit(1)

    oauth = StravaOAuth(settings)
    try:
        token_data = asyncio.run(oauth.refresh_access_token(settings.refresh_token))
        settings.save_tokens(token_data)
        typer.echo(f"Token refreshed. Expires at: {token_data['expires_at']}")
    except FitOpsError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
