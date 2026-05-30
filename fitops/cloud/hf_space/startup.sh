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

# Restore the newest backup produced by this HF Space origin. This recovers
# persisted dashboard data after an HF container restart without pulling a
# local-machine backup into the deployed primary instance.
restore_args=(--from github --origin-kind hf-space --origin-role primary --yes)
if [[ -n "${FITOPS_INSTANCE_LABEL:-}" ]]; then
  restore_args+=(--origin-label "$FITOPS_INSTANCE_LABEL")
fi
fitops backup restore "${restore_args[@]}" || echo "[startup] No HF-origin backup found or restore failed — starting with current data"

# Start dashboard (no browser open, bind to all interfaces on HF port)
exec fitops dashboard serve --host 0.0.0.0 --port 7860 --no-open
