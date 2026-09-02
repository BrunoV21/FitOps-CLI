# Huawei Provider Implementation Plan

This plan assumes Huawei API access is not available yet. The first engineering milestone is therefore provider abstraction plus fixture-driven mappers, not live HTTP sync.

## Phase 0: Access, Fixtures, and Scope Validation

Before runtime implementation:

1. Confirm Huawei developer account type and Health Kit approval path.
2. Confirm OAuth endpoints and redirect URI requirements from Huawei Account/OAuth docs.
3. Request least-privilege scopes for:
   - activity records,
   - activity sample data,
   - privacy/scope status,
   - daily activity summaries,
   - optional running ability and trends later.
4. Capture sanitized payload fixtures for:
   - outdoor run with GPS, HR, cadence, pace,
   - treadmill run,
   - outdoor ride with GPS and power if available,
   - activity with missing summary,
   - manually entered activity,
   - deleted activity record,
   - sampleSet polymerize response,
   - subscription notification.
5. Save fixtures under `tests/fixtures/huawei/`.

Do not make network calls in tests.

## Phase 1: Provider-Neutral Storage and Settings

Changes:

| Area | Work |
|------|------|
| DB models | Add provider-neutral IDs to `Activity`, `Athlete`, and lap/source metadata. |
| Migrations | Backfill existing Strava rows with `provider='strava'` and `provider_activity_id=CAST(strava_id AS TEXT)`. |
| Settings | Add selected provider and provider-specific credential blocks. |
| Sync state | Track last sync and cursors per provider. |
| Output | Include provider fields in CLI JSON where activity identity is shown. |

Compatibility requirements:

1. Existing Strava users keep syncing without editing config.
2. Existing analytics still work against old rows after migration.
3. `strava_id` remains available until all callers use provider-neutral IDs.
4. No schema operations run on dashboard or CLI read paths.

Tests:

| Test file | Coverage |
|-----------|----------|
| `tests/test_models.py` | Provider ID defaults and unique constraints. |
| `tests/test_migrations.py` or existing migration tests | Backfill behavior. |
| `tests/test_output.py` | Provider fields in JSON. |

## Phase 2: Provider Interface and Strava Adapter

Refactor Strava behind the provider contract without changing behavior.

Work:

1. Add `fitops/providers/base.py`.
2. Add canonical DTOs for athlete, activity, stream bundle, laps, sync result, capabilities.
3. Add provider registry.
4. Move Strava mapping from `Activity.from_strava_data` into `providers/strava/mapper.py`.
5. Keep `from_strava_data` as a compatibility wrapper during transition.
6. Update sync engine to accept a provider adapter.
7. Keep existing CLI commands working with `--provider strava` and default active provider.

Tests:

| Test | Purpose |
|------|---------|
| Strava mapper parity tests | Canonical Strava mapping equals previous model mapping. |
| Sync tests | Existing Strava sync behavior unchanged. |
| CLI auth/sync tests | Provider option parses and defaults to Strava. |

This phase is the regression shield for Huawei.

## Phase 3: Huawei Mapper with Fixtures

Implement pure mapping first.

Files:

```text
fitops/providers/huawei/
  __init__.py
  mapper.py
  types.py
```

Mapper responsibilities:

1. Convert `ActivityRecord` to `ProviderActivity`.
2. Convert `ActivitySummary.dataSummary` values into core metrics.
3. Convert `SampleSet`/`SamplePoint` to canonical stream arrays.
4. Convert `PaceSummary`/`sectionSummary` to laps or derived splits.
5. Preserve raw provider payloads for unsupported fields.
6. Emit mapping warnings for unknown data types without failing sync.

Required tests are listed in [`data-mapping.md`](./data-mapping.md).

## Phase 4: Huawei Client

Files:

```text
fitops/providers/huawei/
  auth.py
  client.py
```

Client behavior:

| Method | Endpoint |
|--------|----------|
| `get_privacy_status()` | `GET /profile/privacyRecords` |
| `get_granted_scopes(app_id, lang)` | `GET /consents/{appId}?lang=...` |
| `list_activity_records(start_ms, end_ms, cursor, filters)` | `GET /activityRecords?...` |
| `polymerize_sample_set(start_ms, end_ms, data_types)` | `POST /sampleSet:polymerize` |
| `daily_polymerize(start_day, end_day, data_types, time_zone)` | `POST /sampleSet:dailyPolymerize` |
| `latest_sample_points(data_types)` | `GET /sampleSets/latestSamplePoint?dataType=...` |
| `get_cloud_sync_receipt()` | `GET /cloudSyncMessages/receipts?dataType=all` |

HTTP rules:

