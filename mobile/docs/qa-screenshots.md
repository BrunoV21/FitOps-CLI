# QA build and screenshot workflow

The internal Android build is a separate **FitOps QA** app for testing and representative screenshots. It is not the production package, a released AppGallery app, or proof of Huawei access.

## Build and launch

From `mobile/`:

```sh
npm run validate
npm run build:internal
adb install -r android/app/build/outputs/apk/internal/app-internal.apk
```

Open **FitOps QA** on the connected phone. The build script sets `FITOPS_QA_BUILD=1`, bundles JavaScript, uses the `.internal` application ID suffix and debug signing, and targets `arm64-v8a` by default. Use `FITOPS_ANDROID_ARCHITECTURES` for a different internal-test ABI.

On its first launch, the QA app seeds a separate `fitops-mobile-qa.db` with three deterministic synthetic runs and synthetic running calibration. It does not copy or modify the production app's database. Production builds force QA mode off and do not preload these records.

The QA app keeps the screen awake while it is active to aid capture. This behavior is disabled in production builds.

## What is preloaded

| Synthetic activity | Purpose | Reference stress estimate | Reference VO₂max estimate |
|---|---|---|---|
| Demo · Easy run | Easy-effort unavailable-VO₂max state | 18.75 TSS | Unavailable |
| Demo · Steady run | Steady activity and HR-zone coverage | 46.08 TSS | Unavailable |
| Demo · Threshold run | Qualifying running estimate and multiple HR zones | 82.14 TSS | 43.6 ml/kg/min |

The calibration is explicitly labelled **Synthetic QA calibration — not personal thresholds**: LTHR 170, maximum HR 190, resting HR 50 beats per minute, and threshold pace 300 seconds per kilometre. Do not treat these example values as the user's calibration. The scores above are deterministic fixture expectations, not measured Huawei results or a claim of physiological accuracy.

The global **QA · DEMO DATA** badge identifies a library containing demo records. If the demo records are removed, the app still identifies itself as **QA BUILD**. Keep these labels visible in representative captures.

## Reset and deletion behavior

The seed is applied once, not on every launch. Erasing the QA library leaves it erased across restarts so deletion can be tested.

To restore examples, open **QA library** in the header menu and choose **Reload demo library**. The confirmation replaces the QA app's entire current library and calibration, including real files imported into the QA app. It does not affect the separate production application. Export any QA records you want to retain before reloading.

## Capture useful screens

1. Open Overview with the demo badge and latest running estimate visible.
2. Open Activities and the threshold-run detail to show the actual method, HR coverage, and time in zones.
3. Open Zones to show the saved method, boundaries, and synthetic calibration source.
4. Capture the same screens in Light and Dark appearance; verify large text and keyboard behavior separately.
5. Capture Settings privacy/data controls where useful for review.

Screenshots should come from the current installed native build, not the HTML mockup. Record device model, Android version, app version, and artifact/commit used. Synthetic screenshots illustrate the app's implemented UI; label them as representative/demo data in application materials. They do not establish a live Huawei self-test, permission approval, or AppGallery release. Actual production listing/released-status evidence is still required by the [AppGallery checklist](appgallery-release.md).

## AppGallery APK asset specifications

Huawei's current **APK mobile-app** specifications require 3–8 screenshots in PNG/JPG/JPEG up to 2 MB each, with minimum side 320 px and maximum side 3840 px. The table gives 450 × 800 / 800 × 450 examples and does not impose a screenshot aspect ratio. The icon is square, 216 × 216 or 512 × 512 PNG, up to 2 MB. Use these APK requirements rather than the separate HarmonyOS section. [Official visual-asset specifications](https://developer.huawei.com/consumer/en/doc/app/agc-help-app-material-requirement-0000001146534651/)

The three [captured native QA screens](screenshots/qa/README.md) are 1080 × 2376 PNGs below 200 KB each, within those file/dimension limits. Their demo labels and review context remain necessary; meeting asset dimensions alone does not make them production release evidence. Additional light-mode/activity-detail captures remain useful before final listing review. See the [verification record](verification.md) for the actual APK and capture scope.
