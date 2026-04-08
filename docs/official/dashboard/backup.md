# Dashboard — Backup

The Backup page (`/backup`) lets you back up your entire FitOps data directory to GitHub, restore a previous backup, and set an automatic backup schedule — all without using the CLI.

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

## See Also

- [`fitops backup`](../commands/backup.md) — CLI reference for all backup commands

← [Dashboard Overview](./index.md)
