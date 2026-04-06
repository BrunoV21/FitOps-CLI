# fitops auth

Manage Strava authentication.

## Commands

### `fitops auth login`

Authenticate with Strava via OAuth.

```bash
fitops auth login
```

On **first run**, you'll be prompted for your Strava Client ID and Client Secret (saved to `~/.fitops/config.json`). A browser window then opens for Strava authorization. After you click **Authorize**, FitOps captures the callback on `localhost:8080`, shows a confirmation page in the browser, and saves tokens locally.

On **subsequent runs** (e.g. after a logout), credentials are already saved — the browser opens immediately with no prompts.

```
Authenticated as: Jane Smith (ID: 987654)
Tokens saved. Run `fitops sync run` to fetch your activities.
```

Tokens auto-refresh — you only need to log in once unless you explicitly log out.

---

### `fitops auth status`

Show current authentication status.

```bash
fitops auth status
```

```
Status: Valid
Athlete ID: 987654
Expires at: 1741788000
Scopes: read, activity:read_all, profile:read_all
```

---

### `fitops auth refresh`

Force a token refresh without re-authenticating.

```bash
fitops auth refresh
```

```
Token refreshed. Expires at: 1741788000
```

---

### `fitops auth logout`

Revoke Strava access and clear all stored tokens.

```bash
fitops auth logout
```

```
Logged out. Tokens cleared.
```

## Re-authenticating

To switch accounts or start a clean authorization:

```bash
fitops auth logout
fitops auth login
```

`logout` revokes the token on Strava's side and clears local tokens. `login` then opens the browser immediately (credentials are already saved).

## Token Storage

Tokens are stored in `~/.fitops/config.json`. They are never sent to any third party — all requests go directly to `api.strava.com`.

## See Also

- [Authentication Guide](../getting-started/authentication.md) — step-by-step setup
- [First Sync](../getting-started/first-sync.md) — after login

← [Commands Reference](./README.md)
