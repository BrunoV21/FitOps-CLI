# FitOps Android Privacy Notice

Last updated: November 12, 2026

This notice describes the initial file-based FitOps Android app. It is separate from the [desktop privacy policy](privacy.md). Huawei Health synchronization is not available in this Android release. The notice must be reviewed and updated before a release adds provider access or other data processing.

## Information processed on your phone

When you choose to import an activity file, FitOps processes the activity's name, sport, date/time, duration, distance, source identifiers, and available heart-rate, distance, and speed samples. It also processes the calibration settings you enter, including maximum/resting/threshold HR, an optional running threshold pace, calibration source, and date.

The app uses these records to show activity history, heart-rate zones, measured time in zones, stress approximations, and qualifying running VO₂max estimates. These are fitness estimates, not medical diagnosis or laboratory measurements.

Activity records, samples, calibration, and calculated results are stored in the app's local SQLite database. Appearance preference is stored separately on the device. The app does not require a FitOps account or a desktop connection.

## Network services and Huawei access

The initial app does not include a Huawei authorization flow and does not request or store Huawei credentials. It does not automatically upload your imported activity records, and has no FitOps cloud account, advertising, or analytics tracking service. Android app backup is disabled in the app configuration.

Files may originate from a cloud-backed document provider you choose in Android's file picker. Access by that provider is governed by its own settings and policy. The initial app's independent operation does not mean that every source or destination application is offline.

## Exports you choose

You can select activities and explicitly export them through Android sharing. The export contains activity summaries, source identifiers, timestamps, and available HR/distance/speed samples. It does not contain Huawei credentials, calibration profiles, or cached metric results.

The exported JSON is **not encrypted**. Choose a destination you trust. If you share it with another app, storage service, person, or your own FitOps Desktop installation, that destination receives a copy and may process or upload it according to its own settings. FitOps does not automatically pair or synchronize your phone with a desktop.

To let the destination read the shared file, the app retains a copy in its local temporary export cache after the share chooser returns. Cached exports older than 24 hours are removed on a best-effort basis at the next app startup or export. This cleanup happens when the app runs, not on a guaranteed deletion timer. Erasing the local library also clears the app's export cache.

Desktop CLI output can be accessed by scripts or AI agents you choose to run. If you send imported records or analysis to an external service yourself, that is a separate disclosure under your control; the mobile app does not automatically send them to that service.

## Retention and deletion

Imported records remain locally until you delete them, erase the library, or uninstall the app. You can delete an activity in its detail screen, remove calibration for a sport in Zones, or erase all activities and calibration in Settings.

Deleting local records does not delete original import files, previously exported copies, or data held by your chosen source/destination services. Delete those copies separately at their locations.

## Security and support

Keep your device and any exported files secure. Device access controls and destination sharing settings affect who can read the data. Do not include sensitive records, exports, screenshots, or logs in a public issue unless you intend to disclose them.

For FitOps privacy/support questions, use the [project issue tracker](https://github.com/BrunoV21/FitOps-CLI/issues). It is public: describe the issue without attaching personal fitness data.
