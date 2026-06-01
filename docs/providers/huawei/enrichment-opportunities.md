# Huawei Enrichment Opportunities

Huawei Health exposes several data categories that can make FitOps more useful than a Strava-only sync. These should be added only after the baseline provider sync is stable and the required Huawei scopes are approved.

## Running Ability

Huawei endpoints:

| Endpoint | Data |
|----------|------|
| `GET /healthkit/v2/athleticPerformance/latest?timeZone=...` | Latest running ability index, condition, fitness, fatigue, predicted times. |
| `GET /healthkit/v2/athleticPerformance?types=...&startDay=...&endDay=...&timeZone=...` | Historical running ability, condition, fitness, and fatigue for up to 31 days. |

Huawei docs state this data is not available to all developers and requires applying under "Exercise records > Sport ability" with:

```text
https://www.huawei.com/healthkit/sportsability.read
```

FitOps use:

| Huawei field | FitOps feature |
|--------------|----------------|
| `runningAbility` | Dashboard trend card; CLI `analytics performance` field; compare against FitOps VO2max estimate. |
| `condition` | Training readiness signal. |
| `fitness` | Compare with CTL-like chronic load. |
| `fatigue` | Compare with ATL-like acute load. |
| `predictedTimes.km1/km3/km5/km10/halfMarathon/marathon` | Race predictor calibration and race-plan target suggestions. |

Implementation note: store these in `analytics_snapshots` or a provider-specific performance table at sync time. Do not call Huawei performance endpoints from dashboard routes.

## Personal Scores and Cumulative Sport Reports

Huawei endpoint:

```text
GET /healthkit/v2/sportReports?activityType=running&activityType=cumulative&timeZone=...
```

Docs state this is not available to all developers and requires:

```text
https://www.huawei.com/healthkit/sportachievement.read
```

FitOps use:

| Huawei report | FitOps feature |
|---------------|----------------|
| Walking/running/cycling/jump rope bests | Personal records page, activity badges, race result comparison. |
| `accumulatedDistance` | Lifetime distance total independent of Strava. |
| `accumulatedStep` | Daily activity context for training load. |
| `accumulatedCalorie` | Longitudinal energy expenditure context. |
| `accumulatedDay` | Consistency/streak analytics. |

This should not replace FitOps-computed PRs; it should be shown as provider-reported achievements with source attribution.

## Health Trends

Huawei endpoint:

```text
GET /healthkit/v2/healthTrends?dataType=...&lang=zh-CN&timeZone=...
```

Supported trend items listed by Huawei docs:

| Data type | Trend item |
|-----------|------------|
| `com.huawei.continuous.steps.delta` | Step count |
| `com.huawei.continuous.calories.burnt` | Calories |
| `com.huawei.instantaneous.resting_heart_rate` | Resting heart rate |
| `com.huawei.instantaneous.spo2` | SpO2 |
| `com.huawei.instantaneous.stress` | Stress |
| `com.huawei.continuous.sleep.fragment` | Sleep duration |
| `com.huawei.continuous.exercise_intensity.v2` | Moderate/high-intensity activity duration |
| `com.huawei.active_hours` | Active hours |

FitOps use:

| Trend | Potential feature |
|-------|-------------------|
| Resting heart rate | Readiness and fatigue context. |
| Sleep duration | Recovery dashboard and training recommendation context. |
| SpO2 | Altitude/illness/recovery context, displayed carefully as wellness data. |
| Stress | Recovery context, not a medical interpretation. |
| Active hours/intensity | Non-workout activity load context. |
| Steps/calories | Daily activity summary and low-intensity volume context. |

Docs say this data is not available to all developers. Treat it as phase 3+.

## Latest Health Samples

Huawei endpoint:

```text
GET /healthkit/v2/sampleSets/latestSamplePoint?dataType=...
```

Docs list support for latest points including heart rate, blood pressure, SpO2, blood glucose, weight, height, stress, maximum oxygen uptake, body temperature, and ECG measurement details.

FitOps use:

| Latest sample | FitOps feature |
|---------------|----------------|
| Weight | Power, VO2max, and race simulation inputs. |
| Height | Athlete profile context. |
| VO2max | Compare Huawei estimate to FitOps estimate. |
| Resting/instant HR | Recovery context. |
| Stress | Readiness context. |
| SpO2 | Wellness context with careful wording. |

Medical-adjacent data such as blood pressure, blood glucose, ECG, body temperature, and SpO2 should be treated as user-owned wellness context only. FitOps should not provide diagnosis or medical advice.

## Daily Activity Statistics and Goals

Huawei endpoints:

| Endpoint | Data |
|----------|------|
| `POST /sampleSet:dailyPolymerize` | Daily totals by data type. |
| `POST /sampleSet:dailyActivitySummary` | Daily activity statistics. |
| Activity goals query | Goal config such as step count, active calories, workout duration, active hours. |

FitOps use:

| Data | Feature |
|------|---------|
| Steps | Daily movement load and recovery-day context. |
| Active calories | Energy context for weekly summaries. |
| Workout duration | Cross-check activity sync completeness. |
| Active hours | Habit/consistency dashboard. |
| Goals | Dashboard progress cards. |

These are useful even before full activity-stream support is complete.

## Routes, Running Courses, and Events

Huawei supports writing selected planning objects into Huawei Health:

| API | Endpoint | Use |
|-----|----------|-----|
| Route import | `PUT /routeInfos?format=GPX` | Export FitOps race/course routes to Huawei Health. |
| Running course import | `POST /trainingplan/workouts` | Export structured run workouts to Huawei Health. |
| Batch running course import/update | `POST`/update running course APIs | Bulk plan sync. |
| Event import | `POST /trainingplan/events` | Send marathon events into Huawei Health. |

Restrictions from docs:

| API | Restriction |
|-----|-------------|
| Route import | GPX only; track/route point limits listed by Huawei, including up to 80,000 track points. |
| Running courses | Maximum of 500 customized courses imported. Requires `healthplan.write`. |
| Events | Currently marathon events only; maximum of 100 events per user. Requires `healthplan.write`. |

FitOps use:

1. Export race courses created in FitOps to Huawei Health as GPX.
2. Export planned workouts from `fitops/workouts/` to Huawei running courses.
3. Export race plans/events so the watch ecosystem can show them.

These are write-path features. They need explicit user actions and clear source labeling.

## Privacy and Scope Diagnostics

Huawei-specific diagnostics can improve setup quality:

| Endpoint | FitOps use |
|----------|------------|
| `GET /profile/privacyRecords` | Explain whether the Huawei Health app has granted data openness to Health Kit. |
| `GET /consents/{appId}?lang=...` | Show granted scopes and missing scopes in CLI/dashboard. |
| `DELETE /consents/{appId}?deleteData=false` | Provider logout/deauthorization. |
| `GET /cloudSyncMessages/receipts?dataType=all` | Check whether Huawei cloud sync is recent before blaming FitOps sync. |

The sync receipt endpoint has a documented wait of 5 minutes before calling again. Cache it and never call it from dashboard route handlers.

## Priority Recommendation

Initial Huawei release should include:

1. Activity records.
2. Core summaries: distance, time, speed/pace, calories, heart rate if present.
3. Streams from sample details if accessible.
4. Privacy and scope diagnostics.
5. Provider-scoped CLI/dashboard filters.

Second release:

1. Daily activity statistics.
2. Latest weight/VO2max/resting HR samples.
3. Duplicate detection between Strava and Huawei.
4. Subscription-based incremental sync.

Later releases:

1. Running ability and predicted times.
2. Health trends.
3. Sport reports.
4. Route/workout/event export to Huawei Health.

