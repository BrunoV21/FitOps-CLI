"""
Centralized documentation URL registry.

Both the CLI (help strings) and dashboard (template context) import from here.
To update a doc link, change it once in this file.
"""

from __future__ import annotations

DOC_BASE = "https://brunov21.github.io/FitOps-CLI"

# CLI command docs — keyed by the typer sub-app name passed to app.add_typer()
CLI_DOCS: dict[str, str] = {
    "auth": f"{DOC_BASE}/commands/auth",
    "sync": f"{DOC_BASE}/commands/sync",
    "activities": f"{DOC_BASE}/commands/activities",
    "athlete": f"{DOC_BASE}/commands/athlete",
    "analytics": f"{DOC_BASE}/commands/analytics",
    "weather": f"{DOC_BASE}/commands/weather",
    "workouts": f"{DOC_BASE}/commands/workouts",
    "race": f"{DOC_BASE}/commands/race",
    "notes": f"{DOC_BASE}/commands/notes",
    "backup": f"{DOC_BASE}/commands/backup",
    "dashboard": f"{DOC_BASE}/getting-started/",
    # top-level fitops command
    "main": f"{DOC_BASE}/getting-started/",
}

# Dashboard page docs — keyed by active_page value used in route context
# Mapped to the nearest matching page on the live docs site
DASHBOARD_DOCS: dict[str, str] = {
    "overview": f"{DOC_BASE}/getting-started/",
    "activities": f"{DOC_BASE}/commands/activities",
    "analytics": f"{DOC_BASE}/concepts/training-load",
    "performance": f"{DOC_BASE}/concepts/training-load",
    "workouts": f"{DOC_BASE}/commands/workouts",
    "race": f"{DOC_BASE}/commands/race",
    "notes": f"{DOC_BASE}/commands/notes",
    "weather": f"{DOC_BASE}/commands/weather",
    "profile": f"{DOC_BASE}/commands/athlete",
    "backup": f"{DOC_BASE}/commands/backup",
    "setup": f"{DOC_BASE}/getting-started/authentication",
}
