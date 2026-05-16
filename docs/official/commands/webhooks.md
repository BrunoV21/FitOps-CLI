# fitops webhooks

Manage Strava webhook sync.

Webhooks let Strava call your FitOps backend when an activity is created, updated, or deleted. When webhook sync is enabled, FitOps stops the dashboard's periodic Strava polling and uses these events as the primary sync trigger.

::: tip
Strava requires a public callback URL. A local `localhost` dashboard cannot receive Strava webhooks unless you expose it with a tunnel such as ngrok or cloudflared. Deployed dashboards can use their public URL.
:::

## Commands

## Choosing the Callback URL

The callback URL is the public address Strava calls. It must point to the running FitOps dashboard and end with:

```text
/api/strava/webhook
```

Use the URL for the environment that is actually reachable from Strava:

| Environment | Callback URL |
|-------------|--------------|
| HuggingFace Space | `https://<space-host>/api/strava/webhook` |
| Other deployed server | `https://<your-domain>/api/strava/webhook` |
| Local dashboard only | Not directly supported by Strava |
| Local dashboard through a tunnel | `https://<tunnel-host>/api/strava/webhook` |

For local development, `http://localhost:8888/api/strava/webhook` only works for requests from your own machine. Strava cannot reach your laptop's localhost. Use a public tunnel such as ngrok or cloudflared, then pass the tunnel URL to FitOps.

You do not need to manually paste the callback URL into the Strava developer dashboard when using `fitops webhooks setup`; FitOps calls Strava's push subscription API for you using the Strava app `client_id` and `client_secret` already saved during auth setup. You still need a Strava API app with valid credentials configured in FitOps.

### `fitops webhooks setup`

Create a Strava push subscription and switch FitOps to webhook sync mode.

```bash
fitops webhooks setup --callback-url https://example.com/api/strava/webhook
```

Examples:

```bash
# Deployed dashboard
fitops webhooks setup --callback-url https://my-fitops.hf.space/api/strava/webhook

# Local dashboard exposed through a tunnel
fitops webhooks setup --callback-url https://abc123.ngrok-free.app/api/strava/webhook
```

| Flag | Default | Description |
|------|---------|-------------|
| `--callback-url URL` | required | Public URL where Strava sends webhook verification and event requests |
| `--verify-token TOKEN` | generated | Optional Strava verification token |
| `--json` | false | Print structured JSON |

### `fitops webhooks status`

Show local webhook configuration, remote subscription status, current sync mode, and recent received events.

```bash
fitops webhooks status --json
```

```json
{
  "_meta": {
    "tool": "fitops",
    "version": "0.1.0",
    "generated_at": "2026-05-16T12:00:00+00:00",
    "total_count": 1,
    "filters_applied": {}
  },
  "webhook": {
    "configured": true,
    "enabled": true,
    "callback_url": "https://example.com/api/strava/webhook",
    "subscription_id": 12345,
    "sync_mode": "webhook",
    "recent_events": []
  }
}
```

### `fitops webhooks mode`

Set the dashboard sync mode without changing the Strava subscription.

```bash
fitops webhooks mode webhook
fitops webhooks mode polling
fitops webhooks mode manual
```

| Mode | Behavior |
|------|----------|
| `webhook` | Strava webhook events trigger activity create/update/delete processing |
| `polling` | The dashboard uses the existing periodic incremental sync fallback |
| `manual` | No automatic Strava sync; use `fitops sync run` or the dashboard Sync button |

### `fitops webhooks delete`

Delete the Strava push subscription and return FitOps to polling mode.

```bash
fitops webhooks delete
```

## Event Behavior

| Strava event | FitOps behavior |
|--------------|-----------------|
| `activity/create` | Imports the activity, fetches streams and weather, computes cached metrics, matches plans, and triggers backup sync if configured |
| `activity/update` | Refreshes the activity from Strava and refreshes dependent cached data |
| `activity/delete` | Removes the activity and dependent local rows, including streams, weather, laps, workout links, race links, and cached activity artifacts |

FitOps records webhook events locally so duplicate Strava deliveries are ignored and recent processing status is visible in the dashboard.

## See Also

- [`fitops sync`](./sync.md)
- [Dashboard Backup & Sync](../dashboard/backup.md)
