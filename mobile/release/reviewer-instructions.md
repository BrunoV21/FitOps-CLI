# FitOps Android reviewer walkthrough

This walkthrough exercises the initial file-based production app. No FitOps account, desktop installation, Huawei account, or Huawei authorization is required. The production app starts with an empty local library; it does not preload QA activities.

Use a fresh reviewer installation or test-only local data. The sample and calibration below are synthetic and must not be treated as anyone's personal training thresholds.

## 1. Obtain the sample

Copy [fitops-reviewer-sample.tcx](../../docs/official/public/mobile/fitops-reviewer-sample.tcx) to the review phone's Downloads folder. It is the unchanged shared synthetic TCX fixture, containing one running activity named **Synthetic example - not a recorded workout**: 6 km, 30 minutes, 181 samples at 10-second spacing, and heart rate 170 beats per minute throughout.

After the documentation is deployed, the intended public download is `https://brunov21.github.io/FitOps-CLI/mobile/fitops-reviewer-sample.tcx`. Verify that URL from the review phone before supplying it in AppGallery Connect; the presence of this source file does not prove public deployment.

The production APK must be signed with the verified owner-managed release key before it can be installed for review. The current local unsigned artifact is not that final installable package. Do not substitute the **FitOps QA** internal APK.

## 2. Enter the synthetic calibration

Open **FitOps**, then use the section picker in the header to open **HR zones**. Select **Running**, open **Set calibration** if needed, and choose **LTHR**. Expand **Optional thresholds** to enter maximum/resting HR and threshold pace, then enter:

| Field | Synthetic reviewer value |
|---|---|
| Zone method | LTHR |
| Maximum HR | 190 beats per minute |
| Resting HR | 50 beats per minute |
| Threshold HR / LTHR | 170 beats per minute |
| Threshold pace | 300 seconds per kilometre, equivalent to 5:00/km |
| Calibration source | `Synthetic reviewer example — not personal thresholds` |
| Calibration date | `2026-11-01` |

Select **Save and recalculate**. The date is deliberately fixed for this synthetic reference; use these entries only for the review fixture.

Expected saved boundaries are:

| Zone | Displayed beats per minute |
|---|---|
| Z1 — Recovery | 0–143 |
| Z2 — Aerobic | 144–149 |
| Z3 — Tempo | 150–169 |
| Z4 — Threshold | 170–179 |
| Z5 — High intensity | 180+ |

## 3. Import the sample

Open **Activities**, choose **Import TCX / FitOps file**, and select the downloaded `.tcx` file with Android's file picker. Review the record, confirm sport **Run**, and select **Save to this phone**.

Open the imported activity. With the exact sample and calibration above, expected results are:

| Result | Expected value |
|---|---|
| Distance | 6.00 km |
| Elapsed time | 30:00 |
| Average measured HR | 170 beats per minute |
| HR coverage | 100% |
| Stress approximation | 50.0 TSS, pace-based method |
| Running VO₂max proxy | 38.3 ml/kg/min, Daniels running estimate |
| Time in Z4 | 30:00, 100% |
| Other zones / unclassified time | Zero |

These expected values were checked using the current mobile TCX parser and calculation functions. They validate a deterministic example, not physiological accuracy or live Huawei data. The stress calculation is `0.5 elapsed hours × 1² × 100`; the VO₂max proxy uses the qualifying 6 km/1800-second running segment.

Repeat the same import and confirm it updates the matching local record rather than adding a duplicate. Reopen the app and check that the record persists. After the file is on the phone, these library and calculation operations do not require network access.

## 4. Check calibration, export, and deletion

- Change the synthetic running threshold pace to 240 seconds/km and save; the same activity's pace-based stress becomes 32.0 TSS. Restore 300 seconds/km to return to the reference result.
- In **Activities**, select the sample for export. Choose **Export selected records**, read the sensitive-data warning, and share the JSON to a trusted test destination. It is an unencrypted snapshot containing activity records/samples, not credentials or calibration profiles.
- Use **Settings** to check Light, Dark, and System appearance and the privacy/data controls.
- Delete the sample in its activity detail, or erase the test library in Settings. Original import files and copies already shared to other apps remain separate.

## What is intentionally unavailable

Huawei Health synchronization and its authorization flow are not included in this initial app. No Huawei credentials are requested. Readiness/form, planned training sessions, live recording, native HarmonyOS, and FIT/GPX imports are outside this release.

The [native screenshot set](../docs/screenshots/qa/README.md) shows the same implemented UI in a separate labelled QA app with other synthetic runs. These screenshots illustrate features but do not establish AppGallery release or Huawei approval.
