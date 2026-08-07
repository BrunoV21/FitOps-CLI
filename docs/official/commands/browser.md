# fitops browser

Configure the everyday Chromium browser profile FitOps uses to publish activities through Strava's website. Supported browsers are Brave, Chrome, and Edge.

## Configure

```bash
fitops browser configure --type brave \
  --user-data-dir "$HOME/Library/Application Support/BraveSoftware/Brave-Browser" \
  --profile Default
```

| Flag | Description |
|------|-------------|
| `--type brave\|chrome\|edge` | Browser family |
| `--user-data-dir PATH` | Browser user-data directory, not the individual profile subdirectory |
| `--profile NAME` | Profile directory such as `Default` or `Profile 1` |
| `--executable PATH` | Optional custom browser executable |
| `--json` | Return the saved configuration with a `_meta` block |

The equivalent environment variables are `FITOPS_BROWSER_TYPE`, `FITOPS_BROWSER_USER_DATA_DIR`, `FITOPS_BROWSER_PROFILE`, and `FITOPS_BROWSER_EXECUTABLE`. Environment variables take precedence over saved settings.

## Status

```bash
fitops browser status
fitops browser status --json
```

Status validates browser discovery and reports whether the selected profile is currently open. Close all windows using that profile before publishing. FitOps deliberately fails instead of copying the profile or its cookies.

## Security and behavior

Publishing is local, visible browser automation. FitOps does not store your Strava password, extract cookies, or change activity visibility. New activities use the visibility already configured in your Strava account. Because Strava can change its website, a selector mismatch is reported as a recoverable publication error and the local activity remains intact.

← [Commands Reference](./index.md)
