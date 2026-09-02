# Huawei Health Provider Planning

This directory lays out the planned Huawei Health integration as an alternative provider to Strava.

The goal is not to make Huawei look like Strava internally. The goal is to normalize Huawei data into FitOps' canonical activity, stream, lap, athlete, and analytics shapes while preserving provider-specific metadata for future enrichment.

## Source Status

Huawei source documents reviewed:

| Source | URL | Huawei metadata observed |
|--------|-----|--------------------------|
| Health Kit REST index | `https://developer.huawei.com/consumer/en/doc/HMSCore-References/api_server-0000001050116803` | Updated `2026-05-13 07:14:03` |
| Health Kit data model | `https://developer.huawei.com/consumer/en/doc/HMSCore-References/data-model-0000001054556973` | Updated `2026-05-13 07:14:04` |
| Activity records API | `activityrecords_list-0000001050114862` | Updated `2026-05-13` through Huawei document portal |
| Sampling datasets APIs | `sampleSet:polymerize`, `dailyPolymerize`, latest sample point, dataset range APIs | Updated `2026-05-13` through Huawei document portal |
| Subscription APIs | `subscriptions` and event notification callback docs | Updated `2026-05-13` through Huawei document portal |
| Running ability, health trends, personal scores, personal info | Huawei Health Kit REST docs | Updated `2026-05-13` through Huawei document portal |

Strava source documents reviewed:

| Source | URL |
|--------|-----|
| Authentication | `https://developers.strava.com/docs/authentication/` |
| API reference | `https://developers.strava.com/docs/reference/` |
| Webhooks | `https://developers.strava.com/docs/webhooks/` |

## Documents

| File | Purpose |
|------|---------|
| [`source-index.md`](./source-index.md) | Exact source documents and endpoint pages used for this planning pass. |
| [`provider-architecture.md`](./provider-architecture.md) | Provider abstraction and migration path away from Strava-shaped internals. |
| [`endpoint-comparison.md`](./endpoint-comparison.md) | Equivalent Strava and Huawei endpoints, with gaps and implementation notes. |
| [`data-mapping.md`](./data-mapping.md) | Huawei `ActivityRecord`, `SampleSet`, and `SamplePoint` mapping into FitOps-compatible activity data. |
| [`enrichment-opportunities.md`](./enrichment-opportunities.md) | Huawei-only data that can enrich FitOps beyond current Strava sync. |
| [`implementation-plan.md`](./implementation-plan.md) | Phased engineering plan, tests, docs, risks, and open questions. |

## Key Conclusions

1. Huawei should be integrated through a provider interface and canonical mapper, not by renaming the current Strava client.
2. FitOps must stop treating `strava_id` as the universal activity identity before Huawei sync can be safe.
3. Huawei activity sync should start from `ActivityRecord` records and supplement missing detail through `SampleSet`/`SamplePoint` queries.
4. Huawei timestamps use both milliseconds and nanoseconds, depending on model; conversions must be centralized and tested.
5. Huawei exposes valuable enrichment data that Strava does not: running ability, condition, fitness/fatigue, predicted race times, health trends, SpO2, stress, sleep, daily activity goals, and Huawei Health privacy status.
6. Several Huawei endpoints are explicitly not available to all developers. API access and approved scopes are blockers before implementation can be considered complete.
