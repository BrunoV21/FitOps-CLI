# HuggingFace Spaces

Deploy the FitOps dashboard to a private HuggingFace Space so you can access your training data from anywhere — protected by password + TOTP two-factor authentication.

---

## Prerequisites

| Requirement | Details |
|---|---|
| `fitops[server]` | `pip install 'fitops[server]'` — adds auth, HF, and TOTP dependencies |
| HuggingFace account | Free account at huggingface.co |
| HF write PAT | Settings → Access Tokens → New token (write scope) |
| GitHub backup configured | `fitops backup setup github` must already be set up |

---

## How It Works

```
┌─────────────┐   webhook   ┌─────────────────┐   backup release   ┌──────────────────┐
│   Strava    │ ──────────► │  HF Space       │ ─────────────────► │ GitHub backup    │
│             │             │  dashboard      │                    │ repo             │
└─────────────┘             └─────────────────┘                    └──────────────────┘
```

1. Strava calls the deployed Space's webhook when an activity is created, updated, or deleted.
2. The Space processes that webhook, fetches the activity detail it needs, and backs up changed data to the GitHub releases backup repo.
3. On container startup, the Space restores the newest GitHub backup whose origin matches this HF Space (`hf-space`, the Space host label, `primary`).
4. A GitHub Actions workflow in the backup repo pings the Space every 20 minutes for keepalive only.
5. The Space does not restore local-machine backups and does not restore from GitHub on push, release publication, or a timer.
6. All dashboard routes are protected by password + TOTP (Google Authenticator, Authy, etc.).

Open dashboard tabs poll a lightweight local update stamp every few seconds. When a webhook commits an activity row, the page reloads without waiting for slower follow-up work such as stream fetches, weather, Strava stamping, training-load snapshot writes, or GitHub backup upload.

---

## Deploy

```bash
fitops deploy hf \
  --hf-token   hf_xxxxxxxxxxxxxxxxxxxx \
  --hf-repo    myuser/fitops-dashboard \
  --github-token  ghp_xxxxxxxxxxxxxxxxxxxx \
  --github-repo   myuser/fitops-backups
```

You can also pass `--hf-token` via the `HF_TOKEN` env var and `--github-token` via `GITHUB_BACKUP_TOKEN`.

### What the command does

1. **Generates a TOTP secret** and displays a QR code — scan it with your authenticator app.
2. **Prompts for a dashboard password** and bcrypt-hashes it.
3. **Creates a private HF Space** (Docker SDK) and uploads the container files.
4. **Sets all secrets** on the Space (password hash, TOTP secret, session key, sync token, GitHub credentials, and HF origin metadata).
5. **Configures GitHub Actions** in your backup repo for keepalive.
6. **Stores the Strava webhook callback URL** as a Space secret so webhook sync is enabled automatically after Strava auth is available.

---

## GitHub Actions Setup

`fitops deploy hf` creates or updates `.github/workflows/fitops.yml` in your backup repository and stores the `FITOPS_SYNC_TOKEN` GitHub Actions secret automatically.

The workflow has one job:

| Job | Trigger | Action |
|---|---|---|
| `keepalive` | Every 20 minutes (cron) | `GET /health` — prevents the Space from sleeping |

The generated workflow does not trigger a dashboard sync or restore. With webhook sync enabled, the HF Space is the active sync origin and pushes backups to GitHub after data changes. Startup restore is handled by the Space container itself and is limited to backups produced by that HF Space origin.

## Strava Webhook Setup

Webhook sync is available for the deployed HF dashboard because it has a public HTTPS URL. It is not available for the normal local dashboard at `localhost`.

`fitops deploy hf` derives the Space's webhook callback URL from `--hf-repo`
and stores it automatically as `FITOPS_WEBHOOK_CALLBACK_URL`. You do not pass
the webhook URL yourself.

```text
Strava webhook sync:
  Configured webhook URL: https://<owner>-<space>.hf.space/api/strava/webhook
  FitOps saved this URL in the HuggingFace Space as FITOPS_WEBHOOK_CALLBACK_URL.

  To make Strava accept it, add this Authorization Callback Domain in your Strava API app:
    <owner>-<space>.hf.space
```

After you complete Strava auth in the Space setup flow, FitOps automatically registers the Strava push subscription and switches the dashboard sync mode to `webhook`.

If you want to seed the Space from an existing local dataset, restore explicitly from the Backup page or CLI. Automatic startup restore only considers backups that were previously created by the HF Space itself, so a local-machine backup will not overwrite the deployed primary instance by default.

```bash
fitops backup restore --from github
```

If the Strava developer settings page asks for an **Authorization Callback Domain**, enter the printed domain only:

```text
<owner>-<space>.hf.space
```

Do not enter `localhost` for webhook sync. Strava cannot call your local machine's dashboard.

---

## Signing In

Navigate to your Space URL (`https://myuser-fitops-dashboard.hf.space`):

1. Enter your dashboard password.
2. Enter the 6-digit code from your authenticator app.
3. Sessions last 24 hours — you'll be asked to sign in again after that.

---

## Environment Variables (Space Secrets)

| Variable | Set by | Purpose |
|---|---|---|
| `FITOPS_AUTH_ENABLED` | `fitops deploy hf` | Activates auth middleware (`"true"`) |
| `FITOPS_PASSWORD_HASH` | `fitops deploy hf` | bcrypt hash of your dashboard password |
| `FITOPS_TOTP_SECRET` | `fitops deploy hf` | TOTP seed for your authenticator app |
| `FITOPS_SESSION_SECRET` | `fitops deploy hf` | Signs session cookies (random 32-byte hex) |
| `FITOPS_SYNC_TOKEN` | `fitops deploy hf` | Token for the manual internal restore endpoint; the generated workflow does not call it |
| `FITOPS_WEBHOOK_CALLBACK_URL` | `fitops deploy hf` | Public Strava webhook callback URL for this Space |
| `FITOPS_DEFAULT_SYNC_MODE` | `fitops deploy hf` | Defaults deployed dashboard sync to `webhook` |
| `FITOPS_INSTANCE_KIND` | `fitops deploy hf` | Marks backups from this runtime as `hf-space` |
| `FITOPS_INSTANCE_LABEL` | `fitops deploy hf` | Labels backups with the Space host |
| `FITOPS_INSTANCE_ROLE` | `fitops deploy hf` | Marks the HF Space as the primary backup origin |
| `GITHUB_BACKUP_TOKEN` | `fitops deploy hf` | GitHub PAT for reading backup releases |
| `GITHUB_BACKUP_REPO` | `fitops deploy hf` | Backup repo (`owner/repo`) |

---

## Local Development

Auth is **off by default**. If `FITOPS_AUTH_ENABLED` is not set to `"true"`, the dashboard starts exactly as before — no login page, no TOTP, no `fitops[server]` required.

```bash
fitops dashboard serve          # local — no auth, no extra deps
FITOPS_AUTH_ENABLED=true ...    # only when deploying to HF
```

---

## Updating Your Deployment

To push updated container files (e.g. after a FitOps upgrade):

```bash
fitops deploy hf --hf-token ... --hf-repo myuser/fitops-dashboard \
  --github-token ... --github-repo myuser/fitops-backups
```

Re-running the command is idempotent — `exist_ok=True` on the Space creation means it won't fail if the Space already exists, and secrets are overwritten in place.
