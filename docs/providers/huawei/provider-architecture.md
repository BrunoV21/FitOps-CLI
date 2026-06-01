# Provider Architecture

## Current FitOps Shape

The current sync path is Strava-specific:

```text
fitops sync run
  -> fitops.strava.sync_engine.SyncEngine
  -> fitops.strava.client.StravaClient
  -> Activity.from_strava_data(...)
  -> activities.strava_id
```

The database and code use Strava terms in places that are not actually Strava-only concepts:

| Current item | Problem for Huawei |
|--------------|--------------------|
| `activities.strava_id` is unique and non-null | Huawei activity IDs are strings in `ActivityRecord.id`, not Strava integer IDs. |
| `Activity.from_strava_data` owns canonical mapping | Huawei mapping would either duplicate logic or force Huawei into fake Strava payloads. |
| `ActivityStream.from_strava_stream` names the source | Streams should be canonical FitOps streams, regardless of source provider. |
| `ActivityLap.strava_lap_id` | Huawei lap-like data may come from `sectionSummary`, `paceMap`, `partTimeMap`, or derived splits. |
| `FitOpsSettings` stores only `strava` credentials | Multiple providers need isolated credentials, scopes, and selected-provider state. |
| `SyncState` is global | Incremental cursors and last-sync timestamps must be per provider and per account. |

The correct approach is to introduce provider-neutral contracts, then adapt Strava into them before adding Huawei.

## Target Model

```text
fitops/
  providers/
    base.py              Provider protocols and canonical DTOs
    registry.py          Provider selection and discovery
    strava/
      client.py          Strava HTTP client
      mapper.py          Strava -> canonical FitOps records
      sync.py            Strava adapter over provider sync protocol
    huawei/
      client.py          Huawei Health HTTP client
      mapper.py          Huawei -> canonical FitOps records
      sync.py            Huawei adapter over provider sync protocol
```

Strava-specific modules can remain during the transition, but the shared sync engine should call `ProviderClient`/`ProviderSyncAdapter` rather than importing `StravaClient` directly.

## Canonical Provider Contracts

The provider layer should normalize external payloads into canonical DTOs before DB write logic runs.

```python
class ProviderName(str, Enum):
    STRAVA = "strava"
    HUAWEI = "huawei"


@dataclass(frozen=True)
class ProviderActivity:
    provider: ProviderName
    provider_activity_id: str
    provider_athlete_id: str | None
    name: str
    sport_type: str
    start_date_utc: datetime | None
    start_date_local: datetime | None
    timezone: str | None
    distance_m: float | None
    moving_time_s: int | None
    elapsed_time_s: int | None
    elevation_gain_m: float | None
    average_speed_ms: float | None
    max_speed_ms: float | None
    average_heartrate_bpm: float | None
    max_heartrate_bpm: int | None
    average_cadence_spm_or_rpm: float | None
    average_power_w: float | None
    max_power_w: int | None
    calories_kcal: int | None
    description: str | None
    source_device: str | None
    raw: dict[str, Any]
```

```python
@dataclass(frozen=True)
class ProviderStreamBundle:
    provider: ProviderName
    provider_activity_id: str
    streams: dict[str, list[Any]]
    raw: dict[str, Any]
```

Canonical stream keys should remain the FitOps/Strava-compatible keys that analytics already understand:

| Canonical stream | Unit/shape |
|------------------|------------|
| `time` | seconds from activity start |
| `distance` | meters from start |
| `latlng` | `[lat, lng]` pairs |
| `altitude` | meters |
| `heartrate` | beats per minute |
| `watts` | watts |
| `cadence` | steps/min for running, rpm for cycling |
| `temp` | Celsius when available |
| `moving` | boolean |
| `velocity_smooth` | meters/second |
| `grade_smooth` | percent, derived if needed |

## Database Migration Direction

Add provider-neutral identity without deleting Strava columns immediately.

| Table | Add | Backfill |
|-------|-----|----------|
| `activities` | `provider TEXT NOT NULL DEFAULT 'strava'` | Existing rows become `strava`. |
| `activities` | `provider_activity_id TEXT` | Existing rows use `CAST(strava_id AS TEXT)`. |
| `activities` | `provider_athlete_id TEXT` | Existing rows use `CAST(athlete_id AS TEXT)` until athlete table is migrated. |
| `activities` | `provider_raw_json TEXT NULL` | Optional raw payload cache for mapping diagnostics. |
| `activity_laps` | `provider_lap_id TEXT NULL` | Existing rows use `CAST(strava_lap_id AS TEXT)`. |
| `athletes` | `provider TEXT NOT NULL DEFAULT 'strava'` | Existing rows become `strava`. |
| `athletes` | `provider_athlete_id TEXT` | Existing rows use `CAST(strava_id AS TEXT)`. |

