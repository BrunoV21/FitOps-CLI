# Installation

## Requirements

- Python 3.11 or higher
- pip

## Steps

```bash
git clone https://github.com/yourname/FitOps-CLI.git
cd FitOps-CLI
pip install -e .
```

After installation, the `fitops` command is available globally:

```bash
fitops --help
```

## Verify Installation

```
 Usage: fitops [OPTIONS] COMMAND [ARGS]...

 FitOps-CLI — local Strava analytics with LLM-friendly output.

 Commands:
   auth         Manage Strava authentication.
   sync         Sync activities from Strava.
   activities   View synced activities.
   athlete      View athlete profile and stats.
   analytics    Training analytics (CTL, ATL, VO2max, zones).
   workouts     Manage workouts (Phase 3).
```

## Storage Location

FitOps creates `~/.fitops/` on first run:

```
~/.fitops/
├── config.json            # Strava credentials
├── sync_state.json        # Sync history
├── athlete_settings.json  # Physiology settings (LTHR, max HR, etc.)
└── fitops.db              # SQLite database
```

Override with `export FITOPS_DIR=/path/to/dir`.

← [Getting Started](./README.md) | [Next: Authentication →](./authentication.md)
