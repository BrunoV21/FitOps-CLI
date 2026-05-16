from __future__ import annotations

import asyncio
import json
import secrets

import typer

from fitops.db.migrations import init_db
from fitops.output.formatter import make_meta
from fitops.strava import webhook_config as wcfg
from fitops.strava import webhook_subscription as subs
from fitops.strava.webhooks import recent_events

app = typer.Typer(no_args_is_help=True)


@app.command("setup")
def setup(
    callback_url: str = typer.Option(
        ..., "--callback-url", help="Public callback URL ending in /api/strava/webhook."
    ),
    verify_token: str | None = typer.Option(
        None, "--verify-token", help="Optional Strava callback verification token."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Create a Strava webhook subscription and switch sync mode to webhook."""
    token = verify_token or secrets.token_urlsafe(24)
    wcfg.save_webhook_config(
        callback_url=callback_url,
        verify_token=token,
        enabled=True,
    )
    try:
        subscription_id = subs.create_subscription(callback_url, token)
    except Exception as exc:
        typer.echo(f"Webhook setup failed: {exc}", err=True)
        raise typer.Exit(1)

    wcfg.update_subscription_id(subscription_id)
    wcfg.save_sync_mode("webhook")
    out = {
        "_meta": make_meta(),
        "webhook": {
            "configured": True,
            "callback_url": callback_url,
            "subscription_id": subscription_id,
            "sync_mode": "webhook",
        },
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2))
    else:
        typer.echo(f"Webhook sync enabled: subscription {subscription_id}")


@app.command("status")
def status(
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Show local Strava webhook sync configuration and recent events."""
    init_db()
    cfg = wcfg.get_webhook_config()
    events = asyncio.run(recent_events(limit=10))
    remote = None
    remote_error = None
    try:
        remote = subs.list_subscriptions()
    except Exception as exc:
        remote_error = str(exc)

    out = {
        "_meta": make_meta(total_count=len(events)),
        "webhook": {
            "configured": bool(cfg),
            "enabled": bool((cfg or {}).get("enabled")),
            "callback_url": (cfg or {}).get("callback_url"),
            "subscription_id": (cfg or {}).get("subscription_id"),
            "sync_mode": wcfg.get_sync_mode(),
            "remote_subscriptions": remote,
            "remote_error": remote_error,
            "recent_events": events,
        },
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        webhook = out["webhook"]
        typer.echo(f"Configured: {webhook['configured']}")
        typer.echo(f"Sync mode : {webhook['sync_mode']}")
        typer.echo(f"Callback  : {webhook['callback_url'] or '-'}")
        typer.echo(f"Events    : {len(events)} recent")


@app.command("delete")
def delete(
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Delete the Strava webhook subscription and return to polling mode."""
    cfg = wcfg.get_webhook_config()
    subscription_id = (cfg or {}).get("subscription_id")
    deleted_remote = False
    if subscription_id:
        try:
            subs.delete_subscription(int(subscription_id))
            deleted_remote = True
        except Exception as exc:
            typer.echo(f"Webhook delete failed: {exc}", err=True)
            raise typer.Exit(1)
    wcfg.clear_webhook_config()
    out = {
        "_meta": make_meta(),
        "webhook": {
            "configured": False,
            "deleted_remote": deleted_remote,
            "sync_mode": wcfg.get_sync_mode(),
        },
    }
    if json_output:
        typer.echo(json.dumps(out, indent=2))
    else:
        typer.echo("Webhook subscription deleted. Polling fallback is active.")


@app.command("mode")
def mode(
    value: str = typer.Argument(..., help="One of: webhook, polling, manual."),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text."
    ),
) -> None:
    """Set sync mode without changing the Strava subscription."""
    try:
        wcfg.save_sync_mode(value)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    out = {"_meta": make_meta(), "sync": {"mode": value}}
    if json_output:
        typer.echo(json.dumps(out, indent=2))
    else:
        typer.echo(f"Sync mode set to {value}.")
