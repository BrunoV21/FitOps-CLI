# Dashboard — Backup

The Backup page (`/backup`) lets you back up your entire FitOps data directory to GitHub, restore a previous backup, and set an automatic backup schedule — all without using the CLI.

It also includes Strava webhook sync controls. Webhooks let Strava notify FitOps when activities are created, updated, or deleted, so a deployed dashboard can sync immediately instead of polling every few hours.

## Connecting GitHub

Before you can back up, connect a GitHub repository:

1. Click **Connect GitHub**
2. Paste a GitHub Personal Access Token (PAT) with `repo` scope
3. Enter the target repository in `owner/repo` format (e.g. `yourusername/fitops-backups`)

FitOps stores the token locally and uses it for all subsequent backup and restore operations. To disconnect, click **Remove GitHub**.

## Creating a Backup

Click **Create Backup Now** to immediately push your current FitOps data to GitHub. The backup includes:

- The local database (`fitops.db`)
- All workout files (`~/.fitops/workouts/`)
- All note files (`~/.fitops/notes/`)
- Athlete settings (`athlete_settings.json`)

Each backup is timestamped and pushed as a commit to your GitHub repository.

## Viewing & Restoring Backups

The **Backup History** panel lists your recent backups from GitHub, newest first. Each entry shows the timestamp and commit message.

Click **Restore** on any backup to replace your current local data with that snapshot. This is a destructive operation — your current state will be overwritten.

::: warning
Restore replaces your local database and files. Make sure you don't need your current data before restoring a previous version.
:::

## Automatic Schedule

Set a backup schedule so FitOps backs up your data automatically while the dashboard is running:

- **Frequency** — how often to run (e.g. daily, every 6 hours)
- **Time** — when to run the scheduled backup

The scheduler runs in the background while the dashboard server is active. If you stop the dashboard, scheduled backups pause until you start it again.

For always-on automated backups without keeping the dashboard open, use the CLI:

```bash
fitops backup schedule set --interval 24h
```

## Strava Webhook Sync

Use **Strava Webhook Sync** to register the dashboard as a Strava callback target.

The callback URL must be public and must end at the FitOps webhook endpoint:

```text
https://your-domain.example/api/strava/webhook
```

Use the URL for the dashboard instance Strava can reach:

| Environment | Callback URL |
|-------------|--------------|
| HuggingFace Space | `https://<space-host>/api/strava/webhook` |
| Other deployed server | `https://<your-domain>/api/strava/webhook` |
| Local dashboard only | Not directly supported by Strava |
| Local dashboard through a tunnel | `https://<tunnel-host>/api/strava/webhook` |

`localhost` is only reachable from your machine, so Strava cannot call `http://localhost:8888/api/strava/webhook` directly. For local testing, expose the dashboard with a tunnel such as ngrok or cloudflared and use that public tunnel URL.

The dashboard creates the Strava push subscription through Strava's API. You do not need to manually paste the callback URL into the Strava developer dashboard, but FitOps must already have your Strava app credentials saved.

When webhook sync is enabled:

- New Strava activities are imported automatically
- Streams and weather are fetched after import
- Activity updates refresh the local row
- Activity deletions remove the local activity and dependent cached rows
- The dashboard periodic polling loop is skipped

The **Sync Mode** selector controls automatic Strava sync behavior:

| Mode | Behavior |
|------|----------|
| Webhook | Use Strava webhooks as the automatic sync trigger |
| Polling | Use the periodic dashboard auto-sync fallback |
| Manual | Only sync when you click Sync or run the CLI |

## See Also

- [`fitops backup`](../commands/backup.md) — CLI reference for all backup commands
- [`fitops webhooks`](../commands/webhooks.md) — CLI reference for webhook sync

← [Dashboard Overview](./index.md)
