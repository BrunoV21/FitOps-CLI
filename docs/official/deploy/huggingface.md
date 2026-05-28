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
┌─────────────┐     push     ┌──────────────────┐   POST /api/internal/sync   ┌─────────────────┐
│  fitops sync │ ──────────► │  GitHub backup   │ ──────────────────────────► │  HF Space       │
│  (local)    │              │  repo (GH Actions)│                             │  (always-on)    │
└─────────────┘              └──────────────────┘                             └─────────────────┘
```

1. You run `fitops sync` locally as usual — data backs up to GitHub automatically.
2. A GitHub Actions workflow in the backup repo pings the Space every 20 minutes (keepalive) and triggers a restore on every push (sync).
3. The Space restores your latest backup from GitHub on each sync trigger and on startup.
4. All dashboard routes are protected by password + TOTP (Google Authenticator, Authy, etc.).

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
4. **Sets all secrets** on the Space (password hash, TOTP secret, session key, sync token, GitHub credentials).
5. **Configures GitHub Actions** in your backup repo for keepalive and backup restore sync.
6. **Stores the Strava webhook callback URL** as a Space secret so webhook sync is enabled automatically after Strava auth is available.

---

## GitHub Actions Setup

`fitops deploy hf` creates or updates `.github/workflows/fitops.yml` in your backup repository and stores the `FITOPS_SYNC_TOKEN` GitHub Actions secret automatically.

The workflow has two jobs:

| Job | Trigger | Action |
|---|---|---|
| `keepalive` | Every 20 minutes (cron) | `GET /health` — prevents the Space from sleeping |
| `sync` | Push to `main` | `POST /api/internal/sync` — restores the latest backup |

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

After the Space restores a backup with Strava app credentials, or after you complete Strava auth in the Space setup flow, FitOps automatically registers the Strava push subscription and switches the dashboard sync mode to `webhook`.

You still need to push a backup after deployment so the Space receives your local Strava credentials and data:

```bash
fitops backup create --to github
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
| `FITOPS_SYNC_TOKEN` | `fitops deploy hf` | Token for `POST /api/internal/sync` |
| `FITOPS_WEBHOOK_CALLBACK_URL` | `fitops deploy hf` | Public Strava webhook callback URL for this Space |
| `FITOPS_DEFAULT_SYNC_MODE` | `fitops deploy hf` | Defaults deployed dashboard sync to `webhook` |
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
