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

## Append to an activity description

```bash
fitops browser append-description ACTIVITY_ID TEXT [OPTIONS]
```

This command opens `https://www.strava.com/activities/ACTIVITY_ID` in the configured logged-in browser profile, opens its edit form, preserves the existing description, adds a blank line and the supplied text, saves, and reads the edit form again to confirm that Strava persisted the change.

| Option | Default | Description |
|--------|---------|-------------|
| `--dry-run` | false | Validate access and calculate the new length without filling or saving the form |
| `--headless` / `--show-browser` | headless | Hide the browser when the Playwright fallback is used |
| `--backend auto\|brave-live\|brave-headless\|playwright` | auto | Select live Brave, native headless Brave, or the Playwright fallback |
| `--json` | false | Return a `_meta` block and update result as JSON |

On macOS with Brave, the default `auto` backend controls the currently logged-in Brave session through Apple Events, so Brave may remain open and no cookies are copied or exported. One-time setup: in Brave, enable **View → Developer → Allow JavaScript from Apple Events**. macOS may also ask you to grant your terminal permission to automate Brave.

For a dedicated Brave user-data directory, `auto` selects `brave-headless`. FitOps launches the Brave executable itself with native headless mode, binds its debugging interface to a temporary local port, and attaches Playwright afterward. This keeps Brave's normal macOS credential and cookie handling while providing real background execution. The explicit `playwright` backend remains available as a cross-platform fallback; it should use a separate automation profile because [Playwright does not support automating a modern Chromium browser's default profile](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context).

### One-time headless profile setup

Create and select a dedicated FitOps browser directory:

```bash
mkdir -p "$HOME/.fitops/brave-automation"
fitops browser configure \
  --type brave \
  --user-data-dir "$HOME/.fitops/brave-automation" \
  --profile Default
```

Run FitOps' interactive login bootstrap:

```bash
fitops browser login-headless
```

Complete the Strava login in the dedicated Brave window. This window is launched directly by Brave, so Google login uses Brave's normal security and macOS credential handling instead of an automation-launched browser. FitOps connects only through a temporary local debugging port, verifies the authenticated Profile Settings page, and makes Strava's session-only cookies persistent for 30 days inside that dedicated profile's encrypted Brave cookie store. Cookie values are never printed or exported to a separate file. The command then closes the dedicated window.

Confirm that the profile is closed and ready:

```bash
fitops browser status --json
```

The JSON should report `"is_default_user_data_dir": false`, `"is_open": false`, and `"append_backend": "brave-headless"`. The ordinary Brave profile and dedicated automation profile do not share or copy cookies; the authenticated session remains only in the dedicated profile.

Test the complete headless path without saving:

```bash
fitops browser append-description 19645980884 "Headless check" \
  --dry-run --headless --json
```

With a custom Brave profile, `--backend auto` chooses native headless Brave. You can pass `--backend brave-headless` explicitly, or use `--backend playwright` for the persistent-context fallback.

```bash
# Safely confirm access without changing the activity
fitops browser append-description 19645980884 "Training note" --dry-run --json

# Append text with automatic backend selection
fitops browser append-description 19645980884 "Training note" --headless --json

# Multiline shell argument
fitops browser append-description 19645980884 $'First line\nSecond line'
```

For a detached background job on macOS or Linux:

```bash
nohup fitops browser append-description 19645980884 "Training note" --json \
  >fitops-strava-append.log 2>&1 &
```

The text is intentionally not included in `_meta.filters_applied`, which keeps potentially private activity notes out of routine metadata logs. The result reports the old and new character counts, the activity URL, and whether the update was saved.

Example JSON result:

```json
{
  "_meta": {
    "tool": "fitops",
    "version": "0.1.0",
    "generated_at": "2026-08-08T17:30:00+00:00",
    "total_count": 1,
    "filters_applied": {
      "activity_id": 19645980884,
      "dry_run": false,
      "headless": true,
      "backend": "auto"
    }
  },
  "description_update": {
    "activity_id": 19645980884,
    "activity_url": "https://www.strava.com/activities/19645980884",
    "before_length": 84,
    "after_length": 99,
    "saved": true,
    "dry_run": false,
    "backend": "brave_live_session"
  }
}
```

