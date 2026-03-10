# Strava API Endpoints Used by FitOps-CLI

Base URL: `https://www.strava.com`

## Authentication Endpoints

### `GET /oauth/authorize`
Redirects the user to Strava's consent screen.

**Query Parameters:**
| Parameter | Value |
|-----------|-------|
| `client_id` | Your application's Client ID |
| `redirect_uri` | `http://localhost:8080/callback` |
| `response_type` | `code` |
| `scope` | Comma-separated list (see below) |
| `state` | CSRF protection token |
| `approval_prompt` | `auto` (skip re-prompt if already authorized) |

**Required Scopes:**
| Scope | Purpose |
|-------|---------|
| `read` | Basic athlete info and public data |
| `activity:read_all` | All activities including private |
| `profile:read_all` | Full athlete profile, equipment, zones |

---

### `POST /oauth/token`
Exchanges an authorization code for tokens, or refreshes an existing token.

**Token Exchange (first login):**
```json
{
  "client_id": "12345",
  "client_secret": "abc...",
  "code": "AUTH_CODE",
  "grant_type": "authorization_code",
  "redirect_uri": "http://localhost:8080/callback"
}
```

**Token Refresh:**
```json
{
  "client_id": "12345",
  "client_secret": "abc...",
  "refresh_token": "REFRESH_TOKEN",
  "grant_type": "refresh_token"
}
```

**Response includes:** `access_token`, `refresh_token`, `expires_at` (Unix epoch), `athlete` object (on first exchange).

FitOps auto-refreshes tokens with a **5-minute buffer** before expiry.

---

### `POST /oauth/deauthorize`
Revokes the athlete's access.

```json
{ "access_token": "ACCESS_TOKEN" }
```

---

## Athlete Endpoints

### `GET /api/v3/athlete`
Returns the authenticated athlete's full profile.

**Required scope:** `profile:read_all`

**Key response fields:** `id`, `firstname`, `lastname`, `city`, `country`, `sex`, `weight`, `profile`, `premium`, `bikes[]`, `shoes[]`

**Stored in:** `athletes` table in `fitops.db`

---

### `GET /api/v3/athletes/{id}/stats`
Returns cumulative running/cycling/swimming totals for the athlete.

**Required scope:** `read`

**Key response fields:** `recent_run_totals`, `ytd_run_totals`, `all_run_totals`, `recent_ride_totals`, `ytd_ride_totals`, `all_ride_totals`

---

### `GET /api/v3/athlete/zones`
Returns the athlete's heart rate and power zones as configured in Strava.

**Required scope:** `profile:read_all`

**Key response fields:** `heart_rate.zones[]` (min/max BPM per zone), `power.zones[]`

---

## Activity Endpoints

### `GET /api/v3/athlete/activities`
Returns a paginated list of the authenticated athlete's activities.

**Required scope:** `activity:read_all`

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `before` | integer | Epoch timestamp — return activities before this time |
| `after` | integer | Epoch timestamp — return activities after this time |
| `page` | integer | Page number (default: 1) |
| `per_page` | integer | Results per page (default: 30, max: 200) |

**FitOps defaults:** `per_page=30`, up to 100 pages per sync run.

**Incremental sync:** Uses `after = last_sync_at - 3 days` to catch delayed uploads.

**Key response fields per activity:** `id`, `name`, `sport_type`, `start_date`, `start_date_local`, `timezone`, `distance`, `moving_time`, `elapsed_time`, `total_elevation_gain`, `average_speed`, `max_speed`, `average_heartrate`, `max_heartrate`, `average_cadence`, `average_watts`, `weighted_average_watts`, `suffer_score`, `calories`, `gear_id`, `kudos_count`, `comment_count`, `map.summary_polyline`

---

### `GET /api/v3/activities/{id}`
Returns full details for a single activity (includes all fields not returned in the list endpoint).

**Required scope:** `activity:read_all`

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `include_all_efforts` | boolean | Include all segment efforts (default: false) |

**Tracked in DB:** `activities.detail_fetched = true` after fetch.

---

### `GET /api/v3/activities/{id}/streams`
Returns time-series data for an activity.

**Required scope:** `activity:read_all`

**Query Parameters:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| `keys` | Comma-separated stream names | Which streams to fetch |
| `key_by_type` | `true` | Return as object keyed by stream type |

**Stream types fetched by FitOps:**
| Key | Description | Unit |
|-----|-------------|------|
| `time` | Elapsed time from start | seconds |
| `latlng` | GPS coordinates | `[[lat, lng], ...]` |
| `altitude` | Elevation | meters |
| `heartrate` | Heart rate | BPM |
| `watts` | Power output | watts |
| `cadence` | Pedal/step cadence | RPM (doubled for running) |
| `velocity_smooth` | Smoothed speed | m/s |
| `grade_smooth` | Smoothed gradient | percent |
| `temp` | Temperature | Celsius |
| `moving` | Moving/stopped flag | boolean |

**Tracked in DB:** `activities.streams_fetched = true` after fetch.

---

### `GET /api/v3/activities/{id}/laps`
Returns lap split data for an activity.

**Required scope:** `activity:read_all`

**Key response fields per lap:** `id`, `lap_index`, `name`, `elapsed_time`, `moving_time`, `distance`, `average_speed`, `average_heartrate`, `max_heartrate`, `average_watts`

**Tracked in DB:** `activities.laps_fetched = true` after fetch.

---

## Rate Limits

Strava enforces:
- **100 requests per 15 minutes**
- **1,000 requests per day**

FitOps returns a clear error on HTTP 429 and stops the current operation. Re-run after the rate limit window resets.
