# backup

Back up your entire FitOps data directory to a remote provider and restore it on any machine.

---

## What Gets Backed Up

Every backup is a single `.tar.gz` archive containing:

| File / Directory | Contents |
|---|---|
| `fitops.db` | All synced activities, streams, analytics, and linked workouts |
| `config.json` | Provider settings, zone thresholds, and other config |
| `sync_state.json` | Last sync timestamp and pagination state |
| `athlete_settings.json` | Weight, height, birthday, FTP, and other athlete metadata |
| `notes/` | All training journal `.md` files |
| `workouts/` | All workout definition `.md` files |
| `manifest.json` | Backup metadata: timestamp, FitOps version, archive contents |

Archive filename format: `fitops-backup-YYYY-MM-DD-HHMMSS.tar.gz`

---

## Providers

FitOps currently supports **GitHub** as a backup provider. Each backup is stored as a GitHub Release with the `.tar.gz` file as an asset — releases are cheap, versioned, and easy to inspect.

Future providers planned: Dropbox, Google Drive.

---

## Setup

### GitHub

```bash
fitops backup setup github --token ghp_xxxx --repo owner/repo-name
```

| Flag | Required | Description |
|------|----------|-------------|
| `--token` | Yes | GitHub Personal Access Token with `repo` scope |
| `--repo` | Yes | Target repository in `owner/repo-name` format (can be private) |

The token and repo are saved to `~/.fitops/config.json` under the `backup.github` key.

**Creating a PAT:**
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate a new token with `repo` scope
3. Copy and use immediately — it won't be shown again

**Creating the backup repo:**
```bash
# Create a private repo first if it doesn't exist
# github.com/new → name it e.g. "fitops-backups", set to Private
fitops backup setup github --token ghp_xxxx --repo yourusername/fitops-backups
```

To clear the GitHub backup configuration:

```bash
fitops backup setup github --clear
```

---

## Creating a Backup

```bash
fitops backup create
fitops backup create --provider github
```

Output:

```
Backup complete
  Provider   github
  Archive    fitops-backup-2026-04-06-091500.tar.gz
  Size       4.2 MB
  Release    https://github.com/owner/fitops-backups/releases/tag/fitops-backup-2026-04-06-091500
```

If no `--provider` is specified, FitOps uses whichever provider is configured. If multiple providers are configured in the future, `--provider` selects which one.

---

## Listing Backups

```bash
fitops backup list
fitops backup list --provider github
```

Output:

```
Backups  (github → owner/fitops-backups)

  #   Tag                                    Created               Size
 ────────────────────────────────────────────────────────────────────────
  1   fitops-backup-2026-04-06-091500        2026-04-06 09:15:00   4.2 MB
  2   fitops-backup-2026-04-05-081200        2026-04-05 08:12:00   4.1 MB
  3   fitops-backup-2026-04-04-073000        2026-04-04 07:30:00   4.1 MB
```

---

## Restoring a Backup

```bash
fitops backup restore
fitops backup restore --tag fitops-backup-2026-04-06-091500
fitops backup restore --provider github --tag fitops-backup-2026-04-06-091500
```

With no `--tag`, FitOps restores the most recent backup.

The restore process:
1. Downloads the `.tar.gz` archive from the provider
2. Extracts it to a temp directory
3. Stops any running dashboard server
4. Replaces `~/.fitops/` contents with the archive contents
5. Prints a confirmation with counts of restored files

```
Restore complete
  Source     fitops-backup-2026-04-06-091500 (github)
  DB         fitops.db  ✓
  Notes      12 files restored
  Workouts   5 files restored
```

**Note:** Restore overwrites your current `~/.fitops/` data. Make a manual backup first if you want to preserve current state.

---

## Scheduled Backups

Configure automatic backups on a schedule. The scheduler runs inside the dashboard server process and wakes every 60 seconds to check whether a backup is due.

```bash
# Enable scheduled backups every 24 hours
fitops backup schedule --enable --interval 24

# Change the interval
fitops backup schedule --interval 12

# Disable scheduled backups
fitops backup schedule --disable

# Check current schedule
fitops backup schedule --status
```

Schedule status output:

```
Backup Schedule
  Enabled       true
  Provider      github
  Interval      24h
  Last backup   2026-04-06 09:15:00
  Next backup   2026-04-07 09:15:00
```

The schedule is stored in `~/.fitops/config.json` under `backup.schedule`. It is only active while the dashboard server is running (`fitops dashboard serve`). For fully unattended backups, add a cron job:

```bash
# crontab -e
0 3 * * *  fitops backup create   # daily at 03:00
```

---

## Dashboard

The backup UI is available at **Settings → Backup** in the dashboard (`fitops dashboard serve`). From the browser you can:

- Configure the GitHub provider
- Trigger a manual backup
- Browse backup history
- Restore from any listed backup
- Enable / disable and configure the schedule

---

## Commands Reference

```bash
fitops backup setup github --token TOKEN --repo OWNER/REPO
fitops backup setup github --clear

fitops backup create [--provider github]
fitops backup list [--provider github]
fitops backup restore [--tag TAG] [--provider github]

fitops backup schedule --enable --interval HOURS
fitops backup schedule --disable
fitops backup schedule --interval HOURS
fitops backup schedule --status
```

← [Commands](./index.md)
