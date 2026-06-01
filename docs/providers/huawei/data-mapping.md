# Huawei to FitOps Data Mapping

This document maps Huawei Health Kit models into the FitOps canonical activity model. It is intentionally conservative: fields are marked as confirmed, inferred, or pending validation from real Huawei payloads.

## Primary Huawei Models

| Huawei model | Role in FitOps |
|--------------|----------------|
| `ActivityRecord` | Primary source for one workout/activity row. |
| `ActivitySummary` | Summary metrics for distance, speed, pace, performance, sections, and activity feature data. |
| `SampleSet` | Container for sample points over a time range. |
| `SamplePoint` | Atomic or statistical time-series value. |
| `PaceSummary` | Average/best pace and per-distance pace maps. |
| `PerformanceSummary` | Training performance data if provided. |
| `DeviceInfo` | Candidate source for `device_name`. |
| `AppInfo` | Source application metadata and Huawei client ID. |

## ActivityRecord to Activity

| FitOps field | Huawei source | Conversion | Confidence |
|--------------|---------------|------------|------------|
| `provider` | constant | `"huawei"` | Confirmed design |
| `provider_activity_id` | `ActivityRecord.id` | String as-is | Confirmed |
| `strava_id` | none | Do not synthesize long-term; temporary compatibility only if required during migration | Design |
| `name` | `ActivityRecord.name` | String as-is | Confirmed |
| `description` | `ActivityRecord.desc` | String as-is | Confirmed |
| `sport_type` | `ActivityRecord.activityType` | Map Huawei exercise type to FitOps/Strava-compatible sport type | Pending integer mapping |
| `start_date` | `ActivityRecord.startTime` | milliseconds -> UTC `datetime` | Confirmed |
| `start_date_local` | `startTime` + `timeZone` | milliseconds plus `+0800`-style offset | Confirmed |
| `timezone` | `ActivityRecord.timeZone` | Store as raw offset if no IANA zone is available | Confirmed |
| `elapsed_time_s` | `endTime - startTime` | milliseconds / 1000 | Confirmed |
| `moving_time_s` | `ActivityRecord.activeTime` | milliseconds / 1000 | Confirmed |
| `distance_m` | `ActivitySummary.dataSummary` with `com.huawei.continuous.distance.total`, field `distance` | meters | Confirmed from example |
| `average_speed_ms` | `com.huawei.continuous.speed.statistics`, field `avg`, or pace conversion | Confirm unit with payload; likely meters/second | Inferred |
| `max_speed_ms` | `com.huawei.continuous.speed.statistics`, field `max` | Confirm unit with payload | Inferred |
| `calories` | calories sample/statistic data | Convert to integer kcal if Huawei returns kcal | Pending unit validation |
| `average_heartrate` | exercise heart rate statistics or sampled HR | Use `avg` if present, else compute from stream | Inferred |
| `max_heartrate` | exercise heart rate statistics or sampled HR | Use `max` if present, else compute from stream | Inferred |
| `average_cadence` | steps rate / pedaling rate statistics | Do not apply Strava running cadence doubling until payload confirms units | Pending |
| `average_watts` | instantaneous power samples or statistics | Compute average from stream if summary absent | Pending |
| `max_watts` | power samples or statistics | Compute max from stream if summary absent | Pending |
| `total_elevation_gain_m` | altitude stream/statistics | Derive positive gain from altitude stream if summary absent | Pending |
| `device_name` | `ActivityRecord.deviceInfo` | Combine manufacturer/model/name when present | Pending payload |
| `manual` | `sourceType == 2` | Boolean | Confirmed source type |
| `trainer` | activity type/source/device | Infer for treadmill/indoor cycling exercise types | Pending mapping |
| `private` | no per-activity equivalent found | Default false; provider privacy is account-level | Gap |
| `kudos_count`, `comment_count` | no equivalent | `0` | Gap |
| `map_summary_polyline` | location stream | Generate encoded polyline after stream fetch if needed | Design |
| `external_id` | `ActivityRecord.id` or app metadata | Use `huawei:<id>` if existing field remains source-agnostic | Design |

## Sport Type Mapping

