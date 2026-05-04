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
5. **Prints a GitHub Actions YAML** to add to your backup repo.

---

## GitHub Actions Setup

After running `fitops deploy hf`, copy the printed YAML into your backup repository at:

```
.github/workflows/fitops.yml
```

Then add the sync token as a repository secret named `FITOPS_SYNC_TOKEN`:

```
GitHub repo → Settings → Secrets and variables → Actions → New repository secret
Name: FITOPS_SYNC_TOKEN
Value: <sync token printed by fitops deploy hf>
```

The workflow has two jobs:

| Job | Trigger | Action |
|---|---|---|
| `keepalive` | Every 20 minutes (cron) | `GET /health` — prevents the Space from sleeping |
| `sync` | Push to `main` | `POST /api/internal/sync` — restores the latest backup |

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
