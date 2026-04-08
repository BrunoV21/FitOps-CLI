# Authentication

FitOps uses Strava's OAuth 2.0. Your credentials are stored locally — never sent to any third party.

## Step 1: Create a Strava API Application

To ensure the best experience and bypass rate limits, beta users must use their own Strava API credentials. Follow the [Strava Getting Started Guide](https://developers.strava.com/docs/getting-started/) to create an app.

Go to [https://www.strava.com/settings/api](https://www.strava.com/settings/api) and create an application with **these exact settings**:

| Field | Value |
|-------|-------|
| Application Name | `Surge` |
| Category | `Performance Analysis` |
| Website | `https://brunov21.github.io/Surge/` |
| Authorization Callback Domain | `mclovinittt-kinetic-run-api.hf.space` |

Once created, copy your **Client ID** and **Client Secret** from the [Strava API Settings page](https://www.strava.com/settings/api).

## Step 2: Enter Your Credentials

Paste the **Client ID** and **Client Secret** from your Strava API Settings page when prompted. These are stored securely in `~/.fitops/config.json` and used only to sync your activities — never sent to any third party.

```bash
fitops auth login
```

On **first run** you'll be prompted for your Client ID and Client Secret — these are saved to `~/.fitops/config.json` and never asked again. Then:

1. A browser window opens to Strava's authorization page
2. Click **Authorize**
3. FitOps captures the callback on `localhost:8080`
4. A styled confirmation page appears in the browser — you can close it
5. Tokens and athlete profile are saved locally

```
Authenticated as: Jane Smith (ID: 987654)
Tokens saved. Run `fitops sync run` to fetch your activities.
```

On **subsequent logins** (e.g. after a logout), credentials are already saved so the browser opens immediately — no prompts.

## Re-authenticating

To switch accounts or revoke access and start fresh:

```bash
fitops auth logout   # Revokes token on Strava and clears local tokens
fitops auth login    # Opens browser again for a clean authorization
```

## Token Management

Tokens auto-refresh with a 5-minute buffer — you never need to log in again unless you explicitly log out or revoke access on Strava's side.

```bash
fitops auth status    # Check token validity and expiry
fitops auth refresh   # Force refresh without re-authorizing
fitops auth logout    # Revoke access and clear stored tokens
```

## Scopes Requested

| Scope | Why |
|-------|-----|
| `read` | Basic athlete info |
| `activity:read_all` | All activities including private |
| `profile:read_all` | Full profile, equipment, zones |

← [← Installation](./installation.md) | [Next: First Sync →](./first-sync.md)
