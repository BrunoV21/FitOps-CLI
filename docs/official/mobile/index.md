<script setup>
import { withBase } from 'vitepress'
</script>

# FitOps for Android

FitOps Mobile is an independent Android fitness analytics app. It stores your imported activities on your phone and works without the desktop CLI, a desktop connection, or a FitOps cloud account.

The initial version focuses on heart-rate calibration and zones, per-activity stress approximations, and running VO₂max estimates. Huawei Health sync is awaiting permission approval and is **not available** in this version. Native HarmonyOS, live workout recording, session planning, readiness, and training-form features are not included.

## First use

1. Open **Zones** from the section menu in the header.
2. Choose the sport and zone method, enter the required personal HR values, describe their source, and save the calibration.
3. Open **Activities**, select **Import TCX / FitOps file**, and choose an activity file from your phone.
4. Review the activities and their sports, then select **Save to this phone**. TCX records labelled Other can be assigned the appropriate sport, such as Walking, during review.
5. Open an activity to see its available metrics, sample coverage, and calculation method. **Overview** shows recent stress estimates and qualifying running VO₂max history.

No default age-based thresholds are silently applied. If calibration or samples are missing, the corresponding estimate remains unavailable with an explanation.

To try the import flow without personal data, <a :href="withBase('/mobile/fitops-reviewer-sample.tcx')" download>download the synthetic reviewer TCX</a>. It contains a clearly named synthetic 6 km/30-minute run with heart-rate samples. It is a file example, not your personal calibration or a Huawei recording. Entering the synthetic running LTHR 170, maximum HR 190, resting HR 50, and threshold pace 300 seconds/km (expand **Optional thresholds** in the calibration form for the additional fields) produces the reference 50.0 stress approximation and 38.3 ml/kg/min running estimate; do not use those example thresholds as your own.

## Activity files and local library

The app accepts TCX files and version-1 FitOps JSON activity exports, up to 10 MB per import and 100 activities per file. FIT and GPX imports are not supported by this initial Android version.

TCX files may contain heart-rate, distance, and speed samples, but availability depends on the recording/export source. Running and Biking records map to running/cycling; other TCX records initially map to Other, and file-import review lets you correct the sport before saving. A summary-only file cannot supply measured time in HR zones. TCX does not supply your personal calibration settings; configure those separately.

Repeated imports update matching source identities instead of adding duplicate copies. The library shows sport, date, distance, elapsed time, and available estimates. The sport filter helps you browse activities; opening an activity reveals its detail and deletion control.

After import and calculation, saved records and metrics are available offline. The app does not automatically upload imported files to Strava or Huawei.

## Calibrate heart-rate zones

Calibration is separate for running, cycling, and walking. Record the source and date so you can tell whether values came from a field test or your own confirmed settings.

| Method | Required values |
|---|---|
| LTHR | Lactate-threshold heart rate |
| HR reserve | Maximum and resting heart rate |
| Max HR | Maximum heart rate |

The saved-zone card shows boundaries in beats per minute. A lower boundary belongs to that zone; the upper boundary belongs to the next zone. For HR reserve and maximum-HR methods, samples below Zone 1 remain unclassified.

Activity zone time uses timestamped measured HR intervals. Missing data and intervals longer than 30 seconds do not fill the gaps with assumed heart rates. The final sample is not extended beyond its timestamp.

Saving calibration recalculates all existing activities for that sport. Removing calibration removes estimates that depend on it. This is retrospective, so changing thresholds can change historical results.

## Understand stress estimates

The activity detail identifies which approximation was used:

- **Pace-based stress:** for running with a configured threshold pace, elapsed hours multiplied by squared average-speed/threshold-speed intensity, multiplied by 100.
- **HR-based stress:** measured average HR divided by LTHR supplies the intensity in the same formula. At least 80% timestamped HR coverage is required.

These are fitness stress approximations. They are not normalized-power TSS or a proprietary hrTSS calculation. Duration is elapsed time; pauses, terrain, recording quality, and calibration affect the result. Without the required calibration/data, the app shows an unavailable state.

## Understand running VO₂max estimates

The app shows a Daniels running-performance estimate in ml/kg/min, its activity date, and a simple history of qualifying runs. It needs usable HR and speed samples, a running LTHR or maximum-HR reference, and qualifying continuous near-threshold effort. The minimum qualifying segment length is 10 minutes, with at least 1.5 km across qualifying segments.

This is a pace-based performance proxy, not a laboratory VO₂max measurement. The initial version does not provide a validated probability or confidence score. Hills, heat, effort, and sensor errors can affect the estimate. Easy runs and incomplete recordings may be unsuitable; the app explains why no estimate is available.

## Export selected activities

In **Activities**, select the records to export, then choose **Export selected records**. The confirmation explains that the JSON file contains sensitive fitness data and is not encrypted. Android sharing lets you choose the destination.

Exports contain canonical activity summaries and available HR/distance/speed samples. They do not contain Huawei credentials, calibration profiles, or the app's cached metric estimates. The recipient can calculate its own analytics from the imported records.

You can transfer the file to your own FitOps Desktop installation for further analysis. Desktop import uses the [activities command](../commands/activities.md) or dashboard activity import. Mobile remains fully usable without that transfer.

Exports are snapshots: deleting an activity on the phone does not remove exported copies. A chosen destination app may upload data according to its own settings.

The app retains a temporary copy after sharing so the destination can read it. Copies older than 24 hours are cleaned up on a best-effort basis when the app next starts or exports another file. Erasing the local library clears this local export cache; it does not remove copies already received by other apps.

## Appearance and deletion

**Settings** offers System, Light, and Dark appearance. The header's section picker opens navigation when needed; no bottom tab bar takes up the screen.

Delete individual activities in their details. Remove a sport's calibration in **Zones**, or erase all activities and calibration with **Erase local activities and calibration** in Settings. Original import files and previously shared copies are unaffected. Uninstalling removes the app's local data.

Read the [Android privacy notice](../legal/mobile-privacy.md) before importing or exporting sensitive records.

## QA examples and screenshots

The separate internal **FitOps QA** app includes three labelled synthetic runs and example calibration for testing and screenshots. Its **QA · DEMO DATA** badge distinguishes these examples from personal or Huawei data. They are not your thresholds and should not be used as personal calibration.

QA data lives in a separate library from the production app. Erasing that library leaves it empty across restarts. The **QA library** menu offers an explicit **Reload demo library** action; confirming it replaces the entire QA library and calibration, including any real files imported into the QA app.

The production release does not preload these records. Keep the demo badge visible when capturing representative QA screens and identify the captures as synthetic examples. Such screenshots show the UI; they are not proof of live Huawei access or an AppGallery release.
