# Endpoint Comparison: Strava vs Huawei Health

Huawei Health Kit is not a direct Strava clone. Strava exposes activity resources directly. Huawei exposes exercise records, sampling datasets, health records, subscriptions, and optional performance reports.

## Base URLs and Auth Headers

| Provider | Base/API URL | Auth |
|----------|--------------|------|
| Strava | `https://www.strava.com/api/v3` | `Authorization: Bearer <access_token>` |
| Huawei Health | `https://health-api.cloud.huawei.com/healthkit/v2` | `Authorization: Bearer <access_token>` plus common headers such as `Content-type`, `x-client-id`, `x-version`, and `x-caller-trace-id` |

Huawei REST docs define the URL format as:

```text
https://health-api.cloud.huawei.com/healthkit/v2/{resourcesSet}/{resourceId}?{param=xxx}
```

## Auth and Authorization

| FitOps need | Strava | Huawei Health | Notes |
|-------------|--------|---------------|-------|
| Start OAuth | `GET /oauth/authorize` | Huawei OAuth 2.0 authorization code flow, exact auth setup still needs Huawei console access | Huawei REST docs require bearer tokens and refer to OAuth 2.0 authentication. |
| Token exchange | `POST /oauth/token` | Huawei OAuth token endpoint, not fully specified in reviewed Health Kit REST pages | Need Account Kit/OAuth docs during implementation. |
| Refresh token | `POST /oauth/token` with `grant_type=refresh_token` | Huawei OAuth refresh flow, pending access validation | Keep provider-specific token refresh code. |
| Revoke/deauthorize | `POST /oauth/deauthorize`, with newer `POST /oauth/revoke` recommended by Strava as of 2026-06-01 | `DELETE /healthkit/v2/consents/{appId}?deleteData=false` cancels app scopes; privacy status endpoint checks Huawei Health authorization | Strava docs say `POST /oauth/revoke` becomes the only deauth endpoint on 2027-06-01. |
| Query granted scopes | No equivalent endpoint currently used by FitOps | `GET /healthkit/v2/consents/{appId}?lang=...` | Useful for setup diagnostics. |
| Query privacy status | No direct Strava equivalent | `GET /healthkit/v2/profile/privacyRecords` | Huawei returns `opinion`: `1` granted, `2` not granted, `3` not a Huawei Health app user. |

## Athlete/Profile

| FitOps need | Strava | Huawei Health | Mapping quality |
|-------------|--------|---------------|-----------------|
| Authenticated athlete | `GET /athlete` | No direct Strava-equivalent Health Kit profile endpoint found | Partial |
| Athlete stats | `GET /athletes/{id}/stats` | `POST /sampleSet:dailyPolymerize`, `GET /sportReports`, health trends | Partial/richer in some areas |
| Age/gender | Included in Strava athlete where available | `GET /user/basicInfos` returns `gender` and `age` | Huawei endpoint requires `healthbehavior.read`. |
| Zones | `GET /athlete/zones` | No direct REST equivalent found in reviewed docs | Gap |

## Activity List and Detail

| FitOps need | Strava | Huawei Health | Mapping quality |
|-------------|--------|---------------|-----------------|
| List activities | `GET /athlete/activities?after=&before=&page=&per_page=` | `GET /activityRecords?startTime=&endTime=&activityType=&detailDataType=&sourceType=` | Good, but Huawei has a 31-day max query window. |
| Activity detail | `GET /activities/{id}?include_all_efforts=false` | Query `ActivityRecord` by a time window and optional filters; no single `GET /activityRecords/{id}` found | Partial |
| Deleted activities | Strava webhooks can notify delete events | `activityRecords` response includes `deletedActivityRecord`; subscriptions can notify updates | Good if subscriptions are enabled. |
| Source type | Strava flags like `manual`, `trainer`, `commute` | Huawei `sourceType`: `0` unknown, `1` generated from workout, `2` manual, `3` course records, `4` connectable devices, `5` automatically identified | Good |
| Privacy | Strava activity visibility/private flags | Huawei privacy authorization header/status, not per-activity privacy in reviewed docs | Partial |

Huawei `activityRecords` query parameters confirmed from docs:

| Parameter | Notes |
|-----------|-------|
| `startTime` | Required with `endTime`; 13-digit milliseconds. |
| `endTime` | Required with `startTime`; interval cannot exceed 31 days. |
| `activityType` | Optional list of integer exercise types. |
| `detailDataType` | Optional list of associated atomic sampling detailed data types. |
| `sourceType` | Optional list; default excludes manually entered records. |
| `cursor` | Used for pagination/incremental queries. |
| `order` | Example shows `endTimeDesc`. |

## Streams and Sample Data