Huawei `ActivityRecord.activityType` is documented as an integer whose constants are referenced from "Workout Type Constants". The reviewed REST page does not expose the full integer table inline. The Android `HiHealthActivities` class documents semantic activity names such as `RUNNING`, `RUNNING_MACHINE`, `CYCLING`, `CYCLING_INDOOR`, `HIKING`, `WALKING`, `SWIMMING_POOL`, and `SWIMMING_OPEN_WATER`.

Initial semantic mapping:

| Huawei semantic activity | FitOps sport type | Notes |
|--------------------------|-------------------|-------|
| `RUNNING` | `Run` | Outdoor run. |
| `RUNNING_MACHINE` | `VirtualRun` or `Run` + `trainer=True` | Prefer `VirtualRun` only if dashboard/analytics treat it correctly. |
| `WALKING` / `ON_FOOT` | `Walk` | Preserve lower intensity. |
| `HIKING` | `Hike` | Trail/elevation analytics can still apply. |
| `CYCLING` | `Ride` | Outdoor cycling. |
| `CYCLING_INDOOR` | `VirtualRide` or `Ride` + `trainer=True` | Match existing Strava semantics. |
| `SWIMMING_POOL` | `Swim` | Pool-specific detail can be provider metadata. |
| `SWIMMING_OPEN_WATER` | `Swim` | Open-water detail can be provider metadata. |
| `ROWING` | `Rowing` | Existing support must be checked. |
| `ROWING_MACHINE` | `Rowing` + `trainer=True` | May need a canonical indoor flag. |
| unknown/other | `Workout` or `Other` | Do not drop records. |

Implementation must add fixture tests once real integer `activityType` values are available from Huawei API access.

## Summary Data Extraction

Huawei examples show `ActivitySummary.dataSummary` as a list of `SamplePoint`-like objects:

```json
{
  "dataTypeName": "com.huawei.continuous.distance.total",
  "value": [
    {"fieldName": "distance", "floatValue": 1786.2}
  ]
}
```

```json
{
  "dataTypeName": "com.huawei.continuous.speed.statistics",
  "value": [
    {"fieldName": "avg", "floatValue": 13.54},
    {"fieldName": "max", "floatValue": 15.82},
    {"fieldName": "min", "floatValue": 12.33}
  ]
}
```

Create a helper:

```python
def sample_value(
    points: list[dict],
    data_type_name: str,
    field_name: str,
) -> int | float | str | None:
    ...
```

Rules:

1. Match `dataTypeName` exactly.
2. Match `value[].fieldName` exactly.
3. Accept one of `floatValue`, `integerValue`, `longValue`, `stringValue`, `mapValue`.
4. Return `None` on absence; never raise for optional metrics.
5. Log unknown fields at debug level with provider and activity ID.

## SamplePoint to Streams

Huawei `SamplePoint` uses nanosecond `startTime` and `endTime`; FitOps streams use arrays aligned by index. The mapper should build canonical arrays sorted by sample time.

| FitOps stream | Huawei candidate data type | Value fields | Conversion |
|---------------|----------------------------|--------------|------------|
| `time` | Any selected detail sample | `startTime` or midpoint | `(sample_time_ns - activity_start_ns) / 1e9` |
| `distance` | `com.huawei.continuous.distance.delta` or total distance samples | `distance` | Accumulate deltas if needed. |
| `latlng` | location sample data | latitude/longitude fields | Confirm exact field names from payload. |
| `altitude` | altitude sample data | altitude field | meters. |
| `heartrate` | heart rate / exercise heart rate samples | bpm field | beats per minute. |
| `watts` | power sample data | power field | watts. |
| `cadence` | steps rate or pedaling/stroke rate data | rate field | Preserve native unit; normalize per sport. |
| `velocity_smooth` | speed samples | speed field | meters/second after unit validation. |
| `moving` | speed/distance deltas | derived | `speed > 0` or distance delta > 0. |
| `grade_smooth` | altitude + distance | derived | Percent grade over adjacent points. |

Potential Huawei data types identified in docs/SDK references:

| Huawei data type/constant | Meaning |
|---------------------------|---------|
| `com.huawei.continuous.steps.delta` / `DT_CONTINUOUS_STEPS_DELTA` | Steps since last reading. |
| `DT_INSTANTANEOUS_STEPS_RATE` | Step cadence. |
| `DT_CONTINUOUS_STEPS_RATE_STATISTIC` | Step cadence statistics. |
| `DT_CONTINUOUS_CALORIES_BURNT` | Calories burned in a period. |
| `DT_CONTINUOUS_CALORIES_BURNT_TOTAL` | Total calories. |
| `DT_INSTANTANEOUS_POWER_SAMPLE` | Activity power. |
| `DT_INSTANTANEOUS_HEART_RATE` | Heart rate. |
| `DT_INSTANTANEOUS_EXERCISE_HEART_RATE` | Exercise heart rate details. |
| `DT_CONTINUOUS_EXERCISE_HEART_RATE_STATISTICS` | Exercise heart rate statistics. |
| `DT_INSTANTANEOUS_LOCATION_SAMPLE` | Location. |
| `DT_CONTINUOUS_DISTANCE_DELTA` | Distance since last reading. |
| `com.huawei.continuous.distance.total` / `DT_CONTINUOUS_DISTANCE_TOTAL` | Total distance. |
| `DT_INSTANTANEOUS_SPEED` | Instantaneous speed. |
| `com.huawei.continuous.speed.statistics` / `POLYMERIZE_CONTINUOUS_SPEED_STATISTICS` | Speed statistics. |
| `DT_INSTANTANEOUS_ALTITUDE` | Altitude. |
| `DT_CONTINUOUS_ALTITUDE_STATISTICS` | Altitude statistics. |
| `DT_VO2MAX` / `DT_VO2MAX_STATISTICS` | VO2max. |
| `DT_CONTINUOUS_RUN_POSTURE` | Running form data. |
| `DT_CONTINUOUS_RUN_POSTURE_STATISTICS` | Running form statistics. |

Exact REST `dataTypeName` strings for constants that were only visible as SDK names must be confirmed from API payloads or the full data type overview before implementation.

## Laps and Splits Mapping

Huawei sources, in preferred order:

| Source | FitOps lap fields | Notes |
|--------|-------------------|-------|
| `ActivitySummary.sectionSummary` | lap index, distance, elapsed/moving time, average HR/power if present | Best native equivalent. |
| `PaceSummary.paceMap` | kilometer split pace | Convert pace seconds/km to split duration. |
| `PaceSummary.partTimeMap` | distance-to-time map | Use as split elapsed time where present. |
| Derived from streams | distance/time split every 1 km or every provider section | Last resort. |

Derived laps should be deterministic and explicitly marked in raw/provider metadata so users do not mistake them for watch-recorded laps.

## Duplicates and Cross-Provider Records

Some users will sync the same activity from Strava and Huawei. Do not merge automatically in the first Huawei release.

Initial duplicate strategy:

1. Store all records with `(provider, provider_activity_id)`.
2. Add a duplicate-detection helper that computes candidates by start time, sport type, duration, and distance.
3. Expose duplicate candidates in diagnostics only.
4. Keep analytics provider-scoped by default until merge policy is explicit.

Candidate duplicate key:

```text
sport_type + start_date_utc within 120 seconds + distance within 2% + moving_time within 2%
```

Do not delete or overwrite provider records based on this heuristic.

## Required Mapper Tests

Add fixture-driven tests before wiring sync:

| Test | Fixture |
|------|---------|
| `test_huawei_activity_record_maps_core_fields` | Minimal `ActivityRecord` with distance and speed summary. |
| `test_huawei_activity_record_handles_missing_summary` | Record with no `activitySummary`. |
| `test_huawei_time_conversions_ms_and_ns` | Start/end milliseconds plus sample nanoseconds. |
| `test_huawei_manual_source_type_maps_to_manual_flag` | `sourceType=2`. |
| `test_huawei_stream_points_sort_by_time` | Out-of-order sample points. |
| `test_huawei_laps_derive_from_pace_map` | `PaceSummary.paceMap`. |
| `test_huawei_unknown_activity_type_preserved` | Unsupported `activityType`. |

