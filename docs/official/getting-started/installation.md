# Installation

## One-line installer (recommended)

The fastest way to get FitOps — installs the CLI **and** places the agent skill file in the right directory for every detected coding assistant on your machine:

```bash
curl -fsSL https://raw.githubusercontent.com/brunov21/fitops-cli/main/install.sh | bash
```

**What happens:**

1. The script checks for `uvx` (part of [uv](https://docs.astral.sh/uv/)) and uses it if available — no global Python install needed, each run is isolated.
2. If `uvx` isn't found but Python 3.11+ is, it runs `pip install fitops`.
3. If neither is available, it exits with clear instructions to install one.
4. It then downloads `.claude/commands/fitops.md` from the GitHub repository and places it into every agent directory it can detect (Claude Code, Cursor, Codex, Windsurf, Cline, OpenCode, GitHub Copilot).
5. It prints the exact Strava auth steps so you can start immediately.

**Target a specific agent** with the `AGENT` variable:

```bash
AGENT=claude  bash <(curl -fsSL https://raw.githubusercontent.com/brunov21/fitops-cli/main/install.sh)
AGENT=cursor  bash <(curl -fsSL https://raw.githubusercontent.com/brunov21/fitops-cli/main/install.sh)
AGENT=codex   bash <(curl -fsSL https://raw.githubusercontent.com/brunov21/fitops-cli/main/install.sh)
```

Supported values: `claude`, `cursor`, `codex`, `windsurf`, `cline`, `opencode`, `copilot`.

---

## Manual installation

### Requirements

- Python 3.11 or higher **or** [uv](https://docs.astral.sh/uv/) (manages Python for you)

### Run with uvx — no install needed

```bash
uvx fitops auth login
uvx fitops sync run
uvx fitops dashboard serve
```

[`uvx`](https://docs.astral.sh/uv/guides/tools/) runs FitOps in a temporary isolated environment — nothing written to your global Python. Install `uv` once:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Install from PyPI

```bash
pip install fitops
fitops --help
```

### Install from source

```bash
git clone https://github.com/brunov21/fitops-cli.git
cd fitops-cli
pip install -e .
```

---

## Install the agent skill manually

If you didn't use the one-line installer, grab the skill file directly:

```bash
# Claude Code — project level
mkdir -p .claude/commands
curl -fsSL https://raw.githubusercontent.com/brunov21/fitops-cli/main/.claude/commands/fitops.md \
  -o .claude/commands/fitops.md

# Claude Code — global (available in all projects)
mkdir -p ~/.claude/commands
curl -fsSL https://raw.githubusercontent.com/brunov21/fitops-cli/main/.claude/commands/fitops.md \
  -o ~/.claude/commands/fitops.md

# Cursor
mkdir -p .cursor/rules
curl -fsSL https://raw.githubusercontent.com/brunov21/fitops-cli/main/.claude/commands/fitops.md \
  -o .cursor/rules/fitops.md
```

The skill file teaches your agent the complete FitOps command set, common workflows, an error-recovery table, and key metric interpretations.

---

## Verify installation

```bash
fitops --help
```

Expected output:

```
Usage: fitops [OPTIONS] COMMAND [ARGS]...

  FitOps-CLI — local Strava analytics. Rich terminal output. Your data, your machine.

Commands:
  auth         Manage Strava authentication.
  sync         Sync activities from Strava.
  activities   View synced activities.
  athlete      View athlete profile and stats.
  analytics    Training analytics (CTL, ATL, VO2max, zones).
  workouts     Manage workouts.
  race         Race course import and simulation.
  weather      Activity weather and pace adjustment.
  notes        Training notes (persistent agent memory).
  dashboard    Local browser dashboard.
```

---

## Storage layout

FitOps creates `~/.fitops/` on first run:

```
~/.fitops/
├── config.json            # Strava credentials + physiology settings
├── sync_state.json        # Sync history and last sync timestamp
├── fitops.db              # SQLite database (all data)
├── workouts/              # Markdown workout definition files
└── notes/                 # Markdown training note files
```

Override the base directory with `export FITOPS_DIR=/path/to/dir`.

---

[← Getting Started](./index.md) | [Next: Authentication →](./authentication.md)