Add a unique index on `(provider, provider_activity_id)`. Keep `strava_id` until all CLI/dashboard paths stop using it as the primary external identity.

Do not run any DDL on route handlers, CLI read paths, or dashboard query functions. Add migrations in `fitops/db/migrations.py` and let startup/sync bootstrap handle them.

## Configuration Model

Current config:

```json
{
  "strava": {
    "client_id": "...",
    "client_secret": "...",
    "access_token": "...",
    "refresh_token": "..."
  }
}
```

Target config:

```json
{
  "provider": {
    "active": "strava"
  },
  "providers": {
    "strava": {
      "client_id": "...",
      "client_secret": "...",
      "redirect_uri": "http://localhost:8080/callback",
      "access_token": "...",
      "refresh_token": "...",
      "expires_at": "...",
      "scopes": ["read", "activity:read_all", "profile:read_all"]
    },
    "huawei": {
      "client_id": "...",
      "client_secret": "...",
      "redirect_uri": "http://localhost:8080/callback",
      "access_token": "...",
      "refresh_token": "...",
      "expires_at": "...",
      "scopes": [],
      "app_id": "...",
      "x_version": "mac_fitops_0.0.0"
    }
  }
}
```

Compatibility rule: existing Strava config must continue to work. On first read, `FitOpsSettings` can expose both old and new accessors, and the migration can be lazy in memory until a write occurs.

## CLI and Dashboard Surface

Provider selection is a first-class feature and therefore needs CLI and dashboard parity.

CLI:

```text
fitops providers list --json
fitops providers select strava
fitops providers select huawei
fitops auth login --provider strava
fitops auth login --provider huawei
fitops sync run --provider active
fitops sync run --provider huawei
```

Dashboard:

| Page | Required behavior |
|------|-------------------|
| Setup/auth | Show Strava and Huawei as selectable providers. |
| Profile | Show connected provider, scopes, privacy/authorization status where available. |
| Sync controls | Allow syncing active provider and show provider-specific errors. |
| Activities | Filter by provider once more than one provider exists. |
| Analytics | Default to combined canonical dataset only when duplicate handling is implemented; otherwise default to active provider. |

## Provider Capabilities

Providers should declare capability flags so CLI/dashboard code does not guess.

```python
@dataclass(frozen=True)
class ProviderCapabilities:
    activity_list: bool
    activity_detail: bool
    streams: bool
    laps: bool
    athlete_profile: bool
    zones: bool
    webhooks: bool
    write_activity_notes: bool
    route_import: bool
    workout_import: bool
    health_trends: bool
    running_ability: bool
```

Expected initial capabilities:

| Capability | Strava | Huawei |
|------------|--------|--------|
| Activity list | Yes | Yes, via `ActivityRecord` query. |
| Activity detail | Yes | Partial, through `ActivityRecord.details` and sample sets. |
| Streams | Yes | Yes, if sample data scopes and detail data are available. |
| Laps | Yes | Partial/derived from `sectionSummary`, pace maps, or kilometer splits. |
| Athlete profile | Yes | Partial; Huawei Health REST has age/gender, not full Strava-like athlete profile. |
| Zones | Yes | Unknown/no direct REST equivalent found in reviewed docs. |
| Webhooks/subscriptions | Yes | Yes, via Health Kit subscriptions. |
| Write activity notes | Yes | No direct equivalent for third-party edits to Huawei-native records found. |
| Route import | Read routes in Strava; activity upload support exists | Yes, GPX route import. |
| Workout/course import | Not used by FitOps now | Yes, running course import with `healthplan.write`. |
| Health trends | No | Yes, approval-dependent. |
| Running ability | No | Yes, approval-dependent. |

## Design Decisions

1. Canonical DTOs are the boundary between provider code and FitOps analytics.
2. Raw provider payloads should be kept during early Huawei development to debug mapping failures.
3. Provider IDs are strings. Never coerce Huawei IDs into integers.
4. Provider sync state is per provider/account.
5. Dashboard and CLI read paths must read cached DB rows; no Huawei network calls on read paths except explicit sync/auth operations.
6. Strava behavior should be refactored behind the provider interface before Huawei writes are added. That gives a regression target.