## Upload a GPX or TCX activity

```bash
fitops browser upload-activity FILE --title TITLE --sport SPORT [OPTIONS]
```

This command uploads a GPX or TCX file through the dedicated logged-in browser profile, waits for Strava to process it, applies the supplied metadata, selects optional gear, saves the activity, and returns the new Strava activity ID. It uses the same native headless Brave backend as `append-description`.

| Option | Required | Description |
|--------|----------|-------------|
| `FILE` | yes | Path to a `.gpx` or `.tcx` file, up to 25 MiB |
| `--title TEXT` | yes | Activity title saved on Strava |
| `--description TEXT` | no | Activity description; defaults to empty |
| `--sport VALUE` | yes | Strava sport value or displayed name, such as `Run`, `Ride`, `TrailRun`, or `Gravel Ride` |
| `--gear VALUE` | no | Exact Strava gear value, full displayed label, or gear name without its changing distance suffix |
| `--headless` / `--show-browser` | headless | Visibility for the explicit Playwright fallback |
| `--backend auto\|brave-headless\|playwright` | auto | Browser automation backend |
| `--json` | false | Return a `_meta` block and upload result as JSON |

The dedicated profile setup described above is required for `auto` on Brave. The everyday/default Brave profile selects the live-session backend for description edits, but file uploads require the dedicated profile so Brave can run safely in the background.

```bash
fitops browser upload-activity "$HOME/Downloads/morning-run.tcx" \
  --title "Morning run" \
  --description "Uploaded from FitOps" \
  --sport Run \
  --gear "Adidas Adistar 4" \
  --json
```

Gear matching first checks the option value used by Strava, then the exact displayed label, then the displayed gear name with a trailing distance such as `(852.7 km)` removed. If no option matches, the command exits without saving and reports `gear_not_found` with the available gear labels.

Strava checks duplicates while processing the staged file. A duplicate exits with code 1 and structured JSON such as:

```json
{
  "_meta": {
    "tool": "fitops",
    "total_count": 0,
    "filters_applied": {
      "file_name": "morning-run.tcx",
      "sport_type": "Run",
      "gear": null,
      "headless": true,
      "backend": "auto"
    }
  },
  "error": {
    "code": "activity_already_exists",
    "message": "Strava reports that 'morning-run.tcx' already exists: morning-run.tcx duplicate of Morning run"
  }
}
```

Successful JSON includes the new ID and URL:

```json
{
  "_meta": {
    "tool": "fitops",
    "total_count": 1,
    "filters_applied": {
      "file_name": "morning-run.tcx",
      "sport_type": "Run",
      "gear": "Adidas Adistar 4",
      "headless": true,
      "backend": "auto"
    }
  },
  "activity_upload": {
    "strava_activity_id": 19650000001,
    "activity_url": "https://www.strava.com/activities/19650000001",
    "file_name": "morning-run.tcx",
    "file_format": "tcx",
    "title": "Morning run",
    "sport_type": "Run",
    "gear_value": "27644260",
    "gear_label": "Adidas Adistar 4 (852.7 km)",
    "backend": "brave_headless_cdp"
  }
}
```

Other failures use specific error codes, including `upload_file_not_found`, `upload_file_type_unsupported`, `upload_processing_timeout`, `sport_type_not_found`, `gear_not_available`, `gear_not_found`, and `upload_not_confirmed`. The title and description are intentionally omitted from `_meta.filters_applied` so routine logs do not copy private activity text.

## Security and behavior

Publishing is local browser automation. FitOps does not store your Strava password, extract cookies, or change activity visibility. New activities use the visibility already configured in your Strava account. Because Strava can change its website, a selector mismatch is reported as a recoverable publication error and the local activity remains intact.

← [Commands Reference](./index.md)
