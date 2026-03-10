# Strava OAuth Flow

## Prerequisites

1. Create a Strava API application at [https://www.strava.com/settings/api](https://www.strava.com/settings/api)
2. Set **Authorization Callback Domain** to `localhost`
3. Note your **Client ID** and **Client Secret**

## Step-by-Step Flow

### Step 1: Run `fitops auth login`

If no credentials are configured, you will be prompted:
```
Strava client_id not configured.
Enter your Strava Client ID: 12345
Enter your Strava Client Secret: ****
```

Credentials are saved to `~/.fitops/config.json`.

### Step 2: Browser Opens

FitOps generates an authorization URL and opens it in your default browser:
```
https://www.strava.com/oauth/authorize?
  client_id=12345&
  redirect_uri=http://localhost:8080/callback&
  response_type=code&
  scope=read,activity:read_all,profile:read_all&
  state=<random_csrf_token>&
  approval_prompt=auto
```

### Step 3: You Authorize

Click **Authorize** on the Strava consent screen.

### Step 4: Local Callback Captured

FitOps starts a minimal `asyncio` HTTP server on `127.0.0.1:8080`. Strava redirects to:
```
http://localhost:8080/callback?code=AUTH_CODE&state=<csrf_token>
```

The server:
1. Parses `code` and `state` from the query string
2. Validates `state` matches the saved CSRF token
3. Returns a success HTML page ("You can close this tab")
4. Shuts down immediately

**Timeout:** If no callback is received within 120 seconds, the server closes and an error is displayed.

### Step 5: Token Exchange

FitOps posts to `https://www.strava.com/oauth/token` with the authorization code. The response contains:
- `access_token` — used for API calls (valid ~6 hours)
- `refresh_token` — used to get new access tokens (long-lived)
- `expires_at` — Unix epoch timestamp of expiry

### Step 6: Athlete Profile Fetched

FitOps calls `GET /api/v3/athlete` to retrieve your profile and equipment list (bikes and shoes). This is stored in the `athletes` table for gear name resolution.

### Step 7: Tokens Saved

All tokens and athlete ID are written to `~/.fitops/config.json`.

## Token Refresh

FitOps automatically refreshes your access token before it expires. The refresh happens transparently — you never need to run `fitops auth login` again unless you revoke access or delete `config.json`.

The refresh check uses a **5-minute buffer**: if `now() >= expires_at - 5 minutes`, a refresh is triggered.

## Revoking Access

```bash
fitops auth logout
```

This calls `POST /oauth/deauthorize` and clears all tokens from `config.json`.

## Port Conflicts

If port 8080 is in use, FitOps tries 8081 and 8082. The authorization URL is updated accordingly.