| FitOps need | Strava | Huawei Health | Mapping quality |
|-------------|--------|---------------|-----------------|
| Time-series streams | `GET /activities/{id}/streams?keys=time,distance,...&key_by_type=true` | `ActivityRecord.details` plus `SampleSet`/`SamplePoint` APIs | Good if scopes expose detail sample points. |
| Query sample data by duration | Not needed; stream endpoint is activity-scoped | `GET /dataCollectors/{dataCollectorId}/sampleSets/{startNs-endNs}?limit=&cursor=` | Useful if data collector IDs are known. |
| Query sample details by type | Not needed | `POST /sampleSet:polymerize` with `dataTypeName` and start/end milliseconds | Important fallback for streams. |
| Query grouped statistics | Not needed | `POST /sampleSet:polymerize` with `groupByTime` | Useful for daily summaries and charts. |
| Query daily stats | Strava totals/stats | `POST /sampleSet:dailyPolymerize` with `startDay`, `endDay`, `dataTypes`, `timeZone` | Good for dashboard enrichment. |
| Latest sample point | No broad equivalent | `GET /sampleSets/latestSamplePoint?dataType=...` | Useful for weight, SpO2, stress, VO2max, etc. |

Huawei time units differ by API:

| Huawei model/API | Time unit |
|------------------|-----------|
| `ActivityRecord.startTime`, `endTime`, `modifyTime`, `activeTime` | milliseconds |
| `SampleSet` ID in range query | nanoseconds formatted as `startTime-endTime` |
| `SamplePoint.startTime`, `endTime` | nanoseconds |
| `sampleSet:polymerize` request | milliseconds |
| `dailyPolymerize` request | `yyyyMMdd` day strings plus time zone |

Centralize conversion helpers and test them with boundary cases.

## Laps and Splits

| FitOps need | Strava | Huawei Health | Mapping quality |
|-------------|--------|---------------|-----------------|
| Laps | `GET /activities/{id}/laps` | `ActivitySummary.sectionSummary`, `PaceSummary.paceMap`, `PaceSummary.partTimeMap`, or derived splits from distance/time streams | Partial |

Huawei does not appear to expose a Strava-style lap endpoint in the reviewed REST pages. FitOps should build laps from the best available source:

1. Use `sectionSummary` if present.
2. Use `paceMap`/`partTimeMap` for kilometer splits if present.
3. Derive splits from canonical `distance` and `time` streams.
4. Mark derived laps with `provider_lap_id = NULL` and `source = "derived"` once lap source metadata exists.

## Subscriptions and Webhooks

| FitOps need | Strava | Huawei Health | Notes |
|-------------|--------|---------------|-------|
| Register subscription | Strava webhook subscription API | `POST /healthkit/v2/subscriptions` | Huawei event types include `ACTIVITY_RECORD_EVENT$UPDATE` and sample-set update events. |
| List subscriptions | Strava subscription list endpoint | `GET /healthkit/v2/subscriptions` | Huawei returns `subscriptionId`, `eventType`, `subscriberId`, `openId`, etc. |
| Receive event | Strava sends event payload to callback URL | Huawei sends POST to configured callback URL, with `x-notification-signature` HMAC-SHA256 | Signature verification is required. |
| Delete subscription | Strava delete subscription endpoint | `DELETE /healthkit/v2/subscriptions/{subscriptionId}` or condition delete | Use provider-specific webhook module. |

Huawei notification signature:

```text
HMAC-SHA256(secret, openId + "_" + eventType + "_" + eventTime)
```

The docs say the subscriber secret is Base64-decoded before use.

## Routes, Workouts, and Events

| FitOps need/opportunity | Strava | Huawei Health | Notes |
|-------------------------|--------|---------------|-------|
| Import route into provider | Strava route APIs are primarily read/export in current FitOps context | `PUT /routeInfos?format=GPX` | Huawei supports GPX route import into Huawei Health. |
| Import structured running course | Not currently used | `POST /trainingplan/workouts`, batch import, update | Requires `https://www.huawei.com/healthkit/healthplan.write`. |
| Import event | Not currently used | `POST /trainingplan/events` | Currently marathon events only; max 100 events per user. |

These are not required for initial read-only Huawei sync, but they could later enrich FitOps race planning and workout export.

## Performance and Health Enrichment

| Huawei endpoint | FitOps value | Availability |
|-----------------|-------------|--------------|
| `GET /athleticPerformance/latest?timeZone=...` | Running ability index, condition, fitness, fatigue, predicted race times | Docs say not available to all developers. |
| `GET /athleticPerformance?...` | Historical running ability, condition, fitness, fatigue for up to 31 days | Docs say not available to all developers. |
| `GET /healthTrends?dataType=&lang=&timeZone=` | Trends for steps, calories, resting HR, SpO2, stress, sleep, intensity, active hours | Docs say not available to all developers. |
| `GET /sportReports?activityType=...` | Personal best and cumulative score reports | Docs say not available to all developers. |
| `GET /user/basicInfos` | Gender and age | Requires personal information scope. |

## Initial Endpoint Priority

1. OAuth and token refresh for Huawei.
2. `GET /profile/privacyRecords`.
3. `GET /consents/{appId}` for scope diagnostics.
4. `GET /activityRecords` for activity list sync.
5. `POST /sampleSet:polymerize` for activity detail stream fallback.
6. `POST /sampleSet:dailyPolymerize` for daily stats.
7. `POST /subscriptions` and notification receiver after polling works.
8. Optional enrichment endpoints after approval and real payload fixtures.

