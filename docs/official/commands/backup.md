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
| `manifest.json` | Backup metadata: timestamp, FitOps version, origin, trigger, dataset signature, and archive contents |

Archive filename format: `fitops-backup-ORIGIN-iid-INSTANCE-YYYY-MM-DD-HHMMSS-SIGNATURE.tar.gz`. Legacy `fitops-backup-YYYY-MM-DD-HHMMSS.tar.gz` archives remain restorable.

---

## Providers

FitOps currently supports **GitHub** as a backup provider. Each backup is stored as a GitHub Release with the `.tar.gz` file as an asset — releases are cheap, versioned, and easy to inspect.

Each release body includes machine-readable FitOps metadata: origin, role, trigger, dataset revision, and dataset signature. Origins distinguish local machines from deployed HuggingFace Spaces.

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
fitops backup create --to github --force
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--to PROVIDER` | — | Push archive to a cloud provider after creating (e.g. `github`) |
| `--output-dir PATH` / `-o` | `~/.fitops/backups/` | Local directory for the archive |
| `--keep-local / --no-keep-local` | keep | Whether to keep the local archive after uploading to the cloud |
| `--force` | false | Create a backup even if the dataset signature matches the last successful backup |

Without `--to`, the archive is saved locally only. With `--to github`, it's also pushed to the configured GitHub repo as a Release.

The database is captured with SQLite's online backup mechanism, so backups stay consistent even while the dashboard is running and SQLite is using WAL files.
Before creating an archive, FitOps computes a dataset signature from the DB revision, key table summaries, workout/note file hashes, and stable config. If nothing has changed since the last successful backup, the backup is skipped unless `--force` is used.

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
  fitops-backup-hf-space-user-fitops-dashboard-iid-7f3a2c91e4b0-2026-04-06-091500-a1b2c3d4e5f6.tar.gz  (4.2 MB)  2026-04-06 09:15:00  hf-space/user-fitops-dashboard.hf.space (primary)  a1b2c3d4e5f6
  fitops-backup-local-bv-mac-iid-0a9b8c7d6e5f-2026-04-05-081200-f6e5d4c3b2a1.tar.gz  (4.1 MB)  2026-04-05 08:12:00  local/bv-mac (secondary)  f6e5d4c3b2a1
```

---

## Restoring a Backup

```bash
# Restore the most recent backup from GitHub
fitops backup restore --from github

# Restore a specific backup from GitHub
fitops backup restore --from github --backup fitops-backup-2026-04-06-091500

# Restore the newest backup from a specific origin
fitops backup restore --from github \
  --origin-kind hf-space \
  --origin-label user-fitops-dashboard.hf.space \
  --origin-role primary

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
| `--origin-kind KIND` | Only consider cloud backups whose origin kind matches, such as `hf-space` or `local` |
| `--origin-label LABEL` | Only consider cloud backups whose origin label matches |
| `--origin-role ROLE` | Only consider cloud backups whose origin role matches, such as `primary` or `secondary` |
| `--yes` / `-y` | Skip the confirmation prompt |

Either a local archive path or `--from` is required.

The restore process:
1. Downloads or reads the `.tar.gz` archive
2. Shows the manifest (backup date, contents count) and asks for confirmation
3. Validates the database with SQLite `quick_check`
4. Overwrites `~/.fitops/` contents with the archive contents
5. Replaces SQLite sidecar files (`fitops.db-wal` and `fitops.db-shm`) so the restored database opens cleanly
6. Prints a summary of restored files

When restoring from GitHub without `--backup`, FitOps tries the newest readable release first. Origin filters are applied before selecting the newest release, which is how deployed HuggingFace Spaces restore only their own HF-origin backups on container startup. If the current dataset signature already matches the backup, restore exits as a no-op.

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
  Last check    2026-04-06 21:15:00
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

Scheduled backups use the same signature check as the CLI, so a 12-hour schedule only uploads when synced data, workouts, notes, analytics, race data, or stable config changed.

After each successful GitHub upload, FitOps applies smart retention per origin: recent backups are kept densely, with daily, weekly, and monthly checkpoints retained so the release list stays useful instead of growing indefinitely.

---

## Commands Reference

```bash
# Setup (interactive — prompts for token and repo)
fitops backup setup github

# Create
fitops backup create [--to github] [--output-dir PATH] [--no-keep-local] [--force]

# List
fitops backup list [--local] [--provider github]

# Restore
fitops backup restore [ARCHIVE_PATH]
fitops backup restore --from github [--backup NAME] [--origin-kind KIND] [--origin-label LABEL] [--origin-role ROLE] [--yes]

# Schedule
fitops backup schedule --enable --interval HOURS [--provider github]
fitops backup schedule --disable
fitops backup schedule --interval HOURS
fitops backup schedule --status
```

← [Commands](./index.md)
