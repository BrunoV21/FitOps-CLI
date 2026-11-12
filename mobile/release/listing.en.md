# English AppGallery listing copy

Draft for the initial file-based Android release. Confirm the final app identity, completed device checks, public policy URL, and production signing before submission. No Huawei sync or public-release status is implied.

## App name

FitOps

## Short description

Local fitness analytics, calibrated HR zones, and running estimates.

## Full description

Understand your fitness activity data on your own phone.

FitOps is an independent, local-first Android fitness analytics app. Import activity files, configure your personal heart-rate calibration, and review useful estimates without a FitOps cloud account or desktop connection.

With FitOps you can:

- Import TCX activity files or supported FitOps JSON exports and keep the library on your phone.
- Set sport-specific heart-rate calibration for running, cycling, and walking using lactate-threshold, heart-rate-reserve, or maximum-HR methods.
- See labelled zone boundaries and measured time in zones when heart-rate samples are available.
- Review per-activity stress approximations based on your configured running threshold pace or lactate-threshold heart rate.
- View qualifying running VO₂max estimates and a simple history, with explanations when data is insufficient.
- Browse activity details and use light, dark, or system appearance.
- Explicitly export selected records through Android sharing, delete individual activities, or erase your local library.

Saved activities and metrics are available offline after import. FitOps does not automatically upload your activity library and does not require a FitOps account. Exported JSON contains sensitive fitness data and is not encrypted; choose a destination you trust.

Stress scores are fitness approximations, not normalized-power TSS or a proprietary hrTSS calculation. Running VO₂max is a pace-based performance proxy, not a laboratory measurement. Calibration, recording quality, terrain, and effort affect the results. Some files do not contain the samples required for every estimate.

Huawei Health sync is not included in this release. FIT/GPX import, live workout recording, training-session planning, readiness, and training-form features are not included. The app works independently using supported activity files.

## Reviewer note

No app account is required. Use the supplied synthetic TCX and [reviewer instructions](reviewer-instructions.md) to populate a fresh production installation. The native QA screenshots show explicitly labelled synthetic examples, not live Huawei data.
