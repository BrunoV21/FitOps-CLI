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
fitops backup setup github
```

The setup command is interactive — it will prompt you for:
1. Your GitHub Personal Access Token (input is hidden)
2. The target repository in `owner/name` format

Values are saved to `~/.fitops/config.json` under the `backup.github` key.

If a configuration already exists, you'll be asked to confirm before overwriting.

**Creating a PAT:**
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate a new token with `repo` scope
3. Copy it immediately — it won't be shown again

**Creating the backup repo:**
```bash
# Create a private repo first (github.com/new → name it e.g. "fitops-backups", set to Private)
# Then run the interactive setup:
fitops backup setup github
# → Enter token: ghp_xxxx
# → Enter repo:  yourusername/fitops-backups
```

---

## Creating a Backup

```bash
fitops backup create
fitops backup create --to github
fitops backup create --to github --output-dir /tmp/my-backups
fitops backup create --to github --no-keep-local
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--to PROVIDER` | — | Push archive to a cloud provider after creating (e.g. `github`) |
| `--output-dir PATH` / `-o` | `~/.fitops/backups/` | Local directory for the archive |
| `--keep-local / --no-keep-local` | keep | Whether to keep the local archive after uploading to the cloud |

Without `--to`, the archive is saved locally only. With `--to github`, it's also pushed to the configured GitHub repo as a Release.

Output:

```
Creating backup archive…
  Archive: ~/.fitops/backups/fitops-backup-2026-04-06-091500.tar.gz  (4.2 MB)
  Uploading to github…
  Uploaded: fitops-backup-2026-04-06-091500.tar.gz
Done.
```

---

## Listing Backups

```bash
fitops backup list
fitops backup list --local
fitops backup list --provider github
```

**Options:**

| Flag | Description |
|------|-------------|
| `--local` / `-l` | List locally stored archives in `~/.fitops/backups/` |
| `--provider PROVIDER` / `-p` | List backups from a cloud provider (e.g. `github`) |

With no flags, local archives are shown by default.

Output (local):

```
Local backups (~/.fitops/backups/):
  fitops-backup-2026-04-06-091500.tar.gz  (4.2 MB)
  fitops-backup-2026-04-05-081200.tar.gz  (4.1 MB)
  fitops-backup-2026-04-04-073000.tar.gz  (4.1 MB)
```

Output (cloud):

```
Cloud backups (github):
  fitops-backup-2026-04-06-091500.tar.gz  (4.2 MB)  2026-04-06 09:15:00
  fitops-backup-2026-04-05-081200.tar.gz  (4.1 MB)  2026-04-05 08:12:00
```

---

## Restoring a Backup

```bash
# Restore the most recent backup from GitHub
fitops backup restore --from github

# Restore a specific backup from GitHub
fitops backup restore --from github --backup fitops-backup-2026-04-06-091500

# Restore from a local archive file
fitops backup restore ./fitops-backup-2026-04-06-091500.tar.gz

# Skip the confirmation prompt
fitops backup restore --from github --yes
```

**Options / Arguments:**

| Option | Description |
|--------|-------------|
| `ARCHIVE` (positional) | Path to a local `.tar.gz` archive to restore from |
| `--from PROVIDER` | Cloud provider to restore from (e.g. `github`) |
| `--backup NAME` / `-b` | Specific backup name from the cloud list. If omitted, the most recent is used. |
| `--yes` / `-y` | Skip the confirmation prompt |

Either a local archive path or `--from` is required.

The restore process:
1. Downloads or reads the `.tar.gz` archive
2. Shows the manifest (backup date, contents count) and asks for confirmation
3. Overwrites `~/.fitops/` contents with the archive contents
4. Prints a summary of restored files

```
Restoring from: fitops-backup-2026-04-06-091500.tar.gz
  Backup created: 2026-04-06T09:15:00
  Items: 18

  WARNING: This will overwrite your current FitOps data, including fitops.db, config.json, notes and workouts.

Proceed with restore? [y/N]: y

Restoring…
  Restored: fitops.db
  Restored: notes/hr-drift-march.md
  ...

Done. Restart fitops to use the restored data.
```

**Note:** Restore overwrites your current `~/.fitops/` data. Create a fresh backup first if you want to preserve current state.

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
# Setup (interactive — prompts for token and repo)
fitops backup setup github

# Create
fitops backup create [--to github] [--output-dir PATH] [--no-keep-local]

# List
fitops backup list [--local] [--provider github]

# Restore
fitops backup restore [ARCHIVE_PATH]
fitops backup restore --from github [--backup NAME] [--yes]

# Schedule
fitops backup schedule --enable --interval HOURS [--provider github]
fitops backup schedule --disable
fitops backup schedule --interval HOURS
fitops backup schedule --status
```

← [Commands](./index.md)
