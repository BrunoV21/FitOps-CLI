#!/usr/bin/env bash
set -euo pipefail

# Write GitHub backup config from environment variables
python - <<'PYEOF'
import os
from fitops.backup.config import save_github_config
token = os.environ["GITHUB_BACKUP_TOKEN"]
repo = os.environ["GITHUB_BACKUP_REPO"]
save_github_config(token, repo)
PYEOF

# HF Spaces are a webhook-sync origin. They upload changed data to the GitHub
# releases backup repo after webhook writes, but do not restore remote backups
# automatically on boot.
echo "[startup] GitHub backup configured; automatic restore is disabled"

# Start dashboard (no browser open, bind to all interfaces on HF port)
exec fitops dashboard serve --host 0.0.0.0 --port 7860 --no-open
