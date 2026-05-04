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

# Restore data from GitHub backup (tolerate failure on first deploy)
fitops backup restore --from github --yes || echo "[startup] No backup found or restore failed — starting fresh"

# Start dashboard (no browser open, bind to all interfaces on HF port)
exec fitops dashboard serve --host 0.0.0.0 --port 7860 --no-open