1. Use `httpx.AsyncClient`.
2. Set a finite timeout.
3. Add `Authorization`, `Content-type`, `x-client-id`, `x-version`, and `x-caller-trace-id`.
4. Parse Huawei result codes and HTTP status codes into FitOps provider errors.
5. Log trace IDs.
6. Never call Huawei from dashboard route handlers except explicit auth/sync operations.

## Phase 5: Huawei Sync Adapter

Sync strategy:

1. Determine sync window from provider sync state.
2. Split reads into windows no larger than 31 days.
3. Apply a small overlap window to catch delayed uploads and modifications.
4. Query `activityRecords` for each window.
5. Upsert by `(provider, provider_activity_id)`.
6. Fetch detail sample data only for new/changed activities or explicit stream sync.
7. Persist analytics snapshots after sync, same as Strava.
8. Store deleted records as tombstones or mark local activities deleted after policy is decided.

Do not combine Strava and Huawei analytics by default until duplicate handling exists.

Suggested sync state:

```json
{
  "providers": {
    "huawei": {
      "last_sync_at": "...",
      "last_cursor": "...",
      "last_cloud_sync_time_ms": 1676376320206,
      "history": []
    },
    "strava": {
      "last_sync_at": "...",
      "history": []
    }
  }
}
```

## Phase 6: CLI and Dashboard Parity

CLI:

| Command | Behavior |
|---------|----------|
| `fitops providers list --json` | Shows configured providers, active provider, auth state, capability flags. |
| `fitops providers select huawei` | Sets active provider. |
| `fitops auth login --provider huawei` | Starts Huawei OAuth. |
| `fitops auth status --provider huawei --json` | Shows token, scopes, privacy status if cached. |
| `fitops sync run --provider huawei` | Runs Huawei sync. |
| `fitops activities list --provider huawei --json` | Filters Huawei activities. |

Dashboard:

| Area | Behavior |
|------|----------|
| Setup | Provider selector with Strava/Huawei options. |
| Profile | Provider account status, scopes, Huawei privacy status. |
| Sync | Run sync for active provider. |
| Activities | Provider filter. |
| Analytics | Provider-scoped default until duplicate merging is explicit. |

Docs:

1. Update official auth docs when Huawei login is shipped.
2. Update official sync docs.
3. Update dashboard docs for provider setup and filters.
4. Add output examples for provider fields.

## Phase 7: Subscriptions

Huawei subscriptions are optional for the first release but important for long-term incremental sync.

Work:

1. Add subscription setup command/dashboard action.
2. Store `subscriberId`, `subscriptionId`, event types, and secret metadata.
3. Implement callback signature verification:

```text
HMAC-SHA256(base64_decode(secret), openId + "_" + eventType + "_" + eventTime)
```

4. Handle `ACTIVITY_RECORD_EVENT$UPDATE`.
5. Handle sample-set update events if needed.
6. Queue or trigger provider sync for the event's time range.

Tests:

1. Valid signature accepted.
2. Invalid signature rejected.
3. Activity update event triggers sync request.
4. Event handler is idempotent.

## Open Questions

| Question | Why it matters |
|----------|----------------|
| Which Huawei OAuth endpoint and account scopes are required for server-side local CLI use? | Blocks auth implementation. |
| Are Health Kit REST APIs available for individual developers or only enterprise/approved apps for the needed scopes? | Blocks release scope. |
| What exact `activityType` integer values appear in `ActivityRecord` for run/ride/walk/swim? | Blocks reliable sport mapping. |
| Which sample data types are returned inside `ActivityRecord.details` for common workouts? | Determines whether stream sync is direct or requires separate sample queries. |
| What are the exact REST `dataTypeName` strings for power, cadence, altitude, location, run posture, and exercise HR? | Blocks robust stream mapping. |
| Are speed values returned as meters/second in all relevant Huawei responses? | Prevents unit bugs. |
| How are manually entered Huawei records represented when `sourceType` is omitted? | The docs say default excludes manual records. |
| Can a local-first CLI app receive Huawei subscription callbacks without a public URL? | May require polling or optional tunnel/cloud callback. |
| Does Huawei allow editing or annotating user-created/native activities? | Affects FitOps stamp/notes parity. |

## Acceptance Criteria for First Huawei Release

1. User can choose Strava or Huawei as active provider from CLI and dashboard.
2. Huawei credentials and tokens are stored separately from Strava.
3. Huawei activity records sync into the local DB without corrupting existing Strava rows.
4. CLI `--json` output includes provider identity and remains deterministic.
5. Dashboard activities page can filter Huawei activities.
6. Shared analytics run against Huawei activities with no Strava-specific assumptions.
7. Tests cover mapper, client error handling, sync upsert, CLI JSON, and dashboard route behavior.
8. Official docs are updated for shipped user-facing behavior.
9. No Huawei network calls run on dashboard read paths or CLI read paths.

